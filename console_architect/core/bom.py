"""Bill of materials and retail price."""
from __future__ import annotations

from . import ftl
from .build import Build
from .storage import HDD, IFACE, RAM, ecc_cfg, nand_part

COOLING_USD = {"passive": 0.0, "heatsink": 3.0, "fan": 9.0}
LAYOUT_USD = {"cheap": 0.0, "standard": 0.8, "compact": 2.5}
BATTERY_USD_PER_WH = 0.6


def bom_lines(b: Build, base_usd: float, base_label: str = "Console base (SoC, screen, shell)") -> list[tuple[str, float]]:
    L: list[tuple[str, float]] = [(base_label, base_usd)]
    if b.storage == "hdd":
        L += [("2.5in HDD mechanism", HDD["usd"]), (f"Platters {b.capacity_gb} GB", HDD["usd_per_gb"] * b.capacity_gb)]
    elif b.storage == "ramdisk":
        L += [(f"DRAM {b.capacity_gb} GB", RAM["usd_per_gb"] * b.capacity_gb), ("DRAM controller", RAM["ctrl_usd"])]
    else:
        part, ecc = nand_part(b.cell), ecc_cfg(b.ecc)
        raw = b.capacity_gb * (1.0 + b.op_pct / 100.0)
        L += [(f"{part.cell} NAND {b.capacity_gb} GB (+{b.op_pct}% OP)", raw * part.usd_per_gb),
              (f"{b.storage.upper()} controller", IFACE[b.storage]["usd"]),
              (f"ECC engine ({ecc.kind})", ecc.cost_usd),
              (f"{b.channels} channel(s)", 0.8 * b.channels),
              (f"{b.total_dies} die package(s)", 0.5 * b.total_dies),
              ("Speed-binned parts", max(0.0, 0.0006 * (b.mts - 400)) * b.channels),
              ("On-die termination", 0.15 if b.odt else 0.0),
              ("ZQ calibration", 0.10 if b.zq else 0.0),
              (f"PCB layout ({b.layout})", LAYOUT_USD[b.layout]),
              (f"GC firmware ({b.gc})", ftl.GC_POLICIES[b.gc]["usd"]),
              ("pSLC cache firmware", 0.3 if b.pslc_pct > 0 else 0.0),
              ("Power-loss protection caps", 1.8 if b.plp else 0.0)]
    L += [(f"Battery {b.battery_wh:g} Wh", BATTERY_USD_PER_WH * b.battery_wh),
          (f"Cooling ({b.cooling})", COOLING_USD[b.cooling])]
    return [(k, round(v, 2)) for k, v in L if v > 0 or k == base_label]


def totals(lines: list[tuple[str, float]], markup: float) -> tuple[float, float]:
    bom = sum(v for _, v in lines)
    return bom, bom * markup
