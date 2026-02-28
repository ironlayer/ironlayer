//! Check engine orchestrator — the main entry point for running checks.
//!
//! Coordinates file discovery, caching, header parsing, ref extraction,
//! per-file checks, cross-file checks, and result assembly. Per-file checks
//! run in parallel via rayon; cross-file checks run sequentially after.
//!
//! Every per-file check dispatch is wrapped in `catch_unwind` so that a
//! panic in one checker emits an `INTERNAL` diagnostic instead of crashing
//! the Python process.

use std::collections::HashMap;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::Path;
use std::time::Instant;

use rayon::prelude::*;
use regex::Regex;

use crate::cache::CheckCache;
use crate::checkers::{build_checker_registry, Checker};
use crate::config::CheckConfig;
use crate::discovery::{detect_project_type, walk_files};
use crate::types::{
    CheckCategory, CheckDiagnostic, CheckResult, DiscoveredFile, DiscoveredModel, ProjectType,
    Severity,
};

/// The main check engine orchestrator.
///
/// Discovers files, checks them against all registered checkers, manages
/// caching, and assembles the final result.
pub struct CheckEngine {
    /// The check configuration.
    config: CheckConfig,
    /// All registered checkers.
    checkers: Vec<Box<dyn Checker>>,
}

impl CheckEngine {
    /// Create a new check engine with the given configuration.
    #[must_use]
    pub fn new(config: CheckConfig) -> Self {
        let checkers = build_checker_registry();
        Self { config, checkers }
    }

    /// Run all checks on the project at the given root path.
    ///
    /// This is the main entry point called from Python via PyO3.
    ///
    /// # Panics
    ///
    /// This function catches panics from individual checkers via `catch_unwind`.
    /// A panic in one checker emits an `INTERNAL` diagnostic and does not
    /// prevent other checkers from running.
    pub fn check(&self, root: &Path) -> CheckResult {
        let start = Instant::now();

        // 1. Detect project type
        let project_type = detect_project_type(root);

        // 2. Walk files (respecting .gitignore, .ironlayerignore, exclusions)
        let files = walk_files(root, &self.config);

        // 3. Initialize cache and partition files
        let mut cache = CheckCache::new(root, &self.config);
        let (cached_files, uncached_files) = cache.partition(&files);

        // 4. Parse SQL headers + extract refs from uncached .sql files
        let models: Vec<DiscoveredModel> = uncached_files
            .iter()
            .filter(|f| f.rel_path.ends_with(".sql"))
            .map(|f| discover_model(f))
            .collect();

        // 5. Run per-file checks in parallel via rayon
        let max_diags = self.config.max_diagnostics;

        let per_file_results: Vec<(String, String, Vec<CheckDiagnostic>)> = uncached_files
            .par_iter()
            .map(|file| {
                let model = models.iter().find(|m| m.file_path == file.rel_path);
                let file_diags = self.run_per_file_checks(file, model, &project_type);
                (file.rel_path.clone(), file.content_hash.clone(), file_diags)
            })
            .collect();

        // Collect results and update cache sequentially (cache is not thread-safe)
        let mut all_diags: Vec<CheckDiagnostic> = Vec::new();
        for (rel_path, content_hash, file_diags) in per_file_results {
            cache.update(&rel_path, &content_hash, &file_diags);
            all_diags.extend(file_diags);

            // Early termination at max_diagnostics
            if max_diags > 0 && all_diags.len() >= max_diags {
                break;
            }
        }

        // 6. Run cross-file checks (sequential, needs full model list)
        let project_diags = self.run_cross_file_checks(&models);
        all_diags.extend(project_diags);

        // 7. Truncate to max_diagnostics
        if max_diags > 0 && all_diags.len() > max_diags {
            all_diags.truncate(max_diags);
        }

        // 8. Sort diagnostics by (file_path, line, column)
        all_diags.sort_by(|a, b| {
            a.file_path
                .cmp(&b.file_path)
                .then(a.line.cmp(&b.line))
                .then(a.column.cmp(&b.column))
        });

        // 9. Compute summary counts
        let total_errors = all_diags
            .iter()
            .filter(|d| d.severity == Severity::Error)
            .count() as u32;
        let total_warnings = all_diags
            .iter()
            .filter(|d| d.severity == Severity::Warning)
            .count() as u32;
        let total_infos = all_diags
            .iter()
            .filter(|d| d.severity == Severity::Info)
            .count() as u32;

        // 10. Determine pass/fail
        let passed = if self.config.fail_on_warnings {
            total_errors == 0 && total_warnings == 0
        } else {
            total_errors == 0
        };

        // 11. Flush cache to disk
        cache.flush();

        let elapsed = start.elapsed();

        CheckResult {
            diagnostics: all_diags,
            total_files_checked: uncached_files.len() as u32,
            total_files_skipped_cache: cached_files.len() as u32,
            total_errors,
            total_warnings,
            total_infos,
            elapsed_ms: elapsed.as_millis() as u64,
            project_type: project_type.to_string(),
            passed,
        }
    }

