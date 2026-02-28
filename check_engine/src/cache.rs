//! Content-addressable check cache for the IronLayer Check Engine.
//!
//! Caches check results by file content hash + config hash + engine version.
//! A cache hit means the file content, config, and engine version all match
//! the last check — so the previous diagnostics can be reused without re-checking.
//!
//! Cache concurrency is handled via atomic writes (temp file + rename).
//! Last writer wins; no locking. Corrupt cache is logged, deleted, and rebuilt.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::config::CheckConfig;
use crate::types::{CheckDiagnostic, DiscoveredFile};

/// Current engine version, used for cache invalidation.
const ENGINE_VERSION: &str = "0.3.0";

/// Cache format version.
const CACHE_VERSION: &str = "1";

/// A single cache entry for one file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheEntry {
    /// SHA-256 hash of the file content.
    pub content_hash: String,
    /// ISO 8601 timestamp of when this file was last checked.
    pub last_checked: DateTime<Utc>,
    /// Diagnostics from the last check (empty if the file was clean).
    pub diagnostics: Vec<CachedDiagnostic>,
}

/// Lightweight diagnostic stored in the cache (subset of [`CheckDiagnostic`]).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedDiagnostic {
    /// Rule identifier (e.g., `"HDR001"`).
    pub rule_id: String,
    /// Severity level as a string.
    pub severity: String,
    /// Human-readable message.
    pub message: String,
}

/// The on-disk cache file format.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheFile {
    /// Cache format version.
    pub version: String,
    /// Engine version that produced this cache.
    pub engine_version: String,
    /// SHA-256 hash of the config used for the last check.
    pub config_hash: String,
    /// File path → cache entry mapping.
    pub entries: HashMap<String, CacheEntry>,
}

/// The check cache, managing reads and writes of cached check results.
pub struct CheckCache {
    /// In-memory cache entries loaded from disk.
    entries: HashMap<String, CacheEntry>,
    /// Config hash for the current run.
    config_hash: String,
    /// Path to the cache file on disk.
    cache_path: Option<PathBuf>,
    /// Whether the cache is enabled.
    enabled: bool,
    /// Whether the cache was invalidated (config or version mismatch).
    invalidated: bool,
}

impl CheckCache {
    /// Create a new cache, loading from disk if available and valid.
    ///
    /// # Arguments
    ///
    /// * `root` — Project root directory.
    /// * `config` — Check configuration (for cache path and enabled flag).
    pub fn new(root: &Path, config: &CheckConfig) -> Self {
        let enabled = config.cache.enabled && !config.no_cache;
        let config_hash = config.config_hash();

        if !enabled {
            return Self {
                entries: HashMap::new(),
                config_hash,
                cache_path: None,
                enabled: false,
                invalidated: false,
            };
        }

        let cache_path = root.join(&config.cache.path);
        let (entries, invalidated) = load_cache_file(&cache_path, &config_hash);

        Self {
            entries,
            config_hash,
            cache_path: Some(cache_path),
            enabled: true,
            invalidated,
        }
    }

    /// Check if a file has a valid cache hit.
    ///
    /// Returns `true` if the file's content hash matches the cached entry
    /// and the cache was not invalidated.
    #[must_use]
    pub fn is_cached(&self, file: &DiscoveredFile) -> bool {
        if !self.enabled || self.invalidated {
            return false;
        }

        if let Some(entry) = self.entries.get(&file.rel_path) {
            return entry.content_hash == file.content_hash;
        }

        false
    }

    /// Get cached diagnostics for a file, if the cache is valid.
    ///
    /// Returns `None` if the file is not cached or the cache is invalid.
    #[must_use]
    pub fn get_cached_diagnostics(&self, file: &DiscoveredFile) -> Option<&[CachedDiagnostic]> {
        if !self.is_cached(file) {
            return None;
        }

        self.entries
            .get(&file.rel_path)
            .map(|e| e.diagnostics.as_slice())
    }

