//! Naming convention checker — rules NAME001 through NAME008.
//!
//! Validates model naming conventions using configurable regex patterns.
//! Layer detection (staging, intermediate, marts) is inferred from the
//! file path directory structure.
//!
//! All patterns are configurable via `ironlayer.check.toml` or
//! `[tool.ironlayer.check]` in `pyproject.toml`.

use std::path::Path;

use regex::Regex;

use crate::checkers::Checker;
use crate::config::CheckConfig;
use crate::types::{CheckCategory, CheckDiagnostic, DiscoveredModel, Severity};

/// Naming convention checker implementing NAME001-NAME008.
pub struct NamingChecker;

/// Generate the doc URL for a given rule ID.
fn doc_url(rule_id: &str) -> Option<String> {
    Some(format!("https://docs.ironlayer.app/check/rules/{rule_id}"))
}

impl Checker for NamingChecker {
    fn name(&self) -> &'static str {
        "naming"
    }

    fn check_file(
        &self,
        file_path: &str,
        _content: &str,
        model: Option<&DiscoveredModel>,
        config: &CheckConfig,
    ) -> Vec<CheckDiagnostic> {
        if !file_path.ends_with(".sql") {
            return Vec::new();
        }

        let model_name = if let Some(m) = model {
            &m.name
        } else {
            // Derive model name from filename
            return Vec::new();
        };

        let mut diags = Vec::new();

        let layer = detect_layer(file_path);

        // NAME001: Staging models must start with stg_ or staging_
        check_name001(file_path, model_name, &layer, config, &mut diags);

        // NAME002: Intermediate models must start with int_ or intermediate_
        check_name002(file_path, model_name, &layer, config, &mut diags);

        // NAME003: Fact models must start with fct_ or fact_
        check_name003(file_path, model_name, &layer, config, &mut diags);

        // NAME004: Dimension models must start with dim_ or dimension_
        check_name004(file_path, model_name, &layer, config, &mut diags);

        // NAME005: Model names must be lowercase snake_case
        check_name005(file_path, model_name, config, &mut diags);

        // NAME006: Model file location must match its layer prefix
        check_name006(file_path, model_name, &layer, config, &mut diags);

        // NAME007: Column names must be lowercase snake_case (disabled by default)
        check_name007(file_path, config, &mut diags);

        // NAME008: Model name should not include file extension (disabled by default)
        check_name008(file_path, model_name, config, &mut diags);

        diags
    }
}

/// Detected layer from file path directory structure.
#[derive(Debug, Clone, PartialEq, Eq)]
enum Layer {
    Staging,
    Intermediate,
    Marts,
    Other,
}

/// Detect the model's layer from its file path directory structure.
///
/// - Files in `staging/`, `stg/` → Staging
/// - Files in `intermediate/`, `int/` → Intermediate
/// - Files in `marts/`, `mart/` → Marts
/// - Files in any other directory → Other
fn detect_layer(file_path: &str) -> Layer {
    let path = Path::new(file_path);

    for component in path.components() {
        if let std::path::Component::Normal(name) = component {
            let name_str = name.to_string_lossy().to_lowercase();
            match name_str.as_str() {
                "staging" | "stg" => return Layer::Staging,
                "intermediate" | "int" => return Layer::Intermediate,
                "marts" | "mart" => return Layer::Marts,
                _ => {}
            }
        }
    }

    Layer::Other
}

// ---------------------------------------------------------------------------
// NAME001: Staging models must start with stg_ or staging_
// ---------------------------------------------------------------------------

fn check_name001(
    file_path: &str,
    model_name: &str,
    layer: &Layer,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("NAME001", file_path, true) {
        return;
    }

    if *layer != Layer::Staging {
        return;
    }

    let pattern = config
        .naming
        .layers
        .get("staging")
        .or_else(|| config.naming.layers.get("stg"))
        .map(|s| s.as_str())
        .unwrap_or("^(stg|staging)_");

    if let Ok(re) = Regex::new(pattern) {
        if !re.is_match(model_name) {
            diags.push(CheckDiagnostic {
                rule_id: "NAME001".to_owned(),
                message: format!(
                    "Staging model '{}' does not match naming pattern '{}'. \
                     Staging models should start with 'stg_' or 'staging_'.",
                    model_name, pattern
                ),
                severity: config.effective_severity_for_path(
                    "NAME001",
                    file_path,
                    Severity::Warning,
                ),
                category: CheckCategory::NamingConvention,
                file_path: file_path.to_owned(),
                line: 1,
                column: 0,
                snippet: Some(format!("-- name: {}", model_name)),
                suggestion: Some(format!(
                    "Rename to 'stg_{}' or move to a non-staging directory.",
                    model_name
                )),
                doc_url: doc_url("NAME001"),
            });
        }
    }
}

