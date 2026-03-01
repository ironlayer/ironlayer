//! SQL syntax validation checker — rules SQL001 through SQL009.
//!
//! Uses the lightweight Rust SQL lexer token stream (NOT a full AST) to detect
//! structural issues: bracket balance, string balance, SELECT *, empty body,
//! trailing semicolons, and tab characters.
//!
//! These checks run for ALL project types (IronLayer, dbt, raw SQL).

use crate::checkers::Checker;
use crate::config::CheckConfig;
use crate::sql_lexer::{self, Token, TokenKind};
use crate::types::{CheckCategory, CheckDiagnostic, DiscoveredModel, Severity};

/// SQL syntax checker implementing SQL001-SQL009.
pub struct SqlSyntaxChecker;

/// Generate the doc URL for a given rule ID.
fn doc_url(rule_id: &str) -> Option<String> {
    Some(format!("https://docs.ironlayer.app/check/rules/{rule_id}"))
}

impl Checker for SqlSyntaxChecker {
    fn name(&self) -> &'static str {
        "sql_syntax"
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

        let mut diags = Vec::new();

        check_sql001(file_path, &tokens, config, &mut diags);
        check_sql002(file_path, &tokens, config, &mut diags);
        check_sql003(file_path, &tokens, config, &mut diags);
        check_sql004(file_path, &tokens, config, &mut diags);
        check_sql005(file_path, &tokens, config, &mut diags);
        check_sql006(file_path, content, config, &mut diags);
        check_sql007(file_path, &tokens, content, config, &mut diags);
        check_sql008(file_path, body, config, &mut diags);
        check_sql009(file_path, content, config, &mut diags);

        diags
    }
}

// ---------------------------------------------------------------------------
// SQL001: Unbalanced parentheses in SQL body
// ---------------------------------------------------------------------------

/// Count parenthesis depth, reporting the first unmatched paren.
fn check_sql001(
    file_path: &str,
    tokens: &[Token<'_>],
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SQL001", file_path, true) {
        return;
    }

    let mut depth: i32 = 0;
    let mut first_unmatched_close: Option<&Token<'_>> = None;

    for tok in tokens {
        match tok.kind {
            TokenKind::LeftParen => {
                depth += 1;
            }
            TokenKind::RightParen => {
                depth -= 1;
                if depth < 0 && first_unmatched_close.is_none() {
                    first_unmatched_close = Some(tok);
                }
            }
            _ => {}
        }
    }

    if depth > 0 {
        // More opens than closes — find the last unmatched open
        let mut stack = Vec::new();
        for tok in tokens {
            match tok.kind {
                TokenKind::LeftParen => stack.push(tok),
                TokenKind::RightParen => {
                    stack.pop();
                }
                _ => {}
            }
        }
        if let Some(unmatched) = stack.first() {
            diags.push(CheckDiagnostic {
                rule_id: "SQL001".to_owned(),
                message: format!(
                    "Unbalanced parentheses: {} unclosed opening parenthesis(es). \
                     First unmatched '(' is at line {}, column {}.",
                    depth, unmatched.line, unmatched.column
                ),
                severity: config.effective_severity_for_path("SQL001", file_path, Severity::Error),
                category: CheckCategory::SqlSyntax,
                file_path: file_path.to_owned(),
                line: unmatched.line,
                column: unmatched.column,
                snippet: Some(unmatched.text.to_owned()),
                suggestion: Some("Add the missing closing parenthesis ')'.".to_owned()),
                doc_url: doc_url("SQL001"),
            });
        }
    } else if let Some(tok) = first_unmatched_close {
        diags.push(CheckDiagnostic {
            rule_id: "SQL001".to_owned(),
            message: format!(
                "Unbalanced parentheses: extra closing parenthesis ')' at line {}, column {}.",
                tok.line, tok.column
            ),
            severity: config.effective_severity_for_path("SQL001", file_path, Severity::Error),
            category: CheckCategory::SqlSyntax,
            file_path: file_path.to_owned(),
            line: tok.line,
            column: tok.column,
            snippet: Some(tok.text.to_owned()),
            suggestion: Some(
                "Remove the extra closing parenthesis ')' or add a matching '('.".to_owned(),
            ),
            doc_url: doc_url("SQL001"),
        });
    }
}

