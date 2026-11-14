"""Learning loop (v2): fit the category weights to real outcomes.

v1's weights (Fit 30 / Value 25 / Timing 25 / Intent 20) were a judgment call.
Once sales has filled in the `outcome` column for enough leads, this module:

  1. fits a logistic regression of outcome on the four category scores,
  2. turns the positive coefficients into weights that sum to 1,
  3. checks the new weights with 5-fold cross-validation against the current
     ones (AUC: how often a converting lead is ranked above a non-converting one),
  4. recommends adopting them only if the held-out gain clears a threshold.

Pure Python on purpose: the label count is small (tens to hundreds), the model
has four inputs, and the scheduled job should not need numpy or a GPU.
"""
from __future__ import annotations
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from . import config
from .pipeline_report import outcome_label

CATEGORIES = ("fit", "value", "timing", "intent")
WEIGHT_FLOOR = 0.05  # no category is switched off entirely on limited data


def _features(row: dict) -> Optional[List[float]]:
    try:
        return [float(row[f"{c}_score"]) for c in CATEGORIES]
    except (KeyError, TypeError, ValueError):
        return None


def labelled_examples(rows: Sequence[dict]) -> Tuple[List[List[float]], List[int]]:
    X, y = [], []
    for r in rows:
        label = outcome_label(r.get("outcome", ""))
        x = _features(r)
        if label is not None and x is not None:
            X.append(x)
            y.append(label)
    return X, y


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def auc(scores: Sequence[float], y: Sequence[int]) -> float:
    """Probability a random positive outranks a random negative (ties count half)."""
    pos = [s for s, t in zip(scores, y) if t == 1]
    neg = [s for s, t in zip(scores, y) if t == 0]
    if not pos or not neg:
        return float("nan")
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1.0 if p > n else 0.5 if p == n else 0.0
    return wins / (len(pos) * len(neg))


def precision_at_top(scores: Sequence[float], y: Sequence[int], share: float = 0.2) -> float:
    k = max(1, int(round(len(scores) * share)))
    top = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
    return sum(y[i] for i in top) / k


def weighted_scores(X: Sequence[Sequence[float]], weights: Dict[str, float]) -> List[float]:
    w = [weights[c] for c in CATEGORIES]
    return [sum(wi * xi for wi, xi in zip(w, x)) for x in X]


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def _fit_logistic(X: Sequence[Sequence[float]], y: Sequence[int],
                  l2: float = 0.1, lr: float = 0.1, iters: int = 3000) -> List[float]:
    """L2-regularised logistic regression by gradient descent.

    Fits on standardised features for stable convergence, then returns the
    coefficients on the original 0-10 scale (intercept dropped: it does not
    affect ranking).
    """
    n, d = len(X), len(X[0])
    means = [sum(x[j] for x in X) / n for j in range(d)]
    stds = [math.sqrt(sum((x[j] - means[j]) ** 2 for x in X) / n) or 1.0 for j in range(d)]
    Z = [[(x[j] - means[j]) / stds[j] for j in range(d)] for x in X]

    b = [0.0] * d
    b0 = 0.0
    for _ in range(iters):
        g = [0.0] * d
        g0 = 0.0
        for z, t in zip(Z, y):
            m = b0 + sum(bj * zj for bj, zj in zip(b, z))
            p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, m))))
            err = p - t
            g0 += err
            for j in range(d):
                g[j] += err * z[j]
        b0 -= lr * g0 / n
        for j in range(d):
            b[j] -= lr * (g[j] / n + l2 * b[j])
    return [b[j] / stds[j] for j in range(d)]


def coefficients_to_weights(coefs: Sequence[float]) -> Optional[Dict[str, float]]:
    """Positive coefficients -> weights summing to 1, each at least WEIGHT_FLOOR."""
    pos = [max(c, 0.0) for c in coefs]
    total = sum(pos)
    if total <= 0:
        return None  # nothing predicts conversion positively; keep current weights
    raw = [p / total for p in pos]
    # Pin anything under the floor to the floor, and share what is left among
    # the rest in proportion; repeat until no weight falls under the floor.
    pinned = [False] * len(raw)
    while True:
        free = sum(r for r, p in zip(raw, pinned) if not p)
        budget = 1.0 - WEIGHT_FLOOR * sum(pinned)
        w = [WEIGHT_FLOOR if p else (r / free * budget if free else 0.0) for r, p in zip(raw, pinned)]
        newly = [i for i, (wi, p) in enumerate(zip(w, pinned)) if not p and wi < WEIGHT_FLOOR]
        if not newly:
            break
        for i in newly:
            pinned[i] = True
    weights = {c: round(wi, 3) for c, wi in zip(CATEGORIES, w)}
    # Rounding can leave the sum at 0.999 or 1.001; put the remainder on the largest.
    top = max(weights, key=weights.get)
    weights[top] = round(weights[top] + 1.0 - sum(weights.values()), 3)
    return weights