// ---------------------------------------------------------------------------
// NAME002: Intermediate models must start with int_ or intermediate_
// ---------------------------------------------------------------------------

fn check_name002(
    file_path: &str,
    model_name: &str,
    layer: &Layer,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("NAME002", file_path, true) {
        return;
    }

    if *layer != Layer::Intermediate {
        return;
    }

    let pattern = config
        .naming
        .layers
        .get("intermediate")
        .or_else(|| config.naming.layers.get("int"))
        .map(|s| s.as_str())
        .unwrap_or("^(int|intermediate)_");

    if let Ok(re) = Regex::new(pattern) {
        if !re.is_match(model_name) {
            diags.push(CheckDiagnostic {
                rule_id: "NAME002".to_owned(),
                message: format!(
                    "Intermediate model '{}' does not match naming pattern '{}'. \
                     Intermediate models should start with 'int_' or 'intermediate_'.",
                    model_name, pattern
                ),
                severity: config.effective_severity_for_path(
                    "NAME002",
                    file_path,
                    Severity::Warning,
                ),
                category: CheckCategory::NamingConvention,
                file_path: file_path.to_owned(),
                line: 1,
                column: 0,
                snippet: Some(format!("-- name: {}", model_name)),
                suggestion: Some(format!(
                    "Rename to 'int_{}' or move to a non-intermediate directory.",
                    model_name
                )),
                doc_url: doc_url("NAME002"),
            });
        }
    }
}

// ---------------------------------------------------------------------------
// NAME003: Fact models must start with fct_ or fact_
// ---------------------------------------------------------------------------

fn check_name003(
    file_path: &str,
    model_name: &str,
    layer: &Layer,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("NAME003", file_path, true) {
        return;
    }

    if *layer != Layer::Marts {
        return;
    }

    // NAME003 only applies to fact models in marts — check if name has fct/fact/dim/dimension prefix
    // If it has dim/dimension prefix, skip (that's NAME004's domain)
    let has_dim_prefix = model_name.starts_with("dim_") || model_name.starts_with("dimension_");
    if has_dim_prefix {
        return;
    }

    let pattern = config
        .naming
        .layers
        .get("marts")
        .or_else(|| config.naming.layers.get("mart"))
        .map(|s| s.as_str())
        .unwrap_or("^(fct|fact|dim|dimension)_");

    if let Ok(re) = Regex::new(pattern) {
        if !re.is_match(model_name) {
            diags.push(CheckDiagnostic {
                rule_id: "NAME003".to_owned(),
                message: format!(
                    "Mart model '{}' does not match naming pattern '{}'. \
                     Fact models should start with 'fct_' or 'fact_', \
                     dimension models with 'dim_' or 'dimension_'.",
                    model_name, pattern
                ),
                severity: config.effective_severity_for_path(
                    "NAME003",
                    file_path,
                    Severity::Warning,
                ),
                category: CheckCategory::NamingConvention,
                file_path: file_path.to_owned(),
                line: 1,
                column: 0,
                snippet: Some(format!("-- name: {}", model_name)),
                suggestion: Some(format!(
                    "Rename to 'fct_{}' or 'dim_{}' depending on model type.",
                    model_name, model_name
                )),
                doc_url: doc_url("NAME003"),
            });
        }
    }
}

// ---------------------------------------------------------------------------
// NAME004: Dimension models must start with dim_ or dimension_
// ---------------------------------------------------------------------------

fn check_name004(
    file_path: &str,
    model_name: &str,
    layer: &Layer,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("NAME004", file_path, true) {
        return;
    }

    if *layer != Layer::Marts {
        return;
    }

    // NAME004 only applies to dim models in marts — check if name has dim/dimension prefix
    // This rule only fires if the model name starts with dim/dimension but doesn't match the pattern
    // If the name doesn't have a dim prefix at all, NAME003 handles it
    let has_dim_prefix = model_name.starts_with("dim_") || model_name.starts_with("dimension_");
    if !has_dim_prefix {
        return;
    }

    // dim_ models always pass this check since they already have the prefix
    // This check is for edge cases where the pattern requires more specific naming
    let pattern = "^(dim|dimension)_";

    if let Ok(re) = Regex::new(pattern) {
        if !re.is_match(model_name) {
            diags.push(CheckDiagnostic {
                rule_id: "NAME004".to_owned(),
                message: format!(
                    "Dimension model '{}' does not match naming pattern '{}'. \
                     Dimension models should start with 'dim_' or 'dimension_'.",
                    model_name, pattern
                ),
                severity: config.effective_severity_for_path(
                    "NAME004",
                    file_path,
                    Severity::Warning,
                ),
                category: CheckCategory::NamingConvention,
                file_path: file_path.to_owned(),
                line: 1,
                column: 0,
                snippet: Some(format!("-- name: {}", model_name)),
                suggestion: Some(format!("Rename to 'dim_{}'.", model_name)),
                doc_url: doc_url("NAME004"),
            });
        }
    }
}