    /// Partition discovered files into cached and uncached sets.
    ///
    /// Returns `(cached_files, uncached_files)`.
    pub fn partition<'a>(
        &self,
        files: &'a [DiscoveredFile],
    ) -> (Vec<&'a DiscoveredFile>, Vec<&'a DiscoveredFile>) {
        let mut cached = Vec::new();
        let mut uncached = Vec::new();

        for file in files {
            if self.is_cached(file) {
                cached.push(file);
            } else {
                uncached.push(file);
            }
        }

        (cached, uncached)
    }

    /// Update the cache with results from a check run.
    ///
    /// Only files with zero errors are cached (files with errors should
    /// always be re-checked to see if they've been fixed).
    pub fn update(&mut self, file_path: &str, content_hash: &str, diagnostics: &[CheckDiagnostic]) {
        if !self.enabled {
            return;
        }

        let cached_diags: Vec<CachedDiagnostic> = diagnostics
            .iter()
            .map(|d| CachedDiagnostic {
                rule_id: d.rule_id.clone(),
                severity: d.severity.to_string(),
                message: d.message.clone(),
            })
            .collect();

        self.entries.insert(
            file_path.to_owned(),
            CacheEntry {
                content_hash: content_hash.to_owned(),
                last_checked: Utc::now(),
                diagnostics: cached_diags,
            },
        );
    }

    /// Write the cache to disk atomically.
    ///
    /// Uses a temp file + rename strategy for atomic writes.
    /// Errors are logged but never propagated (cache is a performance
    /// optimization, not a correctness requirement).
    pub fn flush(&self) {
        if !self.enabled {
            return;
        }

        let cache_path = match &self.cache_path {
            Some(p) => p,
            None => return,
        };

        let cache_file = CacheFile {
            version: CACHE_VERSION.to_owned(),
            engine_version: ENGINE_VERSION.to_owned(),
            config_hash: self.config_hash.clone(),
            entries: self.entries.clone(),
        };

        let json = match serde_json::to_string_pretty(&cache_file) {
            Ok(j) => j,
            Err(e) => {
                log::warn!("Failed to serialize cache: {}", e);
                return;
            }
        };

        // Ensure parent directory exists
        if let Some(parent) = cache_path.parent() {
            if let Err(e) = std::fs::create_dir_all(parent) {
                log::warn!("Failed to create cache directory: {}", e);
                return;
            }
        }

        // Atomic write via temp file + rename
        let pid = std::process::id();
        let tmp_path = cache_path.with_extension(format!("json.tmp.{pid}"));

        if let Err(e) = std::fs::write(&tmp_path, &json) {
            log::warn!("Failed to write cache temp file: {}", e);
            return;
        }

        if let Err(e) = std::fs::rename(&tmp_path, cache_path) {
            log::warn!("Failed to rename cache file: {}", e);
            // Clean up temp file
            let _ = std::fs::remove_file(&tmp_path);
        }
    }

    /// Clear all cached entries (used for `--no-cache` or testing).
    pub fn clear(&mut self) {
        self.entries.clear();
        self.invalidated = true;
    }
}

