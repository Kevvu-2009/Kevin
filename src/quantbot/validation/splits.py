"""In-sample / out-of-sample splitting (chronological, no shuffling)."""

from __future__ import annotations

import pandas as pd


def is_oos_split(df: pd.DataFrame, is_frac: float = 0.70) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a time-ordered frame into in-sample (first ``is_frac``) and OOS.

    Time-series data must never be shuffled: the OOS block is strictly *after*
    the in-sample block so the test mimics live deployment on unseen future.
    """
    if not 0.0 < is_frac < 1.0:
        raise ValueError("is_frac must be in (0, 1)")
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    cut = int(len(df) * is_frac)
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()
