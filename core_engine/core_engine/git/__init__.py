"""Git integration for change detection."""

from __future__ import annotations

from core_engine.git.git_client import (
    ChangedFile,
    ChangeStatus,
    GitClientError,
    get_changed_files,
    get_current_sha,
    get_file_at_commit,
    validate_repo,
)

__all__ = [
    "ChangedFile",
    "ChangeStatus",
    "GitClientError",
    "get_changed_files",
    "get_current_sha",
    "get_file_at_commit",
    "validate_repo",
]
