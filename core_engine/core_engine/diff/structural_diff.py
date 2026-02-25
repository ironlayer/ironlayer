"""Structural diff engine for comparing SQL model snapshots by content hash.

Compares two dictionaries mapping model names to their canonical SQL hashes and
produces a deterministic :class:`DiffResult` classifying each model as added,
removed, or modified.  This is the *fast path* -- no SQL parsing is involved,
only hash equality checks.

All output lists are sorted alphabetically and all dictionary keys are sorted to
guarantee that identical inputs always produce byte-identical JSON.
"""

from __future__ import annotations

from core_engine.models.diff import DiffResult, HashChange


def compute_structural_diff(
    previous_versions: dict[str, str],
    current_versions: dict[str, str],
) -> DiffResult:
    """Compare two snapshots by content hash and classify every model.

    Parameters
    ----------
    previous_versions:
        Mapping of ``model_name -> canonical_sql_hash`` for the *base* (old)
        snapshot.
    current_versions:
        Mapping of ``model_name -> canonical_sql_hash`` for the *target* (new)
        snapshot.

    Returns
    -------
    DiffResult
        A fully-populated diff result with deterministically sorted lists and
        hash-change entries.
    """
    previous_keys = set(previous_versions)
    current_keys = set(current_versions)

    # Models present in target but absent from base.
    added_models: list[str] = sorted(current_keys - previous_keys)

    # Models present in base but absent from target.
    removed_models: list[str] = sorted(previous_keys - current_keys)

    # Models present in both snapshots whose content hash differs.
    common_keys = previous_keys & current_keys
    modified_models: list[str] = sorted(
        name for name in common_keys if previous_versions[name] != current_versions[name]
    )

    # Build the hash-change mapping for modified models only.  Keys are sorted
    # deterministically so serialisation is stable.
    hash_changes: dict[str, HashChange] = {
        name: HashChange(
            old_hash=previous_versions[name],
            new_hash=current_versions[name],
        )
        for name in modified_models
    }

    return DiffResult(
        added_models=added_models,
        removed_models=removed_models,
        modified_models=modified_models,
        hash_changes=hash_changes,
    )
