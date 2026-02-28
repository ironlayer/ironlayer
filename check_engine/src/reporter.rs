//! JSON and SARIF output generation for the IronLayer Check Engine.
//!
//! Produces two output formats:
//! - **JSON**: Custom format matching the spec (§8.2) for CLI `--json` mode
//! - **SARIF**: v2.1.0 format for GitHub Code Scanning integration (§8.3)

use serde::Serialize;

use crate::types::{CheckDiagnostic, CheckResult, Severity};

// ---------------------------------------------------------------------------
// JSON output (§8.2)
// ---------------------------------------------------------------------------

/// JSON output format matching spec §8.2.
#[derive(Debug, Serialize)]
pub struct JsonOutput {
    /// Whether the check passed (zero errors).
    pub passed: bool,
    /// Auto-detected project type.
    pub project_type: String,
    /// Wall-clock milliseconds.
    pub elapsed_ms: u64,
    /// Summary counts.
    pub summary: JsonSummary,
    /// All diagnostics.
    pub diagnostics: Vec<JsonDiagnostic>,
}

/// Summary section of JSON output.
#[derive(Debug, Serialize)]
pub struct JsonSummary {
    /// Total files checked (not cached).
    pub total_files_checked: u32,
    /// Total files skipped from cache.
    pub total_files_skipped_cache: u32,
    /// Count of error-severity diagnostics.
    pub total_errors: u32,
    /// Count of warning-severity diagnostics.
    pub total_warnings: u32,
    /// Count of info-severity diagnostics.
    pub total_infos: u32,
}

/// A single diagnostic in JSON output.
#[derive(Debug, Serialize)]
pub struct JsonDiagnostic {
    /// Rule identifier (e.g., `"HDR001"`).
    pub rule_id: String,
    /// Human-readable message.
    pub message: String,
    /// Severity as a lowercase string.
    pub severity: String,
    /// Check category.
    pub category: String,
    /// Relative file path.
    pub file_path: String,
    /// 1-based line number.
    pub line: u32,
    /// 1-based column number.
    pub column: u32,
    /// Offending text snippet.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub snippet: Option<String>,
    /// Suggested fix.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub suggestion: Option<String>,
    /// Documentation URL.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub doc_url: Option<String>,
}

/// Convert a [`CheckResult`] to the JSON output format string.
///
/// # Errors
///
/// Returns an error if JSON serialization fails (should not happen for valid data).
pub fn to_json(result: &CheckResult) -> Result<String, serde_json::Error> {
    let output = JsonOutput {
        passed: result.passed,
        project_type: result.project_type.clone(),
        elapsed_ms: result.elapsed_ms,
        summary: JsonSummary {
            total_files_checked: result.total_files_checked,
            total_files_skipped_cache: result.total_files_skipped_cache,
            total_errors: result.total_errors,
            total_warnings: result.total_warnings,
            total_infos: result.total_infos,
        },
        diagnostics: result.diagnostics.iter().map(diagnostic_to_json).collect(),
    };

    serde_json::to_string_pretty(&output)
}

fn diagnostic_to_json(d: &CheckDiagnostic) -> JsonDiagnostic {
    JsonDiagnostic {
        rule_id: d.rule_id.clone(),
        message: d.message.clone(),
        severity: d.severity.to_string(),
        category: d.category.to_string(),
        file_path: d.file_path.clone(),
        line: d.line,
        column: d.column,
        snippet: d.snippet.clone(),
        suggestion: d.suggestion.clone(),
        doc_url: d.doc_url.clone(),
    }
}

// ---------------------------------------------------------------------------
// SARIF output (§8.3)
// ---------------------------------------------------------------------------

/// SARIF v2.1.0 output for GitHub Code Scanning.
#[derive(Debug, Serialize)]
pub struct SarifOutput {
    /// SARIF schema URI.
    #[serde(rename = "$schema")]
    pub schema: String,
    /// SARIF version.
    pub version: String,
    /// SARIF runs.
    pub runs: Vec<SarifRun>,
}

