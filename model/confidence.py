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
3. Recent model error — the held-out test R2 recorded at training time
   (stored in the checkpoint), already normalized against the target's own
   variance. A model that already showed weak explanatory power on its own
   test set should report lower confidence on every window it produces,
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


def _model_error_score(test_r2: float) -> float:
    """1.0 when the model's recorded held-out test R2 is perfect (explains
    all target variance), decaying toward 0 as R2 approaches 0 (no better
    than predicting the mean) or goes negative (worse than that).

    Previously this compared test_rmse against a hand-rolled "typical_scale"
    (mean(abs(y_mean)) -- the mean of the target's own per-horizon-step
    MEAN value). That's a central-tendency measure, not a spread measure,
    and RMSE is fundamentally a spread/error quantity -- comparing it
    against the wrong kind of baseline produced a relative_error of ~0.81
    for this project's actual checkpoint (model_error_score ~0.19), which
    is below the 0.5 low-confidence threshold for every window regardless
    of input, since this component never varies per-window in the first
    place (it's a fixed property of the trained checkpoint). Swapping in
    mean(abs(y_std)) -- a real spread measure -- barely moved the needle
    (relative_error ~0.85, if anything worse), confirming the baseline
    itself was the wrong concept, not just the wrong array.

    R2 is already RMSE properly normalized against the target's own
    variance (R2 = 1 - SS_res/SS_tot, which reduces to ~1 - MSE/Var(y) for
    a single global fit) -- exactly the "is this error large or small
    relative to what we're predicting" question this score exists to
    answer, computed the statistically standard way instead of
    reinvented. It's already computed and stored in the checkpoint
    (test_metrics['r2']), so this also removes an unnecessary derived
    quantity (typical_scale) rather than adding one.
    """
    return float(np.clip(test_r2, 0.0, 1.0))


def score_window_confidence(
    net_flow_window: np.ndarray,
    observed_days: int,
    lookback: int,
    test_r2: float,
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
    test_r2 : the held-out test R2 recorded in the model checkpoint --
        already RMSE normalized against the target's own variance, the
        correct baseline for "is this model's error large or small"
        (see _model_error_score).
    """
    history_score = _history_completeness_score(observed_days, lookback)
    volatility_score = _volatility_score(net_flow_window)
    model_error_score = _model_error_score(test_r2)

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
