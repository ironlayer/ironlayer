//! Check engine orchestrator — the main entry point for running checks.
//!
//! Coordinates file discovery, caching, header parsing, ref extraction,
//! per-file checks, cross-file checks, and result assembly.
//!
//! Supports `--changed-only` mode for incremental checking (git integration),
//! `--fix` mode for auto-fixing fixable rules, and `--sarif` for SARIF output.
//!
//! Every per-file check dispatch is wrapped in `catch_unwind` so that a
//! panic in one checker emits an `INTERNAL` diagnostic instead of crashing
//! the Python process.

use std::collections::HashMap;
use std::io::Write;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::{Path, PathBuf};
use std::time::Instant;

use rayon::prelude::*;
use regex::Regex;

use crate::cache::CheckCache;
use crate::checkers::{build_checker_registry, Checker};
use crate::config::CheckConfig;
use crate::discovery::{
    compute_sha256, detect_project_type, filter_changed_only, get_changed_files, walk_files,
};
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
        let all_files = walk_files(root, &self.config);

        // 2b. If --changed-only, filter to only git-modified files
        //     but keep all_files available for building the full model registry
        let check_files = if self.config.changed_only {
            match get_changed_files(root) {
                Some(changed) => filter_changed_only(&all_files, &changed),
                None => {
                    log::warn!(
                        "--changed-only requested but git is unavailable. Checking all files."
                    );
                    all_files.clone()
                }
            }
        } else {
            all_files.clone()
        };

        // 3. Initialize cache and partition files
        let mut cache = CheckCache::new(root, &self.config);
        let (cached_files, uncached_files) = cache.partition(&check_files);

        // 4. Parse SQL headers + extract refs from ALL files (not just uncached)
        //    This is required so that cross-file checks (ref resolution, consistency)
        //    have the full model registry even in --changed-only mode.
        let models: Vec<DiscoveredModel> = all_files
            .iter()
            .filter(|f| {
                f.rel_path.ends_with(".sql")
                    || f.rel_path.ends_with(".yml")
                    || f.rel_path.ends_with(".yaml")
            })
            .map(discover_model)
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

        // 7. Run cross-file checks (sequential, needs full model list)
        let project_diags = self.run_cross_file_checks(&models, &project_type);
        all_diags.extend(project_diags);

        // 8. Apply --fix if requested (5-step workflow)
        if self.config.fix {
            let fixed = apply_fixes(root, &all_diags);
            if !fixed.is_empty() {
                // Re-discover and re-check fixed files
                let mut recheck_diags = Vec::new();
                for fixed_path in &fixed {
                    let abs_path = root.join(fixed_path);
                    let content = match std::fs::read_to_string(&abs_path) {
                        Ok(c) => c,
                        Err(_) => continue,
                    };
                    let content_hash = compute_sha256(&content);
                    let file = DiscoveredFile {
                        rel_path: fixed_path.clone(),
                        content,
                        content_hash,
                    };
                    let model = discover_model(&file);
                    let file_diags = self.run_per_file_checks(&file, Some(&model), &project_type);
                    recheck_diags.extend(file_diags);
                }

                // Replace diagnostics for fixed files with re-check results
                all_diags.retain(|d| !fixed.contains(&d.file_path));
                all_diags.extend(recheck_diags);
            }
        }

        // 9. Sort diagnostics by (file_path, line, column)
        all_diags.sort_by(|a, b| {
            a.file_path
                .cmp(&b.file_path)
                .then(a.line.cmp(&b.line))
                .then(a.column.cmp(&b.column))
        });

        // 10. Truncate to max_diagnostics
        if max_diags > 0 && all_diags.len() > max_diags {
            all_diags.truncate(max_diags);
        }

        // 11. Compute summary counts
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

        // 12. Determine pass/fail
        let passed = if self.config.fail_on_warnings {
            total_errors == 0 && total_warnings == 0
        } else {
            total_errors == 0
        };

        // 13. Flush cache to disk
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
    fn run_cross_file_checks(
        &self,
        models: &[DiscoveredModel],
        project_type: &ProjectType,
    ) -> Vec<CheckDiagnostic> {
        let mut diags = Vec::new();

        for checker in &self.checkers {
            if !should_run_checker(checker.name(), project_type) {
                continue;
            }

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
// --fix support
// ---------------------------------------------------------------------------

/// Set of rule IDs that can be auto-fixed.
const FIXABLE_RULES: &[&str] = &["SQL007", "SQL009", "HDR013", "REF004"];

/// Check if a diagnostic is for a fixable rule.
#[must_use]
fn is_fixable(diag: &CheckDiagnostic) -> bool {
    FIXABLE_RULES.contains(&diag.rule_id.as_str())
}

/// Apply auto-fixes for fixable diagnostics.
///
/// Follows the 5-step workflow:
/// 1. Dry-run: diagnostics already collected
/// 2. Filter: only fixable rules
/// 3. Apply: read file → apply fixes in reverse line order → atomic write
/// 4. Re-check: caller re-runs checks on modified files
/// 5. Report: caller reports which fixes were applied
///
/// Returns the set of file paths that were modified.
fn apply_fixes(root: &Path, diags: &[CheckDiagnostic]) -> Vec<String> {
    // Step 2: Filter to fixable diagnostics only
    let fixable: Vec<&CheckDiagnostic> = diags.iter().filter(|d| is_fixable(d)).collect();
    if fixable.is_empty() {
        return Vec::new();
    }

    // Group fixable diagnostics by file path
    let mut by_file: HashMap<String, Vec<&CheckDiagnostic>> = HashMap::new();
    for diag in &fixable {
        by_file
            .entry(diag.file_path.clone())
            .or_default()
            .push(diag);
    }

    let mut modified_files = Vec::new();

    // Step 3: Apply fixes per file in reverse line order
    for (file_path, mut file_diags) in by_file {
        let abs_path = root.join(&file_path);
        let content = match std::fs::read_to_string(&abs_path) {
            Ok(c) => c,
            Err(e) => {
                log::warn!("--fix: could not read {}: {}", file_path, e);
                continue;
            }
        };

        // Sort in reverse line order so that fixes don't shift line numbers
        file_diags.sort_by(|a, b| b.line.cmp(&a.line));

        let mut lines: Vec<String> = content.lines().map(|l| l.to_owned()).collect();
        let mut any_changed = false;

        for diag in &file_diags {
            let changed = apply_single_fix(&mut lines, diag);
            if changed {
                any_changed = true;
            }
        }

        if any_changed {
            // Atomic write: write to temp file, then rename
            if let Err(e) = atomic_write_lines(&abs_path, &lines) {
                log::warn!("--fix: could not write {}: {}", file_path, e);
                continue;
            }
            modified_files.push(file_path);
        }
    }

    modified_files
}

/// Apply a single fix to the lines of a file.
///
/// Returns `true` if any modification was made.
fn apply_single_fix(lines: &mut Vec<String>, diag: &CheckDiagnostic) -> bool {
    match diag.rule_id.as_str() {
        "HDR013" => fix_hdr013(lines, diag),
        "SQL007" => fix_sql007(lines, diag),
        "SQL009" => fix_sql009(lines, diag),
        "REF004" => fix_ref004(lines, diag),
        _ => false,
    }
}

/// HDR013 fix: Remove duplicate header lines (keep first occurrence).
///
/// The diagnostic's line number points to the duplicate. Remove that line.
fn fix_hdr013(lines: &mut Vec<String>, diag: &CheckDiagnostic) -> bool {
    if diag.line == 0 || diag.line as usize > lines.len() {
        return false;
    }
    // Remove the duplicate header line (1-based index)
    lines.remove(diag.line as usize - 1);
    true
}

/// SQL007 fix: Remove trailing semicolons from SQL body.
///
/// The diagnostic's line number points to the line with the trailing semicolon.
fn fix_sql007(lines: &mut [String], diag: &CheckDiagnostic) -> bool {
    if diag.line == 0 || diag.line as usize > lines.len() {
        return false;
    }
    let idx = diag.line as usize - 1;
    let trimmed = lines[idx].trim_end();
    if trimmed.ends_with(';') {
        lines[idx] = trimmed.trim_end_matches(';').to_owned();
        true
    } else {
        false
    }
}

/// SQL009 fix: Replace tab characters with 4 spaces.
///
/// The diagnostic's line number points to the line with tab characters.
fn fix_sql009(lines: &mut [String], diag: &CheckDiagnostic) -> bool {
    if diag.line == 0 || diag.line as usize > lines.len() {
        return false;
    }
    let idx = diag.line as usize - 1;
    if lines[idx].contains('\t') {
        lines[idx] = lines[idx].replace('\t', "    ");
        true
    } else {
        false
    }
}

/// REF004 fix: Replace fully-qualified ref name with short name where unambiguous.
///
/// The diagnostic's snippet should contain the fully-qualified ref pattern.
/// The suggestion contains the short name to use.
fn fix_ref004(lines: &mut [String], diag: &CheckDiagnostic) -> bool {
    if diag.line == 0 || diag.line as usize > lines.len() {
        return false;
    }

    let (snippet, suggestion) = match (&diag.snippet, &diag.suggestion) {
        (Some(s), Some(sug)) => (s, sug),
        _ => return false,
    };

    let idx = diag.line as usize - 1;
    if lines[idx].contains(snippet.as_str()) {
        lines[idx] = lines[idx].replace(snippet.as_str(), suggestion.as_str());
        true
    } else {
        false
    }
}

/// Atomically write lines to a file (write to temp, then rename).
///
/// Uses `.tmp.{pid}` suffix for the temp file, then renames. On POSIX,
/// rename is atomic. No backups are created (assumes files are under VCS).
///
/// # Errors
///
/// Returns an error if the temp file cannot be written or renamed.
fn atomic_write_lines(path: &PathBuf, lines: &[String]) -> std::io::Result<()> {
    let pid = std::process::id();
    let tmp_path = path.with_extension(format!("tmp.{pid}"));

    let mut file = std::fs::File::create(&tmp_path)?;
    for (i, line) in lines.iter().enumerate() {
        file.write_all(line.as_bytes())?;
        if i < lines.len() - 1 {
            file.write_all(b"\n")?;
        }
    }
    // Preserve trailing newline if the original file likely had one
    file.write_all(b"\n")?;
    file.flush()?;
    drop(file);

    std::fs::rename(&tmp_path, path)?;
    Ok(())
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
