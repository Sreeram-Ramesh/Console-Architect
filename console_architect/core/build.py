"""A player's design: every knob in one frozen dataclass."""
from __future__ import annotations

from dataclasses import dataclass, replace

from .phy import Corner, PhyConfig

LAYOUT_MM = {"cheap": 80.0, "standard": 45.0, "compact": 25.0}
TOGGLE_MAX_MTS = 3200


@dataclass(frozen=True)
class Build:
    storage: str = "nvme"       # hdd | sata | nvme | ramdisk
    capacity_gb: int = 256
    cell: str = "tlc"           # slc | tlc | qlc
    ecc: str = "ldpc"           # bch40 | ldpc
    channels: int = 2
    dies: int = 2               # per channel
    bus_mode: str = "Toggle"    # Toggle | ONFI
    mts: int = 1600
    odt: bool = True
    zq: bool = True
    layout: str = "standard"    # cheap | standard | compact (trace length)
    op_pct: int = 7
    gc: str = "lazy"            # lazy | aggressive | idle
    pslc_pct: int = 10
    plp: bool = False
    battery_wh: float = 40.0
    cooling: str = "passive"    # passive | heatsink | fan

    @property
    def nand_based(self) -> bool:
        return self.storage in ("sata", "nvme")

    @property
    def eff_mts(self) -> int:
        return min(self.mts, TOGGLE_MAX_MTS) if self.bus_mode == "Toggle" else self.mts

    @property
    def total_dies(self) -> int:
        return self.channels * self.dies

    def with_(self, **kw) -> "Build":
        return replace(self, **kw)


def phy_config(b: Build, temp_c: float = 25.0, corner: Corner | None = None) -> PhyConfig:
    return PhyConfig(mts=b.eff_mts, odt=b.odt, zq=b.zq, trace_mm=LAYOUT_MM[b.layout],
                     corner=corner or Corner("TT", "Vnom", float(temp_c)))
