"""Pure, stateless, deterministic metric functions for AI engine evaluation.

All functions operate on plain Python lists and return plain Python dicts
or floats.  No side effects, no logging, no external dependencies beyond
the standard library.
"""

from __future__ import annotations


def confusion_matrix(
    predictions: list[str],
    actuals: list[str],
    labels: list[str],
) -> dict[str, dict[str, int]]:
    """Build a confusion matrix as a nested dict.

    Returns ``{actual_label: {predicted_label: count}}``.
    All label combinations are initialised to zero so the matrix is always
    complete even for labels that never appear in the data.

    Parameters
    ----------
    predictions:
        Predicted labels, one per sample.
    actuals:
        Ground-truth labels, one per sample.
    labels:
        Complete list of possible labels (defines matrix dimensions).
    """
    if len(predictions) != len(actuals):
        raise ValueError(f"predictions ({len(predictions)}) and actuals ({len(actuals)}) " f"must have the same length")

    matrix: dict[str, dict[str, int]] = {actual: {predicted: 0 for predicted in labels} for actual in labels}

    for pred, actual in zip(predictions, actuals, strict=False):
        if actual in matrix and pred in matrix[actual]:
            matrix[actual][pred] += 1

    return matrix


def precision_recall_f1(
    predictions: list[str],
    actuals: list[str],
    labels: list[str],
) -> dict[str, dict[str, float]]:
    """Compute per-label and macro-averaged precision, recall, and F1.

    Returns a dict keyed by label name (plus ``"macro"`` for the average)
    where each value is ``{"precision": ..., "recall": ..., "f1": ...}``.

    Parameters
    ----------
    predictions:
        Predicted labels, one per sample.
    actuals:
        Ground-truth labels, one per sample.
    labels:
        Complete list of possible labels.
    """
    matrix = confusion_matrix(predictions, actuals, labels)
    results: dict[str, dict[str, float]] = {}

    precisions: list[float] = []
    recalls: list[float] = []
    f1s: list[float] = []

    for label in labels:
        # True positives: correctly predicted as this label.
        tp = matrix[label][label]

        # False positives: predicted as this label but actually something else.
        fp = sum(matrix[other][label] for other in labels if other != label)

        # False negatives: actually this label but predicted as something else.
        fn = sum(matrix[label][other] for other in labels if other != label)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        results[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)

    # Macro average across all labels.
    n = len(labels) if labels else 1
    results["macro"] = {
        "precision": round(sum(precisions) / n, 4),
        "recall": round(sum(recalls) / n, 4),
        "f1": round(sum(f1s) / n, 4),
    }

    return results


def mean_absolute_error(
    predicted: list[float],
    actual: list[float],
) -> float:
    """Compute mean absolute error between predicted and actual values.

    Parameters
    ----------
    predicted:
        Predicted numeric values.
    actual:
        Ground-truth numeric values.
    """
    if len(predicted) != len(actual):
        raise ValueError(f"predicted ({len(predicted)}) and actual ({len(actual)}) " f"must have the same length")
    if not predicted:
        return 0.0

    total = sum(abs(p - a) for p, a in zip(predicted, actual, strict=False))
    return round(total / len(predicted), 6)


def confidence_calibration(
    predictions: list[tuple[float, bool]],
) -> dict[str, float]:
    """Assess calibration of confidence scores against actual correctness.

    Groups predictions into four confidence buckets and computes the actual
    accuracy (fraction correct) in each bucket.  A well-calibrated model
    should have bucket accuracy close to the bucket's midpoint.

    Parameters
    ----------
    predictions:
        List of ``(confidence_score, was_correct)`` tuples.

    Returns
    -------
    dict[str, float]
        Keys are bucket names (``"0.0-0.3"``, ``"0.3-0.6"``, ``"0.6-0.8"``,
        ``"0.8-1.0"``), values are the actual accuracy in that bucket.
        If a bucket is empty, its value is ``0.0``.
    """
    buckets: dict[str, list[bool]] = {
        "0.0-0.3": [],
        "0.3-0.6": [],
        "0.6-0.8": [],
        "0.8-1.0": [],
    }

    for confidence, correct in predictions:
        if confidence < 0.3:
            buckets["0.0-0.3"].append(correct)
        elif confidence < 0.6:
            buckets["0.3-0.6"].append(correct)
        elif confidence < 0.8:
            buckets["0.6-0.8"].append(correct)
        else:
            buckets["0.8-1.0"].append(correct)

    return {name: round(sum(items) / len(items), 4) if items else 0.0 for name, items in buckets.items()}


def accuracy(
    predictions: list[object],
    actuals: list[object],
) -> float:
    """Compute simple accuracy (fraction of correct predictions).

    Parameters
    ----------
    predictions:
        Predicted values (any comparable type).
    actuals:
        Ground-truth values.
    """
    if len(predictions) != len(actuals):
        raise ValueError(f"predictions ({len(predictions)}) and actuals ({len(actuals)}) " f"must have the same length")
    if not predictions:
        return 0.0

    correct = sum(1 for p, a in zip(predictions, actuals, strict=False) if p == a)
    return round(correct / len(predictions), 4)
