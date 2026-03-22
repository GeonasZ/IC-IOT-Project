# 数据分析：Pearson 相关系数、协方差矩阵等
# 输入为扁平化历史数据 [{ name, time, value }, ...]，按时间对齐后计算

import numpy as np
from collections import defaultdict


def _short_name(name: str) -> str:
    """取可读的短名称，用于表格显示。"""
    if ">" in name:
        return name.split(">")[-1]
    if "/" in name:
        return name.split("/")[-1]
    return name


def flat_to_aligned_matrix(flat: list) -> tuple[list[str], np.ndarray] | None:
    """
    将扁平列表按时间对齐为矩阵。
    flat: [{ "name": str, "time": int, "value": float }, ...]
    返回: (labels, matrix)，matrix 形状 (n_series, n_times)，仅保留所有序列都有值的时间点。
    若数据不足则返回 None。
    """
    if not flat:
        return None
    # 按名称分组 -> name -> [(time, value), ...]
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
    # 每个时间点若在所有序列中都存在，则保留
    time_to_idx = {}
    for name in labels:
        for t, _ in by_name[name]:
            time_to_idx[t] = time_to_idx.get(t, 0) + 1
    n_series = len(labels)
    # 只保留“所有序列都有该时间点”的时间（即出现次数 == n_series）
    common_times = sorted([t for t, count in time_to_idx.items() if count == n_series])
    if len(common_times) < 2:
        return None
    # 每个序列按 common_times 取值
    name_to_vals = {}
    for name in labels:
        t2v = dict(by_name[name])
        name_to_vals[name] = [t2v[t] for t in common_times]
    matrix = np.array([name_to_vals[n] for n in labels], dtype=float)
    return labels, matrix


def pearson_correlation(matrix: np.ndarray) -> np.ndarray:
    """
    matrix: (n_series, n_times)
    返回 (n_series, n_series) 的 Pearson 相关系数矩阵。
    """
    return np.corrcoef(matrix)


def covariance_matrix(matrix: np.ndarray) -> np.ndarray:
    """
    matrix: (n_series, n_times)
    返回 (n_series, n_series) 的协方差矩阵。numpy 默认每行是一个变量。
    """
    return np.cov(matrix)


def spearman_correlation(matrix: np.ndarray) -> np.ndarray | None:
    """
    matrix: (n_series, n_times)
    返回 (n_series, n_series) 的 Spearman 秩相关系数矩阵；若无 scipy 则返回 None。
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
    对扁平历史数据做相关性/协方差分析。
    返回: {
        "labels": ["name1", "name2", ...],
        "labels_short": ["short1", ...],
        "pearson": [[...], ...],
        "covariance": [[...], ...],
        "spearman": [[...], ...]  # 仅当 include_spearman 且 scipy 可用
        "count": int  # 用于计算的时间点数量
    }
    若数据不足返回 None。
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
