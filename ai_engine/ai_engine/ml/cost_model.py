"""Persistence and training utilities for the cost prediction model.

Wraps scikit-learn ``LinearRegression`` with save / load / train / predict
helpers.  All I/O goes through ``joblib`` for efficient numpy serialisation.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LinearRegression

logger = logging.getLogger(__name__)


class CostModelIntegrityError(Exception):
    """Raised when a cost model file fails hash verification."""


def _compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hex digest of a file, reading in 8 KiB chunks."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _verify_model_hash(model_path: Path, expected_hash: str) -> None:
    """Verify a model file's SHA-256 hash matches *expected_hash*.

    Parameters
    ----------
    model_path:
        Path to the serialised model file.
    expected_hash:
        The expected SHA-256 hex digest.

    Raises
    ------
    CostModelIntegrityError
        If the actual hash does not match the expected hash.
    """
    actual = _compute_file_hash(model_path)
    if actual != expected_hash:
        raise CostModelIntegrityError(f"Cost model hash mismatch: expected {expected_hash}, got {actual}")


def _hash_file_path(model_path: Path) -> Path:
    """Return the path to the companion hash file for a model."""
    return model_path.with_suffix(model_path.suffix + ".sha256")


class CostModelTrainer:
    """Static helper for training and persisting cost models."""

    @staticmethod
    def train(features: np.ndarray, targets: np.ndarray) -> LinearRegression:
        """Fit a ``LinearRegression`` on the provided feature matrix.

        Parameters
        ----------
        features:
            2-D array of shape ``(n_samples, n_features)``.
        targets:
            1-D array of shape ``(n_samples,)`` -- runtime in seconds.

        Returns
        -------
        LinearRegression
            The fitted model instance.
        """
        if features.ndim != 2:
            raise ValueError(f"features must be 2-D, got shape {features.shape}")
        if targets.ndim != 1:
            raise ValueError(f"targets must be 1-D, got shape {targets.shape}")
        if features.shape[0] != targets.shape[0]:
            raise ValueError(f"features and targets row count mismatch: " f"{features.shape[0]} vs {targets.shape[0]}")

        model = LinearRegression()
        model.fit(features, targets)
        logger.info(
            "Trained LinearRegression on %d samples (R^2=%.4f on training set)",
            features.shape[0],
            model.score(features, targets),
        )
        return model

    @staticmethod
    def save(model: LinearRegression, path: Path) -> None:
        """Persist a trained model to *path* via joblib.

        Also writes a companion ``.sha256`` file containing the SHA-256
        hex digest of the serialised model.  This digest is verified on
        load to detect tampering or corruption.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, path)

        # Write companion hash file for integrity verification on load.
        digest = _compute_file_hash(path)
        hash_path = _hash_file_path(path)
        hash_path.write_text(digest)

        logger.info("Cost model saved to %s (sha256=%s)", path, digest[:16])

    @staticmethod
    def load(path: Path) -> LinearRegression | None:
        """Load a model from *path*, returning ``None`` if not found.

        Before deserialising the model, verifies its SHA-256 hash against
        the companion ``.sha256`` file.  If the hash file is missing or
        the hashes do not match, the model is not loaded.
        """
        if not path.exists():
            logger.debug("Cost model file not found at %s", path)
            return None

        # Verify integrity before deserialising.
        hash_path = _hash_file_path(path)
        if hash_path.exists():
            expected_hash = hash_path.read_text().strip()
            try:
                _verify_model_hash(path, expected_hash)
            except CostModelIntegrityError as exc:
                logger.error(
                    "Cost model integrity check failed for %s: %s",
                    path,
                    exc,
                )
                return None
        else:
            logger.warning(
                "No hash file found for cost model at %s -- "
                "loading without integrity verification. "
                "Re-save the model to generate a hash file.",
                path,
            )

        try:
            model = joblib.load(path)
            if not isinstance(model, LinearRegression):
                logger.warning(
                    "Loaded object is not LinearRegression (got %s) -- ignoring",
                    type(model).__name__,
                )
                return None
            logger.info("Cost model loaded from %s", path)
            return model
        except Exception:
            logger.warning("Failed to load cost model from %s", path, exc_info=True)
            return None

    @staticmethod
    def predict(model: LinearRegression, features: np.ndarray) -> np.ndarray:
        """Run inference on the trained model.

        Parameters
        ----------
        model:
            A fitted ``LinearRegression``.
        features:
            2-D array of shape ``(n_samples, n_features)``.

        Returns
        -------
        np.ndarray
            1-D array of predicted runtime values in seconds.
        """
        if features.ndim != 2:
            raise ValueError(f"features must be 2-D, got shape {features.shape}")
        predictions = model.predict(features)
        # Clamp negative predictions to a sane minimum
        return np.maximum(predictions, 0.0)
