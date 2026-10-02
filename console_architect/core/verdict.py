"""Scoring, customer reviews and 'why did that happen?' explanations."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import ftl
from .build import Build
from .engine import Boot, Engine
from .levels import Level
from .spec import Spec
from .storage import perf

AXES = ("load", "smooth", "popin", "battery", "reliability", "price", "life")
AXIS_LABEL = {"load": "Load time", "smooth": "Smoothness", "popin": "Texture pop-in",
              "battery": "Battery", "reliability": "Reliability", "price": "Price", "life": "Lifespan"}


@dataclass
class Metrics:
    patch_s: float
    load_s: float
    fps_avg: float
    fps_1pct: float
    stutters: int
    worst_hitch_ms: float
    counts: dict
    pop_pct: float
    battery_h: float
    battery_dead: bool
    dead_at_h: float
    crashed: bool
    crash_t: float
    crash_reason: str
    save_status: str
    temp_peak: float
    nand_peak: float
    throttle_pct: float
    soc_wh: float
    storage_wh: float
    life_years: float | None
    corner_fail: int
    corner_total: int
    worst_slack_ps: float
    worst_corner: str
    bom: float
    retail: float
    fits: bool
    deaths: int = 0
    late_hits: int = 0
    scores: dict = field(default_factory=dict)
    overall: float = 0.0
    stars: int = 0
    verdict: str = ""
    passed: bool = False


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def collect(e: Engine, boot: Boot, spec: Spec, L: Level, deaths: int = 0, late_hits: int = 0) -> Metrics:
    avg, low = e.fps()
    t = max(e.t, 1e-6)
    mean_w = e.mean_power_w()
    sim_h = e.t * e.scale / 3600.0
    m = Metrics(
        patch_s=boot.patch_s, load_s=boot.load_s, fps_avg=avg, fps_1pct=low, stutters=e.stutters,
        worst_hitch_ms=max([h[1] for h in e.hitch_log], default=0.0), counts=dict(e.counts),
        pop_pct=100.0 * e.pop_acc / t, battery_h=e.b.battery_wh / max(1e-9, mean_w),
        battery_dead=e.battery_dead, dead_at_h=sim_h, crashed=e.crashed, crash_t=e.t,
        crash_reason=e.crash_reason, save_status=e.save_status, temp_peak=e.temp_peak,
        nand_peak=e.nand_peak, throttle_pct=100.0 * e.throttle_acc / t,
        soc_wh=e.energy_wh["soc"], storage_wh=e.energy_wh["storage"], life_years=spec.life_years,
        corner_fail=spec.corner_fail, corner_total=spec.corner_total, worst_slack_ps=spec.worst_slack_ps,
        worst_corner=spec.worst_corner, bom=spec.bom, retail=spec.retail, fits=spec.fits,
        deaths=deaths, late_hits=late_hits)
    score(m, L)
    return m


def score(m: Metrics, L: Level) -> None:
    s = {}
    total_load = m.load_s + 0.5 * m.patch_s
    s["load"] = _clamp(100.0 * (1.0 - math.log(max(total_load, 2.0) / 2.0) / math.log(40.0)))
    s["smooth"] = _clamp(100.0 * m.fps_1pct / L.fps_goal)
    s["popin"] = _clamp(100.0 - m.pop_pct * 2.5)
    s["battery"] = _clamp(100.0 * m.battery_h / L.battery_goal_h) if not m.battery_dead else \
        _clamp(60.0 * m.dead_at_h / L.session_h)
    rel = 100.0
    if m.crashed:
        rel = 0.0
    else:
        rel -= 40.0 if m.save_status in ("corrupt", "lost") else 0.0
        rel -= 15.0 * m.counts.get("read_error", 0)
        if m.corner_total:
            rel -= 60.0 * m.corner_fail / m.corner_total
    s["reliability"] = _clamp(rel)
    over = m.retail / L.target_retail_usd - 1.0
    s["price"] = 100.0 if over <= 0 else _clamp(100.0 - 400.0 * over)
    s["life"] = 100.0 if m.life_years is None else _clamp(100.0 * m.life_years / 5.0)
    m.scores = s
    w = L.weights
    m.overall = sum(s[k] * w.get(k, 1.0) for k in AXES) / sum(w.get(k, 1.0) for k in AXES)
    m.stars = int(round(_clamp(m.overall) / 20.0))
    if m.crashed or m.save_status in ("corrupt", "lost"):
        m.stars = min(m.stars, 1)
    elif m.battery_dead:
        m.stars = min(m.stars, 2)
    m.passed = (not m.crashed and not m.battery_dead and m.save_status not in ("corrupt", "lost")
                and m.retail <= L.target_retail_usd and m.fits
                and min(s["load"], s["smooth"], s["popin"]) >= 25)
    if m.crashed:
        m.verdict = "RECALLED: consoles crash in the field"
    elif m.save_status in ("corrupt", "lost"):
        m.verdict = "RECALLED: customers lost their saves"
    elif m.battery_dead:
        m.verdict = "BATTERY FAIL: session ended early"
    elif m.retail > L.target_retail_usd:
        m.verdict = "OVER BUDGET: marketing says no"
    elif min(s["load"], s["smooth"], s["popin"]) < 25:
        m.verdict = "MEH: players will hate how it plays"
    elif m.overall >= 75:
        m.verdict = "SHIP IT!"
    elif m.overall >= 55:
        m.verdict = "SHIPPABLE, but reviewers will notice"
    else:
        m.verdict = "MEH: back to the whiteboard"


def reviews(m: Metrics, L: Level) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []
    if m.crashed:
        out.append((1, "FragMaster", "Blue-screened in my lap. Returned it."))
    if m.save_status in ("corrupt", "lost"):
        out.append((1, "CasualCarl", "Lost 40 hours of progress when the battery wiggled. Never again."))
    if m.battery_dead:
        out.append((1, "BusRider", f"Died after about {m.dead_at_h:.1f} hours. I can't even finish my commute."))
    if m.load_s + 0.5 * m.patch_s > 45:
        out.append((2, "SnackBreak", "I made a sandwich, ate it, and the game was still loading."))
    if m.fps_1pct < 0.6 * L.fps_goal:
        out.append((2, "FrameCounter", "Constant hitching. The frametime graph looks like a seismograph."))
    if m.pop_pct > 15:
        out.append((2, "PixelPeeper", "Textures and obstacles pop in right in my face. Ran into things I could not see."))
    if m.retail > L.target_retail_usd:
        out.append((2, "ValueHunter", f"${m.retail:.0f}? For this? Hard pass."))
    if m.overall >= 75 and not out:
        out.append((5, "HappyGamer", "Loads fast, runs smooth, battery lasts. Bought a second one."))
    if m.battery_h >= 1.4 * L.battery_goal_h and not m.battery_dead and not m.crashed:
        out.append((5, "Marathoner", "Plays all weekend on one charge."))
    if not out:
        out.append((3, "MidReviewer", "Perfectly fine. Nothing to complain about, nothing to rave about."))
    return out[:3]


@dataclass
class Lesson:
    sev: int
    headline: str
    why: str
    tip: str


def explain(m: Metrics, b: Build, L: Level, spec: Spec) -> list[Lesson]:
    out: list[Lesson] = []
    p = perf(b, 40.0, L.pe_fraction)
    eye = spec.eye
    if m.crashed:
        why = m.crash_reason
        if b.nand_based and eye:
            if not b.odt:
                why = (f"With ODT off the receiver looks like an open end, so the reflection coefficient is "
                       f"about {eye.gamma:.2f}. At {b.eff_mts} MT/s one bit lasts only {eye.ui_ps:.0f} ps, so the echo "
                       f"(round trip {eye.t_rt_ps:.0f} ps) lands on the next bit and the eye collapses. "
                       f"Setup slack went negative and the controller captured garbage.")
            elif not b.zq:
                why = (f"The NAND reached {m.nand_peak:.0f} C. Without ZQ calibration the drive and termination "
                       f"impedance drift with temperature, which moved edges by about {1.6 * (m.nand_peak - 25):.0f} ps. "
                       f"That ate the setup margin at {b.eff_mts} MT/s.")
        out.append(Lesson(100, f"CRASH at {m.crash_t:.0f} s of play: {m.crash_reason}", why,
                          "Turn ODT and ZQ on, run a slower MT/s, or shorten the traces (compact layout)."))
    if m.save_status in ("corrupt", "lost"):
        if b.storage == "ramdisk":
            why = "DRAM forgets everything the instant power drops. Nothing was ever written to persistent media."
            tip = "Use real non-volatile storage. RAM disks are for scratch data."
        else:
            why = ("A power cut mid-write leaves NAND pages half-programmed and the FTL mapping table stale. "
                   "Without power-loss-protection capacitors the controller cannot finish the write.")
            tip = "Add PLP caps (about $1.80 of BOM) so the controller can flush its buffers on power loss."
        out.append(Lesson(95, f"Brownout destroyed the save file ({m.save_status})", why, tip))
    if not m.crashed and m.corner_total and m.corner_fail:
        out.append(Lesson(70, f"Passes on the bench, fails in the field: {m.corner_fail}/{m.corner_total} PVT corners closed",
                          f"Worst case is {m.worst_corner} with {m.worst_slack_ps:+.0f} ps of slack. Slow silicon, low voltage "
                          "and heat shrink the eye, and some units you ship will sit at those corners.",
                          "Enable ODT and ZQ, lower MT/s, or use a shorter trace layout until all corners pass."))
    if m.battery_dead or m.battery_h < L.battery_goal_h:
        tot = m.soc_wh + m.storage_wh
        share = m.storage_wh / tot if tot else 0
        if b.storage == "hdd":
            cause = "The HDD spindle motor burns about 1.8 W whenever it spins, even when idle (0.7 W)."
            tip = "Flash storage draws a fraction of that."
        elif b.storage == "ramdisk":
            cause = (f"DRAM must be refreshed constantly: roughly 0.12 W per GB, so {b.capacity_gb} GB costs "
                     f"{0.12 * b.capacity_gb:.0f} W continuously.")
            tip = "Use NAND. DRAM is for caches, not bulk storage."
        elif share > 0.2:
            cause = (f"Storage consumed {share:.0%} of the energy. ")
            if b.bus_mode == "ONFI":
                cause += "ONFI's free-running clock burns power even when idle. "
            if b.gc == "aggressive":
                cause += "Aggressive GC keeps the controller busy in the background. "
            if b.ecc == "ldpc":
                cause += "The LDPC engine is power-hungry. "
            tip = "Try Toggle mode, lazy/idle GC, fewer channels, or a bigger battery."
        else:
            cause = (f"The SoC dominates the budget ({m.soc_wh / max(tot, 1e-9):.0%}). "
                     f"Mean draw was {tot / max(m.dead_at_h, 1e-9):.1f} W against a {b.battery_wh:g} Wh battery.")
            tip = "A bigger battery costs about $0.60 per Wh."
        head = (f"Battery died after {m.dead_at_h:.1f} h" if m.battery_dead
                else f"Battery life {m.battery_h:.1f} h (goal {L.battery_goal_h:g} h)")
        out.append(Lesson(85 if m.battery_dead else 50, head, cause, tip))
    if m.pop_pct > 8:
        lim = spec.limiter
        tips = {"seek": "Move to flash storage.",
                "read": "Add channels or dies so more pages are read in parallel, or use a faster cell type (SLC/TLC).",
                "ECC": "Use the LDPC engine, whose decoder is far faster than BCH.",
                "SATA": "Upgrade to NVMe.",
                "thermal": "Add a heatsink or fan so the NAND stays under 75 C.",
                "retries": "Fix the eye: enable ODT/ZQ or slow the bus so reads stop retrying."}
        key = ("seek" if "seek" in lim else "ECC" if "ECC" in lim else "SATA" if "SATA" in lim else
               "thermal" if "thermal" in lim else "retries" if "retries" in lim else "read")
        out.append(Lesson(65, f"Textures popped in {m.pop_pct:.0f}% of the time"
                              + (f"; {m.late_hits} hit(s) came from obstacles that loaded too late" if m.late_hits else ""),
                          f"The world streams at up to {spec.demand_peak_mbps:.0f} MB/s but your storage delivered about "
                          f"{spec.supply_mbps:.0f} MB/s. The limiter was: {lim}. When supply < demand the look-ahead "
                          "buffer drains and distant tiles render at low resolution (and hide hazards).", tips[key]))
    if m.stutters and m.counts:
        dom = max(("gc", "save", "seek", "read_error"), key=lambda k: m.counts.get(k, 0))
        n = m.counts.get(dom, 0)
        if n:
            if dom == "gc":
                pol = ftl.GC_POLICIES[b.gc]
                why = (f"The '{b.gc}' GC policy paused the controller {n} times for ~{ftl.gc_stall_ms(b.op_pct, b.gc):.0f} ms. "
                       f"While it moves valid pages and erases blocks, reads queue behind it and the frame waits. "
                       f"More over-provisioning ({b.op_pct}% now) means fewer, shorter GC runs.")
                tip = "Try 'idle' GC (shorter pauses, +$1.20) or raise OP to 14% or 28%."
            elif dom == "save":
                why = (f"Autosave writes {L.autosave_mb:.0f} MB. {'The pSLC cache was exhausted so writes fell to the native NAND rate' if b.nand_based and p.write_native_mbps < p.write_pslc_mbps else 'Writes were slow'} "
                       f"({p.write_native_mbps:.0f} MB/s native vs {p.write_pslc_mbps:.0f} MB/s cached).")
                tip = "Use TLC instead of QLC, enlarge the pSLC cache, or add dies for write parallelism."
            elif dom == "seek":
                why = "Streaming needs lots of small reads, and every one costs a ~12 ms head seek on a mechanical drive."
                tip = "Flash has no moving parts: random reads cost microseconds."
            else:
                why = "Reads came back uncorrectable, so the host retried the whole chunk."
                tip = "Strengthen ECC (LDPC), fix the eye margin, or use a lower-density cell."
            out.append(Lesson(60, f"{m.stutters} freezes (worst {m.worst_hitch_ms:.0f} ms), mostly from {dom.replace('_', ' ')}", why, tip))
    if m.load_s + 0.5 * m.patch_s > 25:
        why = f"Loading read {L.load_gb:g} GB at {p.seq_read_mbps:.0f} MB/s ({spec.limiter})."
        if L.patch_gb and m.patch_s > 20:
            if b.nand_based and p.write_native_mbps < p.write_pslc_mbps:
                why += (f" The {L.patch_gb:g} GB day-one patch took {m.patch_s:.0f} s: once the pSLC cache fills, "
                        f"{b.cell.upper()} programs at only {p.write_native_mbps:.0f} MB/s (the 'write cliff').")
            else:
                why += f" The {L.patch_gb:g} GB day-one patch took {m.patch_s:.0f} s at {p.write_native_mbps:.0f} MB/s."
        out.append(Lesson(45, f"Slow start: {m.patch_s:.0f} s patch + {m.load_s:.0f} s load", why,
                          "More dies/channels, a bigger pSLC cache, or TLC/SLC cells all help."))
    if m.retail > L.target_retail_usd:
        top = sorted(spec.lines[1:], key=lambda kv: -kv[1])[:3]
        out.append(Lesson(55, f"${m.retail:.0f} retail vs ${L.target_retail_usd:.0f} target",
                          "Biggest BOM items: " + ", ".join(f"{k} ${v:.0f}" for k, v in top) + f". Retail is BOM x {L.markup:g}.",
                          "Smaller capacity, QLC, fewer channels or dies, and a smaller battery all cut cost."))
    if not m.fits:
        out.append(Lesson(90, f"Game does not fit: needs {L.need_gb:.0f} GB", "The game plus its patch must fit with some free space.",
                          "Pick a larger capacity."))
    if m.life_years is not None and m.life_years < 3:
        out.append(Lesson(40, f"Flash wears out in about {m.life_years:.1f} years",
                          f"Endurance is capacity x P/E cycles / WAF. {b.cell.upper()} gives few cycles and WAF is {p.waf:.1f} at {b.op_pct}% OP.",
                          "Use TLC/SLC, raise over-provisioning, or use a larger drive."))
    if m.throttle_pct > 15:
        out.append(Lesson(50, f"Thermally throttled {m.throttle_pct:.0f}% of the session (peak {m.temp_peak:.0f} C)",
                          "The chassis heats until the SoC cuts clocks, which lowers frame rate. Hot NAND also throttles and "
                          "changes impedance, which shrinks the eye.", "Upgrade cooling: heatsink (+$3) or fan (+$9)."))
    if not out:
        out.append(Lesson(10, "Clean run", f"Eye margin held at every PVT corner, reads stayed ahead of the player, and the "
                          f"battery went the distance ({m.battery_h:.1f} h).", "Now try shaving cost without losing the stars."))
    out.sort(key=lambda x: -x.sev)
    return out[:5]