    /// Run all per-file checkers on a single file, wrapped in catch_unwind.
    fn run_per_file_checks(
        &self,
        file: &DiscoveredFile,
        model: Option<&DiscoveredModel>,
        project_type: &ProjectType,
    ) -> Vec<CheckDiagnostic> {
        let mut diags = Vec::new();

        for checker in &self.checkers {
            // Skip checkers that don't apply to this project type
            if !should_run_checker(checker.name(), project_type) {
                continue;
            }

            let result = catch_unwind(AssertUnwindSafe(|| {
                checker.check_file(&file.rel_path, &file.content, model, &self.config)
            }));

            match result {
                Ok(checker_diags) => diags.extend(checker_diags),
                Err(panic_info) => {
                    let panic_msg = if let Some(s) = panic_info.downcast_ref::<String>() {
                        s.clone()
                    } else if let Some(s) = panic_info.downcast_ref::<&str>() {
                        (*s).to_owned()
                    } else {
                        "unknown panic".to_owned()
                    };

                    diags.push(CheckDiagnostic {
                        rule_id: "INTERNAL".to_owned(),
                        message: format!(
                            "Internal error in checker '{}': {}. \
                             This is a bug — please report it.",
                            checker.name(),
                            panic_msg
                        ),
                        severity: Severity::Warning,
                        category: CheckCategory::FileStructure,
                        file_path: file.rel_path.clone(),
                        line: 0,
                        column: 0,
                        snippet: None,
                        suggestion: Some(
                            "This file was skipped by this checker due to an internal error."
                                .to_owned(),
                        ),
                        doc_url: None,
                    });
                }
            }
        }

        diags
    }

    /// Run all cross-file (project-level) checks, wrapped in catch_unwind.
    fn run_cross_file_checks(&self, models: &[DiscoveredModel]) -> Vec<CheckDiagnostic> {
        let mut diags = Vec::new();

        for checker in &self.checkers {
            let result = catch_unwind(AssertUnwindSafe(|| {
                checker.check_project(models, &self.config)
            }));

            match result {
                Ok(checker_diags) => diags.extend(checker_diags),
                Err(panic_info) => {
                    let panic_msg = if let Some(s) = panic_info.downcast_ref::<String>() {
                        s.clone()
                    } else if let Some(s) = panic_info.downcast_ref::<&str>() {
                        (*s).to_owned()
                    } else {
                        "unknown panic".to_owned()
                    };

                    diags.push(CheckDiagnostic {
                        rule_id: "INTERNAL".to_owned(),
                        message: format!(
                            "Internal error in checker '{}' during project-level checks: {}. \
                             This is a bug — please report it.",
                            checker.name(),
                            panic_msg
                        ),
                        severity: Severity::Warning,
                        category: CheckCategory::FileStructure,
                        file_path: String::new(),
                        line: 0,
                        column: 0,
                        snippet: None,
                        suggestion: None,
                        doc_url: None,
                    });
                }
            }
        }

        diags
    }
}

