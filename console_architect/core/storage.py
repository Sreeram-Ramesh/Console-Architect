"""Storage performance, power and wear for each storage class, from the player's Build."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from . import ftl
from .build import LAYOUT_MM, Build, phy_config
from .nand import bus_mbps, expected_read_latency
from .parts import EccConfig, NandPart
from .phy import EyeResult, analyze
from .power import phy_power_mw

IFACE = {
    "sata": dict(cap=550.0, wcap=520.0, lat_ms=0.09, ctrl_w=0.45, idle_w=0.05, usd=2.5),
    "nvme": dict(cap=3200.0, wcap=3000.0, lat_ms=0.02, ctrl_w=0.90, idle_w=0.08, usd=6.0),
}
HDD = dict(seq=110.0, seek_ms=12.0, active_w=1.8, idle_w=0.7, usd=8.0, usd_per_gb=0.02)
RAM = dict(seq=20000.0, lat_ms=0.0001, w_per_gb=0.12, usd_per_gb=3.5, ctrl_usd=4.0)
DIE_W = 0.06                       # W per actively reading die
NAND_THROTTLE_C = 75.0


@lru_cache(maxsize=None)
def nand_part(name: str) -> NandPart:
    return NandPart.load(name)


@lru_cache(maxsize=None)
def ecc_cfg(name: str) -> EccConfig:
    return EccConfig.load(name)


def nand_throttle(temp_c: float) -> float:
    return 1.0 if temp_c <= NAND_THROTTLE_C else max(0.3, 1.0 - 0.05 * (temp_c - NAND_THROTTLE_C))


@dataclass(frozen=True)
class StoragePerf:
    kind: str
    seq_read_mbps: float
    first_byte_ms: float
    write_pslc_mbps: float
    write_native_mbps: float
    pslc_gb: float
    idle_w: float
    active_w: float
    gc_bg_w: float
    waf: float
    tbw_tb: float | None
    p_uncorr_page: float
    ber_phy: float
    crash_p_per_s: float
    eye: EyeResult | None
    volatile: bool
    limiter: str
    thermal_factor: float


def chunk_bw(perf: StoragePerf, chunk_mb: float) -> float:
    """Effective streaming bandwidth for chunked random reads (latency + transfer)."""
    return chunk_mb / (perf.first_byte_ms / 1000.0 + chunk_mb / perf.seq_read_mbps)


@lru_cache(maxsize=4096)
def perf(b: Build, temp_c: float = 25.0, pe_fraction: float = 0.3) -> StoragePerf:
    if b.storage == "hdd":
        return StoragePerf("hdd", HDD["seq"], HDD["seek_ms"], 100.0, 100.0, 0.0, HDD["idle_w"],
                           HDD["active_w"], 0.0, 1.0, None, 0.0, 0.0, 0.0, None, False,
                           "seek time + spindle speed", 1.0)
    if b.storage == "ramdisk":
        w = RAM["w_per_gb"] * b.capacity_gb
        return StoragePerf("ramdisk", RAM["seq"], RAM["lat_ms"], RAM["seq"], RAM["seq"], 0.0,
                           0.8 * w, w, 0.0, 1.0, None, 0.0, 0.0, 0.0, None, True,
                           "nothing (it is DRAM)", 1.0)

    part, ecc, iface = nand_part(b.cell), ecc_cfg(b.ecc), IFACE[b.storage]
    eye = analyze(phy_config(b, temp_c))
    lat = expected_read_latency(part, ecc, b.eff_mts, eye.ber,
                                pe_cycles=pe_fraction * part.pe_max, bus_bits=8)
    bus_cap = bus_mbps(b.eff_mts) * (0.92 if b.bus_mode == "ONFI" else 0.88)
    die_bw = b.dies * part.page_bytes / lat.total_us
    terms = {"SATA interface": iface["cap"] if b.storage == "sata" else 1e9,
             "NVMe link": iface["cap"] if b.storage == "nvme" else 1e9,
             "ECC engine": ecc.max_mbps,
             "NAND bus": b.channels * bus_cap,
             "NAND array read time (tR)": b.channels * die_bw}
    limiter = min(terms, key=terms.get)
    if lat.mean_retries > 0.3 or lat.p_uncorrectable > 1e-4:
        limiter = "read retries (eye too closed / ECC overloaded)"
    thr = nand_throttle(temp_c)
    if thr < 0.9:
        limiter = "NAND thermal throttle"
    seq = min(terms.values()) * thr

    scale = b.total_dies / 4.0
    native = min(part.native_write_mbps * scale, iface["wcap"]) * thr
    pslc = min(part.pslc_write_mbps * scale, iface["wcap"]) * thr
    pslc_gb = b.capacity_gb * b.pslc_pct / 100.0
    if pslc_gb <= 0:
        pslc = native
    waf = ftl.waf_eff(b.op_pct, b.gc, b.pslc_pct)
    n_ch = b.channels
    active = (iface["ctrl_w"] + DIE_W * b.total_dies + ecc.power_mw / 1000.0
              + phy_power_mw(b.bus_mode, b.eff_mts, LAYOUT_MM[b.layout], b.odt, 1.0) * n_ch / 1000.0)
    idle = iface["idle_w"] + phy_power_mw(b.bus_mode, b.eff_mts, LAYOUT_MM[b.layout], b.odt, 0.0) * n_ch / 1000.0
    return StoragePerf(
        b.storage, seq, lat.total_us / 1000.0 + iface["lat_ms"], pslc, native, pslc_gb, idle, active,
        ftl.GC_POLICIES[b.gc]["bg_w"], waf, ftl.tbw_tb(b.capacity_gb, part.pe_max, waf),
        lat.p_uncorrectable, eye.ber, eye.crash_prob_per_s, eye, False, limiter, thr)