/// A single SARIF run.
#[derive(Debug, Serialize)]
pub struct SarifRun {
    /// Tool information.
    pub tool: SarifTool,
    /// Results (diagnostics).
    pub results: Vec<SarifResult>,
}

/// SARIF tool descriptor.
#[derive(Debug, Serialize)]
pub struct SarifTool {
    /// Tool driver.
    pub driver: SarifDriver,
}

/// SARIF tool driver.
#[derive(Debug, Serialize)]
pub struct SarifDriver {
    /// Tool name.
    pub name: String,
    /// Tool version.
    pub version: String,
    /// Semantic version.
    #[serde(rename = "semanticVersion")]
    pub semantic_version: String,
    /// Information URI.
    #[serde(rename = "informationUri")]
    pub information_uri: String,
    /// Rule descriptors.
    pub rules: Vec<SarifRuleDescriptor>,
}

/// SARIF rule descriptor.
#[derive(Debug, Serialize)]
pub struct SarifRuleDescriptor {
    /// Rule identifier.
    pub id: String,
    /// Short description.
    #[serde(rename = "shortDescription")]
    pub short_description: SarifMessage,
    /// Help URI.
    #[serde(rename = "helpUri", skip_serializing_if = "Option::is_none")]
    pub help_uri: Option<String>,
}

/// SARIF message.
#[derive(Debug, Serialize)]
pub struct SarifMessage {
    /// Message text.
    pub text: String,
}

/// A single SARIF result.
#[derive(Debug, Serialize)]
pub struct SarifResult {
    /// Rule ID.
    #[serde(rename = "ruleId")]
    pub rule_id: String,
    /// Severity level (error, warning, note).
    pub level: String,
    /// Result message.
    pub message: SarifMessage,
    /// Physical locations.
    pub locations: Vec<SarifLocation>,
    /// Suggested fixes.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub fixes: Vec<SarifFix>,
}

/// SARIF location.
#[derive(Debug, Serialize)]
pub struct SarifLocation {
    /// Physical location.
    #[serde(rename = "physicalLocation")]
    pub physical_location: SarifPhysicalLocation,
}

/// SARIF physical location.
#[derive(Debug, Serialize)]
pub struct SarifPhysicalLocation {
    /// Artifact location (file path).
    #[serde(rename = "artifactLocation")]
    pub artifact_location: SarifArtifactLocation,
    /// Region (line/column).
    pub region: SarifRegion,
    /// Context region with snippet.
    #[serde(rename = "contextRegion", skip_serializing_if = "Option::is_none")]
    pub context_region: Option<SarifContextRegion>,
}

/// SARIF artifact location.
#[derive(Debug, Serialize)]
pub struct SarifArtifactLocation {
    /// File URI.
    pub uri: String,
}

/// SARIF region.
#[derive(Debug, Serialize)]
pub struct SarifRegion {
    /// Start line (1-based).
    #[serde(rename = "startLine")]
    pub start_line: u32,
    /// Start column (1-based).
    #[serde(rename = "startColumn")]
    pub start_column: u32,
}

/// SARIF context region with snippet.
#[derive(Debug, Serialize)]
pub struct SarifContextRegion {
    /// Snippet text.
    pub snippet: SarifSnippet,
}

/// SARIF snippet.
#[derive(Debug, Serialize)]
pub struct SarifSnippet {
    /// Snippet text.
    pub text: String,
}

/// SARIF fix suggestion.
#[derive(Debug, Serialize)]
pub struct SarifFix {
    /// Fix description.
    pub description: SarifMessage,
}