/// Determine if a checker should run for a given project type.
///
/// - `sql_header` only runs for IronLayer projects.
/// - Most other checkers run for all project types.
fn should_run_checker(checker_name: &str, project_type: &ProjectType) -> bool {
    match checker_name {
        "sql_header" => *project_type == ProjectType::IronLayer,
        "dbt_project" => *project_type == ProjectType::Dbt,
        _ => true,
    }
}

/// Extract model metadata from a discovered SQL file.
///
/// Parses the header block for `-- key: value` fields and extracts
/// `{{ ref('...') }}` references from the SQL body.
fn discover_model(file: &DiscoveredFile) -> DiscoveredModel {
    let header = parse_header_map(&file.content);
    let ref_names = extract_ref_names(&file.content);

    // Model name: prefer `-- name:` header, fall back to filename stem
    let name = header.get("name").cloned().unwrap_or_else(|| {
        Path::new(&file.rel_path)
            .file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_default()
    });

    DiscoveredModel {
        name,
        file_path: file.rel_path.clone(),
        content_hash: file.content_hash.clone(),
        ref_names,
        header,
        content: file.content.clone(),
    }
}

/// Parse the header block into a key→value map (first occurrence wins).
fn parse_header_map(content: &str) -> HashMap<String, String> {
    let mut map = HashMap::new();

    for line in content.lines() {
        let trimmed = line.trim();

        // Empty lines don't terminate
        if trimmed.is_empty() {
            continue;
        }

        // Must start with `--`
        if let Some(rest) = trimmed.strip_prefix("--") {
            let rest = rest.trim();

            // Bare `--`
            if rest.is_empty() {
                continue;
            }

            // `key: value` pattern
            if let Some(colon_pos) = rest.find(':') {
                let key = rest[..colon_pos].trim().to_lowercase();
                let value = rest[colon_pos + 1..].trim().to_owned();

                if !key.is_empty() {
                    map.entry(key).or_insert(value);
                    continue;
                }
            }

            // Plain comment — skip
            continue;
        }

        // Non-empty, non-comment → terminate header
        break;
    }

    map
}

