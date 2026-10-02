"""The knobs the player can turn, grouped, with per-level value lists and plain-English lessons."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .build import Build
from .levels import Level


def _nand(b: Build) -> bool:
    return b.nand_based


@dataclass(frozen=True)
class Knob:
    key: str
    label: str
    group: str
    values: tuple
    fmt: Callable = str
    applies: Callable = lambda b: True


_onoff = lambda v: "ON" if v else "off"
KNOBS: tuple[Knob, ...] = (
    Knob("storage", "Storage type", "STORAGE", ("hdd", "sata", "nvme", "ramdisk"),
         {"hdd": "Mechanical HDD", "sata": "SATA SSD", "nvme": "NVMe SSD", "ramdisk": "RAM disk (DRAM)"}.get),
    Knob("capacity_gb", "Capacity", "STORAGE", (16, 32, 64, 128, 256, 512, 1024), lambda v: f"{v} GB"),
    Knob("cell", "NAND cell type", "STORAGE", ("slc", "tlc", "qlc"),
         {"slc": "SLC (1 bit)", "tlc": "TLC (3 bit)", "qlc": "QLC (4 bit)"}.get, _nand),
    Knob("channels", "Channels", "STORAGE", (1, 2, 4), str, _nand),
    Knob("dies", "Dies per channel", "STORAGE", (1, 2, 4), str, _nand),
    Knob("bus_mode", "Bus interface", "INTERFACE", ("Toggle", "ONFI"),
         {"Toggle": "Toggle (DQS strobe)", "ONFI": "ONFI (free clock)"}.get, _nand),
    Knob("mts", "Link speed", "INTERFACE", (400, 800, 1600, 3200), lambda v: f"{v} MT/s", _nand),
    Knob("odt", "On-die termination", "INTERFACE", (False, True), _onoff, _nand),
    Knob("zq", "ZQ calibration", "INTERFACE", (False, True), _onoff, _nand),
    Knob("layout", "PCB trace layout", "INTERFACE", ("cheap", "standard", "compact"),
         {"cheap": "Cheap (80 mm)", "standard": "Standard (45 mm)", "compact": "Compact HDI (25 mm)"}.get, _nand),
    Knob("ecc", "ECC engine", "CONTROLLER", ("bch40", "ldpc"),
         {"bch40": "BCH (cheap, slow)", "ldpc": "LDPC (strong, fast)"}.get, _nand),
    Knob("op_pct", "Over-provisioning", "CONTROLLER", (7, 14, 28), lambda v: f"{v}%", _nand),
    Knob("gc", "Garbage collection", "CONTROLLER", ("lazy", "aggressive", "idle"),
         {"lazy": "Lazy", "aggressive": "Aggressive", "idle": "Idle-aware"}.get, _nand),
    Knob("pslc_pct", "pSLC write cache", "CONTROLLER", (0, 5, 10, 20), lambda v: "none" if v == 0 else f"{v}% of drive", _nand),
    Knob("plp", "Power-loss protection", "CONTROLLER", (False, True), _onoff, _nand),
    Knob("battery_wh", "Battery", "POWER & THERMAL", (4, 8, 25, 40), lambda v: f"{v:g} Wh"),
    Knob("cooling", "Cooling", "POWER & THERMAL", ("passive", "heatsink", "fan"),
         {"passive": "Passive", "heatsink": "Heatsink + graphite", "fan": "Active fan"}.get),
)
KNOB_BY_KEY = {k.key: k for k in KNOBS}
_LEVEL_KEYS = {"capacity_gb": "capacity_gb", "mts": "mts", "channels": "channels", "dies": "dies",
               "battery_wh": "battery_wh", "cooling": "cooling"}


def values_for(k: Knob, L: Level) -> tuple:
    lv = L.options.get(_LEVEL_KEYS.get(k.key, ""), None)
    return tuple(lv) if lv else k.values


def nudge(b: Build, k: Knob, L: Level, d: int) -> Build:
    vals = values_for(k, L)
    cur = getattr(b, k.key)
    i = vals.index(cur) if cur in vals else min(range(len(vals)), key=lambda j: abs(vals[j] - cur)) \
        if isinstance(cur, (int, float)) and not isinstance(cur, bool) else 0
    return b.with_(**{k.key: vals[max(0, min(len(vals) - 1, i + d))]})


# ---- lessons: what it does / how it feels / what it costs, plus a per-value line ----
LESSONS: dict[str, dict] = {
    "storage": dict(
        what="Where the game's data lives. It sets the speed ceiling, the power draw and a big chunk of the price.",
        feel="HDD: 60 s+ loads and pop-in. SATA: fine. NVMe: fast. RAM disk: instant, but power-hungry and volatile.",
        price="HDD is cheap per GB. RAM disk costs about $3.50 per GB (a $900 part for 256 GB).",
        v={"hdd": "A spinning disk: every random read is a ~12 ms seek, it burns 1.8 W and drops hard.",
           "sata": "Flash with a 550 MB/s legacy link. A solid budget pick.",
           "nvme": "Flash on a fast PCIe link, up to 3.2 GB/s. Costs about $3.50 more controller.",
           "ramdisk": "DRAM as storage. Zero latency, but refresh drains the battery and a power cut erases it."}),
    "capacity_gb": dict(
        what="How much the drive holds. The game plus its day-one patch must fit.",
        feel="No gameplay effect, but too small and the game does not install.",
        price="Cost scales with capacity. Over-provisioning is carved out on top."),
    "cell": dict(
        what="How many bits each NAND cell stores. More bits per cell is denser and cheaper but slower and weaker.",
        feel="SLC reads in 15 us, TLC 45 us, QLC 100 us. QLC also hits the write cliff once its cache fills.",
        price="SLC $0.30/GB, TLC $0.06/GB, QLC $0.04/GB.",
        v={"slc": "One bit per cell: very fast and tough (100k P/E cycles), but expensive.",
           "tlc": "The mainstream balance: 3000 P/E cycles.",
           "qlc": "Cheapest per GB, but 1000 P/E cycles, slow reads, and writes can fall from 500 to 20 MB/s."}),
    "channels": dict(
        what="Independent buses between the controller and the NAND. Each one moves data in parallel.",
        feel="More channels means higher streaming bandwidth, which stops texture pop-in.",
        price="$0.80 per channel, plus more PHY power."),
    "dies": dict(
        what="NAND dies on each channel. While one die senses a page (tR), another can transfer.",
        feel="Interleaving hides tR. This is often the real bandwidth limiter.",
        price="$0.50 per die package, and about 60 mW each when active."),
    "bus_mode": dict(
        what="How data crosses the NAND bus. ONFI uses a free-running clock, Toggle uses a strobe only during transfers.",
        feel="ONFI reaches higher MT/s. Toggle tops out near 3200 MT/s here.",
        price="Toggle saves idle power: ONFI's clock burns energy even when nothing moves (P = a*C*V^2*f).",
        v={"Toggle": "Strobe only when moving data. Lower idle power, great for handhelds.",
           "ONFI": "Continuous clock. Higher peak speed, higher idle power."}),
    "mts": dict(
        what="Transfers per second on the bus. Each transfer lasts one unit interval: UI = 1e6 / MT/s picoseconds.",
        feel="Faster moves pages sooner, but the eye shrinks: at 3200 MT/s a bit lasts only 312 ps.",
        price="Speed-binned parts cost more, and dynamic power rises with frequency."),
    "odt": dict(
        what="On-die termination matches the receiver to the trace (about 50 ohm) so the signal is absorbed, not reflected.",
        feel="Off: reflections ring on the line. Fine at 200-400 MT/s, fatal beyond. Closed eye means BER, retries, crashes.",
        price="Costs about $0.15 of silicon and a little static power."),
    "zq": dict(
        what="ZQ calibration re-trims drive and termination impedance against a precision resistor as temperature drifts.",
        feel="Off: the chip runs hot, impedance drifts, timing margin leaks away and the system can crash at 70-90 C.",
        price="About $0.10 (the ZQ resistor and calibration logic)."),
    "layout": dict(
        what="PCB routing between controller and NAND. Longer traces mean more delay, loss and reflection time.",
        feel="Compact traces keep reflections within a bit time and widen the eye.",
        price="Cheap $0, standard $0.80, compact HDI $2.50."),
    "ecc": dict(
        what="The error-correction decoder. Flash always has bit errors; ECC fixes them before the game sees them.",
        feel="BCH tops out near 700 MB/s and struggles on worn QLC. LDPC corrects far more errors and decodes faster.",
        price="BCH $0.50, LDPC $2.20 (and more power).",
        v={"bch40": "Cheap hard-decision decoder: 40 bits per 1 KiB, and only 700 MB/s.",
           "ldpc": "Strong soft-decision decoder: about 110 bits per 1 KiB, up to 2.4 GB/s."}),
    "op_pct": dict(
        what="Spare flash the user can't see, giving the FTL room to shuffle data. WAF is about (1+OP)/(2*OP) for random writes.",
        feel="More OP means fewer, shorter GC pauses and fewer freezes.",
        price="Costs raw NAND, but triples endurance: TBW = capacity x P/E / WAF."),
    "gc": dict(
        what="When the controller cleans up stale blocks. Cleaning steals the NAND from the game.",
        feel="Lazy: rare but long freezes. Aggressive: frequent ~90 ms stutters. Idle-aware: only cleans in quiet moments.",
        price="Idle-aware needs firmware ($1.20). Aggressive burns background power.",
        v={"lazy": "Waits until it must, then pauses for ~220 ms. Higher write amplification.",
           "aggressive": "Cleans constantly: steady ~90 ms noise, +0.35 W background.",
           "idle": "Cleans during pauses and loading screens. Smooth, but costs engineering."}),
    "pslc_pct": dict(
        what="A slice of the drive run as 1-bit-per-cell for fast writes. It absorbs bursts, then folds into native cells when idle.",
        feel="When it fills, QLC writes can drop from 500 MB/s to 20 MB/s: the write cliff. Big patches hit it.",
        price="Small firmware cost and a little wear overhead."),
    "plp": dict(
        what="Capacitors that give the controller milliseconds to finish writes after the power drops.",
        feel="Without them a power cut can corrupt the save and the FTL tables.",
        price="About $1.80 of capacitors."),
    "battery_wh": dict(
        what="Energy storage. Run time = capacity / average power.",
        feel="Storage power adds to the SoC's draw: a hot drive costs minutes of play.",
        price="About $0.60 per Wh."),
    "cooling": dict(
        what="How quickly heat leaves the chassis. Temperature rises with power x thermal resistance.",
        feel="Too hot: the SoC throttles (low FPS), NAND throttles (pop-in), and impedance drifts.",
        price="Passive $0, heatsink $3, fan $9.",
        v={"passive": "Free, but the case gets hot.", "heatsink": "Spreads heat. Cuts thermal resistance 25%.",
           "fan": "Cuts thermal resistance 50%, at the cost of $9 and some noise."}),
}


def lesson_lines(key: str, value) -> list[tuple[str, str]]:
    d = LESSONS[key]
    rows = [("WHAT", d["what"]), ("FEEL", d["feel"]), ("COST", d["price"])]
    v = d.get("v", {}).get(value)
    if v:
        rows.insert(0, ("NOW", v))
    return rows
