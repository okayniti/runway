"""
Confidence scoring for cash-flow forecast windows.

Combines three independent reliability signals into a single per-window
confidence score in [0, 1]:

1. History completeness — how much of the requested lookback window is
   backed by real observed days vs. zero-padding for a business with less
   history than the model expects. Thin history means the model is
   extrapolating from less context than it was trained on.
2. Input volatility — the coefficient of variation of net cash flow over
   the lookback window. A business whose daily cash flow swings wildly is
   inherently harder to forecast than one with a smooth, repeating pattern.
3. Recent model error — the held-out test RMSE recorded at training time
   (stored in the checkpoint), expressed as a fraction of the typical cash
   position scale. A model that already showed high forecast error on its
   own test set should report lower confidence on every window it produces,
   not just the volatile ones.

None of these signals require ground truth for the window being scored —
confidence is computed purely from the input window and the model's
checkpoint stats, so it can run at inference time on live, unlabeled data.
The three scores are combined with a weakest-link (min) rule rather than an
average, so one badly-behaved signal pulls confidence down instead of being
smoothed away by two healthy ones.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ConfidenceBreakdown:
    """The overall confidence score plus the three component scores and
    human-readable reasons that produced it (see score_window_confidence)."""

    score: float  # overall confidence in [0, 1]; higher means more reliable
    is_low_confidence: bool
    history_completeness: float
    volatility_score: float
    model_error_score: float
    reasons: list[str]


def _history_completeness_score(observed_days: int, lookback: int) -> float:
    """1.0 when the full lookback window is backed by real data, decaying
    linearly toward 0 as fewer real days are available."""
    if lookback <= 0:
        return 0.0
    return float(np.clip(observed_days / lookback, 0.0, 1.0))


def _volatility_score(net_flow_window: np.ndarray) -> float:
    """1.0 for a smooth/stable window, decaying toward 0 as the coefficient
    of variation of net cash flow grows.

    Uses mean absolute value rather than the raw mean in the denominator,
    since net cash flow crosses zero and a near-zero mean would blow up a
    plain coefficient of variation.
    """
    mean_abs = float(np.mean(np.abs(net_flow_window)))
    std = float(np.std(net_flow_window))
    if mean_abs == 0:
        return 0.0 if std > 0 else 1.0
    cv = std / mean_abs
    # cv == 0 -> 1.0; cv >= 2.0 -> 0.0. The 2.0 ceiling is chosen so that
    # typical business volatility (cv roughly 0.5-1.5) lands mid-range
    # instead of being pinned to an extreme.
    return float(np.clip(1.0 - cv / 2.0, 0.0, 1.0))


def _model_error_score(test_rmse: float, typical_scale: float) -> float:
    """1.0 when the model's recorded held-out RMSE is small relative to the
    typical magnitude of the target series, decaying toward 0 as that
    relative error grows past 100%."""
    if typical_scale <= 0:
        return 0.5  # no reliable scale to compare against
    relative_error = test_rmse / typical_scale
    return float(np.clip(1.0 - relative_error, 0.0, 1.0))


def score_window_confidence(
    net_flow_window: np.ndarray,
    observed_days: int,
    lookback: int,
    test_rmse: float,
    typical_scale: float,
    low_confidence_threshold: float = 0.5,
) -> ConfidenceBreakdown:
    """Score a single forecast window's reliability.

    Parameters
    ----------
    net_flow_window : raw (unnormalized) net_flow feature values for the
        lookback window the forecast was made from.
    observed_days : how many of those `lookback` slots are backed by real
        transaction data, vs. zero-padding for a business with less history
        than the model expects.
    lookback : the model's configured lookback length.
    test_rmse : the held-out test RMSE recorded in the model checkpoint.
    typical_scale : a representative magnitude for the target (e.g. mean
        absolute cash_position over the training set), used to convert
        RMSE into a relative error.
    """
    history_score = _history_completeness_score(observed_days, lookback)
    volatility_score = _volatility_score(net_flow_window)
    model_error_score = _model_error_score(test_rmse, typical_scale)

    overall = min(history_score, volatility_score, model_error_score)

    reasons = []
    if history_score < low_confidence_threshold:
        reasons.append(f"only {observed_days}/{lookback} days of real history available")
    if volatility_score < low_confidence_threshold:
        reasons.append("input window shows high cash-flow volatility")
    if model_error_score < low_confidence_threshold:
        reasons.append("model's recorded test-set error is high relative to typical cash position")

    return ConfidenceBreakdown(
        score=overall,
        is_low_confidence=overall < low_confidence_threshold,
        history_completeness=history_score,
        volatility_score=volatility_score,
        model_error_score=model_error_score,
        reasons=reasons,
    )
