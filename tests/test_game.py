import asyncio

import numpy as np
from rich.cells import cell_len

from console_architect.core.build import Build
from console_architect.core.engine import Engine
from console_architect.core.levels import list_levels, load_level
from console_architect.core.runner import Runner, to_dmg
from console_architect.core.spec import estimate
from console_architect.core.verdict import collect, explain
from console_architect.tui.art import frame_to_text
from console_architect.tui.game import ArchitectApp, BuildScreen, PlayScreen, ResultScreen


def run(level_id, seed=1, **kw):
    L = load_level(level_id)
    b = Build(**{**L.default, **kw})
    sp = estimate(b, L)
    e = Engine(b, L, seed)
    boot = e.boot()
    while not e.finished:
        e.step(0.05)
    return L, b, sp, e, collect(e, boot, sp, L)


def test_levels_load_and_defaults_are_playable():
    for L in list_levels():
        _, _, _, e, m = run(L.id)
        assert not m.crashed and not m.battery_dead and m.fits, L.id
        assert m.retail <= L.target_retail_usd, L.id


def test_engine_is_deterministic():
    a, b = run("2_openworld", 5)[4], run("2_openworld", 5)[4]
    assert a.stutters == b.stutters and a.fps_1pct == b.fps_1pct and a.overall == b.overall


def test_hdd_kills_pocket_battery_and_streams_badly_in_open_world():
    m = run("1_pocket", storage="hdd")[4]
    assert m.battery_dead and m.stars <= 2
    m2 = run("2_openworld", storage="hdd")[4]
    assert m2.pop_pct > 50 and m2.load_s > 30


def test_ramdisk_is_astronomically_expensive_and_volatile():
    m = run("4_brownout", storage="ramdisk", capacity_gb=128, battery_wh=65)[4]
    assert m.retail > 700 and m.save_status == "lost"


def test_odt_off_at_speed_crashes_and_explains_why():
    L, b, sp, e, m = run("2_openworld", odt=False, mts=3200)
    assert m.crashed and m.stars <= 1
    assert any("ODT" in l.why for l in explain(m, b, L, sp))


def test_plp_protects_the_save():
    assert run("4_brownout", plp=True)[4].save_status == "ok"


def test_hotcar_fan_beats_passive_on_smoothness():
    passive = run("3_hotcar")[4]
    fan = run("3_hotcar", cooling="fan")[4]
    assert fan.fps_1pct > passive.fps_1pct and fan.pop_pct < passive.pop_pct


def test_aggressive_gc_causes_more_freezes():
    assert run("2_openworld", gc="aggressive")[4].stutters > run("2_openworld", gc="idle")[4].stutters


def test_more_dies_and_channels_raise_bandwidth():
    L = load_level("2_openworld")
    lo = estimate(Build(**{**L.default, "channels": 1, "dies": 1}), L).supply_mbps
    hi = estimate(Build(**{**L.default, "channels": 4, "dies": 4}), L).supply_mbps
    assert hi > lo


def test_qlc_write_cliff_slows_patch():
    L = load_level("2_openworld")
    tlc = estimate(Build(**{**L.default, "cell": "tlc"}), L).patch_s
    qlc = estimate(Build(**{**L.default, "cell": "qlc", "pslc_pct": 0}), L).patch_s
    assert qlc > 3 * tlc


def test_framebuffer_rows_are_exactly_the_lcd_width():
    r = Runner(2)
    for _ in range(40):
        r.step(0.05, 7.0, False)
    for w, h, ahead in ((40, 36, 30.0), (64, 40, 4.0), (80, 50, 0.0)):
        img = r.render(w, h, ahead)
        assert img.shape == (h, w, 3)
        for line in frame_to_text(img).plain.split("\n"):
            assert cell_len(line) == w
    assert to_dmg(r.render(40, 36, 30.0)).shape == (36, 40, 3)


def test_unloaded_obstacles_are_hidden():
    r = Runner(3)
    r.x = 0.0
    r._spawn(6.0)
    full = r.render(64, 40, 30.0)
    hidden = r.render(64, 40, 0.0)
    assert (full != hidden).any()


def _play_through(level_id, size):
    async def go():
        app = ArchitectApp(level_id)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, BuildScreen)
            await pilot.press("down", "right", "left")
            await pilot.press("enter")
            await pilot.pause()
            ps = app.screen
            assert isinstance(ps, PlayScreen)
            ps._timer.pause()
            for i in range(4000):
                if i % 15 == 3:
                    ps.jump_pending = True
                ps.advance(0.05)
                if isinstance(app.screen, ResultScreen):
                    break
            await pilot.pause()
            assert isinstance(app.screen, ResultScreen)
            assert app.screen.m.scores
            lcd_cols = ps.cols
            assert lcd_cols >= 24
    asyncio.run(go())


def test_full_flow_gameboy(tmp_path, monkeypatch):
    monkeypatch.setenv("CA_SAVE_DIR", str(tmp_path))
    _play_through("1_pocket", (110, 42))


def test_full_flow_deck_small_terminal(tmp_path, monkeypatch):
    monkeypatch.setenv("CA_SAVE_DIR", str(tmp_path))
    _play_through("2_openworld", (110, 36))
