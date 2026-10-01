"""Textual shell: knobs, live eye canvas, telemetry panel, mascot."""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static
from rich.text import Text

from ..core.nand import bus_mbps, expected_read_latency
from ..core.parts import ConsoleSpec, EccConfig, NandPart, list_parts
from ..core.phy import PROCESS_TIMING, VDD_SCALE, Corner, PhyConfig, analyze, eye_traces
from ..core.power import phy_power_mw
from .braille import BrailleCanvas, draw_eye
from .mascot import mascot

WEAR = [("fresh", 0.0), ("50% worn", 0.5), ("end of life", 1.0)]
TEMPS = [-10, 25, 45, 70, 85, 105]


class ConsoleArchitectApp(App):
    TITLE = "Console Architect"
    CSS = """
    #top { height: 1fr; }
    #eye-box { width: 3fr; border: round $accent; padding: 0 1; }
    #stats-box { width: 2fr; border: round $accent; padding: 0 1; }
    #knobs { height: 3; border: round $secondary; padding: 0 1; }
    #mascot { height: 3; border: round $success; padding: 0 1; }
    """
    BINDINGS = [
        Binding("o", "odt", "ODT"), Binding("z", "zq", "ZQ"), Binding("m", "mode", "ONFI/Toggle"),
        Binding("plus,equals_sign", "mts(1)", "MT/s+"), Binding("minus", "mts(-1)", "MT/s-"),
        Binding("right_square_bracket", "temp(1)", "Temp+"), Binding("left_square_bracket", "temp(-1)", "Temp-"),
        Binding("c", "proc", "Process"), Binding("v", "vdd", "Vdd"),
        Binding("n", "nand", "NAND"), Binding("e", "ecc", "ECC"), Binding("p", "wear", "Wear"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, console: str = "deck"):
        super().__init__()
        self.spec = ConsoleSpec.load(console)
        self.nand_names, self.ecc_names = list_parts("parts/nand"), list_parts("parts/controllers")
        self.nand_i = self.nand_names.index(self.spec.nand)
        self.ecc_i = self.ecc_names.index(self.spec.ecc)
        self.part = NandPart.load(self.nand_names[self.nand_i])
        self.ecc = EccConfig.load(self.ecc_names[self.ecc_i])
        self.mode = self.spec.mode
        self.wear_i = 0
        self.frame = 0
        self.cfg = PhyConfig(mts=self.spec.mts, odt=self.spec.odt, zq=self.spec.zq,
                             trace_mm=self.spec.trace_mm, corner=Corner("TT", "Vnom", 25.0))

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="top"):
            yield Static(id="eye-box")
            yield Static(id="stats-box")
        yield Static(id="knobs")
        yield Static(id="mascot")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#eye-box").border_title = "Eye (DQ lane)"
        self.query_one("#stats-box").border_title = "Telemetry"
        self.sub_title = f"{self.spec.name}"
        self.refresh_all()
        self.set_interval(0.2, self.tick)

    # ---- actions ----
    def action_odt(self) -> None: self._set(odt=not self.cfg.odt)
    def action_zq(self) -> None: self._set(zq=not self.cfg.zq)

    def action_mode(self) -> None:
        self.mode = "ONFI" if self.mode == "Toggle" else "Toggle"
        self.refresh_all()

    def action_mts(self, d: int) -> None:
        opts = list(self.spec.mts_options)
        i = min(range(len(opts)), key=lambda k: abs(opts[k] - self.cfg.mts))
        self._set(mts=float(opts[max(0, min(len(opts) - 1, i + d))]))

    def action_temp(self, d: int) -> None:
        i = min(range(len(TEMPS)), key=lambda k: abs(TEMPS[k] - self.cfg.corner.temp_c))
        t = TEMPS[max(0, min(len(TEMPS) - 1, i + d))]
        self._set(corner=Corner(self.cfg.corner.process, self.cfg.corner.vdd, float(t)))

    def action_proc(self) -> None:
        ps = list(PROCESS_TIMING); c = self.cfg.corner
        self._set(corner=Corner(ps[(ps.index(c.process) + 1) % len(ps)], c.vdd, c.temp_c))

    def action_vdd(self) -> None:
        vs = list(VDD_SCALE); c = self.cfg.corner
        self._set(corner=Corner(c.process, vs[(vs.index(c.vdd) + 1) % len(vs)], c.temp_c))

    def action_nand(self) -> None:
        self.nand_i = (self.nand_i + 1) % len(self.nand_names)
        self.part = NandPart.load(self.nand_names[self.nand_i]); self.refresh_all()

    def action_ecc(self) -> None:
        self.ecc_i = (self.ecc_i + 1) % len(self.ecc_names)
        self.ecc = EccConfig.load(self.ecc_names[self.ecc_i]); self.refresh_all()

    def action_wear(self) -> None:
        self.wear_i = (self.wear_i + 1) % len(WEAR); self.refresh_all()

    def _set(self, **kw) -> None:
        self.cfg = self.cfg.with_(**kw); self.refresh_all()

    # ---- rendering ----
    def tick(self) -> None:
        self.frame += 1
        self.draw_eye()

    def draw_eye(self) -> None:
        box = self.query_one("#eye-box")
        cols = max(20, box.size.width - 4)
        rows = max(6, box.size.height - 5)
        eye = analyze(self.cfg)
        t, v = eye_traces(self.cfg, eye, n_traces=90, n_samples=cols * 2, seed=self.frame % 8)
        cv = BrailleCanvas(cols, rows)
        draw_eye(cv, t, v)
        color = "red" if eye.closed else ("yellow" if eye.setup_slack_ps < 25 else "green")
        out = Text(cv.render(), style=color)
        out.append(f"\nW {eye.w_eye_pct:5.1f}% UI   H {eye.h_eye_mv:4.0f} mV   "
                   f"BER {eye.ber:.1e}   slack {eye.setup_slack_ps:+.0f} ps", style="bold")
        box.update(out)

    def refresh_all(self) -> None:
        cfg, eye = self.cfg, analyze(self.cfg)
        pe = WEAR[self.wear_i][1] * self.part.pe_max
        lat = expected_read_latency(self.part, self.ecc, cfg.mts, eye.ber, pe_cycles=pe)
        p_act = phy_power_mw(self.mode, cfg.mts, cfg.trace_mm, cfg.odt, util=0.3)
        p_idle = phy_power_mw(self.mode, cfg.mts, cfg.trace_mm, cfg.odt, util=0.0)

        s = Text()
        def row(k: str, val: str, style: str = "") -> None:
            s.append(f"{k:<13}", style="dim"); s.append(val + "\n", style=style)
        bad = "bold red"
        row("NAND", f"{self.part.name}")
        row("ECC", f"{self.ecc.name}")
        row("Wear", f"{WEAR[self.wear_i][0]} ({pe:.0f} P/E)")
        row("Bus BW", f"{bus_mbps(cfg.mts, cfg.bus_bits):.0f} MB/s")
        row("Gamma / Rterm", f"{eye.gamma:+.2f} / {min(eye.r_term_ohm, 9999):.0f} ohm")
        row("t_read", f"{lat.total_us:,.1f} us", bad if lat.total_us > 500 else "")
        row("  tR+DMA+ECC", f"{lat.t_r_us:.0f}+{lat.t_dma_us:.1f}+{lat.t_ecc_us:.1f} us")
        row("  retry", f"{lat.t_retry_us:.1f} us  (mean {lat.mean_retries:.2f})")
        row("P(uncorr)", f"{lat.p_uncorrectable:.1e}", bad if lat.p_uncorrectable > 1e-6 else "")
        row("Crash / s", f"{eye.crash_prob_per_s:.0%}", bad if eye.crash_prob_per_s > 0 else "green")
        row("PHY power", f"{p_act:.0f} mW active, {p_idle:.0f} mW idle")
        self.query_one("#stats-box").update(s)

        k = Text()
        for name, on in (("ODT", cfg.odt), ("ZQ", cfg.zq)):
            k.append(f"[{name}: {'on' if on else 'off'}] ", style="green" if on else "red")
        k.append(f"[Mode: {self.mode}] [MT/s: {cfg.mts:g}] [Corner: {cfg.corner.name}] "
                 f"[Trace: {cfg.trace_mm:g} mm]")
        self.query_one("#knobs").update(k)

        face, msg = mascot(cfg, eye, lat, self.mode, self.spec.bom_budget_usd, self.part.usd_per_gb)
        self.query_one("#mascot").update(Text(f"{face}  Mascot: \"{msg}\""))
        self.draw_eye()


def run(console: str = "deck") -> None:
    ConsoleArchitectApp(console).run()
