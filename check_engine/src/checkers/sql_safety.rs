//! SQL safety pre-screening checker — rules SAF001 through SAF010.
//!
//! Mirrors `sql_guard.py`'s `DangerousOperation` enum with keyword-sequence
//! detection on the SQL lexer's token stream. These are fast pre-filters:
//! false positives are acceptable since the full AST check runs at plan time.
//!
//! Safety rules only fire on SQL outside of string literals and comments —
//! the lexer's tokenization ensures this.

use crate::checkers::Checker;
use crate::config::CheckConfig;
use crate::sql_lexer::{self, Token, TokenKind};
use crate::types::{CheckCategory, CheckDiagnostic, DiscoveredModel, Severity};

/// SQL safety checker implementing SAF001-SAF010.
pub struct SqlSafetyChecker;

/// Generate the doc URL for a given rule ID.
fn doc_url(rule_id: &str) -> Option<String> {
    Some(format!("https://docs.ironlayer.app/check/rules/{rule_id}"))
}

impl Checker for SqlSafetyChecker {
    fn name(&self) -> &'static str {
        "sql_safety"
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

        let body = sql_lexer::strip_header(content);
        let tokens = sql_lexer::tokenize(body);
        let meaningful = sql_lexer::meaningful_tokens(&tokens);

        // Compute header line offset for correct line reporting
        let header_lines = content
            .lines()
            .take_while(|line| {
                let trimmed = line.trim();
                trimmed.is_empty() || trimmed.starts_with("--")
            })
            .count() as u32;

        let mut diags = Vec::new();

        check_saf001(file_path, &meaningful, header_lines, config, &mut diags);
        check_saf002(file_path, &meaningful, header_lines, config, &mut diags);
        check_saf003(file_path, &meaningful, header_lines, config, &mut diags);
        check_saf004(file_path, &meaningful, header_lines, config, &mut diags);
        check_saf005(file_path, &meaningful, header_lines, config, &mut diags);
        check_saf006(file_path, &meaningful, header_lines, config, &mut diags);
        check_saf007(file_path, &meaningful, header_lines, config, &mut diags);
        check_saf008(file_path, &meaningful, header_lines, config, &mut diags);
        check_saf009(file_path, &meaningful, header_lines, config, &mut diags);
        check_saf010(file_path, &meaningful, header_lines, config, &mut diags);

        diags
    }
}

/// Helper: check if a token is a keyword matching the given word (case-insensitive).
fn is_kw(tok: &Token<'_>, word: &str) -> bool {
    tok.kind == TokenKind::Keyword && tok.text.eq_ignore_ascii_case(word)
}

/// Helper: check if a token is a keyword or identifier matching the given word.
fn is_kw_or_ident(tok: &Token<'_>, word: &str) -> bool {
    (tok.kind == TokenKind::Keyword || tok.kind == TokenKind::Identifier)
        && tok.text.eq_ignore_ascii_case(word)
}

// ---------------------------------------------------------------------------
// SAF001: DROP TABLE keyword sequence detected
// ---------------------------------------------------------------------------

fn check_saf001(
    file_path: &str,
    meaningful: &[&Token<'_>],
    header_lines: u32,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SAF001", file_path, true) {
        return;
    }

    let mut i = 0;
    while i < meaningful.len() {
        if is_kw(meaningful[i], "DROP") {
            // Look ahead: optional IF EXISTS, then TABLE
            let mut j = i + 1;
            if j < meaningful.len() && is_kw(meaningful[j], "IF") {
                j += 1;
                if j < meaningful.len() && is_kw(meaningful[j], "EXISTS") {
                    j += 1;
                }
            }
            if j < meaningful.len() && is_kw(meaningful[j], "TABLE") {
                let line = header_lines + meaningful[i].line;
                let name_text = meaningful.get(j + 1).map_or("...", |t| t.text);
                let snippet = if j == i + 1 {
                    format!("DROP TABLE {}", name_text)
                } else {
                    // Reconstruct e.g. "DROP IF EXISTS TABLE my_table"
                    let middle: Vec<&str> =
                        meaningful[i..=j].iter().map(|t| t.text).collect();
                    format!("{} {}", middle.join(" "), name_text)
                };
                diags.push(CheckDiagnostic {
                    rule_id: "SAF001".to_owned(),
                    message: format!(
                        "DROP TABLE detected at line {}. \
                         This is a destructive operation that permanently removes a table.",
                        line
                    ),
                    severity: config.effective_severity_for_path(
                        "SAF001",
                        file_path,
                        Severity::Error,
                    ),
                    category: CheckCategory::SqlSafety,
                    file_path: file_path.to_owned(),
                    line,
                    column: meaningful[i].column,
                    snippet: Some(snippet),
                    suggestion: Some(
                        "Remove the DROP TABLE statement or use --force-unsafe if intentional."
                            .to_owned(),
                    ),
                    doc_url: doc_url("SAF001"),
                });
                i = j + 1;
                continue;
            }
        }
        i += 1;
    }
}

