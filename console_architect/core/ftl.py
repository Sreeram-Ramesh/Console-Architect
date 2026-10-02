"""FTL: write amplification, GC policy, and the pSLC write-cache state machine."""
from __future__ import annotations

GC_POLICIES = {
    #            mean s between stalls, stall ms, WAF multiplier, background W, firmware $
    "lazy":       dict(interval_s=45.0, stall_ms=220.0, waf_mult=1.25, bg_w=0.05, usd=0.0),
    "aggressive": dict(interval_s=10.0, stall_ms=90.0,  waf_mult=1.00, bg_w=0.35, usd=0.4),
    "idle":       dict(interval_s=30.0, stall_ms=35.0,  waf_mult=0.92, bg_w=0.10, usd=1.2),
}


def waf_greedy(op_pct: float) -> float:
    """Greedy-GC, uniform random writes: (1+OP)/(2*OP)."""
    op = op_pct / 100.0
    return (1.0 + op) / (2.0 * op)


def waf_eff(op_pct: float, gc: str, pslc_pct: float = 0.0, randomness: float = 0.15) -> float:
    """Game workloads are mostly sequential, so only a fraction of the random-write worst case applies."""
    base = 1.0 + (waf_greedy(op_pct) - 1.0) * randomness
    return max(1.0, base * GC_POLICIES[gc]["waf_mult"] * (1.0 + 0.01 * pslc_pct))


def gc_interval_s(op_pct: float, gc: str, write_pressure: float = 1.0) -> float:
    return GC_POLICIES[gc]["interval_s"] * (op_pct / 7.0) / max(0.05, write_pressure)


def gc_stall_ms(op_pct: float, gc: str) -> float:
    return GC_POLICIES[gc]["stall_ms"] * (7.0 / op_pct) ** 0.5


def tbw_tb(capacity_gb: float, pe_max: float, waf: float) -> float:
    return capacity_gb * pe_max / 1000.0 / waf


class PslcCache:
    """pSLC write cache. Fast until full, then the native (QLC/TLC) rate; refills only when idle."""

    def __init__(self, size_mb: float, pslc_mbps: float, native_mbps: float):
        self.size_mb, self.free_mb = size_mb, size_mb
        self.pslc, self.native = pslc_mbps, native_mbps

    def write_time(self, mb: float) -> float:
        fast = min(mb, self.free_mb)
        self.free_mb -= fast
        slow = mb - fast
        return fast / self.pslc + slow / self.native

    def idle(self, seconds: float, fold_mbps: float) -> None:
        self.free_mb = min(self.size_mb, self.free_mb + seconds * fold_mbps)

    @property
    def fill(self) -> float:
        return 0.0 if self.size_mb <= 0 else 1.0 - self.free_mb / self.size_mb
