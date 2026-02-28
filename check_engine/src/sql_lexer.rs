//! Lightweight SQL tokenizer for the IronLayer Check Engine.
//!
//! Produces a zero-copy token stream over `&str` input, sufficient for
//! syntax checks (SQL001-SQL009) and safety pre-screening (SAF001-SAF010).
//! This is NOT a full SQL parser — it tokenizes enough to detect bracket
//! balance, string balance, dangerous keyword sequences, and Jinja templates.
//!
//! The lexer correctly handles:
//! - Nested `/* /* */ */` block comments
//! - String escaping: `'it''s'` (doubled single quote)
//! - Jinja templates: `{{ ... }}`, `{% ... %}`, `{# ... #}`
//! - Databricks-specific: backtick quoting, `$` in identifiers
//! - Unicode identifiers
//!
//! All 19 [`TokenKind`] variants are handled explicitly — no catch-all arms.

/// The kind of a SQL token.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum TokenKind {
    /// SQL keyword (SELECT, FROM, WHERE, INSERT, DELETE, DROP, etc.).
    Keyword,
    /// Unquoted identifier (table_name, column_name).
    Identifier,
    /// Backtick-quoted or double-quoted identifier.
    QuotedIdent,
    /// Single-quoted string literal (with `''` escape support).
    StringLiteral,
    /// Numeric literal (42, 3.14, 1e10).
    NumberLiteral,
    /// Operator (=, <>, !=, >=, <=, +, -, *, /, %).
    Operator,
    /// Left parenthesis `(`.
    LeftParen,
    /// Right parenthesis `)`.
    RightParen,
    /// Comma `,`.
    Comma,
    /// Semicolon `;`.
    Semicolon,
    /// Dot `.`.
    Dot,
    /// Single-line comment `-- ...`.
    LineComment,
    /// Block comment `/* ... */` (supports nesting).
    BlockComment,
    /// Jinja open `{{`.
    JinjaOpen,
    /// Jinja close `}}`.
    JinjaClose,
    /// Jinja block `{% ... %}` or Jinja comment `{# ... #}`.
    JinjaBlock,
    /// Whitespace (spaces, tabs — not newlines).
    Whitespace,
    /// Newline character(s) (`\n` or `\r\n`).
    Newline,
    /// Unrecognized character.
    Unknown,
}

/// A single token with a zero-copy text slice into the source.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Token<'a> {
    /// The kind of this token.
    pub kind: TokenKind,
    /// Zero-copy slice of the source text for this token.
    pub text: &'a str,
    /// Byte offset in the source where this token starts.
    pub offset: usize,
    /// 1-based line number.
    pub line: u32,
    /// 1-based column number (in bytes from line start).
    pub column: u32,
}

/// SQL keywords recognized by the lexer for `TokenKind::Keyword` classification.
const SQL_KEYWORDS: &[&str] = &[
    "ADD",
    "ALL",
    "ALTER",
    "AND",
    "ANY",
    "AS",
    "ASC",
    "BETWEEN",
    "BY",
    "CASE",
    "CAST",
    "CHECK",
    "COLUMN",
    "CONSTRAINT",
    "CREATE",
    "CROSS",
    "CURRENT",
    "DATABASE",
    "DEFAULT",
    "DELETE",
    "DESC",
    "DISTINCT",
    "DROP",
    "ELSE",
    "END",
    "ESCAPE",
    "EXCEPT",
    "EXEC",
    "EXECUTE",
    "EXISTS",
    "EXTERNAL",
    "FALSE",
    "FETCH",
    "FOR",
    "FOREIGN",
    "FROM",
    "FULL",
    "GRANT",
    "GROUP",
    "HAVING",
    "IF",
    "IN",
    "INCREMENTAL",
    "INDEX",
    "INNER",
    "INSERT",
    "INTERSECT",
    "INTO",
    "IS",
    "JOIN",
    "KEY",
    "LEFT",
    "LIKE",
    "LIMIT",
    "MERGE",
    "NOT",
    "NULL",
    "OFFSET",
    "ON",
    "OR",
    "ORDER",
    "OUTER",
    "OVER",
    "OVERWRITE",
    "PARTITION",
    "PRIMARY",
    "REFERENCES",
    "REVOKE",
    "RIGHT",
    "ROLE",
    "ROLLBACK",
    "ROW",
    "SCHEMA",
    "SELECT",
    "SET",
    "TABLE",
    "THEN",
    "TOP",
    "TRUNCATE",
    "UNION",
    "UNIQUE",
    "UPDATE",
    "USER",
    "USING",
    "VALUES",
    "VIEW",
    "WHEN",
    "WHERE",
    "WINDOW",
    "WITH",
];

