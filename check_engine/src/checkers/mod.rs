//! Checker trait definition and checker registry.
//!
//! Every checker implements the [`Checker`] trait, providing per-file and
//! optionally cross-file validation. Checkers are stateless — all context
//! is passed via parameters.
//!
//! The registry function [`build_checker_registry`] returns all available
//! checkers for the current phase.

pub mod sql_header;

use crate::config::CheckConfig;
use crate::types::{CheckDiagnostic, DiscoveredModel};

/// Every checker implements this trait.
///
/// Checkers are stateless and receive all context via parameters.
/// They must be `Send + Sync` to support parallel execution via rayon.
pub trait Checker: Send + Sync {
    /// Unique name for this checker (used in config to enable/disable).
    fn name(&self) -> &'static str;

    /// Run checks against a single file.
    ///
    /// Returns diagnostics for this file only. The `model` parameter is
    /// `Some` for `.sql` files that have been parsed for header metadata,
    /// `None` for non-SQL files or SQL files that failed header parsing.
    fn check_file(
        &self,
        file_path: &str,
        content: &str,
        model: Option<&DiscoveredModel>,
        config: &CheckConfig,
    ) -> Vec<CheckDiagnostic>;

    /// Run checks that require cross-file context (e.g., ref resolution).
    ///
    /// Called once after all files have been individually checked. The default
    /// implementation returns no diagnostics (no cross-file checks needed).
    fn check_project(
        &self,
        _models: &[DiscoveredModel],
        _config: &CheckConfig,
    ) -> Vec<CheckDiagnostic> {
        Vec::new()
    }
}

/// Build the checker registry containing all available checkers.
///
/// Returns a vector of boxed checker trait objects, one per check category.
/// Phase 1 includes only the SQL header checker (HDR001-HDR013).
#[must_use]
pub fn build_checker_registry() -> Vec<Box<dyn Checker>> {
    vec![Box::new(sql_header::SqlHeaderChecker)]
}