// ---------------------------------------------------------------------------
// SAF002: DROP VIEW keyword sequence detected
// ---------------------------------------------------------------------------

fn check_saf002(
    file_path: &str,
    meaningful: &[&Token<'_>],
    header_lines: u32,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SAF002", file_path, true) {
        return;
    }

    let mut i = 0;
    while i < meaningful.len() {
        if is_kw(meaningful[i], "DROP") {
            // Look ahead: optional IF EXISTS, then VIEW
            let mut j = i + 1;
            if j < meaningful.len() && is_kw(meaningful[j], "IF") {
                j += 1;
                if j < meaningful.len() && is_kw(meaningful[j], "EXISTS") {
                    j += 1;
                }
            }
            if j < meaningful.len() && is_kw(meaningful[j], "VIEW") {
                let line = header_lines + meaningful[i].line;
                let name_text = meaningful.get(j + 1).map_or("...", |t| t.text);
                let snippet = if j == i + 1 {
                    format!("DROP VIEW {}", name_text)
                } else {
                    let middle: Vec<&str> =
                        meaningful[i..=j].iter().map(|t| t.text).collect();
                    format!("{} {}", middle.join(" "), name_text)
                };
                diags.push(CheckDiagnostic {
                    rule_id: "SAF002".to_owned(),
                    message: format!(
                        "DROP VIEW detected at line {}. \
                         This is a destructive operation that permanently removes a view.",
                        line
                    ),
                    severity: config.effective_severity_for_path(
                        "SAF002",
                        file_path,
                        Severity::Error,
                    ),
                    category: CheckCategory::SqlSafety,
                    file_path: file_path.to_owned(),
                    line,
                    column: meaningful[i].column,
                    snippet: Some(snippet),
                    suggestion: Some(
                        "Remove the DROP VIEW statement or use --force-unsafe if intentional."
                            .to_owned(),
                    ),
                    doc_url: doc_url("SAF002"),
                });
                i = j + 1;
                continue;
            }
        }
        i += 1;
    }
}

// ---------------------------------------------------------------------------
// SAF003: DROP SCHEMA / DROP DATABASE keyword sequence detected
// ---------------------------------------------------------------------------

fn check_saf003(
    file_path: &str,
    meaningful: &[&Token<'_>],
    header_lines: u32,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SAF003", file_path, true) {
        return;
    }

    let mut i = 0;
    while i < meaningful.len() {
        if is_kw(meaningful[i], "DROP") {
            // Look ahead: optional IF EXISTS, then SCHEMA or DATABASE
            let mut j = i + 1;
            if j < meaningful.len() && is_kw(meaningful[j], "IF") {
                j += 1;
                if j < meaningful.len() && is_kw(meaningful[j], "EXISTS") {
                    j += 1;
                }
            }
            if j < meaningful.len()
                && (is_kw(meaningful[j], "SCHEMA") || is_kw(meaningful[j], "DATABASE"))
            {
                let line = header_lines + meaningful[i].line;
                let target = meaningful[j].text.to_uppercase();
                let snippet = if j == i + 1 {
                    format!("DROP {}", target)
                } else {
                    let middle: Vec<&str> =
                        meaningful[i..=j].iter().map(|t| t.text).collect();
                    middle.join(" ")
                };
                diags.push(CheckDiagnostic {
                    rule_id: "SAF003".to_owned(),
                    message: format!(
                        "DROP {} detected at line {}. \
                         This is a destructive operation that removes an entire schema/database.",
                        target, line
                    ),
                    severity: config.effective_severity_for_path(
                        "SAF003",
                        file_path,
                        Severity::Error,
                    ),
                    category: CheckCategory::SqlSafety,
                    file_path: file_path.to_owned(),
                    line,
                    column: meaningful[i].column,
                    snippet: Some(snippet),
                    suggestion: Some(
                        "Remove the DROP SCHEMA/DATABASE statement or use --force-unsafe if intentional."
                            .to_owned(),
                    ),
                    doc_url: doc_url("SAF003"),
                });
                i = j + 1;
                continue;
            }
        }
        i += 1;
    }
}