/// Convert a [`CheckResult`] to SARIF v2.1.0 format.
///
/// # Errors
///
/// Returns an error if JSON serialization fails.
pub fn to_sarif_json(result: &CheckResult) -> Result<String, serde_json::Error> {
    // Collect unique rule IDs for the rules section
    let mut rule_ids: Vec<String> = result
        .diagnostics
        .iter()
        .map(|d| d.rule_id.clone())
        .collect::<std::collections::HashSet<_>>()
        .into_iter()
        .collect();
    rule_ids.sort();

    let rules: Vec<SarifRuleDescriptor> = rule_ids
        .iter()
        .map(|id| SarifRuleDescriptor {
            id: id.clone(),
            short_description: SarifMessage {
                text: format!("IronLayer check rule {}", id),
            },
            help_uri: Some(format!("https://docs.ironlayer.app/check/rules/{id}")),
        })
        .collect();

    let results: Vec<SarifResult> = result.diagnostics.iter().map(diagnostic_to_sarif).collect();

    let output = SarifOutput {
        schema: "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json".to_owned(),
        version: "2.1.0".to_owned(),
        runs: vec![SarifRun {
            tool: SarifTool {
                driver: SarifDriver {
                    name: "ironlayer-check-engine".to_owned(),
                    version: "0.3.0".to_owned(),
                    semantic_version: "0.3.0".to_owned(),
                    information_uri: "https://docs.ironlayer.app/check".to_owned(),
                    rules,
                },
            },
            results,
        }],
    };

    serde_json::to_string_pretty(&output)
}

/// Map a Severity to a SARIF level string.
fn severity_to_sarif_level(severity: &Severity) -> String {
    match severity {
        Severity::Error => "error".to_owned(),
        Severity::Warning => "warning".to_owned(),
        Severity::Info => "note".to_owned(),
    }
}