// ---------------------------------------------------------------------------
// SQL002: Unbalanced single quotes (unclosed string literal)
// ---------------------------------------------------------------------------

fn check_sql002(
    file_path: &str,
    tokens: &[Token<'_>],
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SQL002", file_path, true) {
        return;
    }

    for tok in tokens {
        if tok.kind == TokenKind::StringLiteral {
            let text = tok.text;
            // A properly closed string starts and ends with single quote
            if !text.ends_with('\'') {
                diags.push(CheckDiagnostic {
                    rule_id: "SQL002".to_owned(),
                    message: format!(
                        "Unclosed string literal starting at line {}, column {}. \
                         The single quote is not properly closed.",
                        tok.line, tok.column
                    ),
                    severity: config.effective_severity_for_path(
                        "SQL002",
                        file_path,
                        Severity::Error,
                    ),
                    category: CheckCategory::SqlSyntax,
                    file_path: file_path.to_owned(),
                    line: tok.line,
                    column: tok.column,
                    snippet: Some(truncate_snippet(text, 120)),
                    suggestion: Some(
                        "Add a closing single quote (') to terminate the string.".to_owned(),
                    ),
                    doc_url: doc_url("SQL002"),
                });
            }
        }
    }
}

// ---------------------------------------------------------------------------
// SQL003: Unbalanced backtick quotes
// ---------------------------------------------------------------------------

fn check_sql003(
    file_path: &str,
    tokens: &[Token<'_>],
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SQL003", file_path, true) {
        return;
    }

    for tok in tokens {
        if tok.kind == TokenKind::QuotedIdent
            && tok.text.starts_with('`')
            && (!tok.text.ends_with('`') || tok.text.len() < 2)
        {
            diags.push(CheckDiagnostic {
                rule_id: "SQL003".to_owned(),
                message: format!(
                    "Unclosed backtick-quoted identifier starting at line {}, column {}.",
                    tok.line, tok.column
                ),
                severity: config.effective_severity_for_path("SQL003", file_path, Severity::Error),
                category: CheckCategory::SqlSyntax,
                file_path: file_path.to_owned(),
                line: tok.line,
                column: tok.column,
                snippet: Some(truncate_snippet(tok.text, 120)),
                suggestion: Some(
                    "Add a closing backtick (`) to terminate the identifier.".to_owned(),
                ),
                doc_url: doc_url("SQL003"),
            });
        }
    }
}

// ---------------------------------------------------------------------------
// SQL004: SELECT * detected (non-terminal query)
// ---------------------------------------------------------------------------

