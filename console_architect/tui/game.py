"""Console Architect: the playable terminal game (Textual)."""
from __future__ import annotations

import math
import time

import numpy as np
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from ..core import save
from ..core.build import Build
from ..core.engine import Engine
from ..core.levels import Level, list_levels, load_level
from ..core.options import KNOBS, lesson_lines, nudge, values_for
from ..core.runner import Runner, to_dmg
from ..core.spec import Spec, estimate
from ..core.storage import perf
from ..core.verdict import AXES, AXIS_LABEL, collect, explain, reviews
from .art import (GB_BRAND, GB_CAPTION, bar, deck_left, deck_right, deck_shoulders, frame_to_text,
                  gb_ab, gb_dpad, gb_selstart, score_style, text_screen)
from .braille import BrailleCanvas, draw_eye
from ..core.phy import eye_traces

LOGO = (
    "\u2554\u2550\u2557\u2554\u2550\u2557\u2554\u2557\u2554\u2554\u2550\u2557\u2554\u2550\u2557\u2566  \u2554\u2550\u2557   \u2554\u2550\u2557\u2566\u2550\u2557\u2554\u2550\u2557\u2566 \u2566\u2566\u2554\u2566\u2557\u2554\u2550\u2557\u2554\u2550\u2557\u2554\u2566\u2557\n"
    "\u2551  \u2551 \u2551\u2551\u2551\u2551\u255a\u2550\u2557\u2551 \u2551\u2551  \u2551\u2563    \u2560\u2550\u2563\u2560\u2566\u255d\u2551  \u2560\u2550\u2563\u2551 \u2551 \u2551\u2563 \u2551   \u2551 \n"
    "\u255a\u2550\u255d\u255a\u2550\u255d\u255d\u255a\u255d\u255a\u2550\u255d\u255a\u2550\u255d\u2569\u2550\u255d\u255a\u2550\u255d   \u2569 \u2569\u2569\u255a\u2550\u255a\u2550\u255d\u2569 \u2569\u2569 \u2569 \u255a\u2550\u255d\u255a\u2550\u255d \u2569 ")


def T(*parts) -> Text:
    t = Text(no_wrap=False)
    for p in parts:
        if isinstance(p, tuple):
            t.append(p[0], style=p[1])
        else:
            t.append(p)
    return t


def stars(n: int) -> str:
    return "\u2605" * n + "\u2606" * (5 - n)


