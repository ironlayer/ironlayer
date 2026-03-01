//! Ref resolution checker — rules REF001 through REF006.
//!
//! Validates `{{ ref('...') }}` macro usage, reimplementing the resolution
//! logic from `ref_resolver.py`. Uses regex extraction identical to
//! `ref_resolver._REF_PATTERN` and cross-file resolution via model registry.
//!
//! REF001-REF003 and REF005 are cross-file checks that run in `check_project()`.
//! REF004 and REF006 are per-file checks.

use std::collections::{HashMap, HashSet};

use regex::Regex;

use crate::checkers::Checker;
use crate::config::CheckConfig;
use crate::types::{CheckCategory, CheckDiagnostic, DiscoveredModel, Severity};

/// Ref resolution checker implementing REF001-REF006.
pub struct RefResolverChecker;

/// Generate the doc URL for a given rule ID.
fn doc_url(rule_id: &str) -> Option<String> {
    Some(format!("https://docs.ironlayer.app/check/rules/{rule_id}"))
}

impl Checker for RefResolverChecker {
    fn name(&self) -> &'static str {
        "ref_resolver"
    }

    fn check_file(
        &self,
        file_path: &str,
        content: &str,
        _model: Option<&DiscoveredModel>,
        config: &CheckConfig,
    ) -> Vec<CheckDiagnostic> {
        if !file_path.ends_with(".sql") {
            return Vec::new();
        }

        let mut diags = Vec::new();

        // REF004: Ref uses fully-qualified name where short name would suffice
        check_ref004(file_path, content, config, &mut diags);

        // REF006: Direct table reference instead of ref() — disabled by default
        check_ref006(file_path, content, config, &mut diags);

        diags
    }

    fn check_project(
        &self,
        models: &[DiscoveredModel],
        config: &CheckConfig,
    ) -> Vec<CheckDiagnostic> {
        let mut diags = Vec::new();

        // Build model registry: short_name → canonical, canonical → canonical
        let registry = build_model_registry(models);
        let model_names: HashSet<&str> = models.iter().map(|m| m.name.as_str()).collect();

        // REF001: Undefined ref
        check_ref001(models, &registry, &model_names, config, &mut diags);

        // REF002: Circular ref dependency
        check_ref002(models, config, &mut diags);

        // REF003: Self-referential ref
        check_ref003(models, config, &mut diags);

        // REF005: Ambiguous short name
        check_ref005(models, config, &mut diags);

        diags
    }
}

/// Build a model registry mapping short names and canonical names to canonical names.
///
/// This mirrors `ref_resolver.build_model_registry()`.
fn build_model_registry(models: &[DiscoveredModel]) -> HashMap<String, String> {
    let mut registry = HashMap::new();

    for model in models {
        let canonical = model.name.clone();

        // Map canonical name to itself
        registry.insert(canonical.clone(), canonical.clone());

        // Map short name (after last dot) to canonical name if unambiguous
        if let Some(dot_pos) = canonical.rfind('.') {
            let short_name = &canonical[dot_pos + 1..];
            if !short_name.is_empty() {
                registry
                    .entry(short_name.to_owned())
                    .or_insert_with(|| canonical.clone());
            }
        }
    }

    registry
}

/// Full Wagner-Fischer Levenshtein distance computation.
///
/// Returns the minimum number of single-character edits (insertions,
/// deletions, substitutions) needed to transform `a` into `b`.
fn levenshtein(a: &str, b: &str) -> usize {
    let a_chars: Vec<char> = a.chars().collect();
    let b_chars: Vec<char> = b.chars().collect();
    let m = a_chars.len();
    let n = b_chars.len();

    if m == 0 {
        return n;
    }
    if n == 0 {
        return m;
    }

    // Use two rows instead of full matrix for O(min(m,n)) space
    let mut prev = vec![0usize; n + 1];
    let mut curr = vec![0usize; n + 1];

    for (j, val) in prev.iter_mut().enumerate().take(n + 1) {
        *val = j;
    }

    for i in 1..=m {
        curr[0] = i;
        for j in 1..=n {
            let cost = if a_chars[i - 1] == b_chars[j - 1] {
                0
            } else {
                1
            };
            curr[j] = (prev[j] + 1) // deletion
                .min(curr[j - 1] + 1) // insertion
                .min(prev[j - 1] + cost); // substitution
        }
        std::mem::swap(&mut prev, &mut curr);
    }

    prev[n]
}