fn diagnostic_to_sarif(d: &CheckDiagnostic) -> SarifResult {
    let context_region = d.snippet.as_ref().map(|s| SarifContextRegion {
        snippet: SarifSnippet { text: s.clone() },
    });

    let fixes = d
        .suggestion
        .as_ref()
        .map(|s| {
            vec![SarifFix {
                description: SarifMessage { text: s.clone() },
            }]
        })
        .unwrap_or_default();

    SarifResult {
        rule_id: d.rule_id.clone(),
        level: severity_to_sarif_level(&d.severity),
        message: SarifMessage {
            text: d.message.clone(),
        },
        locations: vec![SarifLocation {
            physical_location: SarifPhysicalLocation {
                artifact_location: SarifArtifactLocation {
                    uri: d.file_path.clone(),
                },
                region: SarifRegion {
                    start_line: d.line.max(1),
                    start_column: d.column.max(1),
                },
                context_region,
            },
        }],
        fixes,
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{CheckCategory, CheckDiagnostic, CheckResult, Severity};

    fn sample_result() -> CheckResult {
        CheckResult {
            diagnostics: vec![
                CheckDiagnostic {
                    rule_id: "HDR001".to_owned(),
                    message: "Missing required field 'name'.".to_owned(),
                    severity: Severity::Error,
                    category: CheckCategory::SqlHeader,
                    file_path: "models/stg_orders.sql".to_owned(),
                    line: 1,
                    column: 0,
                    snippet: None,
                    suggestion: Some("Add '-- name: <model_name>'.".to_owned()),
                    doc_url: Some("https://docs.ironlayer.app/check/rules/HDR001".to_owned()),
                },
                CheckDiagnostic {
                    rule_id: "SQL004".to_owned(),
                    message: "SELECT * detected.".to_owned(),
                    severity: Severity::Warning,
                    category: CheckCategory::SqlSyntax,
                    file_path: "models/stg_orders.sql".to_owned(),
                    line: 5,
                    column: 1,
                    snippet: Some("SELECT *".to_owned()),
                    suggestion: Some("List columns explicitly.".to_owned()),
                    doc_url: Some("https://docs.ironlayer.app/check/rules/SQL004".to_owned()),
                },
            ],
            total_files_checked: 10,
            total_files_skipped_cache: 5,
            total_errors: 1,
            total_warnings: 1,
            total_infos: 0,
            elapsed_ms: 247,
            project_type: "ironlayer".to_owned(),
            passed: false,
        }
    }

    #[test]
    fn test_to_json_format() {
        let result = sample_result();
        let json = to_json(&result).unwrap();

        assert!(json.contains("\"passed\": false"));
        assert!(json.contains("\"project_type\": \"ironlayer\""));
        assert!(json.contains("\"elapsed_ms\": 247"));
        assert!(json.contains("\"total_errors\": 1"));
        assert!(json.contains("\"total_warnings\": 1"));
        assert!(json.contains("\"rule_id\": \"HDR001\""));
        assert!(json.contains("\"rule_id\": \"SQL004\""));
    }

    #[test]
    fn test_to_json_roundtrip() {
        let result = sample_result();
        let json = to_json(&result).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed["passed"], false);
        assert_eq!(parsed["diagnostics"].as_array().unwrap().len(), 2);
    }

    #[test]
    fn test_to_sarif_json_format() {
        let result = sample_result();
        let sarif = to_sarif_json(&result).unwrap();

        assert!(sarif.contains("\"version\": \"2.1.0\""));
        assert!(sarif.contains("\"name\": \"ironlayer-check-engine\""));
        assert!(sarif.contains("\"ruleId\": \"HDR001\""));
        assert!(sarif.contains("\"level\": \"error\""));
        assert!(sarif.contains("\"level\": \"warning\""));
    }

    #[test]
    fn test_to_sarif_roundtrip() {
        let result = sample_result();
        let sarif = to_sarif_json(&result).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&sarif).unwrap();
        assert_eq!(parsed["version"], "2.1.0");
        let runs = parsed["runs"].as_array().unwrap();
        assert_eq!(runs.len(), 1);
        let results = runs[0]["results"].as_array().unwrap();
        assert_eq!(results.len(), 2);
    }

    #[test]
    fn test_severity_to_sarif_level() {
        assert_eq!(severity_to_sarif_level(&Severity::Error), "error");
        assert_eq!(severity_to_sarif_level(&Severity::Warning), "warning");
        assert_eq!(severity_to_sarif_level(&Severity::Info), "note");
    }

    #[test]
    fn test_json_empty_result() {
        let result = CheckResult {
            diagnostics: Vec::new(),
            total_files_checked: 0,
            total_files_skipped_cache: 0,
            total_errors: 0,
            total_warnings: 0,
            total_infos: 0,
            elapsed_ms: 5,
            project_type: "raw_sql".to_owned(),
            passed: true,
        };
        let json = to_json(&result).unwrap();
        assert!(json.contains("\"passed\": true"));
        assert!(json.contains("\"diagnostics\": []"));
    }

    #[test]
    fn test_sarif_snippet_included() {
        let result = sample_result();
        let sarif = to_sarif_json(&result).unwrap();
        assert!(sarif.contains("\"text\": \"SELECT *\""));
    }

    #[test]
    fn test_sarif_fix_included() {
        let result = sample_result();
        let sarif = to_sarif_json(&result).unwrap();
        assert!(sarif.contains("List columns explicitly."));
    }

    #[test]
    fn test_json_null_fields_omitted() {
        let result = CheckResult {
            diagnostics: vec![CheckDiagnostic {
                rule_id: "HDR001".to_owned(),
                message: "test".to_owned(),
                severity: Severity::Error,
                category: CheckCategory::SqlHeader,
                file_path: "test.sql".to_owned(),
                line: 1,
                column: 0,
                snippet: None,
                suggestion: None,
                doc_url: None,
            }],
            total_files_checked: 1,
            total_files_skipped_cache: 0,
            total_errors: 1,
            total_warnings: 0,
            total_infos: 0,
            elapsed_ms: 1,
            project_type: "ironlayer".to_owned(),
            passed: false,
        };
        let json = to_json(&result).unwrap();
        // snippet, suggestion, doc_url should not appear when None
        assert!(!json.contains("\"snippet\""));
        assert!(!json.contains("\"suggestion\""));
        assert!(!json.contains("\"doc_url\""));
    }
}
