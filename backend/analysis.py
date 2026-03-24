# Data analysis: Pearson correlation coefficient, covariance matrix, etc.
# Input is a flat list of history data [{ name, time, value }, ...], aligned by time.

import numpy as np
from collections import defaultdict


def _short_name(name: str) -> str:
    """Shorten the name for display."""
    if ">" in name:
        return name.split(">")[-1]
    if "/" in name:
        return name.split("/")[-1]
    return name


def flat_to_aligned_matrix(flat: list) -> tuple[list[str], np.ndarray] | None:
    """
    Align the flat list by time to a matrix.
    flat: [{ "name": str, "time": int, "value": float }, ...]
    Return: (labels, matrix), matrix shape (n_series, n_times), only keep the time points that all series have values.
    If the data is not enough, return None.
    """
    if not flat:
        return None
    # Group by name -> name -> [(time, value), ...]
    by_name = defaultdict(list)
    for item in flat:
        n = item.get("name") or "unknown"
        t = item.get("time")
        v = item.get("value")
        if t is None:
            continue
        try:
            val = float(v)
            if np.isnan(val):
                continue
        except (TypeError, ValueError):
            continue
        by_name[n].append((t, val))

    if not by_name:
        return None
    labels = sorted(by_name.keys())
    # Keep the time points that exist in all series
    time_to_idx = {}
    for name in labels:
        for t, _ in by_name[name]:
            time_to_idx[t] = time_to_idx.get(t, 0) + 1
    n_series = len(labels)
    # Only keep the time points that exist in all series (count == n_series)
    common_times = sorted([t for t, count in time_to_idx.items() if count == n_series])
    if len(common_times) < 2:
        return None
    # For each series, take the values at common_times
    name_to_vals = {}
    for name in labels:
        t2v = dict(by_name[name])
        name_to_vals[name] = [t2v[t] for t in common_times]
    matrix = np.array([name_to_vals[n] for n in labels], dtype=float)
    return labels, matrix


def pearson_correlation(matrix: np.ndarray) -> np.ndarray:
    """
    matrix: (n_series, n_times)
    Return the Pearson correlation coefficient matrix of (n_series, n_series).
    """
    return np.corrcoef(matrix)


def covariance_matrix(matrix: np.ndarray) -> np.ndarray:
    """
    matrix: (n_series, n_times)
    Return the covariance matrix of (n_series, n_series). numpy defaults to each row being a variable.
    """
    return np.cov(matrix)


def spearman_correlation(matrix: np.ndarray) -> np.ndarray | None:
    """
    matrix: (n_series, n_times)
    Return the Spearman rank correlation coefficient matrix of (n_series, n_series); if scipy is not available, return None.
    """
    try:
        from scipy import stats
    except ImportError:
        return None
    n = matrix.shape[0]
    out = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            r, _ = stats.spearmanr(matrix[i], matrix[j])
            out[i, j] = r if not np.isnan(r) else 0.0
            out[j, i] = out[i, j]
    return out


def run_analysis(flat: list, include_spearman: bool = False) -> dict | None:
    """
    Do correlation/covariance analysis on the flat history data.
    Return: {
        "labels": ["name1", "name2", ...], # The original names
        "labels_short": ["short1", ...], # The short names
        "pearson": [[...], ...], # The Pearson correlation coefficient matrix
        "covariance": [[...], ...], # The covariance matrix
        "spearman": [[...], ...]  # Only when include_spearman and scipy is available
        "count": int  # The number of time points used for calculation
    }, If the data is not enough, return None.
    """
    aligned = flat_to_aligned_matrix(flat)
    if aligned is None:
        return None
    labels, matrix = aligned
    labels_short = [_short_name(n) for n in labels]
    pearson = pearson_correlation(matrix).tolist()
    cov = covariance_matrix(matrix).tolist()
    result = {
        "labels": labels,
        "labels_short": labels_short,
        "pearson": pearson,
        "covariance": cov,
        "count": matrix.shape[1],
    }
    if include_spearman:
        sp = spearman_correlation(matrix)
        if sp is not None:
            result["spearman"] = sp.tolist()
    return result