/// Tokenize a SQL source string into a vector of tokens.
///
/// The lexer processes the entire input in a single pass, producing one
/// token per recognized element. Jinja templates (`{{ }}`, `{% %}`, `{# #}`)
/// are emitted as opaque tokens — their contents are not further tokenized.
///
/// # Arguments
///
/// * `source` — The SQL source text (must be valid UTF-8).
///
/// # Returns
///
/// A vector of [`Token`] references into the source string.
#[must_use]
pub fn tokenize(source: &str) -> Vec<Token<'_>> {
    let mut tokens = Vec::new();
    let bytes = source.as_bytes();
    let len = bytes.len();
    let mut pos: usize = 0;
    let mut line: u32 = 1;
    let mut col: u32 = 1;

    while pos < len {
        let start = pos;
        let start_line = line;
        let start_col = col;
        let ch = bytes[pos];

        // ── Newlines ───────────────────────────────────────────────────
        if ch == b'\n' {
            pos += 1;
            tokens.push(Token {
                kind: TokenKind::Newline,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            line += 1;
            col = 1;
            continue;
        }
        if ch == b'\r' {
            pos += 1;
            if pos < len && bytes[pos] == b'\n' {
                pos += 1;
            }
            tokens.push(Token {
                kind: TokenKind::Newline,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            line += 1;
            col = 1;
            continue;
        }

        // ── Whitespace (not newlines) ──────────────────────────────────
        if ch == b' ' || ch == b'\t' {
            pos += 1;
            col += 1;
            while pos < len && (bytes[pos] == b' ' || bytes[pos] == b'\t') {
                pos += 1;
                col += 1;
            }
            tokens.push(Token {
                kind: TokenKind::Whitespace,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Line comment: -- ───────────────────────────────────────────
        if ch == b'-' && pos + 1 < len && bytes[pos + 1] == b'-' {
            pos += 2;
            col += 2;
            while pos < len && bytes[pos] != b'\n' && bytes[pos] != b'\r' {
                pos += 1;
                col += 1;
            }
            tokens.push(Token {
                kind: TokenKind::LineComment,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Block comment: /* ... */ (with nesting) ────────────────────
        if ch == b'/' && pos + 1 < len && bytes[pos + 1] == b'*' {
            pos += 2;
            col += 2;
            let mut depth: u32 = 1;
            while pos < len && depth > 0 {
                if bytes[pos] == b'/' && pos + 1 < len && bytes[pos + 1] == b'*' {
                    depth += 1;
                    pos += 2;
                    col += 2;
                } else if bytes[pos] == b'*' && pos + 1 < len && bytes[pos + 1] == b'/' {
                    depth -= 1;
                    pos += 2;
                    col += 2;
                } else if bytes[pos] == b'\n' {
                    pos += 1;
                    line += 1;
                    col = 1;
                } else if bytes[pos] == b'\r' {
                    pos += 1;
                    if pos < len && bytes[pos] == b'\n' {
                        pos += 1;
                    }
                    line += 1;
                    col = 1;
                } else {
                    pos += 1;
                    col += 1;
                }
            }
            tokens.push(Token {
                kind: TokenKind::BlockComment,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Jinja open: {{ ─────────────────────────────────────────────
        if ch == b'{' && pos + 1 < len && bytes[pos + 1] == b'{' {
            pos += 2;
            col += 2;
            tokens.push(Token {
                kind: TokenKind::JinjaOpen,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Jinja close: }} ────────────────────────────────────────────
        if ch == b'}' && pos + 1 < len && bytes[pos + 1] == b'}' {
            pos += 2;
            col += 2;
            tokens.push(Token {
                kind: TokenKind::JinjaClose,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Jinja block: {% ... %} ────────────────────────────────────
        if ch == b'{' && pos + 1 < len && bytes[pos + 1] == b'%' {
            pos += 2;
            col += 2;
            while pos < len {
                if bytes[pos] == b'%' && pos + 1 < len && bytes[pos + 1] == b'}' {
                    pos += 2;
                    col += 2;
                    break;
                }
                if bytes[pos] == b'\n' {
                    line += 1;
                    col = 1;
                    pos += 1;
                } else if bytes[pos] == b'\r' {
                    pos += 1;
                    if pos < len && bytes[pos] == b'\n' {
                        pos += 1;
                    }
                    line += 1;
                    col = 1;
                } else {
                    pos += 1;
                    col += 1;
                }
            }
            tokens.push(Token {
                kind: TokenKind::JinjaBlock,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Jinja comment: {# ... #} ──────────────────────────────────
        if ch == b'{' && pos + 1 < len && bytes[pos + 1] == b'#' {
            pos += 2;
            col += 2;
            while pos < len {
                if bytes[pos] == b'#' && pos + 1 < len && bytes[pos + 1] == b'}' {
                    pos += 2;
                    col += 2;
                    break;
                }
                if bytes[pos] == b'\n' {
                    line += 1;
                    col = 1;
                    pos += 1;
                } else if bytes[pos] == b'\r' {
                    pos += 1;
                    if pos < len && bytes[pos] == b'\n' {
                        pos += 1;
                    }
                    line += 1;
                    col = 1;
                } else {
                    pos += 1;
                    col += 1;
                }
            }
            tokens.push(Token {
                kind: TokenKind::JinjaBlock,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Single-quoted string literal: '...' with '' escaping ───────
        if ch == b'\'' {
            pos += 1;
            col += 1;
            while pos < len {
                if bytes[pos] == b'\'' {
                    pos += 1;
                    col += 1;
                    // Doubled quote escape: ''
                    if pos < len && bytes[pos] == b'\'' {
                        pos += 1;
                        col += 1;
                        continue;
                    }
                    break;
                }
                if bytes[pos] == b'\n' {
                    line += 1;
                    col = 1;
                    pos += 1;
                } else if bytes[pos] == b'\r' {
                    pos += 1;
                    if pos < len && bytes[pos] == b'\n' {
                        pos += 1;
                    }
                    line += 1;
                    col = 1;
                } else {
                    pos += 1;
                    col += 1;
                }
            }
            tokens.push(Token {
                kind: TokenKind::StringLiteral,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Backtick-quoted identifier: `...` ──────────────────────────
        if ch == b'`' {
            pos += 1;
            col += 1;
            while pos < len && bytes[pos] != b'`' {
                if bytes[pos] == b'\n' {
                    line += 1;
                    col = 1;
                    pos += 1;
                } else {
                    pos += 1;
                    col += 1;
                }
            }
            if pos < len {
                pos += 1; // consume closing backtick
                col += 1;
            }
            tokens.push(Token {
                kind: TokenKind::QuotedIdent,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Double-quoted identifier: "..." ────────────────────────────
        if ch == b'"' {
            pos += 1;
            col += 1;
            while pos < len && bytes[pos] != b'"' {
                if bytes[pos] == b'\n' {
                    line += 1;
                    col = 1;
                    pos += 1;
                } else {
                    pos += 1;
                    col += 1;
                }
            }
            if pos < len {
                pos += 1; // consume closing double-quote
                col += 1;
            }
            tokens.push(Token {
                kind: TokenKind::QuotedIdent,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Number literal: digits, optional dot, optional exponent ────
        if ch.is_ascii_digit() {
            pos += 1;
            col += 1;
            while pos < len && bytes[pos].is_ascii_digit() {
                pos += 1;
                col += 1;
            }
            // Optional decimal part
            if pos < len && bytes[pos] == b'.' && pos + 1 < len && bytes[pos + 1].is_ascii_digit() {
                pos += 1; // dot
                col += 1;
                while pos < len && bytes[pos].is_ascii_digit() {
                    pos += 1;
                    col += 1;
                }
            }
            // Optional exponent
            if pos < len && (bytes[pos] == b'e' || bytes[pos] == b'E') {
                pos += 1;
                col += 1;
                if pos < len && (bytes[pos] == b'+' || bytes[pos] == b'-') {
                    pos += 1;
                    col += 1;
                }
                while pos < len && bytes[pos].is_ascii_digit() {
                    pos += 1;
                    col += 1;
                }
            }
            tokens.push(Token {
                kind: TokenKind::NumberLiteral,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Punctuation: single-character tokens ───────────────────────
        if ch == b'(' {
            pos += 1;
            col += 1;
            tokens.push(Token {
                kind: TokenKind::LeftParen,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }
        if ch == b')' {
            pos += 1;
            col += 1;
            tokens.push(Token {
                kind: TokenKind::RightParen,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }
        if ch == b',' {
            pos += 1;
            col += 1;
            tokens.push(Token {
                kind: TokenKind::Comma,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }
        if ch == b';' {
            pos += 1;
            col += 1;
            tokens.push(Token {
                kind: TokenKind::Semicolon,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }
        if ch == b'.' {
            pos += 1;
            col += 1;
            tokens.push(Token {
                kind: TokenKind::Dot,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Operators (multi-char first, then single-char) ─────────────
        if is_operator_start(ch) {
            let op_len = match_operator(bytes, pos);
            pos += op_len;
            col += op_len as u32;
            tokens.push(Token {
                kind: TokenKind::Operator,
                text: &source[start..pos],
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Identifier or keyword ──────────────────────────────────────
        if is_ident_start(ch) {
            pos += 1;
            col += 1;
            while pos < len && is_ident_continue(bytes[pos]) {
                pos += 1;
                col += 1;
            }
            let text = &source[start..pos];
            let kind = if is_keyword(text) {
                TokenKind::Keyword
            } else {
                TokenKind::Identifier
            };
            tokens.push(Token {
                kind,
                text,
                offset: start,
                line: start_line,
                column: start_col,
            });
            continue;
        }

        // ── Multi-byte UTF-8 identifier start ─────────────────────────
        // Handle Unicode identifiers (letters beyond ASCII)
        if ch >= 0x80 {
            let ch_str = &source[pos..];
            if let Some(c) = ch_str.chars().next() {
                if c.is_alphabetic() {
                    let c_len = c.len_utf8();
                    pos += c_len;
                    col += 1;
                    while pos < len {
                        if bytes[pos] < 0x80 {
                            if is_ident_continue(bytes[pos]) {
                                pos += 1;
                                col += 1;
                            } else {
                                break;
                            }
                        } else {
                            let rest = &source[pos..];
                            if let Some(nc) = rest.chars().next() {
                                if nc.is_alphanumeric() || nc == '_' {
                                    pos += nc.len_utf8();
                                    col += 1;
                                } else {
                                    break;
                                }
                            } else {
                                break;
                            }
                        }
                    }
                    tokens.push(Token {
                        kind: TokenKind::Identifier,
                        text: &source[start..pos],
                        offset: start,
                        line: start_line,
                        column: start_col,
                    });
                    continue;
                }
                // Non-alphabetic multi-byte char → Unknown
                let c_len = c.len_utf8();
                pos += c_len;
                col += 1;
                tokens.push(Token {
                    kind: TokenKind::Unknown,
                    text: &source[start..pos],
                    offset: start,
                    line: start_line,
                    column: start_col,
                });
                continue;
            }
        }

        // ── Unknown single byte ────────────────────────────────────────
        pos += 1;
        col += 1;
        tokens.push(Token {
            kind: TokenKind::Unknown,
            text: &source[start..pos],
            offset: start,
            line: start_line,
            column: start_col,
        });
    }

    tokens
}

/// Check if a byte can start an operator.
fn is_operator_start(ch: u8) -> bool {
    matches!(
        ch,
        b'=' | b'<'
            | b'>'
            | b'!'
            | b'+'
            | b'-'
            | b'*'
            | b'/'
            | b'%'
            | b'&'
            | b'|'
            | b'^'
            | b'~'
            | b':'
    )
}

/// Match the longest operator starting at `pos`, returning its byte length.
///
/// Handles multi-character operators: `<>`, `!=`, `>=`, `<=`, `||`, `::`.
fn match_operator(bytes: &[u8], pos: usize) -> usize {
    let ch = bytes[pos];
    let next = if pos + 1 < bytes.len() {
        Some(bytes[pos + 1])
    } else {
        None
    };

    match (ch, next) {
        (b'<', Some(b'>')) => 2, // <>
        (b'<', Some(b'=')) => 2, // <=
        (b'>', Some(b'=')) => 2, // >=
        (b'!', Some(b'=')) => 2, // !=
        (b'|', Some(b'|')) => 2, // ||
        (b':', Some(b':')) => 2, // :: (cast)
        _ => 1,
    }
}

/// Check if a byte can start an identifier (ASCII letters, underscore, dollar sign).
fn is_ident_start(ch: u8) -> bool {
    ch.is_ascii_alphabetic() || ch == b'_' || ch == b'$'
}

/// Check if a byte can continue an identifier.
fn is_ident_continue(ch: u8) -> bool {
    ch.is_ascii_alphanumeric() || ch == b'_' || ch == b'$'
}

/// Check if a word is a SQL keyword (case-insensitive).
fn is_keyword(word: &str) -> bool {
    let upper = word.to_uppercase();
    SQL_KEYWORDS.binary_search(&upper.as_str()).is_ok()
}

/// Extract only the meaningful tokens (filter out whitespace, newlines, comments).
///
/// Useful for checkers that only care about the SQL structure.
#[must_use]
pub fn meaningful_tokens<'a>(tokens: &'a [Token<'a>]) -> Vec<&'a Token<'a>> {
    tokens
        .iter()
        .filter(|t| {
            !matches!(
                t.kind,
                TokenKind::Whitespace
                    | TokenKind::Newline
                    | TokenKind::LineComment
                    | TokenKind::BlockComment
            )
        })
        .collect()
}

/// Get the text content after stripping the header comment block.
///
/// Returns the SQL body text after the header (first non-empty, non-comment line).
#[must_use]
pub fn strip_header(content: &str) -> &str {
    let mut last_header_end = 0;

    for line in content.lines() {
        let trimmed = line.trim();

        if trimmed.is_empty() {
            last_header_end += line.len() + 1; // +1 for newline
            continue;
        }

        if trimmed.starts_with("--") {
            last_header_end += line.len() + 1;
            continue;
        }

        // First non-empty, non-comment line — this is the SQL body start
        break;
    }

    if last_header_end > content.len() {
        ""
    } else {
        &content[last_header_end..]
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_select() {
        let tokens = tokenize("SELECT 1");
        let kinds: Vec<TokenKind> = tokens.iter().map(|t| t.kind).collect();
        assert_eq!(
            kinds,
            vec![
                TokenKind::Keyword,
                TokenKind::Whitespace,
                TokenKind::NumberLiteral
            ]
        );
    }

    #[test]
    fn test_select_from_where() {
        let tokens = tokenize("SELECT * FROM t WHERE x = 1");
        let meaningful: Vec<&str> = meaningful_tokens(&tokens).iter().map(|t| t.text).collect();
        assert_eq!(
            meaningful,
            vec!["SELECT", "*", "FROM", "t", "WHERE", "x", "=", "1"]
        );
    }

    #[test]
    fn test_line_comment() {
        let tokens = tokenize("-- this is a comment\nSELECT 1");
        assert_eq!(tokens[0].kind, TokenKind::LineComment);
        assert_eq!(tokens[0].text, "-- this is a comment");
    }

    #[test]
    fn test_block_comment() {
        let tokens = tokenize("/* comment */ SELECT 1");
        assert_eq!(tokens[0].kind, TokenKind::BlockComment);
        assert_eq!(tokens[0].text, "/* comment */");
    }

    #[test]
    fn test_nested_block_comment() {
        let tokens = tokenize("/* outer /* inner */ still outer */ SELECT 1");
        assert_eq!(tokens[0].kind, TokenKind::BlockComment);
        assert_eq!(tokens[0].text, "/* outer /* inner */ still outer */");
    }

    #[test]
    fn test_string_literal() {
        let tokens = tokenize("'hello world'");
        assert_eq!(tokens[0].kind, TokenKind::StringLiteral);
        assert_eq!(tokens[0].text, "'hello world'");
    }

    #[test]
    fn test_string_with_escape() {
        let tokens = tokenize("'it''s a test'");
        assert_eq!(tokens[0].kind, TokenKind::StringLiteral);
        assert_eq!(tokens[0].text, "'it''s a test'");
    }

    #[test]
    fn test_backtick_quoted_ident() {
        let tokens = tokenize("`my column`");
        assert_eq!(tokens[0].kind, TokenKind::QuotedIdent);
        assert_eq!(tokens[0].text, "`my column`");
    }

    #[test]
    fn test_double_quoted_ident() {
        let tokens = tokenize("\"my column\"");
        assert_eq!(tokens[0].kind, TokenKind::QuotedIdent);
        assert_eq!(tokens[0].text, "\"my column\"");
    }

    #[test]
    fn test_number_literal_integer() {
        let tokens = tokenize("42");
        assert_eq!(tokens[0].kind, TokenKind::NumberLiteral);
        assert_eq!(tokens[0].text, "42");
    }

    #[test]
    fn test_number_literal_decimal() {
        let tokens = tokenize("3.14");
        assert_eq!(tokens[0].kind, TokenKind::NumberLiteral);
        assert_eq!(tokens[0].text, "3.14");
    }

    #[test]
    fn test_number_literal_exponent() {
        let tokens = tokenize("1e10");
        assert_eq!(tokens[0].kind, TokenKind::NumberLiteral);
        assert_eq!(tokens[0].text, "1e10");
    }

    #[test]
    fn test_operators() {
        let tokens = tokenize("= <> != >= <=");
        let ops: Vec<&str> = tokens
            .iter()
            .filter(|t| t.kind == TokenKind::Operator)
            .map(|t| t.text)
            .collect();
        assert_eq!(ops, vec!["=", "<>", "!=", ">=", "<="]);
    }

    #[test]
    fn test_punctuation() {
        let tokens = tokenize("(a, b)");
        let kinds: Vec<TokenKind> = tokens.iter().map(|t| t.kind).collect();
        assert_eq!(
            kinds,
            vec![
                TokenKind::LeftParen,
                TokenKind::Identifier,
                TokenKind::Comma,
                TokenKind::Whitespace,
                TokenKind::Identifier,
                TokenKind::RightParen,
            ]
        );
    }

    #[test]
    fn test_semicolon() {
        let tokens = tokenize("SELECT 1;");
        assert!(tokens.iter().any(|t| t.kind == TokenKind::Semicolon));
    }

    #[test]
    fn test_dot() {
        // "schema" and "table" are SQL keywords, so the lexer classifies them as keywords
        let tokens = tokenize("schema.table");
        let kinds: Vec<TokenKind> = tokens.iter().map(|t| t.kind).collect();
        assert_eq!(
            kinds,
            vec![TokenKind::Keyword, TokenKind::Dot, TokenKind::Keyword]
        );

        // Non-keyword identifiers
        let tokens2 = tokenize("my_schema.my_table");
        let kinds2: Vec<TokenKind> = tokens2.iter().map(|t| t.kind).collect();
        assert_eq!(
            kinds2,
            vec![TokenKind::Identifier, TokenKind::Dot, TokenKind::Identifier]
        );
    }

    #[test]
    fn test_jinja_open_close() {
        let tokens = tokenize("{{ ref('model') }}");
        assert_eq!(tokens[0].kind, TokenKind::JinjaOpen);
        assert_eq!(tokens[0].text, "{{");
        assert!(tokens.iter().any(|t| t.kind == TokenKind::JinjaClose));
    }

    #[test]
    fn test_jinja_block() {
        let tokens = tokenize("{% if condition %}SELECT 1{% endif %}");
        assert_eq!(tokens[0].kind, TokenKind::JinjaBlock);
        assert_eq!(tokens[0].text, "{% if condition %}");
    }

    #[test]
    fn test_jinja_comment() {
        let tokens = tokenize("{# this is a jinja comment #}");
        assert_eq!(tokens[0].kind, TokenKind::JinjaBlock);
        assert_eq!(tokens[0].text, "{# this is a jinja comment #}");
    }

    #[test]
    fn test_newline() {
        let tokens = tokenize("SELECT\n1");
        assert!(tokens.iter().any(|t| t.kind == TokenKind::Newline));
    }

    #[test]
    fn test_crlf_newline() {
        let tokens = tokenize("SELECT\r\n1");
        let newlines: Vec<_> = tokens
            .iter()
            .filter(|t| t.kind == TokenKind::Newline)
            .collect();
        assert_eq!(newlines.len(), 1);
        assert_eq!(newlines[0].text, "\r\n");
    }

    #[test]
    fn test_keyword_case_insensitive() {
        let tokens_upper = tokenize("SELECT");
        let tokens_lower = tokenize("select");
        assert_eq!(tokens_upper[0].kind, TokenKind::Keyword);
        assert_eq!(tokens_lower[0].kind, TokenKind::Keyword);
    }

    #[test]
    fn test_identifier_with_underscore() {
        let tokens = tokenize("my_table");
        assert_eq!(tokens[0].kind, TokenKind::Identifier);
        assert_eq!(tokens[0].text, "my_table");
    }

    #[test]
    fn test_identifier_with_dollar() {
        let tokens = tokenize("$variable");
        assert_eq!(tokens[0].kind, TokenKind::Identifier);
        assert_eq!(tokens[0].text, "$variable");
    }

    #[test]
    fn test_line_numbers() {
        let tokens = tokenize("SELECT\n1");
        assert_eq!(tokens[0].line, 1); // SELECT
        assert_eq!(tokens[2].line, 2); // 1
    }

    #[test]
    fn test_column_numbers() {
        let tokens = tokenize("SELECT 1");
        assert_eq!(tokens[0].column, 1); // SELECT starts at column 1
        assert_eq!(tokens[2].column, 8); // 1 starts at column 8
    }

    #[test]
    fn test_empty_input() {
        let tokens = tokenize("");
        assert!(tokens.is_empty());
    }

    #[test]
    fn test_only_whitespace() {
        let tokens = tokenize("   ");
        assert_eq!(tokens.len(), 1);
        assert_eq!(tokens[0].kind, TokenKind::Whitespace);
    }

    #[test]
    fn test_unknown_character() {
        let tokens = tokenize("@");
        assert_eq!(tokens[0].kind, TokenKind::Unknown);
    }

    #[test]
    fn test_complex_query() {
        let sql = "SELECT a, b FROM {{ ref('stg_orders') }} WHERE x > 1 AND y = 'hello'";
        let tokens = tokenize(sql);
        let meaningful = meaningful_tokens(&tokens);
        assert!(meaningful.len() > 5);
        assert!(meaningful.iter().any(|t| t.kind == TokenKind::JinjaOpen));
        assert!(meaningful.iter().any(|t| t.kind == TokenKind::JinjaClose));
        assert!(meaningful
            .iter()
            .any(|t| t.kind == TokenKind::StringLiteral));
    }

    #[test]
    fn test_concat_operator() {
        let tokens = tokenize("a || b");
        let ops: Vec<_> = tokens
            .iter()
            .filter(|t| t.kind == TokenKind::Operator)
            .collect();
        assert_eq!(ops.len(), 1);
        assert_eq!(ops[0].text, "||");
    }

    #[test]
    fn test_cast_operator() {
        let tokens = tokenize("x::int");
        let ops: Vec<_> = tokens
            .iter()
            .filter(|t| t.kind == TokenKind::Operator)
            .collect();
        assert_eq!(ops.len(), 1);
        assert_eq!(ops[0].text, "::");
    }

    #[test]
    fn test_minus_not_confused_with_comment() {
        let tokens = tokenize("x - 1");
        let meaningful = meaningful_tokens(&tokens);
        assert_eq!(meaningful.len(), 3);
        assert_eq!(meaningful[1].kind, TokenKind::Operator);
        assert_eq!(meaningful[1].text, "-");
    }

    #[test]
    fn test_strip_header_basic() {
        let content = "-- name: test\n-- kind: FULL_REFRESH\nSELECT 1";
        let body = strip_header(content);
        assert_eq!(body, "SELECT 1");
    }

    #[test]
    fn test_strip_header_with_blank_lines() {
        let content = "-- name: test\n\n-- kind: FULL_REFRESH\nSELECT 1";
        let body = strip_header(content);
        assert_eq!(body, "SELECT 1");
    }

    #[test]
    fn test_strip_header_no_header() {
        let content = "SELECT 1";
        let body = strip_header(content);
        assert_eq!(body, "SELECT 1");
    }

    #[test]
    fn test_strip_header_only_header() {
        let content = "-- name: test\n-- kind: FULL_REFRESH\n";
        let body = strip_header(content);
        assert_eq!(body, "");
    }

    #[test]
    fn test_all_19_token_kinds_exist() {
        // Verify we can construct all 19 token kinds
        let kinds = vec![
            TokenKind::Keyword,
            TokenKind::Identifier,
            TokenKind::QuotedIdent,
            TokenKind::StringLiteral,
            TokenKind::NumberLiteral,
            TokenKind::Operator,
            TokenKind::LeftParen,
            TokenKind::RightParen,
            TokenKind::Comma,
            TokenKind::Semicolon,
            TokenKind::Dot,
            TokenKind::LineComment,
            TokenKind::BlockComment,
            TokenKind::JinjaOpen,
            TokenKind::JinjaClose,
            TokenKind::JinjaBlock,
            TokenKind::Whitespace,
            TokenKind::Newline,
            TokenKind::Unknown,
        ];
        assert_eq!(kinds.len(), 19);
    }

    #[test]
    fn test_sql_keywords_sorted() {
        // Binary search requires sorted array
        for window in SQL_KEYWORDS.windows(2) {
            assert!(
                window[0] < window[1],
                "SQL_KEYWORDS not sorted: {:?} >= {:?}",
                window[0],
                window[1]
            );
        }
    }

    #[test]
    fn test_multiline_string() {
        let sql = "'line1\nline2'";
        let tokens = tokenize(sql);
        assert_eq!(tokens[0].kind, TokenKind::StringLiteral);
        assert_eq!(tokens[0].text, "'line1\nline2'");
    }

    #[test]
    fn test_select_star() {
        let tokens = tokenize("SELECT *");
        let meaningful = meaningful_tokens(&tokens);
        assert_eq!(meaningful[0].text, "SELECT");
        assert_eq!(meaningful[1].kind, TokenKind::Operator);
        assert_eq!(meaningful[1].text, "*");
    }

    #[test]
    fn test_tab_as_whitespace() {
        let tokens = tokenize("\tSELECT");
        assert_eq!(tokens[0].kind, TokenKind::Whitespace);
        assert_eq!(tokens[0].text, "\t");
    }
}
