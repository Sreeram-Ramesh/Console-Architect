"""Static spec-sheet estimate for the Build screen (no simulation run needed)."""
from __future__ import annotations

from dataclasses import dataclass

from . import ftl
from .bom import bom_lines, totals
from .build import Build, phy_config
from .engine import COOLING_R, NAND_RISE_K_PER_W
from .levels import Level
from .phy import EyeResult, corner_sweep
from .storage import StoragePerf, chunk_bw, perf

DAILY_WRITE_GB = {"gb": 8.0, "deck": 120.0}


@dataclass(frozen=True)
class Spec:
    fits: bool
    need_gb: float
    patch_s: float
    load_s: float
    supply_mbps: float
    demand_peak_mbps: float
    supply_ratio: float
    freezes_per_min: float
    worst_hitch_ms: float
    battery_h: float
    mean_w: float
    temp_case: float
    temp_nand: float
    corner_fail: int
    corner_total: int
    worst_slack_ps: float
    worst_corner: str
    life_years: float | None
    bom: float
    retail: float
    lines: tuple
    limiter: str
    eye: EyeResult | None
    perf: StoragePerf


def estimate(b: Build, L: Level) -> Spec:
    amb = L.ambient_c
    t_case = amb + 2.0
    avg_speed = 0.5 * (L.speed0 + L.speed1)
    R = L.r_base * COOLING_R[b.cooling]
    p = perf(b, round(t_case / 2) * 2.0, L.pe_fraction)
    mean_w = L.soc_w
    for _ in range(8):
        t_nand = t_case + NAND_RISE_K_PER_W * p.idle_w
        p = perf(b, float(round(t_nand / 2) * 2), L.pe_fraction)
        util = min(1.0, avg_speed * L.mb_per_col / max(1.0, p.seq_read_mbps))
        sw = p.idle_w + (p.active_w - p.idle_w) * util + (p.gc_bg_w if b.nand_based else 0.0)
        t_nand = t_case + NAND_RISE_K_PER_W * sw
        thr = 1.0 if t_case <= L.throttle_c else max(0.35, 1.0 - 0.04 * (t_case - L.throttle_c))
        mean_w = L.soc_w * (0.6 + 0.4 * thr) + sw
        t_case = amb + R * mean_w
    t_nand = t_case + NAND_RISE_K_PER_W * sw
    p = perf(b, float(round(t_nand / 2) * 2), L.pe_fraction)

    # boot (cold, cache empty)
    p0 = perf(b, round((amb + 2.0) / 2) * 2.0, L.pe_fraction)
    cache = ftl.PslcCache(p0.pslc_gb * 1024, p0.write_pslc_mbps, p0.write_native_mbps)
    patch_s = cache.write_time(L.patch_gb * 1024) if L.patch_gb > 0 else 0.0
    load_s = L.load_gb * 1024 / p0.seq_read_mbps + p0.first_byte_ms / 1000

    supply = chunk_bw(p, L.chunk_mb)
    peak = L.speed1 * L.mb_per_col
    freezes, worst = 0.0, 0.0
    if b.nand_based:
        stall = ftl.gc_stall_ms(b.op_pct, b.gc)
        freezes += 60.0 / ftl.gc_interval_s(b.op_pct, b.gc, L.write_pressure)
        worst = max(worst, stall)
    if b.storage == "hdd" and avg_speed * L.mb_per_col > 0.4 * supply:
        freezes += 30.0
        worst = max(worst, 160.0)
    ms = min(3000.0, cache.write_time(L.autosave_mb) * 300.0)
    if ms > 50:
        freezes += 60.0 / L.autosave_every_s
        worst = max(worst, ms)

    if b.nand_based:
        nf, nt, ws, wn = corner_sweep(phy_config(b, 25.0))
    else:
        nf, nt, ws, wn = 0, 0, 0.0, "n/a"
    lines = bom_lines(b, L.base_bom_usd)
    bom, retail = totals(lines, L.markup)
    life = None if p.tbw_tb is None else min(99.0, p.tbw_tb * 1000.0 / DAILY_WRITE_GB[L.theme] / 365.0)
    return Spec(b.capacity_gb >= L.need_gb, L.need_gb, patch_s, load_s, supply, peak,
                supply / max(1.0, peak), freezes, worst, b.battery_wh / mean_w, mean_w, t_case, t_nand,
                nf, nt, ws, wn, life, bom, retail, tuple(lines), p.limiter, p.eye, p)
