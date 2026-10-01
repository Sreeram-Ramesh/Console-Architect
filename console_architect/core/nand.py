"""NAND cell physics and the read pipeline: tR + DMA + ECC + read-retry + GC."""
from __future__ import annotations

from dataclasses import dataclass

from .ecc import decode_latency_us, page_fail_prob
from .parts import EccConfig, NandPart

T_CMD_US = 0.5


def rber_cell(part: NandPart, pe_cycles: float, retention_days: float = 0.0) -> float:
    wear = (max(0.0, pe_cycles) / part.pe_max) ** 1.5
    ret = 1.0 + part.retention_gain * max(0.0, retention_days) / 365.0
    return min(0.5, part.rber0 * (1.0 + part.wear_gain * wear) * ret)


def bus_mbps(mts: float, bus_bits: int = 8) -> float:
    """DDR bus bandwidth in MB/s (MT/s already counts both edges)."""
    return mts * bus_bits / 8.0


def t_dma_us(page_bytes: int, mts: float, bus_bits: int = 8) -> float:
    return page_bytes * 8.0 / (bus_bits * mts)


@dataclass(frozen=True)
class ReadLatency:
    t_cmd_us: float
    t_r_us: float
    t_dma_us: float
    t_ecc_us: float
    t_retry_us: float
    t_gc_us: float
    total_us: float
    p_uncorrectable: float
    mean_retries: float
    rber_cell: float
    ber_phy: float


def expected_read_latency(part: NandPart, ecc: EccConfig, mts: float, ber_phy: float,
                          pe_cycles: float = 0.0, retention_days: float = 0.0,
                          bus_bits: int = 8, p_gc: float = 0.0,
                          gc_stall_us: float = 100_000.0) -> ReadLatency:
    """Expected page-read latency.

    Read-retry shifts Vref and improves the *cell* RBER by ecc.retry_gain per attempt,
    but it cannot fix errors injected by the PHY, so a bad eye keeps retries failing.
    """
    rc = rber_cell(part, pe_cycles, retention_days)
    dma = t_dma_us(part.page_bytes, mts, bus_bits)
    reach, t_retry, mean_retries = 1.0, 0.0, 0.0
    t_ecc0 = 0.0
    for k in range(ecc.max_retries + 1):
        soft = k >= ecc.soft_after
        rber_k = rc * (ecc.retry_gain ** k) + ber_phy
        e = decode_latency_us(ecc, rber_k, soft)
        attempt = part.t_r_us + dma + e
        if k == 0:
            t_ecc0 = e
        else:
            t_retry += reach * attempt
            mean_retries += reach
        reach *= page_fail_prob(ecc, rber_k, part.page_bytes, soft)
        if reach < 1e-15:
            reach = 0.0
            break
    t_gc = p_gc * gc_stall_us
    total = T_CMD_US + part.t_r_us + dma + t_ecc0 + t_retry + t_gc
    return ReadLatency(T_CMD_US, part.t_r_us, dma, t_ecc0, t_retry, t_gc, total,
                       reach, mean_retries, rc, ber_phy)