// ---------------------------------------------------------------------------
// NAME005: Model names must be lowercase snake_case
// ---------------------------------------------------------------------------

fn check_name005(
    file_path: &str,
    model_name: &str,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("NAME005", file_path, true) {
        return;
    }

    let pattern = &config.naming.model_pattern;

    if let Ok(re) = Regex::new(pattern) {
        if !re.is_match(model_name) {
            diags.push(CheckDiagnostic {
                rule_id: "NAME005".to_owned(),
                message: format!(
                    "Model name '{}' does not match pattern '{}'. \
                     Model names must be lowercase snake_case.",
                    model_name, pattern
                ),
                severity: config.effective_severity_for_path(
                    "NAME005",
                    file_path,
                    Severity::Warning,
                ),
                category: CheckCategory::NamingConvention,
                file_path: file_path.to_owned(),
                line: 1,
                column: 0,
                snippet: Some(format!("-- name: {}", model_name)),
                suggestion: Some(format!(
                    "Rename to '{}'.",
                    model_name.to_lowercase().replace(['-', ' '], "_")
                )),
                doc_url: doc_url("NAME005"),
            });
        }
    }
}

// ---------------------------------------------------------------------------
// NAME006: Model file location must match its layer prefix
// ---------------------------------------------------------------------------

fn check_name006(
    file_path: &str,
    model_name: &str,
    layer: &Layer,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("NAME006", file_path, true) {
        return;
    }

    // Only check when we can detect a layer from the name prefix
    let name_layer = if model_name.starts_with("stg_") || model_name.starts_with("staging_") {
        Some(Layer::Staging)
    } else if model_name.starts_with("int_") || model_name.starts_with("intermediate_") {
        Some(Layer::Intermediate)
    } else if model_name.starts_with("fct_")
        || model_name.starts_with("fact_")
        || model_name.starts_with("dim_")
        || model_name.starts_with("dimension_")
    {
        Some(Layer::Marts)
    } else {
        None
    };

    if let Some(expected_layer) = name_layer {
        if *layer != Layer::Other && *layer != expected_layer {
            let expected_dir = match expected_layer {
                Layer::Staging => "staging/ or stg/",
                Layer::Intermediate => "intermediate/ or int/",
                Layer::Marts => "marts/ or mart/",
                Layer::Other => "other",
            };
            let actual_dir = match layer {
                Layer::Staging => "staging",
                Layer::Intermediate => "intermediate",
                Layer::Marts => "marts",
                Layer::Other => "other",
            };

            diags.push(CheckDiagnostic {
                rule_id: "NAME006".to_owned(),
                message: format!(
                    "Model '{}' has a '{}' layer prefix but is located in the '{}' directory. \
                     Move it to {}.",
                    model_name,
                    model_name.split('_').next().unwrap_or(""),
                    actual_dir,
                    expected_dir
                ),
                severity: config.effective_severity_for_path(
                    "NAME006",
                    file_path,
                    Severity::Warning,
                ),
                category: CheckCategory::NamingConvention,
                file_path: file_path.to_owned(),
                line: 0,
                column: 0,
                snippet: None,
                suggestion: Some(format!("Move this file to the {} directory.", expected_dir)),
                doc_url: doc_url("NAME006"),
            });
        }
    }
}

// ---------------------------------------------------------------------------
// NAME007: Column names must be lowercase snake_case (disabled by default)
// ---------------------------------------------------------------------------

fn check_name007(file_path: &str, config: &CheckConfig, _diags: &mut Vec<CheckDiagnostic>) {
    // Disabled by default — detecting column names requires full AST analysis
    // via Python's sql_toolkit.scope_analyzer.extract_columns(). This will be
    // implemented in Phase 3 via the YML006 Python callback pattern.
    if !config.is_rule_enabled_for_path("NAME007", file_path, false) {
        // Rule disabled: no column analysis available in Phase 2
    }
}