/// Find the best suggestion for an undefined ref name from the model registry.
///
/// Returns a suggestion string if a close match (Levenshtein distance ≤ 3) is found.
fn find_suggestion(ref_name: &str, model_names: &HashSet<&str>) -> Option<String> {
    let mut best_distance = usize::MAX;
    let mut best_name = None;

    for &name in model_names {
        let dist = levenshtein(ref_name, name);
        if dist < best_distance && dist <= 3 {
            best_distance = dist;
            best_name = Some(name);
        }
    }

    best_name.map(|name| {
        format!(
            "Did you mean '{}'? (Levenshtein distance: {})",
            name, best_distance
        )
    })
}

/// Extract ref names with their line numbers from SQL content.
fn extract_refs_with_lines(content: &str) -> Vec<(String, u32)> {
    let re = Regex::new(r#"\{\{\s*ref\s*\(\s*(?:'([^']+)'|"([^"]+)")\s*\)\s*\}\}"#)
        .expect("ref pattern regex is valid");

    let mut refs = Vec::new();

    for (line_idx, line) in content.lines().enumerate() {
        let line_num = (line_idx + 1) as u32;
        for cap in re.captures_iter(line) {
            let ref_name = cap
                .get(1)
                .or_else(|| cap.get(2))
                .map(|m| m.as_str().to_owned());
            if let Some(name) = ref_name {
                refs.push((name, line_num));
            }
        }
    }

    refs
}

// ---------------------------------------------------------------------------
// REF001: Undefined ref — model doesn't exist in project
// ---------------------------------------------------------------------------

fn check_ref001(
    models: &[DiscoveredModel],
    registry: &HashMap<String, String>,
    model_names: &HashSet<&str>,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    for model in models {
        if !config.is_rule_enabled_for_path("REF001", &model.file_path, true) {
            continue;
        }

        let refs_with_lines = extract_refs_with_lines(&model.content);

        for (ref_name, line) in &refs_with_lines {
            if !registry.contains_key(ref_name) {
                let suggestion = find_suggestion(ref_name, model_names);

                diags.push(CheckDiagnostic {
                    rule_id: "REF001".to_owned(),
                    message: format!(
                        "Undefined ref: '{}'. No model with this name exists in the project.",
                        ref_name
                    ),
                    severity: config.effective_severity_for_path(
                        "REF001",
                        &model.file_path,
                        Severity::Error,
                    ),
                    category: CheckCategory::RefResolution,
                    file_path: model.file_path.clone(),
                    line: *line,
                    column: 0,
                    snippet: Some(format!("{{{{ ref('{}') }}}}", ref_name)),
                    suggestion,
                    doc_url: doc_url("REF001"),
                });
            }
        }
    }
}

// ---------------------------------------------------------------------------
// REF002: Circular ref dependency detected (A->B->A)
// ---------------------------------------------------------------------------

fn check_ref002(
    models: &[DiscoveredModel],
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if models.is_empty() {
        return;
    }

    // Build adjacency: model_name → set of ref'd model names
    let model_name_set: HashSet<&str> = models.iter().map(|m| m.name.as_str()).collect();
    let mut adj: HashMap<&str, Vec<&str>> = HashMap::new();
    let name_to_file: HashMap<&str, &str> = models
        .iter()
        .map(|m| (m.name.as_str(), m.file_path.as_str()))
        .collect();

    for model in models {
        let deps: Vec<&str> = model
            .ref_names
            .iter()
            .filter(|r| model_name_set.contains(r.as_str()))
            .map(|r| r.as_str())
            .collect();
        adj.insert(model.name.as_str(), deps);
    }

    // DFS cycle detection
    let mut visited: HashSet<&str> = HashSet::new();
    let mut in_stack: HashSet<&str> = HashSet::new();
    let mut reported_cycles: HashSet<String> = HashSet::new();

    for model in models {
        let file_path = model.file_path.as_str();
        if !config.is_rule_enabled_for_path("REF002", file_path, true) {
            continue;
        }

        if !visited.contains(model.name.as_str()) {
            detect_cycles_dfs(
                model.name.as_str(),
                &adj,
                &name_to_file,
                &mut visited,
                &mut in_stack,
                &mut Vec::new(),
                &mut reported_cycles,
                config,
                diags,
            );
        }
    }
}

/// DFS helper for cycle detection.
#[allow(clippy::too_many_arguments)]
fn detect_cycles_dfs<'a>(
    node: &'a str,
    adj: &HashMap<&'a str, Vec<&'a str>>,
    name_to_file: &HashMap<&'a str, &'a str>,
    visited: &mut HashSet<&'a str>,
    in_stack: &mut HashSet<&'a str>,
    path: &mut Vec<&'a str>,
    reported_cycles: &mut HashSet<String>,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    visited.insert(node);
    in_stack.insert(node);
    path.push(node);

    if let Some(deps) = adj.get(node) {
        for &dep in deps {
            if !visited.contains(dep) {
                detect_cycles_dfs(
                    dep,
                    adj,
                    name_to_file,
                    visited,
                    in_stack,
                    path,
                    reported_cycles,
                    config,
                    diags,
                );
            } else if in_stack.contains(dep) {
                // Cycle found — build the cycle path
                let cycle_start = path.iter().position(|&n| n == dep).unwrap_or(0);
                let mut cycle: Vec<&str> = path[cycle_start..].to_vec();
                cycle.push(dep);

                // Deduplicate: normalize the cycle to a canonical form
                let cycle_key = {
                    let mut key_parts = cycle.clone();
                    key_parts.sort();
                    key_parts.join(" -> ")
                };

                if !reported_cycles.contains(&cycle_key) {
                    reported_cycles.insert(cycle_key);

                    let file_path = name_to_file.get(node).copied().unwrap_or("");
                    let cycle_str = cycle.join(" -> ");

                    diags.push(CheckDiagnostic {
                        rule_id: "REF002".to_owned(),
                        message: format!(
                            "Circular ref dependency detected: {}. \
                             Models must not form dependency cycles.",
                            cycle_str
                        ),
                        severity: config.effective_severity_for_path(
                            "REF002",
                            file_path,
                            Severity::Warning,
                        ),
                        category: CheckCategory::RefResolution,
                        file_path: file_path.to_owned(),
                        line: 0,
                        column: 0,
                        snippet: None,
                        suggestion: Some(
                            "Break the cycle by removing one of the ref() dependencies.".to_owned(),
                        ),
                        doc_url: doc_url("REF002"),
                    });
                }
            }
        }
    }

    path.pop();
    in_stack.remove(node);
}