/// Extract `{{ ref('...') }}` references from SQL content.
///
/// Uses the exact regex from `ref_resolver._REF_PATTERN`:
/// `r"\{\{\s*ref\s*\(\s*(?:'([^']+)'|\"([^\"]+)\")\s*\)\s*\}\}"`
fn extract_ref_names(content: &str) -> Vec<String> {
    // This regex matches the Python ref_resolver._REF_PATTERN exactly
    let re = Regex::new(r#"\{\{\s*ref\s*\(\s*(?:'([^']+)'|"([^"]+)")\s*\)\s*\}\}"#)
        .expect("ref pattern regex is valid");

    let mut refs = Vec::new();
    for cap in re.captures_iter(content) {
        // Group 1 = single-quoted, Group 2 = double-quoted
        if let Some(m) = cap.get(1) {
            refs.push(m.as_str().to_owned());
        } else if let Some(m) = cap.get(2) {
            refs.push(m.as_str().to_owned());
        }
    }
    refs
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::discovery::compute_sha256;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn test_extract_ref_names_single_quotes() {
        let content = "SELECT * FROM {{ ref('stg_orders') }}";
        let refs = extract_ref_names(content);
        assert_eq!(refs, vec!["stg_orders"]);
    }

    #[test]
    fn test_extract_ref_names_double_quotes() {
        let content = r#"SELECT * FROM {{ ref("stg_orders") }}"#;
        let refs = extract_ref_names(content);
        assert_eq!(refs, vec!["stg_orders"]);
    }

    #[test]
    fn test_extract_ref_names_multiple() {
        let content = "SELECT * FROM {{ ref('stg_orders') }} JOIN {{ ref('stg_customers') }}";
        let refs = extract_ref_names(content);
        assert_eq!(refs, vec!["stg_orders", "stg_customers"]);
    }

    #[test]
    fn test_extract_ref_names_with_whitespace() {
        let content = "SELECT * FROM {{  ref(  'stg_orders'  )  }}";
        let refs = extract_ref_names(content);
        assert_eq!(refs, vec!["stg_orders"]);
    }

    #[test]
    fn test_extract_ref_names_no_refs() {
        let content = "SELECT * FROM raw_orders";
        let refs = extract_ref_names(content);
        assert!(refs.is_empty());
    }

    #[test]
    fn test_parse_header_map() {
        let content = "-- name: stg_orders\n-- kind: FULL_REFRESH\nSELECT 1";
        let map = parse_header_map(content);
        assert_eq!(map.get("name"), Some(&"stg_orders".to_owned()));
        assert_eq!(map.get("kind"), Some(&"FULL_REFRESH".to_owned()));
    }

    #[test]
    fn test_parse_header_map_first_occurrence_wins() {
        let content = "-- name: first\n-- name: second\nSELECT 1";
        let map = parse_header_map(content);
        assert_eq!(map.get("name"), Some(&"first".to_owned()));
    }

    #[test]
    fn test_parse_header_map_blank_lines() {
        let content = "-- name: test\n\n-- kind: FULL_REFRESH\nSELECT 1";
        let map = parse_header_map(content);
        assert_eq!(map.get("name"), Some(&"test".to_owned()));
        assert_eq!(map.get("kind"), Some(&"FULL_REFRESH".to_owned()));
    }

    #[test]
    fn test_parse_header_map_bare_comment() {
        let content = "-- name: test\n--\n-- kind: FULL_REFRESH\nSELECT 1";
        let map = parse_header_map(content);
        assert!(map.contains_key("name"));
        assert!(map.contains_key("kind"));
    }

    #[test]
    fn test_discover_model_from_header() {
        let file = DiscoveredFile {
            rel_path: "models/stg_orders.sql".to_owned(),
            content:
                "-- name: stg_orders\n-- kind: FULL_REFRESH\nSELECT * FROM {{ ref('raw_orders') }}"
                    .to_owned(),
            content_hash: compute_sha256("test"),
        };
        let model = discover_model(&file);
        assert_eq!(model.name, "stg_orders");
        assert_eq!(model.ref_names, vec!["raw_orders"]);
        assert_eq!(model.header.get("kind"), Some(&"FULL_REFRESH".to_owned()));
    }

    #[test]
    fn test_discover_model_fallback_to_filename() {
        let file = DiscoveredFile {
            rel_path: "models/stg_orders.sql".to_owned(),
            content: "SELECT 1".to_owned(),
            content_hash: compute_sha256("test"),
        };
        let model = discover_model(&file);
        assert_eq!(model.name, "stg_orders");
    }

    #[test]
    fn test_check_engine_ironlayer_project() {
        let dir = tempdir().unwrap();
        fs::write(dir.path().join("ironlayer.yaml"), "version: 1\n").unwrap();
        let models_dir = dir.path().join("models");
        fs::create_dir_all(&models_dir).unwrap();
        fs::write(
            models_dir.join("stg_orders.sql"),
            "-- name: stg_orders\n-- kind: FULL_REFRESH\nSELECT 1",
        )
        .unwrap();

        let config = CheckConfig::default();
        let engine = CheckEngine::new(config);
        let result = engine.check(dir.path());

        assert_eq!(result.project_type, "ironlayer");
        assert!(result.passed);
        assert_eq!(result.total_errors, 0);
    }

    #[test]
    fn test_check_engine_detects_errors() {
        let dir = tempdir().unwrap();
        fs::write(dir.path().join("ironlayer.yaml"), "version: 1\n").unwrap();
        let models_dir = dir.path().join("models");
        fs::create_dir_all(&models_dir).unwrap();
        // Missing kind → HDR002
        fs::write(
            models_dir.join("stg_orders.sql"),
            "-- name: stg_orders\nSELECT 1",
        )
        .unwrap();

        let config = CheckConfig::default();
        let engine = CheckEngine::new(config);
        let result = engine.check(dir.path());

        assert!(!result.passed);
        assert!(result.total_errors > 0);
        assert!(result.diagnostics.iter().any(|d| d.rule_id == "HDR002"));
    }

    #[test]
    fn test_check_engine_empty_project() {
        let dir = tempdir().unwrap();
        let config = CheckConfig::default();
        let engine = CheckEngine::new(config);
        let result = engine.check(dir.path());

        assert!(result.passed);
        assert_eq!(result.total_files_checked, 0);
    }

    #[test]
    fn test_check_engine_non_ironlayer_skips_hdr() {
        let dir = tempdir().unwrap();
        // No ironlayer.yaml → raw_sql project type
        fs::write(dir.path().join("query.sql"), "SELECT 1").unwrap();

        let config = CheckConfig::default();
        let engine = CheckEngine::new(config);
        let result = engine.check(dir.path());

        // HDR rules should not fire for raw_sql project type
        assert!(!result
            .diagnostics
            .iter()
            .any(|d| d.rule_id.starts_with("HDR")));
    }

    #[test]
    fn test_check_engine_max_diagnostics() {
        let dir = tempdir().unwrap();
        fs::write(dir.path().join("ironlayer.yaml"), "version: 1\n").unwrap();
        let models_dir = dir.path().join("models");
        fs::create_dir_all(&models_dir).unwrap();

        // Create many files with errors
        for i in 0..20 {
            fs::write(
                models_dir.join(format!("model_{i}.sql")),
                "SELECT 1", // Missing name and kind
            )
            .unwrap();
        }

        let mut config = CheckConfig::default();
        config.max_diagnostics = 5;
        let engine = CheckEngine::new(config);
        let result = engine.check(dir.path());

        assert!(result.diagnostics.len() <= 5);
    }

    #[test]
    fn test_check_engine_fail_on_warnings() {
        let dir = tempdir().unwrap();
        fs::write(dir.path().join("ironlayer.yaml"), "version: 1\n").unwrap();
        let models_dir = dir.path().join("models");
        fs::create_dir_all(&models_dir).unwrap();
        // Duplicate header → HDR013 (warning)
        fs::write(
            models_dir.join("stg_orders.sql"),
            "-- name: stg_orders\n-- kind: FULL_REFRESH\n-- name: stg_orders2\nSELECT 1",
        )
        .unwrap();

        // Without fail_on_warnings: should pass (only warnings)
        let config = CheckConfig::default();
        let engine = CheckEngine::new(config);
        let result = engine.check(dir.path());
        assert!(result.passed);

        // With fail_on_warnings: should fail
        let mut config_strict = CheckConfig::default();
        config_strict.fail_on_warnings = true;
        let engine_strict = CheckEngine::new(config_strict);
        let result_strict = engine_strict.check(dir.path());
        assert!(!result_strict.passed);
    }

    #[test]
    fn test_should_run_checker() {
        assert!(should_run_checker("sql_header", &ProjectType::IronLayer));
        assert!(!should_run_checker("sql_header", &ProjectType::Dbt));
        assert!(!should_run_checker("sql_header", &ProjectType::RawSql));
        assert!(should_run_checker("dbt_project", &ProjectType::Dbt));
        assert!(!should_run_checker("dbt_project", &ProjectType::IronLayer));
        assert!(should_run_checker("sql_syntax", &ProjectType::IronLayer));
        assert!(should_run_checker("sql_syntax", &ProjectType::Dbt));
        assert!(should_run_checker("sql_syntax", &ProjectType::RawSql));
    }

    #[test]
    fn test_diagnostics_sorted() {
        let dir = tempdir().unwrap();
        fs::write(dir.path().join("ironlayer.yaml"), "version: 1\n").unwrap();
        let models_dir = dir.path().join("models");
        fs::create_dir_all(&models_dir).unwrap();
        fs::write(
            models_dir.join("b_model.sql"),
            "-- name: b\nSELECT 1", // Missing kind
        )
        .unwrap();
        fs::write(
            models_dir.join("a_model.sql"),
            "-- name: a\nSELECT 1", // Missing kind
        )
        .unwrap();

        let config = CheckConfig::default();
        let engine = CheckEngine::new(config);
        let result = engine.check(dir.path());

        // Should be sorted by file_path
        if result.diagnostics.len() >= 2 {
            assert!(result.diagnostics[0].file_path <= result.diagnostics[1].file_path);
        }
    }
}