// ---------------------------------------------------------------------------
// SAF004: TRUNCATE TABLE keyword sequence detected
// ---------------------------------------------------------------------------

fn check_saf004(
    file_path: &str,
    meaningful: &[&Token<'_>],
    header_lines: u32,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SAF004", file_path, true) {
        return;
    }

    for (i, tok) in meaningful.iter().enumerate() {
        if is_kw(tok, "TRUNCATE") {
            // TRUNCATE or TRUNCATE TABLE
            let target = meaningful.get(i + 1).map_or("...", |t| t.text);
            let line = header_lines + tok.line;
            diags.push(CheckDiagnostic {
                rule_id: "SAF004".to_owned(),
                message: format!(
                    "TRUNCATE detected at line {}. \
                     This removes all rows from the table without logging individual deletions.",
                    line
                ),
                severity: config.effective_severity_for_path("SAF004", file_path, Severity::Error),
                category: CheckCategory::SqlSafety,
                file_path: file_path.to_owned(),
                line,
                column: tok.column,
                snippet: Some(format!("TRUNCATE {}", target)),
                suggestion: Some(
                    "Use DELETE with a WHERE clause instead, or use --force-unsafe if intentional."
                        .to_owned(),
                ),
                doc_url: doc_url("SAF004"),
            });
        }
    }
}

// ---------------------------------------------------------------------------
// SAF005: DELETE FROM without subsequent WHERE keyword
// ---------------------------------------------------------------------------

