"""ECC: uncorrectable-codeword probability and decode latency."""
from __future__ import annotations

import math

from .parts import EccConfig


def poisson_tail(lam: float, t: int) -> float:
    """P(X > t) for X ~ Poisson(lam), numerically careful in both regimes."""
    if lam <= 0.0:
        return 0.0
    log_lam = math.log(lam)

    def pmf(k: int) -> float:
        return math.exp(-lam + k * log_lam - math.lgamma(k + 1))

    if t < lam:  # tail is large: use complement of a short CDF sum
        cdf = sum(pmf(k) for k in range(0, t + 1))
        return min(1.0, max(0.0, 1.0 - cdf))
    tail, k = 0.0, t + 1
    while k < t + 1 + 400:
        p = pmf(k)
        tail += p
        if p < tail * 1e-18:
            break
        k += 1
    return min(1.0, tail)


def codeword_fail_prob(ecc: EccConfig, rber: float, soft: bool = False) -> float:
    n_bits = (ecc.codeword_bytes + ecc.parity_bytes) * 8
    t = int(ecc.t_correct * (ecc.soft_gain if soft else 1.0))
    return poisson_tail(n_bits * min(rber, 0.5), t)


def page_fail_prob(ecc: EccConfig, rber: float, page_bytes: int, soft: bool = False) -> float:
    p = codeword_fail_prob(ecc, rber, soft)
    n_cw = max(1, page_bytes // ecc.codeword_bytes)
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    return -math.expm1(n_cw * math.log1p(-p))


def decode_latency_us(ecc: EccConfig, rber: float, soft: bool = False) -> float:
    """Latency grows exponentially as the error load approaches correction capability."""
    n_bits = (ecc.codeword_bytes + ecc.parity_bytes) * 8
    load = (n_bits * min(rber, 0.5)) / max(1.0, ecc.t_correct)
    lat = ecc.decode_base_us * math.exp(min(6.0, 3.0 * load))
    return lat + (ecc.soft_decode_us if soft else 0.0)