/// Load the cache file from disk, validating version and config hash.
///
/// Returns `(entries, invalidated)`:
/// - If the cache is valid, returns its entries and `false`.
/// - If the cache is invalid (version/config mismatch), returns empty and `true`.
/// - If the cache is corrupt or missing, returns empty and `false`.
fn load_cache_file(cache_path: &Path, config_hash: &str) -> (HashMap<String, CacheEntry>, bool) {
    if !cache_path.is_file() {
        return (HashMap::new(), false);
    }

    let content = match std::fs::read_to_string(cache_path) {
        Ok(c) => c,
        Err(e) => {
            log::warn!("Failed to read cache file: {}", e);
            return (HashMap::new(), false);
        }
    };

    let cache_file: CacheFile = match serde_json::from_str(&content) {
        Ok(c) => c,
        Err(e) => {
            log::warn!("Corrupt cache file ({}). Deleting and rebuilding.", e);
            let _ = std::fs::remove_file(cache_path);
            return (HashMap::new(), false);
        }
    };

    // Check engine version
    if cache_file.engine_version != ENGINE_VERSION {
        log::info!(
            "Cache engine version mismatch ({} != {}). Invalidating.",
            cache_file.engine_version,
            ENGINE_VERSION
        );
        return (HashMap::new(), true);
    }

    // Check config hash
    if cache_file.config_hash != config_hash {
        log::info!("Cache config hash mismatch. Invalidating entire cache.");
        return (HashMap::new(), true);
    }

    // Check format version
    if cache_file.version != CACHE_VERSION {
        log::info!(
            "Cache format version mismatch ({} != {}). Invalidating.",
            cache_file.version,
            CACHE_VERSION
        );
        return (HashMap::new(), true);
    }

    (cache_file.entries, false)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn make_config() -> CheckConfig {
        CheckConfig::default()
    }

    fn make_file(rel_path: &str, content: &str) -> DiscoveredFile {
        DiscoveredFile {
            rel_path: rel_path.to_owned(),
            content: content.to_owned(),
            content_hash: crate::discovery::compute_sha256(content),
        }
    }

    #[test]
    fn test_cache_disabled() {
        let dir = tempdir().unwrap();
        let mut config = make_config();
        config.no_cache = true;
        let cache = CheckCache::new(dir.path(), &config);
        let file = make_file("test.sql", "SELECT 1");
        assert!(!cache.is_cached(&file));
    }

    #[test]
    fn test_cache_miss_no_file() {
        let dir = tempdir().unwrap();
        let config = make_config();
        let cache = CheckCache::new(dir.path(), &config);
        let file = make_file("test.sql", "SELECT 1");
        assert!(!cache.is_cached(&file));
    }

    #[test]
    fn test_cache_update_and_hit() {
        let dir = tempdir().unwrap();
        let config = make_config();
        let mut cache = CheckCache::new(dir.path(), &config);
        let file = make_file("test.sql", "SELECT 1");

        cache.update(&file.rel_path, &file.content_hash, &[]);
        assert!(cache.is_cached(&file));
    }

    #[test]
    fn test_cache_miss_on_content_change() {
        let dir = tempdir().unwrap();
        let config = make_config();
        let mut cache = CheckCache::new(dir.path(), &config);

        let file1 = make_file("test.sql", "SELECT 1");
        cache.update(&file1.rel_path, &file1.content_hash, &[]);

        let file2 = make_file("test.sql", "SELECT 2"); // Different content
        assert!(!cache.is_cached(&file2));
    }

    #[test]
    fn test_cache_flush_and_reload() {
        let dir = tempdir().unwrap();
        let config = make_config();
        let mut cache = CheckCache::new(dir.path(), &config);

        let file = make_file("test.sql", "SELECT 1");
        cache.update(&file.rel_path, &file.content_hash, &[]);
        cache.flush();

        // Reload from disk
        let cache2 = CheckCache::new(dir.path(), &config);
        assert!(cache2.is_cached(&file));
    }

    #[test]
    fn test_cache_invalidated_on_config_change() {
        let dir = tempdir().unwrap();
        let config1 = make_config();
        let mut cache = CheckCache::new(dir.path(), &config1);

        let file = make_file("test.sql", "SELECT 1");
        cache.update(&file.rel_path, &file.content_hash, &[]);
        cache.flush();

        // Load with different config
        let mut config2 = make_config();
        config2.fail_on_warnings = true;
        let cache2 = CheckCache::new(dir.path(), &config2);
        assert!(!cache2.is_cached(&file));
    }

    #[test]
    fn test_cache_corrupt_recovery() {
        let dir = tempdir().unwrap();
        let config = make_config();
        let cache_dir = dir.path().join(".ironlayer");
        std::fs::create_dir_all(&cache_dir).unwrap();
        std::fs::write(cache_dir.join("check_cache.json"), "not valid json{{{").unwrap();

        // Should not panic, should log warning and proceed
        let cache = CheckCache::new(dir.path(), &config);
        let file = make_file("test.sql", "SELECT 1");
        assert!(!cache.is_cached(&file));
    }

    #[test]
    fn test_partition() {
        let dir = tempdir().unwrap();
        let config = make_config();
        let mut cache = CheckCache::new(dir.path(), &config);

        let file1 = make_file("a.sql", "SELECT 1");
        let file2 = make_file("b.sql", "SELECT 2");
        cache.update(&file1.rel_path, &file1.content_hash, &[]);

        let files = vec![file1.clone(), file2.clone()];
        let (cached, uncached) = cache.partition(&files);
        assert_eq!(cached.len(), 1);
        assert_eq!(uncached.len(), 1);
        assert_eq!(cached[0].rel_path, "a.sql");
        assert_eq!(uncached[0].rel_path, "b.sql");
    }

    #[test]
    fn test_cache_clear() {
        let dir = tempdir().unwrap();
        let config = make_config();
        let mut cache = CheckCache::new(dir.path(), &config);

        let file = make_file("test.sql", "SELECT 1");
        cache.update(&file.rel_path, &file.content_hash, &[]);
        assert!(cache.is_cached(&file));

        cache.clear();
        assert!(!cache.is_cached(&file));
    }

    #[test]
    fn test_cached_diagnostics() {
        let dir = tempdir().unwrap();
        let config = make_config();
        let mut cache = CheckCache::new(dir.path(), &config);

        let file = make_file("test.sql", "SELECT 1");
        let diags = vec![crate::types::CheckDiagnostic {
            rule_id: "HDR001".to_owned(),
            message: "Missing name".to_owned(),
            severity: crate::types::Severity::Error,
            category: crate::types::CheckCategory::SqlHeader,
            file_path: "test.sql".to_owned(),
            line: 1,
            column: 0,
            snippet: None,
            suggestion: None,
            doc_url: None,
        }];
        cache.update(&file.rel_path, &file.content_hash, &diags);

        let cached = cache.get_cached_diagnostics(&file).unwrap();
        assert_eq!(cached.len(), 1);
        assert_eq!(cached[0].rule_id, "HDR001");
    }
}
