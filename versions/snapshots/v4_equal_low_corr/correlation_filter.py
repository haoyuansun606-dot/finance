"""Select equity indices with low pairwise correlation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.corr()


def greedy_drop_correlated(
    returns: pd.DataFrame,
    threshold: float = 0.85,
) -> tuple[list[str], list[str], pd.DataFrame]:
    """
    Iteratively drop the asset with higher mean |corr| when a pair exceeds threshold.
    Returns (kept, dropped, corr_matrix).
    """
    corr = returns.corr().fillna(0.0)
    remaining = list(corr.columns)
    dropped: list[str] = []

    while len(remaining) > 1:
        sub = corr.loc[remaining, remaining]
        max_corr = -1.0
        pair: tuple[str, str] | None = None
        for i, a in enumerate(remaining):
            for b in remaining[i + 1 :]:
                c = abs(sub.loc[a, b])
                if c > max_corr:
                    max_corr = c
                    pair = (a, b)
        if pair is None or max_corr <= threshold:
            break
        a, b = pair
        others_a = sub.loc[a, [x for x in remaining if x != a]].abs().mean()
        others_b = sub.loc[b, [x for x in remaining if x != b]].abs().mean()
        drop = a if others_a >= others_b else b
        remaining.remove(drop)
        dropped.append(drop)

    return remaining, dropped, corr


def cluster_representatives(
    returns: pd.DataFrame,
    threshold: float = 0.85,
) -> tuple[list[str], list[str], pd.DataFrame]:
    """
    Hierarchical cluster on distance = 1 - |corr|; keep one name per cluster.
    Representative = asset with lowest average |corr| to cluster peers.
    """
    corr = returns.corr().fillna(0.0)
    assets = list(corr.columns)
    dist = 1.0 - corr.abs().values
    np.fill_diagonal(dist, 0.0)
    dist = np.clip(dist, 0.0, None)
    condensed = squareform(dist, checks=False)
    z = linkage(condensed, method="average")
    labels = fcluster(z, t=1.0 - threshold, criterion="distance")

    kept: list[str] = []
    dropped: list[str] = []
    for cluster_id in sorted(set(labels)):
        members = [assets[i] for i, lab in enumerate(labels) if lab == cluster_id]
        if len(members) == 1:
            kept.append(members[0])
            continue
        sub = corr.loc[members, members]
        scores = {m: sub.loc[m, members].drop(m).abs().mean() for m in members}
        rep = min(scores, key=scores.get)
        kept.append(rep)
        dropped.extend([m for m in members if m != rep])

    return kept, dropped, corr


def select_stock_universe(
    returns: pd.DataFrame,
    method: str = "cluster",
    threshold: float = 0.85,
) -> dict:
    if method == "greedy":
        kept, dropped, corr = greedy_drop_correlated(returns, threshold)
    else:
        kept, dropped, corr = cluster_representatives(returns, threshold)

    return {
        "kept": kept,
        "dropped": dropped,
        "corr": corr,
        "threshold": threshold,
        "method": method,
    }