fn check_saf005(
    file_path: &str,
    meaningful: &[&Token<'_>],
    header_lines: u32,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SAF005", file_path, true) {
        return;
    }

    for (i, tok) in meaningful.iter().enumerate() {
        if is_kw(tok, "DELETE") {
            if let Some(next) = meaningful.get(i + 1) {
                if is_kw(next, "FROM") {
                    // Scan forward for WHERE before end of statement
                    let mut found_where = false;
                    for t in meaningful.iter().skip(i + 2) {
                        if t.kind == TokenKind::Semicolon {
                            break;
                        }
                        if is_kw(t, "WHERE") {
                            found_where = true;
                            break;
                        }
                    }
                    if !found_where {
                        let line = header_lines + tok.line;
                        diags.push(CheckDiagnostic {
                            rule_id: "SAF005".to_owned(),
                            message: format!(
                                "DELETE FROM without WHERE clause at line {}. \
                                 This will delete all rows from the table.",
                                line
                            ),
                            severity: config.effective_severity_for_path(
                                "SAF005",
                                file_path,
                                Severity::Warning,
                            ),
                            category: CheckCategory::SqlSafety,
                            file_path: file_path.to_owned(),
                            line,
                            column: tok.column,
                            snippet: Some("DELETE FROM ...".to_owned()),
                            suggestion: Some(
                                "Add a WHERE clause to limit the rows affected.".to_owned(),
                            ),
                            doc_url: doc_url("SAF005"),
                        });
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// SAF006: ALTER TABLE ... DROP COLUMN keyword sequence
// ---------------------------------------------------------------------------

fn check_saf006(
    file_path: &str,
    meaningful: &[&Token<'_>],
    header_lines: u32,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SAF006", file_path, true) {
        return;
    }

    let mut i = 0;
    while i < meaningful.len() {
        if is_kw(meaningful[i], "ALTER") {
            if i + 1 < meaningful.len() && is_kw(meaningful[i + 1], "TABLE") {
                let alter_idx = i;
                // Scan forward within this statement for DROP COLUMN
                let mut j = i + 2;
                while j < meaningful.len() {
                    if meaningful[j].kind == TokenKind::Semicolon {
                        break;
                    }
                    if is_kw(meaningful[j], "DROP")
                        && j + 1 < meaningful.len()
                        && is_kw(meaningful[j + 1], "COLUMN")
                    {
                        let line = header_lines + meaningful[alter_idx].line;
                        diags.push(CheckDiagnostic {
                            rule_id: "SAF006".to_owned(),
                            message: format!(
                                "ALTER TABLE ... DROP COLUMN detected at line {}. \
                                 Dropping columns can break downstream dependencies.",
                                line
                            ),
                            severity: config.effective_severity_for_path(
                                "SAF006",
                                file_path,
                                Severity::Warning,
                            ),
                            category: CheckCategory::SqlSafety,
                            file_path: file_path.to_owned(),
                            line,
                            column: meaningful[alter_idx].column,
                            snippet: Some(format!(
                                "ALTER TABLE ... DROP COLUMN {}",
                                meaningful.get(j + 2).map_or("...", |t| t.text)
                            )),
                            suggestion: Some(
                                "Consider deprecating the column first before dropping it."
                                    .to_owned(),
                            ),
                            doc_url: doc_url("SAF006"),
                        });
                        j += 2;
                        continue;
                    }
                    j += 1;
                }
                i = j.max(i + 2);
                continue;
            }
        }
        i += 1;
    }
}

// ---------------------------------------------------------------------------
// SAF007: GRANT keyword at statement start
// ---------------------------------------------------------------------------

fn check_saf007(
    file_path: &str,
    meaningful: &[&Token<'_>],
    header_lines: u32,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SAF007", file_path, true) {
        return;
    }

    for (i, tok) in meaningful.iter().enumerate() {
        if is_kw(tok, "GRANT") && is_statement_start(meaningful, i) {
            let line = header_lines + tok.line;
            diags.push(CheckDiagnostic {
                rule_id: "SAF007".to_owned(),
                message: format!(
                    "GRANT statement detected at line {}. \
                     Permission grants should be managed outside of model SQL files.",
                    line
                ),
                severity: config.effective_severity_for_path("SAF007", file_path, Severity::Error),
                category: CheckCategory::SqlSafety,
                file_path: file_path.to_owned(),
                line,
                column: tok.column,
                snippet: Some("GRANT ...".to_owned()),
                suggestion: Some(
                    "Move GRANT statements to a dedicated permissions script.".to_owned(),
                ),
                doc_url: doc_url("SAF007"),
            });
        }
    }
}

// ---------------------------------------------------------------------------
// SAF008: REVOKE keyword at statement start
// ---------------------------------------------------------------------------

fn check_saf008(
    file_path: &str,
    meaningful: &[&Token<'_>],
    header_lines: u32,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SAF008", file_path, true) {
        return;
    }

    for (i, tok) in meaningful.iter().enumerate() {
        if is_kw(tok, "REVOKE") && is_statement_start(meaningful, i) {
            let line = header_lines + tok.line;
            diags.push(CheckDiagnostic {
                rule_id: "SAF008".to_owned(),
                message: format!(
                    "REVOKE statement detected at line {}. \
                     Permission revocations should be managed outside of model SQL files.",
                    line
                ),
                severity: config.effective_severity_for_path("SAF008", file_path, Severity::Error),
                category: CheckCategory::SqlSafety,
                file_path: file_path.to_owned(),
                line,
                column: tok.column,
                snippet: Some("REVOKE ...".to_owned()),
                suggestion: Some(
                    "Move REVOKE statements to a dedicated permissions script.".to_owned(),
                ),
                doc_url: doc_url("SAF008"),
            });
        }
    }
}

// ---------------------------------------------------------------------------
// SAF009: CREATE USER / CREATE ROLE keyword sequence
// ---------------------------------------------------------------------------

fn check_saf009(
    file_path: &str,
    meaningful: &[&Token<'_>],
    header_lines: u32,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SAF009", file_path, true) {
        return;
    }

    for (i, tok) in meaningful.iter().enumerate() {
        if is_kw(tok, "CREATE") {
            if let Some(next) = meaningful.get(i + 1) {
                if is_kw_or_ident(next, "USER") || is_kw(next, "ROLE") {
                    let line = header_lines + tok.line;
                    let target = next.text.to_uppercase();
                    diags.push(CheckDiagnostic {
                        rule_id: "SAF009".to_owned(),
                        message: format!(
                            "CREATE {} detected at line {}. \
                             User/role management should be handled outside of model SQL files.",
                            target, line
                        ),
                        severity: config.effective_severity_for_path(
                            "SAF009",
                            file_path,
                            Severity::Error,
                        ),
                        category: CheckCategory::SqlSafety,
                        file_path: file_path.to_owned(),
                        line,
                        column: tok.column,
                        snippet: Some(format!("CREATE {}", target)),
                        suggestion: Some(
                            "Move user/role creation to a dedicated identity management script."
                                .to_owned(),
                        ),
                        doc_url: doc_url("SAF009"),
                    });
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// SAF010: INSERT OVERWRITE without PARTITION clause
// ---------------------------------------------------------------------------

fn check_saf010(
    file_path: &str,
    meaningful: &[&Token<'_>],
    header_lines: u32,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SAF010", file_path, true) {
        return;
    }

    for (i, tok) in meaningful.iter().enumerate() {
        if is_kw(tok, "INSERT") {
            if let Some(next) = meaningful.get(i + 1) {
                if is_kw_or_ident(next, "OVERWRITE") {
                    // Scan forward for PARTITION before end of statement
                    let mut found_partition = false;
                    for t in meaningful.iter().skip(i + 2) {
                        if t.kind == TokenKind::Semicolon {
                            break;
                        }
                        if is_kw(t, "SELECT") {
                            // SELECT marks the start of the data source, stop scanning
                            break;
                        }
                        if is_kw(t, "PARTITION") {
                            found_partition = true;
                            break;
                        }
                    }
                    if !found_partition {
                        let line = header_lines + tok.line;
                        diags.push(CheckDiagnostic {
                            rule_id: "SAF010".to_owned(),
                            message: format!(
                                "INSERT OVERWRITE without PARTITION clause at line {}. \
                                 This will overwrite the entire table.",
                                line
                            ),
                            severity: config.effective_severity_for_path(
                                "SAF010",
                                file_path,
                                Severity::Warning,
                            ),
                            category: CheckCategory::SqlSafety,
                            file_path: file_path.to_owned(),
                            line,
                            column: tok.column,
                            snippet: Some("INSERT OVERWRITE ...".to_owned()),
                            suggestion: Some(
                                "Add a PARTITION clause to limit the scope of the overwrite."
                                    .to_owned(),
                            ),
                            doc_url: doc_url("SAF010"),
                        });
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Check if a token at index `i` is at the start of a statement.
///
/// A token is at statement start if it's the first meaningful token, or
/// if the previous meaningful token is a semicolon.
fn is_statement_start(meaningful: &[&Token<'_>], i: usize) -> bool {
    if i == 0 {
        return true;
    }
    meaningful
        .get(i - 1)
        .is_some_and(|prev| prev.kind == TokenKind::Semicolon)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::CheckConfig;

    fn default_config() -> CheckConfig {
        CheckConfig::default()
    }

    fn check(content: &str) -> Vec<CheckDiagnostic> {
        let checker = SqlSafetyChecker;
        checker.check_file("test.sql", content, None, &default_config())
    }

    // ── SAF001 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_saf001_drop_table() {
        let diags = check("DROP TABLE my_table");
        assert!(diags.iter().any(|d| d.rule_id == "SAF001"));
    }

    #[test]
    fn test_saf001_no_drop() {
        let diags = check("SELECT * FROM my_table");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF001"));
    }

    #[test]
    fn test_saf001_drop_table_if_exists() {
        let diags = check("DROP TABLE IF EXISTS my_table");
        assert!(diags.iter().any(|d| d.rule_id == "SAF001"));
    }

    #[test]
    fn test_saf001_severity_is_error() {
        let diags = check("DROP TABLE t");
        let d = diags.iter().find(|d| d.rule_id == "SAF001").unwrap();
        assert_eq!(d.severity, Severity::Error);
    }

    #[test]
    fn test_saf001_in_string_not_detected() {
        let diags = check("SELECT 'DROP TABLE trick' FROM t");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF001"));
    }

    // ── SAF002 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_saf002_drop_view() {
        let diags = check("DROP VIEW my_view");
        assert!(diags.iter().any(|d| d.rule_id == "SAF002"));
    }

    #[test]
    fn test_saf002_no_drop_view() {
        let diags = check("CREATE VIEW my_view AS SELECT 1");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF002"));
    }

    // ── SAF003 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_saf003_drop_schema() {
        let diags = check("DROP SCHEMA my_schema");
        assert!(diags.iter().any(|d| d.rule_id == "SAF003"));
    }

    #[test]
    fn test_saf003_drop_database() {
        let diags = check("DROP DATABASE my_db");
        assert!(diags.iter().any(|d| d.rule_id == "SAF003"));
    }

    #[test]
    fn test_saf003_no_drop_schema() {
        let diags = check("CREATE SCHEMA my_schema");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF003"));
    }

    // ── SAF004 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_saf004_truncate() {
        let diags = check("TRUNCATE TABLE my_table");
        assert!(diags.iter().any(|d| d.rule_id == "SAF004"));
    }

    #[test]
    fn test_saf004_truncate_bare() {
        let diags = check("TRUNCATE my_table");
        assert!(diags.iter().any(|d| d.rule_id == "SAF004"));
    }

    #[test]
    fn test_saf004_no_truncate() {
        let diags = check("DELETE FROM my_table WHERE id = 1");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF004"));
    }

    // ── SAF005 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_saf005_delete_without_where() {
        let diags = check("DELETE FROM my_table");
        assert!(diags.iter().any(|d| d.rule_id == "SAF005"));
    }

    #[test]
    fn test_saf005_delete_with_where() {
        let diags = check("DELETE FROM my_table WHERE id = 1");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF005"));
    }

    #[test]
    fn test_saf005_severity_is_warning() {
        let diags = check("DELETE FROM t");
        let d = diags.iter().find(|d| d.rule_id == "SAF005").unwrap();
        assert_eq!(d.severity, Severity::Warning);
    }

    // ── SAF006 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_saf006_alter_drop_column() {
        let diags = check("ALTER TABLE my_table DROP COLUMN old_col");
        assert!(diags.iter().any(|d| d.rule_id == "SAF006"));
    }

    #[test]
    fn test_saf006_alter_add_column() {
        let diags = check("ALTER TABLE my_table ADD COLUMN new_col INT");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF006"));
    }

    #[test]
    fn test_saf006_severity_is_warning() {
        let diags = check("ALTER TABLE t DROP COLUMN c");
        let d = diags.iter().find(|d| d.rule_id == "SAF006").unwrap();
        assert_eq!(d.severity, Severity::Warning);
    }

    // ── SAF007 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_saf007_grant() {
        let diags = check("GRANT SELECT ON t TO user1");
        assert!(diags.iter().any(|d| d.rule_id == "SAF007"));
    }

    #[test]
    fn test_saf007_no_grant() {
        let diags = check("SELECT * FROM t");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF007"));
    }

    #[test]
    fn test_saf007_severity_is_error() {
        let diags = check("GRANT SELECT ON t TO u");
        let d = diags.iter().find(|d| d.rule_id == "SAF007").unwrap();
        assert_eq!(d.severity, Severity::Error);
    }

    // ── SAF008 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_saf008_revoke() {
        let diags = check("REVOKE SELECT ON t FROM user1");
        assert!(diags.iter().any(|d| d.rule_id == "SAF008"));
    }

    #[test]
    fn test_saf008_no_revoke() {
        let diags = check("SELECT * FROM t");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF008"));
    }

    // ── SAF009 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_saf009_create_user() {
        let diags = check("CREATE USER admin");
        assert!(diags.iter().any(|d| d.rule_id == "SAF009"));
    }

    #[test]
    fn test_saf009_create_role() {
        let diags = check("CREATE ROLE admin_role");
        assert!(diags.iter().any(|d| d.rule_id == "SAF009"));
    }

    #[test]
    fn test_saf009_create_table_ok() {
        let diags = check("CREATE TABLE my_table (id INT)");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF009"));
    }

    // ── SAF010 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_saf010_insert_overwrite_no_partition() {
        let diags = check("INSERT OVERWRITE my_table SELECT * FROM t");
        assert!(diags.iter().any(|d| d.rule_id == "SAF010"));
    }

    #[test]
    fn test_saf010_insert_overwrite_with_partition() {
        let diags =
            check("INSERT OVERWRITE my_table PARTITION (dt = '2024-01-01') SELECT * FROM t");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF010"));
    }

    #[test]
    fn test_saf010_regular_insert_ok() {
        let diags = check("INSERT INTO my_table SELECT * FROM t");
        assert!(!diags.iter().any(|d| d.rule_id == "SAF010"));
    }

    #[test]
    fn test_saf010_severity_is_warning() {
        let diags = check("INSERT OVERWRITE t SELECT 1");
        let d = diags.iter().find(|d| d.rule_id == "SAF010").unwrap();
        assert_eq!(d.severity, Severity::Warning);
    }

    // ── Non-SQL file test ──────────────────────────────────────────────────

    #[test]
    fn test_non_sql_file_ignored() {
        let checker = SqlSafetyChecker;
        let diags = checker.check_file("schema.yml", "DROP TABLE t", None, &default_config());
        assert!(diags.is_empty());
    }

    // ── Config override test ───────────────────────────────────────────────

    #[test]
    fn test_rule_disabled_via_config() {
        let mut config = default_config();
        config.rules.insert(
            "SAF001".to_owned(),
            crate::config::RuleSeverityOverride::Off,
        );
        let checker = SqlSafetyChecker;
        let diags = checker.check_file("test.sql", "DROP TABLE t", None, &config);
        assert!(!diags.iter().any(|d| d.rule_id == "SAF001"));
    }
}