# =============================================================================
class TitleScreen(Screen):
    BINDINGS = [Binding("up", "move(-1)", "Up"), Binding("down", "move(1)", "Down"),
                Binding("enter", "pick", "Select"), Binding("q", "app.quit", "Quit")]
    DEFAULT_CSS = """
    TitleScreen { align: center top; background: #0e1018; }
    #logo { width: auto; height: 3; margin-top: 1; color: #6ee7b7; }
    #tag { width: auto; height: 2; color: #9aa3b8; }
    #pick { width: 100; height: 1fr; }
    #list { width: 40; height: 100%; border: round #3c4150; padding: 0 1; }
    #brief { width: 1fr; height: 100%; border: round #3c4150; padding: 0 1; }
    """

    def __init__(self):
        super().__init__()
        self.levels = list_levels()
        self.i = 0

    def compose(self) -> ComposeResult:
        yield Static(Text(LOGO), id="logo")
        yield Static(Text("Design a handheld's memory system. Then play on it. Feel what every choice does.",
                          justify="center"), id="tag")
        with Horizontal(id="pick"):
            yield Static(id="list")
            yield Static(id="brief")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_view()

    def action_move(self, d: int) -> None:
        self.i = (self.i + d) % len(self.levels)
        self.refresh_view()

    def action_pick(self) -> None:
        self.app.push_screen(BuildScreen(self.levels[self.i]))

    def on_screen_resume(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        best = save.load_scores()
        lst = Text()
        for k, L in enumerate(self.levels):
            cur = k == self.i
            b = best.get(L.id)
            lst.append(("\u25b6 " if cur else "  ") + f"{L.order}. {L.name}\n", style="bold #6ee7b7" if cur else "")
            lst.append(f"     {L.console}  " + (stars(b['stars']) if b else "\u2606\u2606\u2606\u2606\u2606") + "\n",
                       style="#8b93a7")
        self.query_one("#list").update(lst)
        L = self.levels[self.i]
        t = Text()
        t.append(f"{L.name}\n", style="bold")
        t.append(f"{L.console}\n\n", style="#8b93a7")
        t.append(L.blurb + "\n\n")
        t.append("GOALS\n", style="bold #6ee7b7")
        for g in L.goals:
            t.append(f"  \u2022 {g}\n")
        t.append(f"\nSession: {L.session_h:g} h of play (compressed), ambient {L.ambient_c:g} C\n", style="#8b93a7")
        if L.patch_gb:
            t.append(f"Day-one patch {L.patch_gb:g} GB, world load {L.load_gb:g} GB\n", style="#8b93a7")
        if L.power_cut_at:
            t.append("Event: sudden power loss mid-session\n", style="#e8c547")
        self.query_one("#brief").update(t)


# =============================================================================
class BuildScreen(Screen):
    BINDINGS = [Binding("up", "move(-1)", "Select"), Binding("down", "move(1)", "Select"),
                Binding("left", "change(-1)", "Less"), Binding("right", "change(1)", "More"),
                Binding("enter", "tapeout", "TAPE OUT"), Binding("r", "reset", "Reset"),
                Binding("escape", "back", "Back")]
    DEFAULT_CSS = """
    BuildScreen { background: #0e1018; }
    #title { height: 2; padding: 0 1; }
    #main { height: 1fr; }
    #knobs { width: 52; height: 100%; border: round #3c4150; padding: 0 1; }
    #right { width: 1fr; }
    #spec { height: auto; min-height: 15; border: round #3c4150; padding: 0 1; }
    #scope { height: 1fr; min-height: 8; border: round #3c4150; padding: 0 1; }
    #learn { height: 9; border: round #6ee7b7; padding: 0 1; }
    """

    def __init__(self, level: Level, build: Build | None = None):
        super().__init__()
        self.level = level
        self.build = build or Build(**level.default)
        self.cur = 0
        self.spec = estimate(self.build, level)
        self.prev: dict | None = None
        self.frame = 0
        self._fix_cursor(1)

    def compose(self) -> ComposeResult:
        yield Static(id="title")
        with Horizontal(id="main"):
            yield Static(id="knobs")
            with Vertical(id="right"):
                yield Static(id="spec")
                yield Static(id="scope")
        yield Static(id="learn")
        yield Footer()

    def on_resize(self, event) -> None:
        self.render_knobs()
        self.draw_scope()

    def on_mount(self) -> None:
        self.query_one("#spec").border_title = "Spec sheet (live)"
        self.query_one("#scope").border_title = "Signal scope"
        self.refresh_all()
        self.set_interval(0.25, self.draw_scope)

    # ---- cursor / edits ----
    def _applicable(self, i: int) -> bool:
        return KNOBS[i].applies(self.build)

    def _fix_cursor(self, d: int) -> None:
        for _ in range(len(KNOBS)):
            if self._applicable(self.cur):
                return
            self.cur = (self.cur + d) % len(KNOBS)

    def action_move(self, d: int) -> None:
        self.cur = (self.cur + d) % len(KNOBS)
        self._fix_cursor(d)
        self.refresh_all()

    def action_change(self, d: int) -> None:
        k = KNOBS[self.cur]
        old = self.spec
        self.build = nudge(self.build, k, self.level, d)
        self.prev = self._vals(old)
        self.spec = estimate(self.build, self.level)
        self._fix_cursor(1)
        self.refresh_all()

    def action_reset(self) -> None:
        self.prev = self._vals(self.spec)
        self.build = Build(**self.level.default)
        self.spec = estimate(self.build, self.level)
        self.refresh_all()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_tapeout(self) -> None:
        if not self.spec.fits:
            self.notify(f"The game doesn't fit! Needs {self.spec.need_gb:.0f} GB.", severity="error")
            return
        self.app.push_screen(PlayScreen(self.level, self.build))

    # ---- rendering ----
    @staticmethod
    def _vals(s: Spec) -> dict:
        return dict(boot=s.patch_s + s.load_s, ratio=s.supply_ratio, freezes=s.freezes_per_min,
                    battery=s.battery_h, temp=s.temp_nand, corners=s.corner_fail,
                    life=s.life_years if s.life_years is not None else 99.0, retail=s.retail)

    def _delta(self, key: str, now: float, higher_better: bool, fmt: str = "{:.1f}") -> Text:
        if not self.prev or key not in self.prev:
            return Text("")
        d = now - self.prev[key]
        if abs(d) < 1e-9 or abs(d) < 0.005 * max(1.0, abs(now)):
            return Text("")
        good = (d > 0) == higher_better
        return Text(f"  {'\u25b2' if d > 0 else '\u25bc'}{fmt.format(abs(d))}", style="bold green" if good else "bold red")

    def refresh_all(self) -> None:
        L, b, s = self.level, self.build, self.spec
        self.query_one("#title").update(T(
            ("BUILD  ", "bold #6ee7b7"), (f"{L.name} \u00b7 {L.console}", "bold"),
            (f"    target retail ${L.target_retail_usd:g} \u00b7 battery \u2265 {L.battery_goal_h:g} h \u00b7 fps \u2265 {L.fps_goal:g}", "#8b93a7")))
        self.render_knobs()
        self.render_spec()
        self.render_learn()
        self.draw_scope()

    def render_knobs(self) -> None:
        w = self.query_one("#knobs")
        lines: list[Text] = []
        cursor_line = 0
        group = ""
        for i, k in enumerate(KNOBS):
            if k.group != group:
                group = k.group
                lines.append(Text(group, style="bold #6ee7b7"))
            ok = k.applies(self.build)
            v = getattr(self.build, k.key)
            val = str(k.fmt(v))
            sel = i == self.cur
            if sel:
                cursor_line = len(lines)
            t = Text()
            t.append("\u25b6 " if sel else "  ", style="bold #6ee7b7")
            t.append(f"{k.label:<20}", style=("bold" if sel else "") if ok else "dim")
            if not ok:
                t.append("  n/a", style="dim")
            else:
                warn = (k.key == "mts" and self.build.bus_mode == "Toggle" and v > 3200)
                t.append(("\u25c0 " if sel else "  ") + val + (" \u25b6" if sel else ""),
                         style="bold #6ee7b7" if sel else ("#e8c547" if warn else ""))
                if warn:
                    t.append(" (Toggle caps 3200)", style="#e8c547")
            lines.append(t)
        h = max(8, (w.size.height or self.app.size.height - 14) - 2)
        start = max(0, min(cursor_line - h // 2, len(lines) - h))
        out = Text("\n").join(lines[start:start + h])
        w.update(out)

    def render_spec(self) -> None:
        L, s, b = self.level, self.spec, self.build
        t = Text()

        def row(label: str, parts: list, delta: Text | None = None) -> None:
            t.append(f"{label:<14}", style="#8b93a7")
            for p in parts:
                t.append(*p) if isinstance(p, tuple) else t.append(p)
            if delta:
                t.append_text(delta)
            t.append("\n")

        boot = s.patch_s + s.load_s
        row("Boot", [(f"{s.patch_s:.1f} s patch + {s.load_s:.1f} s load", "red" if boot > 45 else "yellow" if boot > 15 else "green")],
            self._delta("boot", boot, False))
        r = s.supply_ratio
        row("Streaming", [(f"{s.supply_mbps:.0f} of {s.demand_peak_mbps:.0f} MB/s", "green" if r >= 1.15 else "yellow" if r >= 0.9 else "red"),
                          ("  ok" if r >= 1.15 else "  marginal" if r >= 0.9 else "  POP-IN", "dim")],
            self._delta("ratio", r, True, "{:.2f}x"))
        row("", [(f"limit: {s.limiter}", "dim")])
        row("Freezes", [(f"{s.freezes_per_min:.1f}/min", "green" if s.freezes_per_min < 1 else "yellow" if s.freezes_per_min < 4 else "red"),
                        (f"  worst {s.worst_hitch_ms:.0f} ms", "dim")], self._delta("freezes", s.freezes_per_min, False))
        row("Battery", [(f"{s.battery_h:.1f} h", "green" if s.battery_h >= L.battery_goal_h else "red"),
                        (f"  ({s.mean_w:.1f} W avg, goal {L.battery_goal_h:g} h)", "dim")], self._delta("battery", s.battery_h, True))
        row("Temperature", [(f"case {s.temp_case:.0f} C", "red" if s.temp_case > L.throttle_c else ""), (f"  NAND {s.temp_nand:.0f} C", "red" if s.temp_nand > 75 else "")],
            self._delta("temp", s.temp_nand, False, "{:.0f}"))
        if b.nand_based:
            if s.corner_fail == 0:
                row("PVT corners", [(f"{s.corner_total}/{s.corner_total} pass", "green"), (f"  worst {s.worst_slack_ps:+.0f} ps", "dim")],
                    self._delta("corners", s.corner_fail, False, "{:.0f}"))
            else:
                row("PVT corners", [(f"{s.corner_fail}/{s.corner_total} FAIL", "bold red"), (f"  worst {s.worst_slack_ps:+.0f} ps @ {s.worst_corner}", "dim")],
                    self._delta("corners", s.corner_fail, False, "{:.0f}"))
        else:
            row("PVT corners", [("n/a (no NAND PHY)", "dim")])
        row("Lifespan", [("n/a" if s.life_years is None else f"{s.life_years:.1f} years", "green" if (s.life_years or 9) >= 3 else "red"),
                         (f"  @{ {'gb': 8, 'deck': 120}[L.theme] } GB/day", "dim")], self._delta("life", s.life_years if s.life_years is not None else 99.0, True))
        row("Fits game", [("yes" if s.fits else f"NO, needs {s.need_gb:.0f} GB", "green" if s.fits else "bold red")])
        t.append("\n")
        over = s.retail > L.target_retail_usd
        t.append(f"BOM ${s.bom:.0f}   RETAIL ${s.retail:.0f} ", style="bold red" if over else "bold green")
        t.append(f"/ ${L.target_retail_usd:g} ", style="dim")
        t.append(bar(min(1.0, s.retail / (1.4 * L.target_retail_usd)), 16), style="red" if over else "green")
        t.append_text(self._delta("retail", s.retail, False, "${:.0f}"))
        self.query_one("#spec").update(t)

    def render_learn(self) -> None:
        k = KNOBS[self.cur]
        w = self.query_one("#learn")
        w.border_title = f"Why {k.label.lower()} matters"
        t = Text()
        for tag, text in lesson_lines(k.key, getattr(self.build, k.key)):
            t.append(f"{tag:<6}", style="bold #6ee7b7" if tag != "NOW" else "bold #e8c547")
            t.append(text + "\n")
        w.update(t)

    def draw_scope(self) -> None:
        w = self.query_one("#scope")
        s, b = self.spec, self.build
        if not b.nand_based or s.eye is None:
            w.update(Text("No NAND bus here: nothing to terminate. The physics for this device is mechanical or DRAM.", style="dim"))
            return
        self.frame += 1
        cols = max(16, min(70, (w.size.width or 60) - 6))
        rows = max(3, min(8, (w.size.height or 10) - 5))
        from ..core.build import phy_config
        cfg = phy_config(b, s.temp_nand)
        t_ui, v = eye_traces(cfg, s.eye, n_traces=70, n_samples=cols * 2, seed=self.frame % 6)
        cv = BrailleCanvas(cols, rows)
        draw_eye(cv, t_ui, v)
        e = s.eye
        out = Text(cv.render(), style="red" if e.closed else "yellow" if e.setup_slack_ps < 25 else "green")
        out.append(f"\nW {e.w_eye_pct:.0f}% UI  H {e.h_eye_mv:.0f} mV  slack {e.setup_slack_ps:+.0f} ps @ {s.temp_nand:.0f} C", style="bold")
        w.update(out)


# =============================================================================
class PlayScreen(Screen):
    BINDINGS = [Binding("escape", "abort", "Abort"), Binding("p", "pause", "Pause")]
    DEFAULT_CSS = """
    PlayScreen { background: #0e1018; align: center top; }
    #root { height: 1fr; width: 1fr; }
    #telemetry { padding: 0 1; border: round #3c4150; }
    #lcd, #hud { width: auto; }

    PlayScreen.gb #root { layout: horizontal; }
    PlayScreen.gb #body { width: 50; height: auto; background: #c4c6b8; border: heavy #9a9c8e; padding: 0 1; margin-right: 1; }
    PlayScreen.gb #brand { width: 100%; content-align: center middle; color: #3d3f4a; text-style: bold; height: 1; }
    PlayScreen.gb #bezel { width: 100%; height: auto; background: #565a68; padding: 1 1; align-horizontal: center; }
    PlayScreen.gb #caption { width: 100%; content-align: center middle; color: #3d3f6b; height: 1; margin-top: 1; }
    PlayScreen.gb #controls { height: 6; margin-top: 1; }
    PlayScreen.gb #dpad { width: 26; height: 5; }
    PlayScreen.gb #ab { width: 1fr; height: 5; }
    PlayScreen.gb #selstart { height: 1; margin-top: 1; }
    PlayScreen.gb #telemetry { width: 1fr; height: 100%; }
    PlayScreen.gb #hud { background: #565a68; }

    PlayScreen.deck #root { layout: vertical; }
    PlayScreen.deck #body { width: auto; height: auto; background: #14161b; border: round #3c4150; padding: 0 1; }
    PlayScreen.deck #mid { height: auto; width: auto; }
    PlayScreen.deck #left, PlayScreen.deck #right { width: 17; height: auto; margin-top: 1; }
    PlayScreen.deck #bezel { width: auto; height: auto; background: #05060a; border: round #2a2e3a; }
    PlayScreen.deck #caption { height: 1; color: #6b7388; width: 100%; content-align: center middle; }
    PlayScreen.deck #telemetry { width: 100%; height: 1fr; }
    """

    def __init__(self, level: Level, build: Build, seed: int | None = None):
        super().__init__(classes=level.theme)
        self.level, self.build = level, build
        self.seed = seed if seed is not None else int(time.time()) % 100000
        self.spec = estimate(build, level)
        self.engine = Engine(build, level, self.seed)
        self.runner = Runner(self.seed)
        self.boot = self.engine.boot()
        self.phase = "boot"
        self.boot_t = 0.0
        self.boot_total = max(2.5, min(5.0, 1.5 + 1.3 * math.log10(1.0 + self.boot.patch_s + self.boot.load_s)))
        self.phase_t = 0.0
        self.jump_pending = False
        self.flash = 0.0
        self.credit = 1.0
        self.overlay: tuple | None = None
        self.overlay_t = 0.0
        self.paused = False
        self.events_log: list[tuple[str, str]] = []
        self.cols = 40
        self.rows = 18
        self.last_img: Text | None = None
        self._last = time.monotonic()
        self.finish_reason = ""
        self.metrics = None

    # ---- layout ----
    def _lcd_size(self) -> tuple[int, int]:
        W, H = self.app.size
        if self.level.theme == "gb":
            rows = min(18, max(8, H - 16))
            cols = min(40, int(round(rows * 2 * 10 / 9)), max(16, W - 60))
            rows = max(6, int(round(cols * 9 / 10 / 2)))
        else:
            rows = min(21, max(8, H - 19))
            cols = min(int(round(rows * 2 * 1.6)), max(24, W - 42))
            rows = max(6, int(round(cols / 1.6 / 2)))
        return cols - cols % 2, rows

    def compose(self) -> ComposeResult:
        if self.level.theme == "gb":
            with Horizontal(id="root"):
                with Vertical(id="body"):
                    yield Static(GB_BRAND, id="brand")
                    with Vertical(id="bezel"):
                        yield Static(id="hud")
                        yield Static(id="lcd")
                    yield Static(GB_CAPTION, id="caption")
                    with Horizontal(id="controls"):
                        yield Static(gb_dpad(), id="dpad")
                        yield Static(gb_ab(False), id="ab")
                    yield Static(gb_selstart(), id="selstart")
                yield Static(id="telemetry")
        else:
            with Vertical(id="root"):
                with Vertical(id="body"):
                    yield Static(id="shoulders")
                    with Horizontal(id="mid"):
                        yield Static(deck_left(), id="left")
                        with Vertical(id="bezel"):
                            yield Static(id="hud")
                            yield Static(id="lcd")
                        yield Static(deck_right(False), id="right")
                    yield Static("\u2630  VIEW  \u00b7  STEAM-SHAPED MEMORY LAB  \u00b7  MENU  \u2630", id="caption")
                yield Static(id="telemetry")
        yield Footer()

    def on_mount(self) -> None:
        self.cols, self.rows = self._lcd_size()
        lcd = self.query_one("#lcd")
        lcd.styles.width, lcd.styles.height = self.cols, self.rows
        self.query_one("#hud").styles.width = self.cols
        if self.level.theme == "deck":
            self.query_one("#shoulders").update(deck_shoulders(self.cols + 34))
        self.query_one("#telemetry").border_title = "Live telemetry"
        self._timer = self.set_interval(1 / 20, self._on_timer)
        self.draw_boot()
        self.draw_telemetry()

    # ---- input ----
    def on_key(self, event) -> None:
        if event.key in ("space", "up", "w", "enter", "z"):
            self.jump_pending = True
            self.flash = 0.18
            self._update_buttons()
            event.stop()

    def _update_buttons(self) -> None:
        on = self.flash > 0
        if self.level.theme == "gb":
            self.query_one("#ab").update(gb_ab(on))
        else:
            self.query_one("#right").update(deck_right(on))

    def action_abort(self) -> None:
        self._timer.stop()
        self.app.pop_screen()

    def action_pause(self) -> None:
        self.paused = not self.paused

    # ---- loop ----
    def _on_timer(self) -> None:
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        if not self.paused:
            self.advance(dt)

    def advance(self, dt: float) -> None:
        if self.flash > 0:
            self.flash = max(0.0, self.flash - dt)
            if self.flash == 0.0:
                self._update_buttons()
        if self.phase == "boot":
            self.boot_t += dt
            self.draw_boot()
            if self.boot_t >= self.boot_total:
                self.phase = "play"
        elif self.phase == "play":
            self._play(dt)
        elif self.phase == "end":
            self.phase_t += dt
            if self.phase_t >= 3.0:
                self._finish()
        self.draw_telemetry()

    def _play(self, dt: float) -> None:
        e, r = self.engine, self.runner
        tick = e.step(dt)
        for kind, text in tick.events:
            self.events_log.insert(0, (kind, f"{e.t:5.1f}s  {text}"))
            if kind == "power_cut":
                self.overlay, self.overlay_t = ("power", e.save_status), 2.0
        del self.events_log[8:]
        frozen = e.frozen
        jump = self.jump_pending and not frozen
        self.jump_pending = False
        r.step(dt, e.speed, jump)
        if self.overlay:
            self.overlay_t -= dt
            self.draw_overlay()
            if self.overlay_t <= 0:
                self.overlay = None
        elif not frozen:
            self.credit += e.fps_factor
            if self.credit >= 1.0:
                self.credit -= 1.0
                self.draw_game()
        if e.finished:
            self.phase, self.phase_t = "end", 0.0
            self.finish_reason = "crash" if e.crashed else "battery" if e.battery_dead else "done"
            self.draw_end()

    # ---- drawing ----
    def _bg(self) -> tuple[str, str]:
        return ("#9bbc0f", "#0f380f") if self.level.theme == "gb" else ("white", "#05060a")

    def draw_boot(self) -> None:
        cols, rows = self.cols, self.rows
        fg, bg = self._bg()
        b, L = self.boot, self.level
        p = min(1.0, self.boot_t / self.boot_total)
        total = b.patch_s + b.load_s
        share = b.patch_s / total if total > 0 else 0
        w = max(8, cols - 12)
        if L.patch_gb > 0 and p < share:
            pp = p / share if share else 1
            lines = [("ARCHITECT OS", "bold"), "", f"Installing day-one patch ({L.patch_gb:g} GB)",
                     f"[{bar(pp, w)}]", f"{pp * b.patch_s:.1f} s of {b.patch_s:.1f} s",
                     f"({b.patch_s / (self.boot_total * share + 1e-9):.0f}x speed-up)" if b.patch_s > 5 else ""]
        else:
            pl = (p - share) / (1 - share) if share < 1 else 1
            pl = max(0.0, pl)
            lines = [("ARCHITECT OS", "bold"), "", f"Loading world ({L.load_gb:g} GB)",
                     f"[{bar(pl, w)}]", f"{pl * b.load_s:.1f} s of {b.load_s:.1f} s", ""]
        lines += ["", (f"Read speed {self.spec.perf.seq_read_mbps:.0f} MB/s", "dim")]
        self.query_one("#lcd").update(text_screen(cols, rows, lines, fg, bg))
        self.query_one("#hud").update(Text(" " * cols, style=f"{fg} on {bg}"))

    def draw_game(self) -> None:
        e, r = self.engine, self.runner
        W = self.cols
        Hpx = self.rows * 2
        img = r.render(W, Hpx, e.ahead)
        if self.level.theme == "gb":
            img = to_dmg(img)
        self.last_img = frame_to_text(img)
        self.query_one("#lcd").update(self.last_img)
        fg, bg = ("#9bbc0f", "#0f380f") if self.level.theme == "gb" else ("#e6e9f2", "#05060a")
        hearts = "\u2665" * r.hp + "\u2661" * (3 - r.hp)
        hud = Text(f"{hearts}  {int(r.x):>4} m", style=f"bold {fg} on {bg}")
        pad = W - len(hud.plain) - 12
        hud.append(" " * max(1, pad), style=f"on {bg}")
        hud.append(f"{int(60 * e.fps_factor):>2} FPS", style=f"bold {fg} on {bg}")
        self.query_one("#hud").update(hud)

    def draw_overlay(self) -> None:
        cols, rows = self.cols, self.rows
        kind, status = self.overlay
        if self.overlay_t > 1.0:
            lines = [("POWER LOST", "bold"), "", "(battery connector wiggled loose)"]
        else:
            ok = status == "ok"
            lines = [("REBOOTING...", "bold"), "", "save file: " + ("OK" if ok else "CORRUPTED" if status == "corrupt" else "LOST (RAM is volatile)")]
        self.query_one("#lcd").update(text_screen(cols, rows, lines, "#c0c0c0" if self.level.theme == "deck" else "#9bbc0f", "#000000"))

    def draw_end(self) -> None:
        cols, rows = self.cols, self.rows
        e = self.engine
        if self.finish_reason == "crash":
            lines = [("A problem has been detected", "bold"), "", "DQ_SETUP_HOLD_VIOLATION", "",
                     *self._wrap(e.crash_reason, cols - 4), "", "Collecting memory dump..."]
            self.query_one("#lcd").update(text_screen(cols, rows, lines, "white", "#0a3dc2"))
        elif self.finish_reason == "battery":
            self.query_one("#lcd").update(text_screen(cols, rows, [("BATTERY EMPTY", "bold"), "", "session ended early"], "white", "#300000"))
        else:
            fg, bg = self._bg()
            self.query_one("#lcd").update(text_screen(cols, rows, [("SESSION COMPLETE", "bold"), "", f"{int(self.runner.x)} m run"], fg, bg))

    @staticmethod
    def _wrap(s: str, w: int) -> list[str]:
        out, cur = [], ""
        for word in s.split():
            if len(cur) + len(word) + 1 > w:
                out.append(cur)
                cur = word
            else:
                cur = (cur + " " + word).strip()
        return out + ([cur] if cur else [])

    def draw_telemetry(self) -> None:
        e, L, b = self.engine, self.level, self.build
        p = e.perf(e.temp_nand)
        t = Text()

        def row(k: str, *parts) -> None:
            t.append(f"{k:<11}", style="#8b93a7")
            for x in parts:
                t.append(*x) if isinstance(x, tuple) else t.append(x)
            t.append("\n")

        if self.phase == "boot":
            row("Phase", ("BOOT: patch + load", "bold"))
            row("Storage", f"{p.seq_read_mbps:.0f} MB/s read, {p.write_native_mbps:.0f} MB/s native write")
            row("Limiter", (p.limiter, "dim"))
        else:
            fps = 0 if e.frozen else 60 * e.fps_factor
            _, low = e.fps()
            row("Frame", ("FROZEN", "bold red") if e.frozen else (f"{fps:.0f} fps", "green" if fps >= 55 else "yellow"),
                f"   1% low {low:.0f}   stutters {e.stutters}")
            need, have = e.speed * L.mb_per_col, e.supply_mbps
            row("Streaming", (f"{have:.0f} MB/s", "green" if have > need else "red"), f" supply vs {need:.0f} need")
            ahead_frac = e.ahead / L.ahead_max
            row("Look-ahead", (bar(ahead_frac, 12), "green" if ahead_frac > 0.5 else "yellow" if ahead_frac > 0.25 else "red"),
                f" {e.ahead:.0f}/{L.ahead_max:.0f} cols")
            thr = e.fps_factor < 0.98
            row("Temp", (f"case {e.temp_case:.0f} C", "red" if thr else ""), (f"  NAND {e.temp_nand:.0f} C", "red" if e.temp_nand > 75 else ""),
                ("  THROTTLING" if thr else "", "bold red"))
            row("Battery", (bar(e.battery_pct / 100, 12), "green" if e.battery_pct > 25 else "red"),
                f" {e.battery_pct:.0f}%  {e.total_w:.1f} W")
            if p.pslc_gb > 0:
                row("pSLC cache", (bar(e.cache.fill, 12), "yellow" if e.cache.fill > 0.5 else "green"), f" {e.cache.fill:.0%} full")
            if p.eye:
                row("Eye", (f"slack {p.eye.setup_slack_ps:+.0f} ps", "red" if p.eye.closed else "green"), f"  BER {p.eye.ber:.0e}")
            row("Session", bar(e.t / L.real_s, 12), f" {e.t / L.real_s * L.session_h:.1f}/{L.session_h:g} h")
        t.append("\nEVENTS\n", style="bold #6ee7b7")
        col = {"gc": "yellow", "save": "yellow", "seek": "red", "read_error": "red", "crash": "bold red",
               "power_cut": "bold magenta", "battery": "bold red"}
        for kind, text in self.events_log[:6]:
            t.append(text + "\n", style=col.get(kind, ""))
        if self.paused:
            t.append("\nPAUSED\n", style="bold")
        t.append("\nSpace/Up/Enter = jump   P = pause   Esc = abort", style="dim")
        self.query_one("#telemetry").update(t)

    # ---- end of run ----
    def _finish(self) -> None:
        self._timer.stop()
        e = self.engine
        self.metrics = collect(e, self.boot, self.spec, self.level, self.runner.deaths, self.runner.late_hits)
        self.app.switch_screen(ResultScreen(self.level, self.build, self.spec, self.metrics))


# =============================================================================
class ResultScreen(Screen):
    BINDINGS = [Binding("r", "retry", "Redesign"), Binding("n", "next", "Next level"),
                Binding("q,escape", "menu", "Menu")]
    DEFAULT_CSS = """
    ResultScreen { background: #0e1018; }
    #verdict { height: 3; padding: 0 1; border: round #6ee7b7; }
    #top { height: auto; min-height: 12; }
    #card { width: 3fr; border: round #3c4150; padding: 0 1; height: auto; }
    #bom { width: 2fr; border: round #3c4150; padding: 0 1; height: auto; }
    #whywrap { height: 1fr; border: round #e8c547; padding: 0 1; }
    """

    def __init__(self, level: Level, build: Build, spec: Spec, m):
        super().__init__()
        self.level, self.build, self.spec, self.m = level, build, spec, m
        self.new_best = save.record(level.id, m.stars, m.overall, m.retail)

    def compose(self) -> ComposeResult:
        yield Static(id="verdict")
        with Horizontal(id="top"):
            yield Static(id="card")
            yield Static(id="bom")
        with VerticalScroll(id="whywrap"):
            yield Static(id="why")
        yield Footer()

    def on_mount(self) -> None:
        m, L = self.m, self.level
        v = Text()
        ok = m.passed and m.overall >= 55
        v.append(f"{stars(m.stars)}  ", style="bold #e8c547")
        v.append(m.verdict, style="bold green" if ok else "bold red")
        v.append(f"   overall {m.overall:.0f}/100", style="dim")
        if self.new_best:
            v.append("   NEW BEST", style="bold #e8c547")
        self.query_one("#verdict").update(v)
        self.query_one("#verdict").border_title = f"{L.name}"

        raw = {
            "load": f"{m.patch_s:.1f} s patch + {m.load_s:.1f} s load",
            "smooth": f"avg {m.fps_avg:.0f} / 1% low {m.fps_1pct:.0f} fps ({m.stutters} freezes)",
            "popin": f"{m.pop_pct:.0f}% of the time" + (f", {m.late_hits} late hits" if m.late_hits else ""),
            "battery": (f"DIED at {m.dead_at_h:.1f} h" if m.battery_dead else f"{m.battery_h:.1f} h (goal {L.battery_goal_h:g})"),
            "reliability": ("CRASHED" if m.crashed else "saves " + m.save_status.upper() if m.save_status in ("corrupt", "lost")
                            else f"{m.corner_fail}/{m.corner_total} corners fail" if m.corner_fail else "all clear"),
            "price": f"${m.retail:.0f} vs ${L.target_retail_usd:g}",
            "life": "n/a" if m.life_years is None else f"{m.life_years:.1f} years",
        }
        t = Text()
        for k in AXES:
            s = m.scores[k]
            t.append(f"{AXIS_LABEL[k]:<15}", style="#8b93a7")
            t.append(bar(s / 100, 12), style=score_style(s))
            t.append(f" {s:>3.0f}  ", style=score_style(s))
            t.append(raw[k] + "\n")
        t.append("\nCustomer reviews\n", style="bold #6ee7b7")
        for n, who, text in reviews(m, L):
            t.append(f"{stars(n)} ", style="#e8c547")
            t.append(f"{who}: ", style="bold")
            t.append(text + "\n")
        c = self.query_one("#card")
        c.border_title = "Scorecard"
        c.update(t)

        bt = Text()
        for name, usd in self.spec.lines:
            bt.append(f"{name[:34]:<35}", style="")
            bt.append(f"${usd:>7.2f}\n", style="#8b93a7")
        bt.append(f"{'BOM total':<35}", style="bold")
        bt.append(f"${self.spec.bom:>7.2f}\n", style="bold")
        bt.append(f"{'Retail (x' + format(L.markup, 'g') + ')':<35}", style="bold")
        bt.append(f"${self.spec.retail:>7.2f}", style="bold " + ("red" if self.spec.retail > L.target_retail_usd else "green"))
        b = self.query_one("#bom")
        b.border_title = "Bill of materials"
        b.update(bt)

        w = Text()
        for les in explain(m, self.build, L, self.spec):
            w.append(f"\u25cf {les.headline}\n", style="bold")
            w.append(f"  Why: {les.why}\n")
            w.append(f"  Try: {les.tip}\n\n", style="#6ee7b7")
        self.query_one("#whywrap").border_title = "Why did that happen?"
        self.query_one("#why").update(w)

    def action_retry(self) -> None:
        self.app.pop_screen()   # back to the BuildScreen with the same design

    def action_next(self) -> None:
        levels = list_levels()
        ids = [l.id for l in levels]
        i = ids.index(self.level.id)
        nxt = levels[(i + 1) % len(levels)]
        self.app.pop_screen()
        self.app.pop_screen()
        self.app.push_screen(BuildScreen(nxt))

    def action_menu(self) -> None:
        while len(self.app.screen_stack) > 2:
            self.app.pop_screen()


# =============================================================================
class ArchitectApp(App):
    TITLE = "Console Architect"
    CSS = "Screen { background: #0e1018; }"

    def __init__(self, level_id: str | None = None):
        super().__init__()
        self.start_level = level_id

    def on_mount(self) -> None:
        self.push_screen(TitleScreen())
        if self.start_level:
            self.push_screen(BuildScreen(load_level(self.start_level)))


def run(level_id: str | None = None) -> None:
    ArchitectApp(level_id).run()
