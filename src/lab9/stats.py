"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _norm(labels: Sequence[str]) -> list[str]:
    return [str(x).strip().upper() for x in labels]


def _pairs(human: Sequence[str], judge: Sequence[str]) -> list[tuple[str, str]]:
    h, j = _norm(human), _norm(judge)
    if len(h) != len(j):
        raise ValueError(f"human has {len(h)} labels, judge has {len(j)}")
    return list(zip(h, j))


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for h, j in _pairs(human, judge):
        if j == POS:
            cm["tp" if h == POS else "fp"] += 1
        else:
            cm["fn" if h == POS else "tn"] += 1
    return cm


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    """precision = tp/(tp+fp), recall = tp/(tp+fn); 0.0 when the denominator is 0."""
    cm = confusion(human, judge)
    p = cm["tp"] / (cm["tp"] + cm["fp"]) if cm["tp"] + cm["fp"] else 0.0
    r = cm["tp"] / (cm["tp"] + cm["fn"]) if cm["tp"] + cm["fn"] else 0.0
    return p, r


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    pairs = _pairs(human, judge)
    n = len(pairs)
    if n == 0:
        raise ValueError("kappa undefined: no labels")
    p_o = sum(h == j for h, j in pairs) / n
    cats = {c for pair in pairs for c in pair}
    p_e = sum((sum(h == c for h, _ in pairs) / n) * (sum(j == c for _, j in pairs) / n) for c in cats)
    if p_e >= 1.0:
        raise ValueError("kappa undefined: chance agreement is 1 (both raters constant)")
    return (p_o - p_e) / (1.0 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1].
    When sens + spec <= 1 the judge is no better than a coin and the rate cannot be
    corrected: return nan rather than a number that looks meaningful."""
    denom = sensitivity + specificity - 1.0
    if denom <= 0:
        return float("nan")
    return min(1.0, max(0.0, (observed_rate + specificity - 1.0) / denom))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy.stats import bootstrap

    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if x.shape != y.shape:
        raise ValueError(f"paired samples differ in length: {x.shape} vs {y.shape}")
    if x.size == 0:
        raise ValueError("paired bootstrap needs at least one item")
    if np.array_equal(x, y):
        return 0.0, 0.0, 0.0

    def diff(u, v, axis=-1):
        return np.mean(u, axis=axis) - np.mean(v, axis=axis)

    res = bootstrap((x, y), diff, paired=True, vectorized=True, n_resamples=n_resamples,
                    confidence_level=confidence, method="percentile", rng=np.random.default_rng(rng))
    lo, hi = res.confidence_interval
    return float(x.mean() - y.mean()), float(lo), float(hi)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    # TODO M6
    raise NotImplementedError


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    # TODO M6
    raise NotImplementedError
