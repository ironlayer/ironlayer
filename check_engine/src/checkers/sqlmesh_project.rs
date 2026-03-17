//! SQLMesh-specific project-level checks (checker name: `sqlmesh_project`).
//!
//! These checks only run when the project type is detected as `SQLMesh`.
//! They validate SQLMesh-specific conventions:
//!
//! ## Rule Summary
//!
//! | Rule    | Default  | Severity | Description                                                  |
//! |---------|----------|----------|--------------------------------------------------------------|
//! | SMQ-001 | enabled  | error    | Every `.sql` model file must contain a `MODEL()` DDL block   |
//! | SMQ-002 | enabled  | warning  | Incremental models must define `grain` or `unique_key`       |
//! | SMQ-003 | enabled  | warning  | `INCREMENTAL_BY_TIME_RANGE` models must use `@start_ds`/`@end_ds` |
//! | SMQ-004 | enabled  | warning  | Model names must follow `snake_case` convention              |

use crate::checkers::Checker;
use crate::config::CheckConfig;
use crate::types::{CheckCategory, CheckDiagnostic, DiscoveredModel, Severity};

/// Checker that enforces SQLMesh project conventions.
pub struct SQLMeshProjectChecker;

impl Checker for SQLMeshProjectChecker {
    fn name(&self) -> &'static str {
        "sqlmesh_project"
    }

    fn check_file(
        &self,
        file_path: &str,
        content: &str,
        model: Option<&DiscoveredModel>,
        config: &CheckConfig,
    ) -> Vec<CheckDiagnostic> {
        // Only check .sql files
        if !file_path.ends_with(".sql") {
            return Vec::new();
        }

        let mut diags: Vec<CheckDiagnostic> = Vec::new();

        // SMQ-001: MODEL() block presence
        if config.is_rule_enabled_for_path("SMQ-001", file_path, true)
            && !has_model_block(content)
        {
            let severity = config.effective_severity("SMQ-001", Severity::Error);
            diags.push(CheckDiagnostic {
                rule_id: "SMQ-001".to_owned(),
                message: "SQLMesh model missing `MODEL()` DDL block. Every SQLMesh model must \
                           begin with a `MODEL(name = ..., kind = ...)` block."
                    .to_owned(),
                severity,
                category: CheckCategory::SQLMeshProject,
                file_path: file_path.to_owned(),
                line: 1,
                column: 0,
                snippet: None,
                suggestion: Some(
                    "Add a `MODEL(name = catalog.schema.model_name, kind = FULL)` block \
                     at the top of the file."
                        .to_owned(),
                ),
                doc_url: Some(
                    "https://docs.ironlayer.app/check/rules/SMQ-001".to_owned(),
                ),
            });
            // Without MODEL() block further structural checks are meaningless.
            return diags;
        }

        // SMQ-002: incremental models must declare grain / unique_key
        let kind = extract_model_kind(content);
        let is_incremental = matches!(
            kind.as_deref(),
            Some("INCREMENTAL_BY_TIME_RANGE") | Some("INCREMENTAL_BY_UNIQUE_KEY")
        );

        if is_incremental
            && config.is_rule_enabled_for_path("SMQ-002", file_path, true)
            && !has_grain_or_unique_key(content)
        {
            let severity = config.effective_severity("SMQ-002", Severity::Warning);
            diags.push(CheckDiagnostic {
                rule_id: "SMQ-002".to_owned(),
                message: format!(
                    "Incremental model (kind = {}) is missing `grain` or `unique_key` \
                     declaration in the MODEL() block.",
                    kind.as_deref().unwrap_or("UNKNOWN")
                ),
                severity,
                category: CheckCategory::SQLMeshProject,
                file_path: file_path.to_owned(),
                line: 0,
                column: 0,
                snippet: None,
                suggestion: Some(
                    "Add `grain = (primary_key_column)` (for time-range) or \
                     `unique_key = [id_col]` (for unique-key) to the MODEL() block."
                        .to_owned(),
                ),
                doc_url: Some(
                    "https://docs.ironlayer.app/check/rules/SMQ-002".to_owned(),
                ),
            });
        }

        // SMQ-003: INCREMENTAL_BY_TIME_RANGE should use @start_ds / @end_ds macros
        if kind.as_deref() == Some("INCREMENTAL_BY_TIME_RANGE")
            && config.is_rule_enabled_for_path("SMQ-003", file_path, true)
            && !content.contains("@start_ds")
            && !content.contains("@end_ds")
        {
            let severity = config.effective_severity("SMQ-003", Severity::Warning);
            diags.push(CheckDiagnostic {
                rule_id: "SMQ-003".to_owned(),
                message: "INCREMENTAL_BY_TIME_RANGE model does not use `@start_ds` / `@end_ds` \
                           macros. Without them the filter clause is not dynamically bounded."
                    .to_owned(),
                severity,
                category: CheckCategory::SQLMeshProject,
                file_path: file_path.to_owned(),
                line: 0,
                column: 0,
                snippet: None,
                suggestion: Some(
                    "Add `WHERE ds BETWEEN @start_ds AND @end_ds` (or equivalent) to \
                     your incremental filter."
                        .to_owned(),
                ),
                doc_url: Some(
                    "https://docs.ironlayer.app/check/rules/SMQ-003".to_owned(),
                ),
            });
        }

        // SMQ-004: model name snake_case
        if let Some(mdl) = model {
            if config.is_rule_enabled_for_path("SMQ-004", file_path, true)
                && !is_snake_case(&mdl.name)
            {
                let severity = config.effective_severity("SMQ-004", Severity::Warning);
                let suggestion = format!("Rename to `{}`.", to_snake_case(&mdl.name));
                diags.push(CheckDiagnostic {
                    rule_id: "SMQ-004".to_owned(),
                    message: format!(
                        "Model name `{}` is not snake_case. SQLMesh convention requires \
                         lowercase snake_case model names.",
                        mdl.name
                    ),
                    severity,
                    category: CheckCategory::SQLMeshProject,
                    file_path: file_path.to_owned(),
                    line: 0,
                    column: 0,
                    snippet: None,
                    suggestion: Some(suggestion),
                    doc_url: Some(
                        "https://docs.ironlayer.app/check/rules/SMQ-004".to_owned(),
                    ),
                });
            }
        }

        diags
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Return `true` if the content contains a `MODEL(` block (case-insensitive).
fn has_model_block(content: &str) -> bool {
    content
        .lines()
        .any(|l| l.trim_start().to_uppercase().starts_with("MODEL("))
}

/// Extract the `kind = VALUE` from the MODEL() block, returning `Some(VALUE)`.
///
/// Handles both `kind = FULL` and `kind = INCREMENTAL_BY_TIME_RANGE(...)` forms.
fn extract_model_kind(content: &str) -> Option<String> {
    let upper = content.to_uppercase();
    let model_start = upper.find("MODEL(")?;
    let model_end = upper[model_start..].find(')')? + model_start;
    let block = &content[model_start..=model_end];

    for part in block.split(',') {
        let trimmed = part.trim();
        let upper_part = trimmed.to_uppercase();
        if let Some(rest) = upper_part.strip_prefix("KIND") {
            let rest = rest
                .trim_start_matches(|c: char| c == ' ' || c == '=')
                .trim();
            // Strip inline parens or quotes so `INCREMENTAL_BY_TIME_RANGE(...)` becomes
            // `INCREMENTAL_BY_TIME_RANGE`.
            let kind = rest
                .split(|c: char| c == '(' || c == ' ' || c == ')')
                .next()
                .unwrap_or(rest)
                .trim()
                .to_uppercase();
            if !kind.is_empty() {
                return Some(kind);
            }
        }
    }

    None
}

/// Return `true` if the MODEL() block contains a `grain` or `unique_key` declaration.
fn has_grain_or_unique_key(content: &str) -> bool {
    let upper = content.to_uppercase();
    if let Some(start) = upper.find("MODEL(") {
        if let Some(end_offset) = upper[start..].find(')') {
            let block = &upper[start..start + end_offset];
            return block.contains("GRAIN") || block.contains("UNIQUE_KEY");
        }
    }
    false
}

/// Return `true` if `s` is entirely lowercase snake_case (letters, digits, underscores).
fn is_snake_case(s: &str) -> bool {
    !s.is_empty()
        && s.chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

/// Best-effort conversion to snake_case for the suggestion message.
fn to_snake_case(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for (i, c) in s.chars().enumerate() {
        if c.is_uppercase() && i > 0 {
            out.push('_');
        }
        out.push(c.to_ascii_lowercase());
    }
    out.replace('-', "_")
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn dummy_config() -> CheckConfig {
        CheckConfig::default()
    }

    // ---- SMQ-001 -----------------------------------------------------------

    #[test]
    fn smq001_missing_model_block() {
        let checker = SQLMeshProjectChecker;
        let sql = "SELECT id FROM events";
        let diags = checker.check_file("models/events.sql", sql, None, &dummy_config());
        assert!(
            diags.iter().any(|d| d.rule_id == "SMQ-001"),
            "should fire SMQ-001 when MODEL() block is absent"
        );
    }

    #[test]
    fn smq001_present_model_block_passes() {
        let checker = SQLMeshProjectChecker;
        let sql = "MODEL(name = db.schema.events, kind = FULL)\nSELECT id FROM raw.events";
        let diags = checker.check_file("models/events.sql", sql, None, &dummy_config());
        assert!(
            diags.iter().all(|d| d.rule_id != "SMQ-001"),
            "should not fire SMQ-001 when MODEL() block is present"
        );
    }

    #[test]
    fn smq001_case_insensitive_model_keyword() {
        let checker = SQLMeshProjectChecker;
        let sql = "model(name = db.schema.events, kind = FULL)\nSELECT 1";
        let diags = checker.check_file("models/events.sql", sql, None, &dummy_config());
        assert!(
            diags.iter().all(|d| d.rule_id != "SMQ-001"),
            "MODEL() detection should be case-insensitive"
        );
    }

    // ---- SMQ-002 -----------------------------------------------------------

    #[test]
    fn smq002_incremental_missing_grain() {
        let checker = SQLMeshProjectChecker;
        let sql = "MODEL(name = db.s.orders, kind = INCREMENTAL_BY_TIME_RANGE)\n\
                   SELECT * FROM raw.orders WHERE ds BETWEEN @start_ds AND @end_ds";
        let diags = checker.check_file("models/orders.sql", sql, None, &dummy_config());
        assert!(
            diags.iter().any(|d| d.rule_id == "SMQ-002"),
            "should fire SMQ-002 when incremental model has no grain"
        );
    }

    #[test]
    fn smq002_incremental_with_grain_passes() {
        let checker = SQLMeshProjectChecker;
        let sql = "MODEL(name = db.s.orders, kind = INCREMENTAL_BY_TIME_RANGE, grain = (id))\n\
                   SELECT * FROM raw.orders WHERE ds BETWEEN @start_ds AND @end_ds";
        let diags = checker.check_file("models/orders.sql", sql, None, &dummy_config());
        assert!(
            diags.iter().all(|d| d.rule_id != "SMQ-002"),
            "should not fire SMQ-002 when grain is declared"
        );
    }

    #[test]
    fn smq002_full_refresh_skipped() {
        let checker = SQLMeshProjectChecker;
        let sql = "MODEL(name = db.s.orders, kind = FULL)\nSELECT * FROM raw.orders";
        let diags = checker.check_file("models/orders.sql", sql, None, &dummy_config());
        assert!(
            diags.iter().all(|d| d.rule_id != "SMQ-002"),
            "SMQ-002 should not fire for FULL refresh models"
        );
    }

    // ---- SMQ-003 -----------------------------------------------------------

    #[test]
    fn smq003_missing_date_macros() {
        let checker = SQLMeshProjectChecker;
        let sql =
            "MODEL(name = db.s.orders, kind = INCREMENTAL_BY_TIME_RANGE, grain = (id))\n\
             SELECT * FROM raw.orders";
        let diags = checker.check_file("models/orders.sql", sql, None, &dummy_config());
        assert!(
            diags.iter().any(|d| d.rule_id == "SMQ-003"),
            "should fire SMQ-003 when @start_ds/@end_ds absent in time-range model"
        );
    }

    #[test]
    fn smq003_with_date_macros_passes() {
        let checker = SQLMeshProjectChecker;
        let sql =
            "MODEL(name = db.s.orders, kind = INCREMENTAL_BY_TIME_RANGE, grain = (id))\n\
             SELECT * FROM raw.orders WHERE ds BETWEEN @start_ds AND @end_ds";
        let diags = checker.check_file("models/orders.sql", sql, None, &dummy_config());
        assert!(
            diags.iter().all(|d| d.rule_id != "SMQ-003"),
            "should not fire SMQ-003 when @start_ds/@end_ds are present"
        );
    }

    // ---- SMQ-004 -----------------------------------------------------------

    #[test]
    fn smq004_model_name_not_snake_case() {
        let checker = SQLMeshProjectChecker;
        let sql = "MODEL(name = db.s.MyOrders, kind = FULL)\nSELECT * FROM raw.orders";
        let model = DiscoveredModel {
            name: "MyOrders".to_owned(),
            file_path: "models/MyOrders.sql".to_owned(),
            content_hash: String::new(),
            ref_names: vec![],
            header: std::collections::HashMap::new(),
            content: sql.to_owned(),
        };
        let diags =
            checker.check_file("models/MyOrders.sql", sql, Some(&model), &dummy_config());
        assert!(
            diags.iter().any(|d| d.rule_id == "SMQ-004"),
            "should fire SMQ-004 when model name is not snake_case"
        );
    }

    #[test]
    fn smq004_snake_case_passes() {
        let checker = SQLMeshProjectChecker;
        let sql = "MODEL(name = db.s.my_orders, kind = FULL)\nSELECT * FROM raw.orders";
        let model = DiscoveredModel {
            name: "my_orders".to_owned(),
            file_path: "models/my_orders.sql".to_owned(),
            content_hash: String::new(),
            ref_names: vec![],
            header: std::collections::HashMap::new(),
            content: sql.to_owned(),
        };
        let diags =
            checker.check_file("models/my_orders.sql", sql, Some(&model), &dummy_config());
        assert!(
            diags.iter().all(|d| d.rule_id != "SMQ-004"),
            "should not fire SMQ-004 for snake_case model names"
        );
    }

    // ---- Non-.sql files skipped --------------------------------------------

    #[test]
    fn skips_non_sql_files() {
        let checker = SQLMeshProjectChecker;
        let diags = checker.check_file(
            "config.yaml",
            "model_defaults:\n  dialect: spark",
            None,
            &dummy_config(),
        );
        assert!(diags.is_empty(), "should skip non-.sql files");
    }

    // ---- Helper unit tests -------------------------------------------------

    #[test]
    fn has_model_block_case_insensitive() {
        assert!(has_model_block("model(\nname = x\n)"));
        assert!(has_model_block("MODEL(name = x)"));
        assert!(!has_model_block("SELECT * FROM t"));
    }

    #[test]
    fn extract_model_kind_full() {
        let sql = "MODEL(name = a.b.c, kind = FULL)\nSELECT 1";
        assert_eq!(extract_model_kind(sql).as_deref(), Some("FULL"));
    }

    #[test]
    fn extract_model_kind_incremental() {
        let sql = "MODEL(name = a.b.c, kind = INCREMENTAL_BY_TIME_RANGE)\nSELECT 1";
        assert_eq!(
            extract_model_kind(sql).as_deref(),
            Some("INCREMENTAL_BY_TIME_RANGE")
        );
    }

    #[test]
    fn snake_case_check() {
        assert!(is_snake_case("my_model_v2"));
        assert!(!is_snake_case("MyModel"));
        assert!(!is_snake_case("my-model"));
        assert!(!is_snake_case(""));
    }

    #[test]
    fn to_snake_case_conversion() {
        assert_eq!(to_snake_case("MyModel"), "my_model");
        assert_eq!(to_snake_case("my-model"), "my_model");
        assert_eq!(to_snake_case("mymodel"), "mymodel");
    }
}