// ---------------------------------------------------------------------------
// NAME008: Model name should not include file extension (disabled by default)
// ---------------------------------------------------------------------------

fn check_name008(
    file_path: &str,
    model_name: &str,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    // Disabled by default
    if !config.is_rule_enabled_for_path("NAME008", file_path, false) {
        return;
    }

    if model_name.ends_with(".sql") || model_name.ends_with(".SQL") {
        diags.push(CheckDiagnostic {
            rule_id: "NAME008".to_owned(),
            message: format!(
                "Model name '{}' includes the file extension. \
                 The '-- name:' field should contain just the model name without the extension.",
                model_name
            ),
            severity: config.effective_severity_for_path("NAME008", file_path, Severity::Info),
            category: CheckCategory::NamingConvention,
            file_path: file_path.to_owned(),
            line: 1,
            column: 0,
            snippet: Some(format!("-- name: {}", model_name)),
            suggestion: Some(format!(
                "Change to '-- name: {}'.",
                model_name.trim_end_matches(".sql").trim_end_matches(".SQL")
            )),
            doc_url: doc_url("NAME008"),
        });
    }
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

    fn make_model(name: &str, file_path: &str) -> DiscoveredModel {
        DiscoveredModel {
            name: name.to_owned(),
            file_path: file_path.to_owned(),
            content_hash: "sha256:test".to_owned(),
            ref_names: Vec::new(),
            header: HashMap::new(),
            content: format!("-- name: {}\n-- kind: FULL_REFRESH\nSELECT 1", name),
        }
    }

    fn check_with_model(name: &str, file_path: &str) -> Vec<CheckDiagnostic> {
        let model = make_model(name, file_path);
        let checker = NamingChecker;
        checker.check_file(file_path, &model.content, Some(&model), &default_config())
    }

    // ── Layer detection tests ──────────────────────────────────────────────

    #[test]
    fn test_detect_staging_layer() {
        assert_eq!(
            detect_layer("models/staging/stg_orders.sql"),
            Layer::Staging
        );
        assert_eq!(detect_layer("models/stg/stg_orders.sql"), Layer::Staging);
    }

    #[test]
    fn test_detect_intermediate_layer() {
        assert_eq!(
            detect_layer("models/intermediate/int_orders.sql"),
            Layer::Intermediate
        );
        assert_eq!(
            detect_layer("models/int/int_orders.sql"),
            Layer::Intermediate
        );
    }

    #[test]
    fn test_detect_marts_layer() {
        assert_eq!(detect_layer("models/marts/fct_orders.sql"), Layer::Marts);
        assert_eq!(detect_layer("models/mart/fct_orders.sql"), Layer::Marts);
    }

    #[test]
    fn test_detect_other_layer() {
        assert_eq!(detect_layer("models/other/orders.sql"), Layer::Other);
        assert_eq!(detect_layer("orders.sql"), Layer::Other);
    }

    // ── NAME001 tests ──────────────────────────────────────────────────────

    #[test]
    fn test_name001_staging_wrong_prefix() {
        let diags = check_with_model("orders", "models/staging/orders.sql");
        assert!(diags.iter().any(|d| d.rule_id == "NAME001"));
    }

    #[test]
    fn test_name001_staging_correct_prefix() {
        let diags = check_with_model("stg_orders", "models/staging/stg_orders.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME001"));
    }

    #[test]
    fn test_name001_staging_alt_prefix() {
        let diags = check_with_model("staging_orders", "models/staging/staging_orders.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME001"));
    }

    #[test]
    fn test_name001_non_staging_no_fire() {
        let diags = check_with_model("orders", "models/marts/orders.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME001"));
    }

    #[test]
    fn test_name001_severity_is_warning() {
        let diags = check_with_model("orders", "models/staging/orders.sql");
        let d = diags.iter().find(|d| d.rule_id == "NAME001").unwrap();
        assert_eq!(d.severity, Severity::Warning);
    }

    // ── NAME002 tests ──────────────────────────────────────────────────────

    #[test]
    fn test_name002_intermediate_wrong_prefix() {
        let diags = check_with_model("orders", "models/intermediate/orders.sql");
        assert!(diags.iter().any(|d| d.rule_id == "NAME002"));
    }

    #[test]
    fn test_name002_intermediate_correct_prefix() {
        let diags = check_with_model("int_orders", "models/intermediate/int_orders.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME002"));
    }

    #[test]
    fn test_name002_non_intermediate_no_fire() {
        let diags = check_with_model("orders", "models/staging/orders.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME002"));
    }

    // ── NAME003 tests ──────────────────────────────────────────────────────

    #[test]
    fn test_name003_marts_wrong_prefix() {
        let diags = check_with_model("orders", "models/marts/orders.sql");
        assert!(diags.iter().any(|d| d.rule_id == "NAME003"));
    }

    #[test]
    fn test_name003_marts_fct_prefix() {
        let diags = check_with_model("fct_orders", "models/marts/fct_orders.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME003"));
    }

    #[test]
    fn test_name003_marts_dim_prefix_no_fire() {
        let diags = check_with_model("dim_customers", "models/marts/dim_customers.sql");
        // NAME003 should not fire for dim_ models (NAME004 handles them)
        assert!(!diags.iter().any(|d| d.rule_id == "NAME003"));
    }

    // ── NAME004 tests ──────────────────────────────────────────────────────

    #[test]
    fn test_name004_dim_correct_prefix() {
        let diags = check_with_model("dim_customers", "models/marts/dim_customers.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME004"));
    }

    #[test]
    fn test_name004_non_marts_no_fire() {
        let diags = check_with_model("dim_customers", "models/staging/dim_customers.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME004"));
    }

    // ── NAME005 tests ──────────────────────────────────────────────────────

    #[test]
    fn test_name005_snake_case() {
        let diags = check_with_model("stg_orders", "models/stg_orders.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME005"));
    }

    #[test]
    fn test_name005_uppercase() {
        let diags = check_with_model("STG_ORDERS", "models/STG_ORDERS.sql");
        assert!(diags.iter().any(|d| d.rule_id == "NAME005"));
    }

    #[test]
    fn test_name005_camel_case() {
        let diags = check_with_model("StgOrders", "models/StgOrders.sql");
        assert!(diags.iter().any(|d| d.rule_id == "NAME005"));
    }

    #[test]
    fn test_name005_with_numbers() {
        let diags = check_with_model("stg_orders_v2", "models/stg_orders_v2.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME005"));
    }

    // ── NAME006 tests ──────────────────────────────────────────────────────

    #[test]
    fn test_name006_stg_in_staging() {
        let diags = check_with_model("stg_orders", "models/staging/stg_orders.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME006"));
    }

    #[test]
    fn test_name006_stg_in_marts() {
        let diags = check_with_model("stg_orders", "models/marts/stg_orders.sql");
        assert!(diags.iter().any(|d| d.rule_id == "NAME006"));
    }

    #[test]
    fn test_name006_no_layer_prefix() {
        let diags = check_with_model("orders", "models/staging/orders.sql");
        // No layer prefix detected from name → NAME006 should not fire
        assert!(!diags.iter().any(|d| d.rule_id == "NAME006"));
    }

    // ── NAME008 tests ──────────────────────────────────────────────────────

    #[test]
    fn test_name008_disabled_by_default() {
        let diags = check_with_model("stg_orders.sql", "models/stg_orders.sql");
        assert!(!diags.iter().any(|d| d.rule_id == "NAME008"));
    }

    #[test]
    fn test_name008_enabled_detects_extension() {
        let model = make_model("stg_orders.sql", "models/stg_orders.sql");
        let mut config = default_config();
        config.rules.insert(
            "NAME008".to_owned(),
            crate::config::RuleSeverityOverride::Info,
        );
        let checker = NamingChecker;
        let diags = checker.check_file(
            "models/stg_orders.sql",
            &model.content,
            Some(&model),
            &config,
        );
        assert!(diags.iter().any(|d| d.rule_id == "NAME008"));
    }

    // ── Non-SQL file test ──────────────────────────────────────────────────

    #[test]
    fn test_non_sql_file_ignored() {
        let checker = NamingChecker;
        let diags = checker.check_file("schema.yml", "", None, &default_config());
        assert!(diags.is_empty());
    }

    // ── Config override test ───────────────────────────────────────────────

    #[test]
    fn test_custom_naming_pattern() {
        let model = make_model("ORDERS", "models/ORDERS.sql");
        let mut config = default_config();
        config.naming.model_pattern = "^[A-Z][A-Z0-9_]*$".to_owned();
        let checker = NamingChecker;
        let diags = checker.check_file("models/ORDERS.sql", &model.content, Some(&model), &config);
        assert!(!diags.iter().any(|d| d.rule_id == "NAME005"));
    }
}