// ---------------------------------------------------------------------------
// REF003: Self-referential ref (model references itself)
// ---------------------------------------------------------------------------

fn check_ref003(
    models: &[DiscoveredModel],
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    for model in models {
        if !config.is_rule_enabled_for_path("REF003", &model.file_path, true) {
            continue;
        }

        let refs_with_lines = extract_refs_with_lines(&model.content);

        for (ref_name, line) in &refs_with_lines {
            if ref_name == &model.name {
                diags.push(CheckDiagnostic {
                    rule_id: "REF003".to_owned(),
                    message: format!(
                        "Model '{}' references itself via {{{{ ref('{}') }}}}. \
                         Self-referential refs create infinite loops.",
                        model.name, ref_name
                    ),
                    severity: config.effective_severity_for_path(
                        "REF003",
                        &model.file_path,
                        Severity::Warning,
                    ),
                    category: CheckCategory::RefResolution,
                    file_path: model.file_path.clone(),
                    line: *line,
                    column: 0,
                    snippet: Some(format!("{{{{ ref('{}') }}}}", ref_name)),
                    suggestion: Some(
                        "Remove the self-reference or use a different model name.".to_owned(),
                    ),
                    doc_url: doc_url("REF003"),
                });
            }
        }
    }
}

// ---------------------------------------------------------------------------
// REF004: Ref uses fully-qualified name where short name would suffice
// ---------------------------------------------------------------------------

