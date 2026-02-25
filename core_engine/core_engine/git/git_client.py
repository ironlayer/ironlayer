"""Thin git client for detecting SQL model changes between commits.

All interaction with the ``git`` binary is done through :func:`subprocess.run`
with explicit timeouts and structured error handling so that callers receive
:class:`GitClientError` exceptions with descriptive messages rather than raw
subprocess failures.
"""

from __future__ import annotations

import logging
import re
import subprocess
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_SUBPROCESS_TIMEOUT = 30  # seconds

# ---------------------------------------------------------------------------
# Git ref validation
# ---------------------------------------------------------------------------

# Matches hex SHAs (4-40 chars) and common ref patterns like branch names,
# tags, HEAD, HEAD~2, origin/main, etc.
_GIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{4,40}$")
_GIT_REF_RE = re.compile(r"^[a-zA-Z0-9_./@~^{}\-]+$")


def _validate_git_ref(ref: str) -> None:
    """Validate a git ref or SHA to prevent command injection.

    Accepts hex SHAs (4-40 characters) and safe ref names (branch names,
    tags, HEAD, etc.).  Rejects strings containing shell metacharacters,
    spaces, or other characters that could be used for injection.

    Raises
    ------
    ValueError
        If *ref* does not match the expected pattern.
    """
    if not ref:
        raise ValueError("Git ref cannot be empty")
    # Accept either a hex SHA or a safe ref name
    if not (_GIT_SHA_RE.match(ref) or _GIT_REF_RE.match(ref)):
        raise ValueError(f"Invalid git ref: {ref!r}")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class ChangeStatus(str, Enum):
    """Classification of a file-level change between two commits."""

    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"


class ChangedFile(BaseModel):
    """A single file that differs between two git revisions."""

    path: str
    status: ChangeStatus


class GitClientError(Exception):
    """Raised when a git operation fails or the repository is invalid."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_git(
    cmd: list[str],
    repo_path: Path,
) -> subprocess.CompletedProcess[str]:
    """Execute a git command and return the completed process.

    Parameters
    ----------
    cmd:
        Command list (e.g. ``["git", "rev-parse", "HEAD"]``).
    repo_path:
        Working directory passed to the subprocess.

    Raises
    ------
    GitClientError
        On non-zero exit, timeout, or if the process cannot be started.
    """
    try:
        return subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise GitClientError(f"git command failed: {' '.join(cmd)}\n" f"Exit code {exc.returncode}: {stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitClientError(f"git command timed out after {_SUBPROCESS_TIMEOUT}s: {' '.join(cmd)}") from exc
    except FileNotFoundError as exc:
        raise GitClientError("git executable not found. Ensure git is installed and on PATH.") from exc


# Status letters emitted by `git diff --name-status`.  We map anything that
# is not A or D to MODIFIED (covers R, C, T, etc.).
_STATUS_MAP: dict[str, ChangeStatus] = {
    "A": ChangeStatus.ADDED,
    "D": ChangeStatus.DELETED,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_repo(repo_path: Path) -> None:
    """Verify that *repo_path* is the root of a git repository.

    Raises
    ------
    GitClientError
        If the ``.git`` directory does not exist or the path is not a
        directory.
    """
    if not repo_path.is_dir():
        raise GitClientError(f"Repository path does not exist: {repo_path}")
    if not (repo_path / ".git").exists():
        raise GitClientError(f"Not a git repository (no .git directory): {repo_path}")


def get_changed_files(
    repo_path: Path,
    base_sha: str,
    target_sha: str,
) -> list[ChangedFile]:
    """Return SQL files that changed between *base_sha* and *target_sha*.

    Only files matching the ``*.sql`` glob are included.  The returned list
    is sorted by file path for deterministic ordering.

    Parameters
    ----------
    repo_path:
        Root of the git repository.
    base_sha:
        The base commit SHA (e.g. main branch HEAD).
    target_sha:
        The target commit SHA (e.g. feature branch HEAD).
    """
    _validate_git_ref(base_sha)
    _validate_git_ref(target_sha)

    result = _run_git(
        ["git", "diff", "--name-status", base_sha, target_sha, "--", "*.sql"],
        repo_path,
    )

    changed: list[ChangedFile] = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t", maxsplit=1)
        if len(parts) != 2:
            logger.warning("Skipping unparseable diff line: %s", line)
            continue
        raw_status, file_path = parts
        # The status letter may include a numeric similarity score for
        # renames/copies (e.g. "R100").  Take only the first character.
        status_char = raw_status[0]
        status = _STATUS_MAP.get(status_char, ChangeStatus.MODIFIED)
        changed.append(ChangedFile(path=file_path, status=status))

    changed.sort(key=lambda f: f.path)
    return changed


def get_file_at_commit(
    repo_path: Path,
    sha: str,
    file_path: str,
) -> str:
    """Return the contents of *file_path* as it existed at *sha*.

    Parameters
    ----------
    repo_path:
        Root of the git repository.
    sha:
        The commit hash to read from.
    file_path:
        Repository-relative path to the file.

    Raises
    ------
    GitClientError
        If the file does not exist at the given commit or git fails.
    """
    _validate_git_ref(sha)

    result = _run_git(
        ["git", "show", f"{sha}:{file_path}"],
        repo_path,
    )
    return result.stdout


def get_current_sha(repo_path: Path) -> str:
    """Return the full SHA of the current HEAD commit.

    Raises
    ------
    GitClientError
        If the repository has no commits or git fails.
    """
    result = _run_git(
        ["git", "rev-parse", "HEAD"],
        repo_path,
    )
    return result.stdout.strip()
