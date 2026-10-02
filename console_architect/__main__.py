"""`ca` entry point: sweep (CSV), report (fake report_timing), tui."""
from __future__ import annotations

import argparse
import csv
import itertools
import sys

from .core.nand import expected_read_latency
from .core.parts import EccConfig, NandPart
from .core.phy import Corner, PhyConfig, analyze, lane_slacks


def _floats(s: str) -> list[float]:
    return [float(x) for x in s.split(",")]


def _bools(s: str) -> list[bool]:
    m = {"on": True, "off": False, "1": True, "0": False, "true": True, "false": False}
    return [m[x.strip().lower()] for x in s.split(",")]


def cmd_sweep(a) -> None:
    part, ecc = NandPart.load(a.nand), EccConfig.load(a.ecc)
    w = csv.writer(sys.stdout, lineterminator="\n")
    w.writerow(["mts", "odt", "zq", "temp_c", "w_eye_pct", "h_eye_mv", "slack_ps",
                "ber_phy", "t_read_us", "p_uncorr", "crash_p_per_s"])
    for mts, odt, zq, t in itertools.product(_floats(a.mts), _bools(a.odt), _bools(a.zq),
                                             _floats(a.temp)):
        cfg = PhyConfig(mts=mts, odt=odt, zq=zq, trace_mm=a.trace,
                        corner=Corner(a.process, a.vdd, t))
        r = analyze(cfg)
        lat = expected_read_latency(part, ecc, mts, r.ber, pe_cycles=a.pe)
        w.writerow([f"{mts:g}", int(odt), int(zq), f"{t:g}", f"{r.w_eye_pct:.1f}",
                    f"{r.h_eye_mv:.0f}", f"{r.setup_slack_ps:.1f}", f"{r.ber:.2e}",
                    f"{lat.total_us:.1f}", f"{lat.p_uncorrectable:.2e}",
                    f"{r.crash_prob_per_s:.3f}"])


def cmd_report(a) -> None:
    cfg = PhyConfig(mts=a.mts, odt=a.odt, zq=a.zq, trace_mm=a.trace,
                    corner=Corner(a.process, a.vdd, a.temp))
    r = analyze(cfg)
    print(f"report_timing  corner={cfg.corner.name}  {cfg.mts:g} MT/s  "
          f"UI={r.ui_ps:.0f}ps  ODT={'on' if cfg.odt else 'off'}  ZQ={'on' if cfg.zq else 'off'}")
    print(f"{'lane':<6}{'setup(ps)':>11}{'hold(ps)':>11}   status")
    for i, (s, h) in enumerate(lane_slacks(cfg, a.seed)):
        ok = min(s, h) >= 0
        print(f"DQ[{i}]  {s:>9.1f}  {h:>9.1f}   {'MET' if ok else 'VIOLATED'}")
    print(f"eye W={r.w_eye_pct:.1f}% UI  H={r.h_eye_mv:.0f} mV  BER={r.ber:.1e}  "
          f"crash/s={r.crash_prob_per_s:.2f}")


def cmd_run(a) -> None:
    from dataclasses import fields
    from .core.build import Build
    from .core.engine import Engine
    from .core.levels import load_level
    from .core.spec import estimate
    from .core.verdict import AXIS_LABEL, AXES, collect, explain, reviews
    L = load_level(a.level)
    kw = dict(L.default)
    types = {f.name: f.type for f in fields(Build)}
    for kv in a.set:
        k, v = kv.split("=", 1)
        t = types[k]
        kw[k] = (v.lower() in ("1", "true", "on", "yes")) if t in ("bool", bool) else \
                int(v) if t in ("int", int) else float(v) if t in ("float", float) else v
    b = Build(**kw)
    sp = estimate(b, L)
    e = Engine(b, L, a.seed)
    boot = e.boot()
    while not e.finished:
        e.step(0.05)
    m = collect(e, boot, sp, L)
    print(f"{L.name}: {m.verdict}   {'*' * m.stars}{'.' * (5 - m.stars)}  overall {m.overall:.0f}/100")
    for k in AXES:
        print(f"  {AXIS_LABEL[k]:<15}{m.scores[k]:>5.0f}")
    print(f"  patch {m.patch_s:.1f}s load {m.load_s:.1f}s | 1% low {m.fps_1pct:.0f} fps, {m.stutters} freezes {m.counts} | pop-in {m.pop_pct:.0f}% | "
          f"battery {m.battery_h:.1f} h | retail ${m.retail:.0f} (target ${L.target_retail_usd:g})")
    for les in explain(m, b, L, sp):
        print(f"- {les.headline}\n    why: {les.why}\n    try: {les.tip}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="ca", description="Console Architect")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--trace", type=float, default=40.0, help="trace length mm")
        sp.add_argument("--process", default="TT", choices=["SS", "TT", "FF"])
        sp.add_argument("--vdd", default="Vnom", choices=["Vmin", "Vnom", "Vmax"])

    s = sub.add_parser("sweep", help="design-space sweep, prints CSV")
    common(s)
    s.add_argument("--mts", default="800,1600,2400,3200,3600")
    s.add_argument("--odt", default="on,off")
    s.add_argument("--zq", default="on,off")
    s.add_argument("--temp", default="25,85")
    s.add_argument("--nand", default="tlc")
    s.add_argument("--ecc", default="ldpc")
    s.add_argument("--pe", type=float, default=0.0, help="P/E cycles consumed")
    s.set_defaults(fn=cmd_sweep)

    r = sub.add_parser("report", help="per-lane timing slack report")
    common(r)
    r.add_argument("--mts", type=float, default=3200)
    r.add_argument("--temp", type=float, default=25)
    r.add_argument("--no-odt", dest="odt", action="store_false")
    r.add_argument("--no-zq", dest="zq", action="store_false")
    r.add_argument("--seed", type=int, default=0)
    r.set_defaults(fn=cmd_report)

    t = sub.add_parser("lab", help="the PHY signal-integrity lab (eye scope sandbox)")
    t.add_argument("--console", default="deck")
    t.set_defaults(fn=lambda a: __import__("console_architect.tui.app", fromlist=["run"]).run(a.console))

    g = sub.add_parser("play", help="the playable game")
    g.add_argument("--level", default=None, help="jump straight to a level id, e.g. 2_openworld")
    g.set_defaults(fn=lambda a: __import__("console_architect.tui.game", fromlist=["run"]).run(a.level))

    u = sub.add_parser("run", help="headless: simulate one level with a build, print the scorecard")
    u.add_argument("level")
    u.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE", help="override Build knobs")
    u.add_argument("--seed", type=int, default=0)
    u.set_defaults(fn=cmd_run)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