fn check_ref004(
    file_path: &str,
    content: &str,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("REF004", file_path, true) {
        return;
    }

    let refs_with_lines = extract_refs_with_lines(content);

    for (ref_name, line) in &refs_with_lines {
        // A fully-qualified name contains a dot (e.g., "schema.model_name")
        if ref_name.contains('.') {
            if let Some(dot_pos) = ref_name.rfind('.') {
                let short_name = &ref_name[dot_pos + 1..];
                if !short_name.is_empty() {
                    diags.push(CheckDiagnostic {
                        rule_id: "REF004".to_owned(),
                        message: format!(
                            "Ref '{}' uses a fully-qualified name. \
                             Consider using the short name '{}' if it's unambiguous.",
                            ref_name, short_name
                        ),
                        severity: config.effective_severity_for_path(
                            "REF004",
                            file_path,
                            Severity::Info,
                        ),
                        category: CheckCategory::RefResolution,
                        file_path: file_path.to_owned(),
                        line: *line,
                        column: 0,
                        snippet: Some(format!("{{{{ ref('{}') }}}}", ref_name)),
                        suggestion: Some(format!(
                            "Replace with {{{{ ref('{}') }}}} if the short name is unambiguous.",
                            short_name
                        )),
                        doc_url: doc_url("REF004"),
                    });
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// REF005: Ambiguous short name — two models share the same short name
// ---------------------------------------------------------------------------

fn check_ref005(
    models: &[DiscoveredModel],
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    // Group models by short name (part after last dot, or entire name)
    let mut short_name_groups: HashMap<String, Vec<&DiscoveredModel>> = HashMap::new();

    for model in models {
        let short_name = if let Some(dot_pos) = model.name.rfind('.') {
            model.name[dot_pos + 1..].to_owned()
        } else {
            model.name.clone()
        };
        short_name_groups.entry(short_name).or_default().push(model);
    }

    for (short_name, group) in &short_name_groups {
        if group.len() > 1 {
            for model in group {
                if !config.is_rule_enabled_for_path("REF005", &model.file_path, true) {
                    continue;
                }

                let other_names: Vec<&str> = group
                    .iter()
                    .filter(|m| m.name != model.name)
                    .map(|m| m.name.as_str())
                    .collect();

                diags.push(CheckDiagnostic {
                    rule_id: "REF005".to_owned(),
                    message: format!(
                        "Ambiguous short name '{}': model '{}' shares this short name with: {}. \
                         Use fully-qualified names to disambiguate.",
                        short_name,
                        model.name,
                        other_names.join(", ")
                    ),
                    severity: config.effective_severity_for_path(
                        "REF005",
                        &model.file_path,
                        Severity::Warning,
                    ),
                    category: CheckCategory::RefResolution,
                    file_path: model.file_path.clone(),
                    line: 0,
                    column: 0,
                    snippet: None,
                    suggestion: Some(format!(
                        "Rename one of the models or use fully-qualified refs like {{{{ ref('{}') }}}}.",
                        model.name
                    )),
                    doc_url: doc_url("REF005"),
                });
            }
        }
    }
}

// ---------------------------------------------------------------------------
// REF006: Direct table reference instead of ref() (disabled by default)
// ---------------------------------------------------------------------------

fn check_ref006(
    file_path: &str,
    _content: &str,
    config: &CheckConfig,
    _diags: &mut Vec<CheckDiagnostic>,
) {
    // Disabled by default — detecting hardcoded table names without full AST
    // analysis would produce too many false positives. This rule is a placeholder
    // for Phase 3 when Python-side AST analysis is available.
    if !config.is_rule_enabled_for_path("REF006", file_path, false) {
        // Early exit: rule disabled
    }

    // REF006 implementation requires full AST analysis via Python's sql_toolkit
    // to distinguish between table references and column references. The Rust
    // lexer alone cannot reliably detect this pattern. When enabled, this rule
    // will be backed by the Python callback in Phase 3.
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::CheckConfig;
    use std::collections::HashMap;

    fn default_config() -> CheckConfig {
        CheckConfig::default()
    }

    fn make_model(name: &str, file_path: &str, content: &str, refs: &[&str]) -> DiscoveredModel {
        DiscoveredModel {
            name: name.to_owned(),
            file_path: file_path.to_owned(),
            content_hash: "sha256:test".to_owned(),
            ref_names: refs.iter().map(|r| (*r).to_owned()).collect(),
            header: HashMap::new(),
            content: content.to_owned(),
        }
    }

    // ── Levenshtein tests ──────────────────────────────────────────────────

    #[test]
    fn test_levenshtein_identical() {
        assert_eq!(levenshtein("hello", "hello"), 0);
    }

    #[test]
    fn test_levenshtein_one_edit() {
        assert_eq!(levenshtein("hello", "helo"), 1);
        assert_eq!(levenshtein("hello", "hellp"), 1);
        assert_eq!(levenshtein("hello", "helloo"), 1);
    }

    #[test]
    fn test_levenshtein_two_edits() {
        assert_eq!(levenshtein("hello", "help"), 2);
    }

    #[test]
    fn test_levenshtein_empty() {
        assert_eq!(levenshtein("", "hello"), 5);
        assert_eq!(levenshtein("hello", ""), 5);
        assert_eq!(levenshtein("", ""), 0);
    }

    #[test]
    fn test_levenshtein_completely_different() {
        assert_eq!(levenshtein("abc", "xyz"), 3);
    }

    // ── REF001 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_ref001_undefined_ref() {
        let models = vec![make_model(
            "stg_orders",
            "models/stg_orders.sql",
            "SELECT * FROM {{ ref('nonexistent') }}",
            &["nonexistent"],
        )];
        let checker = RefResolverChecker;
        let diags = checker.check_project(&models, &default_config());
        assert!(diags.iter().any(|d| d.rule_id == "REF001"));
    }

    #[test]
    fn test_ref001_valid_ref() {
        let models = vec![
            make_model("raw_orders", "models/raw_orders.sql", "SELECT 1", &[]),
            make_model(
                "stg_orders",
                "models/stg_orders.sql",
                "SELECT * FROM {{ ref('raw_orders') }}",
                &["raw_orders"],
            ),
        ];
        let checker = RefResolverChecker;
        let diags = checker.check_project(&models, &default_config());
        assert!(!diags.iter().any(|d| d.rule_id == "REF001"));
    }

    #[test]
    fn test_ref001_suggestion() {
        let models = vec![
            make_model("stg_orders", "models/stg_orders.sql", "SELECT 1", &[]),
            make_model(
                "fct_revenue",
                "models/fct_revenue.sql",
                "SELECT * FROM {{ ref('stg_orderz') }}",
                &["stg_orderz"],
            ),
        ];
        let checker = RefResolverChecker;
        let diags = checker.check_project(&models, &default_config());
        let ref001 = diags.iter().find(|d| d.rule_id == "REF001").unwrap();
        assert!(ref001.suggestion.as_ref().unwrap().contains("stg_orders"));
    }

    // ── REF002 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_ref002_circular_dependency() {
        let models = vec![
            make_model(
                "model_a",
                "models/model_a.sql",
                "SELECT * FROM {{ ref('model_b') }}",
                &["model_b"],
            ),
            make_model(
                "model_b",
                "models/model_b.sql",
                "SELECT * FROM {{ ref('model_a') }}",
                &["model_a"],
            ),
        ];
        let checker = RefResolverChecker;
        let diags = checker.check_project(&models, &default_config());
        assert!(diags.iter().any(|d| d.rule_id == "REF002"));
    }

    #[test]
    fn test_ref002_no_circular() {
        let models = vec![
            make_model("model_a", "models/model_a.sql", "SELECT 1", &[]),
            make_model(
                "model_b",
                "models/model_b.sql",
                "SELECT * FROM {{ ref('model_a') }}",
                &["model_a"],
            ),
        ];
        let checker = RefResolverChecker;
        let diags = checker.check_project(&models, &default_config());
        assert!(!diags.iter().any(|d| d.rule_id == "REF002"));
    }

    // ── REF003 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_ref003_self_reference() {
        let models = vec![make_model(
            "model_a",
            "models/model_a.sql",
            "SELECT * FROM {{ ref('model_a') }}",
            &["model_a"],
        )];
        let checker = RefResolverChecker;
        let diags = checker.check_project(&models, &default_config());
        assert!(diags.iter().any(|d| d.rule_id == "REF003"));
    }

    #[test]
    fn test_ref003_no_self_reference() {
        let models = vec![make_model(
            "model_a",
            "models/model_a.sql",
            "SELECT * FROM {{ ref('model_b') }}",
            &["model_b"],
        )];
        let checker = RefResolverChecker;
        let diags = checker.check_project(&models, &default_config());
        assert!(!diags.iter().any(|d| d.rule_id == "REF003"));
    }

    // ── REF004 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_ref004_fully_qualified_ref() {
        let checker = RefResolverChecker;
        let diags = checker.check_file(
            "test.sql",
            "SELECT * FROM {{ ref('schema.stg_orders') }}",
            None,
            &default_config(),
        );
        assert!(diags.iter().any(|d| d.rule_id == "REF004"));
    }

    #[test]
    fn test_ref004_short_name_ref() {
        let checker = RefResolverChecker;
        let diags = checker.check_file(
            "test.sql",
            "SELECT * FROM {{ ref('stg_orders') }}",
            None,
            &default_config(),
        );
        assert!(!diags.iter().any(|d| d.rule_id == "REF004"));
    }

    #[test]
    fn test_ref004_severity_is_info() {
        let checker = RefResolverChecker;
        let diags = checker.check_file(
            "test.sql",
            "SELECT * FROM {{ ref('s.t') }}",
            None,
            &default_config(),
        );
        let d = diags.iter().find(|d| d.rule_id == "REF004").unwrap();
        assert_eq!(d.severity, Severity::Info);
    }

    // ── REF005 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_ref005_ambiguous_short_name() {
        let models = vec![
            make_model("schema_a.orders", "models/a/orders.sql", "SELECT 1", &[]),
            make_model("schema_b.orders", "models/b/orders.sql", "SELECT 1", &[]),
        ];
        let checker = RefResolverChecker;
        let diags = checker.check_project(&models, &default_config());
        assert!(diags.iter().any(|d| d.rule_id == "REF005"));
    }

    #[test]
    fn test_ref005_unique_short_names() {
        let models = vec![
            make_model("stg_orders", "models/stg_orders.sql", "SELECT 1", &[]),
            make_model("stg_customers", "models/stg_customers.sql", "SELECT 1", &[]),
        ];
        let checker = RefResolverChecker;
        let diags = checker.check_project(&models, &default_config());
        assert!(!diags.iter().any(|d| d.rule_id == "REF005"));
    }

    // ── REF006 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_ref006_disabled_by_default() {
        let checker = RefResolverChecker;
        let diags = checker.check_file(
            "test.sql",
            "SELECT * FROM raw_orders",
            None,
            &default_config(),
        );
        assert!(!diags.iter().any(|d| d.rule_id == "REF006"));
    }

    // ── Non-SQL file test ──────────────────────────────────────────────────

    #[test]
    fn test_non_sql_file_ignored() {
        let checker = RefResolverChecker;
        let diags = checker.check_file("schema.yml", "ref content", None, &default_config());
        assert!(diags.is_empty());
    }

    // ── Config override test ───────────────────────────────────────────────

    #[test]
    fn test_rule_disabled_via_config() {
        let mut config = default_config();
        config.rules.insert(
            "REF004".to_owned(),
            crate::config::RuleSeverityOverride::Off,
        );
        let checker = RefResolverChecker;
        let diags = checker.check_file("test.sql", "SELECT * FROM {{ ref('s.t') }}", None, &config);
        assert!(!diags.iter().any(|d| d.rule_id == "REF004"));
    }

    // ── Empty models ───────────────────────────────────────────────────────

    #[test]
    fn test_empty_models_no_errors() {
        let checker = RefResolverChecker;
        let diags = checker.check_project(&[], &default_config());
        assert!(diags.is_empty());
    }
}