fn check_sql004(
    file_path: &str,
    tokens: &[Token<'_>],
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SQL004", file_path, true) {
        return;
    }

    let meaningful = sql_lexer::meaningful_tokens(tokens);

    for (i, tok) in meaningful.iter().enumerate() {
        if tok.kind == TokenKind::Keyword && tok.text.to_uppercase() == "SELECT" {
            // Check if the next meaningful token is *
            if let Some(next) = meaningful.get(i + 1) {
                if next.kind == TokenKind::Operator && next.text == "*" {
                    // Check it's not SELECT COUNT(*) — the token after * should not be a right paren
                    // or check that it's not preceded by an aggregate function
                    let is_count_star = if i >= 1 {
                        meaningful
                            .get(i - 1)
                            .is_some_and(|prev: &&Token<'_>| prev.kind == TokenKind::LeftParen)
                    } else {
                        false
                    };

                    // Also check that SELECT * is not inside COUNT(*)
                    let next_after_star = meaningful.get(i + 2);
                    let star_followed_by_rparen =
                        next_after_star.is_some_and(|t| t.kind == TokenKind::RightParen);

                    // Only flag if it's really SELECT * (not part of COUNT(*))
                    if !is_count_star && !star_followed_by_rparen {
                        diags.push(CheckDiagnostic {
                            rule_id: "SQL004".to_owned(),
                            message: format!(
                                "SELECT * detected at line {}, column {}. \
                                 Explicitly list columns instead of using * for better \
                                 maintainability and contract enforcement.",
                                tok.line, tok.column
                            ),
                            severity: config.effective_severity_for_path(
                                "SQL004",
                                file_path,
                                Severity::Warning,
                            ),
                            category: CheckCategory::SqlSyntax,
                            file_path: file_path.to_owned(),
                            line: tok.line,
                            column: tok.column,
                            snippet: Some("SELECT *".to_owned()),
                            suggestion: Some(
                                "Replace 'SELECT *' with an explicit column list.".to_owned(),
                            ),
                            doc_url: doc_url("SQL004"),
                        });
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// SQL005: Missing WHERE clause on DELETE statement
// ---------------------------------------------------------------------------

fn check_sql005(
    file_path: &str,
    tokens: &[Token<'_>],
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SQL005", file_path, true) {
        return;
    }

    let meaningful = sql_lexer::meaningful_tokens(tokens);

    for (i, tok) in meaningful.iter().enumerate() {
        if tok.kind == TokenKind::Keyword && tok.text.to_uppercase() == "DELETE" {
            // Check next token is FROM
            if let Some(next) = meaningful.get(i + 1) {
                if next.kind == TokenKind::Keyword && next.text.to_uppercase() == "FROM" {
                    // Scan forward for WHERE before end of statement (semicolon or EOF)
                    let mut found_where = false;
                    for t in meaningful.iter().skip(i + 2) {
                        if t.kind == TokenKind::Semicolon {
                            break;
                        }
                        if t.kind == TokenKind::Keyword && t.text.to_uppercase() == "WHERE" {
                            found_where = true;
                            break;
                        }
                    }
                    if !found_where {
                        diags.push(CheckDiagnostic {
                            rule_id: "SQL005".to_owned(),
                            message: format!(
                                "DELETE FROM without WHERE clause at line {}, column {}. \
                                 This will delete all rows from the table.",
                                tok.line, tok.column
                            ),
                            severity: config.effective_severity_for_path(
                                "SQL005",
                                file_path,
                                Severity::Warning,
                            ),
                            category: CheckCategory::SqlSyntax,
                            file_path: file_path.to_owned(),
                            line: tok.line,
                            column: tok.column,
                            snippet: Some("DELETE FROM ...".to_owned()),
                            suggestion: Some(
                                "Add a WHERE clause to limit the rows affected.".to_owned(),
                            ),
                            doc_url: doc_url("SQL005"),
                        });
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// SQL006: SQL body exceeds configured max line count (disabled by default)
// ---------------------------------------------------------------------------

fn check_sql006(
    file_path: &str,
    content: &str,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    // Disabled by default
    if !config.is_rule_enabled_for_path("SQL006", file_path, false) {
        return;
    }

    let body = sql_lexer::strip_header(content);
    let line_count = body.lines().count();

    // Default max is 500 lines; this could be configurable in the future
    let max_lines: usize = 500;

    if line_count > max_lines {
        diags.push(CheckDiagnostic {
            rule_id: "SQL006".to_owned(),
            message: format!(
                "SQL body is {} lines long (max recommended: {}). \
                 Consider breaking this model into smaller, composable models.",
                line_count, max_lines
            ),
            severity: config.effective_severity_for_path("SQL006", file_path, Severity::Info),
            category: CheckCategory::SqlSyntax,
            file_path: file_path.to_owned(),
            line: 1,
            column: 0,
            snippet: None,
            suggestion: Some(
                "Split this model into smaller models using {{ ref() }} to compose them."
                    .to_owned(),
            ),
            doc_url: doc_url("SQL006"),
        });
    }
}

// ---------------------------------------------------------------------------
// SQL007: Trailing semicolons in model SQL (fixable)
// ---------------------------------------------------------------------------

fn check_sql007(
    file_path: &str,
    tokens: &[Token<'_>],
    content: &str,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SQL007", file_path, true) {
        return;
    }

    // Find the last meaningful token
    let meaningful = sql_lexer::meaningful_tokens(tokens);

    // Check if the last meaningful token is a semicolon
    if let Some(tok) = meaningful.last() {
        if tok.kind == TokenKind::Semicolon {
            // Compute the actual line in the original content
            let body_start_line = content
                .lines()
                .take_while(|line| {
                    let trimmed = line.trim();
                    trimmed.is_empty() || trimmed.starts_with("--")
                })
                .count() as u32;

            let actual_line = body_start_line + tok.line;

            diags.push(CheckDiagnostic {
                rule_id: "SQL007".to_owned(),
                message: format!(
                    "Trailing semicolon at line {}. IronLayer models should not end \
                     with semicolons — the engine handles statement termination.",
                    actual_line
                ),
                severity: config.effective_severity_for_path(
                    "SQL007",
                    file_path,
                    Severity::Warning,
                ),
                category: CheckCategory::SqlSyntax,
                file_path: file_path.to_owned(),
                line: actual_line,
                column: tok.column,
                snippet: Some(";".to_owned()),
                suggestion: Some("Remove the trailing semicolon.".to_owned()),
                doc_url: doc_url("SQL007"),
            });
        }
    }
}

// ---------------------------------------------------------------------------
// SQL008: Empty SQL body (no SQL after header)
// ---------------------------------------------------------------------------

fn check_sql008(
    file_path: &str,
    body: &str,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    if !config.is_rule_enabled_for_path("SQL008", file_path, true) {
        return;
    }

    let trimmed_body = body.trim();

    // Empty body or body with only comments
    if trimmed_body.is_empty() {
        diags.push(CheckDiagnostic {
            rule_id: "SQL008".to_owned(),
            message: "Empty SQL body — no SQL statements found after the header block.".to_owned(),
            severity: config.effective_severity_for_path("SQL008", file_path, Severity::Error),
            category: CheckCategory::SqlSyntax,
            file_path: file_path.to_owned(),
            line: 1,
            column: 0,
            snippet: None,
            suggestion: Some("Add a SQL SELECT statement after the header comments.".to_owned()),
            doc_url: doc_url("SQL008"),
        });
        return;
    }

    // Check if body is only comments (no actual SQL)
    let tokens = sql_lexer::tokenize(body);
    let meaningful = sql_lexer::meaningful_tokens(&tokens);
    let has_sql = meaningful.iter().any(|t| {
        !matches!(
            t.kind,
            TokenKind::JinjaOpen
                | TokenKind::JinjaClose
                | TokenKind::JinjaBlock
                | TokenKind::Semicolon
                | TokenKind::Unknown
        )
    });

    if !has_sql {
        diags.push(CheckDiagnostic {
            rule_id: "SQL008".to_owned(),
            message:
                "SQL body contains no meaningful SQL statements (only comments or whitespace)."
                    .to_owned(),
            severity: config.effective_severity_for_path("SQL008", file_path, Severity::Error),
            category: CheckCategory::SqlSyntax,
            file_path: file_path.to_owned(),
            line: 1,
            column: 0,
            snippet: None,
            suggestion: Some("Add a SQL SELECT statement after the header comments.".to_owned()),
            doc_url: doc_url("SQL008"),
        });
    }
}

// ---------------------------------------------------------------------------
// SQL009: Tab characters detected (fixable, disabled by default)
// ---------------------------------------------------------------------------

fn check_sql009(
    file_path: &str,
    content: &str,
    config: &CheckConfig,
    diags: &mut Vec<CheckDiagnostic>,
) {
    // Disabled by default
    if !config.is_rule_enabled_for_path("SQL009", file_path, false) {
        return;
    }

    for (line_idx, line) in content.lines().enumerate() {
        if let Some(col) = line.find('\t') {
            diags.push(CheckDiagnostic {
                rule_id: "SQL009".to_owned(),
                message: format!(
                    "Tab character detected at line {}, column {}. \
                     Use spaces for consistent indentation.",
                    line_idx + 1,
                    col + 1
                ),
                severity: config.effective_severity_for_path(
                    "SQL009",
                    file_path,
                    Severity::Warning,
                ),
                category: CheckCategory::SqlSyntax,
                file_path: file_path.to_owned(),
                line: (line_idx + 1) as u32,
                column: (col + 1) as u32,
                snippet: Some(truncate_snippet(line, 120)),
                suggestion: Some("Replace tab characters with 4 spaces.".to_owned()),
                doc_url: doc_url("SQL009"),
            });
            // Only report the first tab per file to avoid spam
            break;
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Truncate a text snippet to a max length, appending "..." if truncated.
fn truncate_snippet(text: &str, max_len: usize) -> String {
    if text.len() <= max_len {
        text.to_owned()
    } else {
        format!("{}...", &text[..max_len.saturating_sub(3)])
    }
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
        let checker = SqlSyntaxChecker;
        checker.check_file("test.sql", content, None, &default_config())
    }

    // ── SQL001 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_sql001_balanced_parens() {
        let diags = check("SELECT (a + b) FROM t");
        assert!(!diags.iter().any(|d| d.rule_id == "SQL001"));
    }

    #[test]
    fn test_sql001_unclosed_paren() {
        let diags = check("SELECT (a + b FROM t");
        assert!(diags.iter().any(|d| d.rule_id == "SQL001"));
    }

    #[test]
    fn test_sql001_extra_close_paren() {
        let diags = check("SELECT a + b) FROM t");
        assert!(diags.iter().any(|d| d.rule_id == "SQL001"));
    }

    #[test]
    fn test_sql001_nested_balanced() {
        let diags = check("SELECT ((a + b) * (c + d)) FROM t");
        assert!(!diags.iter().any(|d| d.rule_id == "SQL001"));
    }

    #[test]
    fn test_sql001_severity_is_error() {
        let diags = check("SELECT (a FROM t");
        let d = diags.iter().find(|d| d.rule_id == "SQL001").unwrap();
        assert_eq!(d.severity, Severity::Error);
    }

    // ── SQL002 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_sql002_balanced_strings() {
        let diags = check("SELECT 'hello' FROM t");
        assert!(!diags.iter().any(|d| d.rule_id == "SQL002"));
    }

    #[test]
    fn test_sql002_escaped_quotes() {
        let diags = check("SELECT 'it''s fine' FROM t");
        assert!(!diags.iter().any(|d| d.rule_id == "SQL002"));
    }

    // ── SQL003 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_sql003_balanced_backticks() {
        let diags = check("SELECT `my column` FROM t");
        assert!(!diags.iter().any(|d| d.rule_id == "SQL003"));
    }

    // ── SQL004 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_sql004_select_star() {
        let diags = check("SELECT * FROM t");
        assert!(diags.iter().any(|d| d.rule_id == "SQL004"));
    }

    #[test]
    fn test_sql004_no_select_star() {
        let diags = check("SELECT a, b FROM t");
        assert!(!diags.iter().any(|d| d.rule_id == "SQL004"));
    }

    #[test]
    fn test_sql004_severity_is_warning() {
        let diags = check("SELECT * FROM t");
        let d = diags.iter().find(|d| d.rule_id == "SQL004").unwrap();
        assert_eq!(d.severity, Severity::Warning);
    }

    // ── SQL005 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_sql005_delete_without_where() {
        let diags = check("DELETE FROM t");
        assert!(diags.iter().any(|d| d.rule_id == "SQL005"));
    }

    #[test]
    fn test_sql005_delete_with_where() {
        let diags = check("DELETE FROM t WHERE id = 1");
        assert!(!diags.iter().any(|d| d.rule_id == "SQL005"));
    }

    #[test]
    fn test_sql005_severity_is_warning() {
        let diags = check("DELETE FROM t");
        let d = diags.iter().find(|d| d.rule_id == "SQL005").unwrap();
        assert_eq!(d.severity, Severity::Warning);
    }

    // ── SQL006 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_sql006_disabled_by_default() {
        let long_sql = "SELECT\n".repeat(600);
        let diags = check(&long_sql);
        assert!(!diags.iter().any(|d| d.rule_id == "SQL006"));
    }

    #[test]
    fn test_sql006_enabled_long_file() {
        let long_sql = "SELECT\n".repeat(600);
        let mut config = default_config();
        config.rules.insert(
            "SQL006".to_owned(),
            crate::config::RuleSeverityOverride::Info,
        );
        let checker = SqlSyntaxChecker;
        let diags = checker.check_file("test.sql", &long_sql, None, &config);
        assert!(diags.iter().any(|d| d.rule_id == "SQL006"));
    }

    // ── SQL007 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_sql007_trailing_semicolon() {
        let diags = check("SELECT 1;");
        assert!(diags.iter().any(|d| d.rule_id == "SQL007"));
    }

    #[test]
    fn test_sql007_no_semicolon() {
        let diags = check("SELECT 1");
        assert!(!diags.iter().any(|d| d.rule_id == "SQL007"));
    }

    #[test]
    fn test_sql007_severity_is_warning() {
        let diags = check("SELECT 1;");
        let d = diags.iter().find(|d| d.rule_id == "SQL007").unwrap();
        assert_eq!(d.severity, Severity::Warning);
    }

    // ── SQL008 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_sql008_empty_body() {
        let diags = check("-- name: test\n-- kind: FULL_REFRESH\n");
        assert!(diags.iter().any(|d| d.rule_id == "SQL008"));
    }

    #[test]
    fn test_sql008_has_body() {
        let diags = check("-- name: test\n-- kind: FULL_REFRESH\nSELECT 1");
        assert!(!diags.iter().any(|d| d.rule_id == "SQL008"));
    }

    #[test]
    fn test_sql008_severity_is_error() {
        let diags = check("-- name: test\n");
        assert!(diags
            .iter()
            .any(|d| d.rule_id == "SQL008" && d.severity == Severity::Error));
    }

    // ── SQL009 tests ───────────────────────────────────────────────────────

    #[test]
    fn test_sql009_disabled_by_default() {
        let diags = check("\tSELECT 1");
        assert!(!diags.iter().any(|d| d.rule_id == "SQL009"));
    }

    #[test]
    fn test_sql009_enabled_detects_tabs() {
        let mut config = default_config();
        config.rules.insert(
            "SQL009".to_owned(),
            crate::config::RuleSeverityOverride::Warning,
        );
        let checker = SqlSyntaxChecker;
        let diags = checker.check_file("test.sql", "\tSELECT 1", None, &config);
        assert!(diags.iter().any(|d| d.rule_id == "SQL009"));
    }

    // ── Non-SQL file test ──────────────────────────────────────────────────

    #[test]
    fn test_non_sql_file_ignored() {
        let checker = SqlSyntaxChecker;
        let diags = checker.check_file("schema.yml", "SELECT (", None, &default_config());
        assert!(diags.is_empty());
    }

    // ── Config override test ───────────────────────────────────────────────

    #[test]
    fn test_rule_disabled_via_config() {
        let mut config = default_config();
        config.rules.insert(
            "SQL004".to_owned(),
            crate::config::RuleSeverityOverride::Off,
        );
        let checker = SqlSyntaxChecker;
        let diags = checker.check_file("test.sql", "SELECT * FROM t", None, &config);
        assert!(!diags.iter().any(|d| d.rule_id == "SQL004"));
    }
}