def fit_weights(X, y) -> Optional[Dict[str, float]]:
    return coefficients_to_weights(_fit_logistic(X, y))


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
@dataclass
class LearnResult:
    n_labels: int
    n_positive: int
    current_weights: Dict[str, float]
    learned_weights: Optional[Dict[str, float]]
    current_auc: float
    cv_auc: float
    current_precision_top20: float
    learned_precision_top20: float
    recommend: bool
    message: str

    def to_plain_text(self) -> str:
        lines = [
            "=" * 78,
            f"LEARN — {self.n_labels} labelled leads ({self.n_positive} positive)",
            "=" * 78,
        ]
        if self.learned_weights is None:
            lines += [f"  {self.message}", "=" * 78]
            return "\n".join(lines)
        lines.append(f"  {'category':10s} {'current':>8s} {'learned':>8s}")
        for c in CATEGORIES:
            lines.append(f"  {c:10s} {self.current_weights[c]:8.2f} {self.learned_weights[c]:8.2f}")
        lines += [
            "",
            f"  AUC, current weights:            {self.current_auc:.3f}",
            f"  AUC, learned (5-fold held-out):  {self.cv_auc:.3f}",
            f"  Conversion in top 20%, current:  {self.current_precision_top20:.0%}",
            f"  Conversion in top 20%, learned:  {self.learned_precision_top20:.0%}  (held-out)",
            "",
            f"  → {self.message}",
            "=" * 78,
        ]
        return "\n".join(lines)


def _folds(n: int, k: int, seed: int) -> List[List[int]]:
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    return [idx[i::k] for i in range(k)]


def learn(rows: Sequence[dict], k: int = 5, seed: int = 7) -> LearnResult:
    X, y = labelled_examples(rows)
    n, n_pos = len(y), sum(y)
    current = dict(config.CATEGORY_WEIGHTS)

    def refuse(msg: str) -> LearnResult:
        return LearnResult(n, n_pos, current, None, float("nan"), float("nan"),
                           float("nan"), float("nan"), False, msg)

    if n < config.MIN_LABELS_TO_LEARN:
        return refuse(f"Need at least {config.MIN_LABELS_TO_LEARN} leads with a known outcome; have {n}. "
                      f"Keeping current weights.")
    if min(n_pos, n - n_pos) < config.MIN_PER_CLASS_TO_LEARN:
        return refuse(f"Need at least {config.MIN_PER_CLASS_TO_LEARN} positive and negative outcomes each; "
                      f"have {n_pos} positive, {n - n_pos} negative. Keeping current weights.")

    learned = fit_weights(X, y)
    if learned is None:
        return refuse("No category score predicts conversion positively on this data. Keeping current weights; "
                      "the signals themselves need work.")

    # Held-out scores: each lead is scored by weights fitted without it.
    held_out = [0.0] * n
    for fold in _folds(n, k, seed):
        fold_set = set(fold)
        train = [i for i in range(n) if i not in fold_set]
        w = fit_weights([X[i] for i in train], [y[i] for i in train]) or current
        for i, s in zip(fold, weighted_scores([X[i] for i in fold], w)):
            held_out[i] = s

    cur_scores = weighted_scores(X, current)
    cur_auc, cv_auc = auc(cur_scores, y), auc(held_out, y)
    gain = cv_auc - cur_auc
    recommend = gain >= config.MIN_AUC_GAIN_TO_ADOPT
    if recommend:
        msg = (f"Adopt: learned weights rank held-out leads better (+{gain:.3f} AUC). "
               f"Re-run with --write to apply them.")
    else:
        msg = (f"Keep current weights: held-out gain {gain:+.3f} AUC is below the "
               f"{config.MIN_AUC_GAIN_TO_ADOPT:.2f} bar.")
    return LearnResult(
        n_labels=n, n_positive=n_pos, current_weights=current, learned_weights=learned,
        current_auc=cur_auc, cv_auc=cv_auc,
        current_precision_top20=precision_at_top(cur_scores, y),
        learned_precision_top20=precision_at_top(held_out, y),
        recommend=recommend, message=msg,
    )


def write_weights(result: LearnResult, path: str = None) -> str:
    path = path or config.LEARNED_WEIGHTS_PATH
    payload = {
        "weights": result.learned_weights,
        "n_labels": result.n_labels,
        "n_positive": result.n_positive,
        "current_auc": round(result.current_auc, 4),
        "cv_auc": round(result.cv_auc, 4),
        "previous_weights": result.current_weights,
        "fitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path
