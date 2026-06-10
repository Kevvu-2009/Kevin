"""Purged & embargoed K-fold cross-validation for financial time series.

Why ordinary K-fold leaks
-------------------------
A label at time ``t`` is realised over ``(t, t + horizon]``.  If a training
sample's label window overlaps the test fold, the model is effectively shown
the test outcome ("leakage through the label").  Serial correlation leaks a
little further still, hence an additional *embargo* after each test fold.

This is the standard remedy from López de Prado, *Advances in Financial
Machine Learning* (2018), ch. 7.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PurgedKFold:
    """Contiguous, chronological folds with purging and embargo.

    Args:
        n_splits: number of contiguous test folds.
        label_horizon: bars over which each label is realised; training
            samples within ``label_horizon`` *before* a test fold are purged
            (their label window reaches into the fold).
        embargo: extra bars dropped from training *after* each test fold to
            absorb serial correlation.
    """

    n_splits: int = 5
    label_horizon: int = 1
    embargo: int = 0

    def split(self, n_samples: int):
        if self.n_splits < 2:
            raise ValueError("n_splits must be >= 2")
        if n_samples < self.n_splits * 2:
            raise ValueError("not enough samples for the requested folds")
        indices = np.arange(n_samples)
        fold_bounds = np.array_split(indices, self.n_splits)
        for fold in fold_bounds:
            test_start, test_end = fold[0], fold[-1]
            train_mask = np.ones(n_samples, dtype=bool)
            # The test fold itself.
            train_mask[test_start : test_end + 1] = False
            # Purge: samples before the fold whose label window enters it.
            purge_lo = max(0, test_start - self.label_horizon)
            train_mask[purge_lo:test_start] = False
            # Embargo: samples right after the fold.
            emb_hi = min(n_samples, test_end + 1 + self.embargo)
            train_mask[test_end + 1 : emb_hi] = False
            yield indices[train_mask], fold

    def get_n_splits(self) -> int:  # sklearn-compatible
        return self.n_splits
