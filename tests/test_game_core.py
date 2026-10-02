import numpy as np
import pytest

from console_architect.core import ftl
from console_architect.core.bom import bom_lines, totals
from console_architect.core.build import Build
from console_architect.core.engine import Engine
from console_architect.core.levels import list_levels, load_level
from console_architect.core.options import KNOBS, nudge, values_for
from console_architect.core.runner import Runner, to_dmg
from console_architect.core.spec import estimate
from console_architect.core.storage import perf
from console_architect.core.verdict import collect, explain


def run(level_id, seed=0, **kw):
    L = load_level(level_id)
    b = Build(**{**L.default, **kw})
    sp, e = estimate(b, L), Engine(b, L, seed)
    boot = e.boot()
    while not e.finished:
        e.step(0.05)
    return collect(e, boot, sp, L), b, L, sp


def test_levels_load_and_defaults_are_valid_builds():
    ls = list_levels()
    assert [l.order for l in ls] == sorted(l.order for l in ls) and len(ls) == 4
    for L in ls:
        b = Build(**L.default)
        for k in KNOBS:
            assert getattr(b, k.key) in values_for(k, L), (L.id, k.key)


def test_engine_is_deterministic_per_seed():
    a, *_ = run("2_openworld", seed=5)
    b, *_ = run("2_openworld", seed=5)
    assert (a.stutters, a.counts, round(a.fps_1pct, 6)) == (b.stutters, b.counts, round(b.fps_1pct, 6))


def test_storage_ordering_hdd_sata_nvme():
    b = Build()
    hdd, sata, nvme = (perf(b.with_(storage=s), 30.0) for s in ("hdd", "sata", "nvme"))
    assert hdd.seq_read_mbps < sata.seq_read_mbps < nvme.seq_read_mbps
    assert hdd.first_byte_ms > 50 * sata.first_byte_ms
    assert perf(b.with_(storage="ramdisk"), 30.0).volatile


def test_hdd_pops_in_and_flash_does_not():
    assert run("2_openworld", storage="hdd")[0].pop_pct > 50
    assert run("2_openworld")[0].pop_pct < 1


def test_odt_off_at_speed_crashes_but_not_when_slow():
    assert run("2_openworld", odt=False, mts=3200)[0].crashed
    assert not run("1_pocket", odt=False, mts=400)[0].crashed


def test_zq_off_crashes_only_when_hot():
    assert run("3_hotcar", zq=False)[0].crashed
    assert not run("3_hotcar")[0].crashed


def test_battery_story():
    assert run("1_pocket", storage="hdd")[0].battery_dead
    assert run("1_pocket", storage="ramdisk")[0].battery_dead
    assert not run("1_pocket")[0].battery_dead


def test_power_loss_protection_saves_the_save_file():
    assert run("4_brownout", plp=True)[0].save_status == "ok"
    assert run("4_brownout", storage="ramdisk", capacity_gb=128)[0].save_status == "lost"


def test_cooling_fixes_hot_car_thermal_throttle():
    base, fan = run("3_hotcar")[0], run("3_hotcar", cooling="fan")[0]
    assert base.throttle_pct > 50 and fan.throttle_pct < base.throttle_pct
    assert fan.fps_1pct > base.fps_1pct


def test_aggressive_gc_means_more_freezes_than_idle_gc():
    agg, idle = run("2_openworld", gc="aggressive")[0], run("2_openworld", gc="idle")[0]
    assert agg.stutters > idle.stutters


def test_price_monotonic_and_ramdisk_is_astronomical():
    L = load_level("2_openworld")
    price = lambda **kw: totals(bom_lines(Build(**{**L.default, **kw}), L.base_bom_usd), L.markup)[1]
    assert price(capacity_gb=512) > price(capacity_gb=256) > price(capacity_gb=128)
    assert price(cell="slc") > price(cell="tlc") > price(cell="qlc")
    assert price(storage="ramdisk") > 3 * price()


def test_game_that_does_not_fit_is_flagged():
    L = load_level("2_openworld")
    assert not estimate(Build(**{**L.default, "capacity_gb": 64}), L).fits
    assert estimate(Build(**L.default), L).fits


def test_pvt_corner_check_catches_works_on_my_bench():
    L = load_level("2_openworld")
    bad = estimate(Build(**{**L.default, "odt": False, "mts": 3200}), L)
    good = estimate(Build(**L.default), L)
    assert bad.corner_fail > 0 and good.corner_fail == 0


def test_pslc_cache_write_cliff_and_refill():
    c = ftl.PslcCache(1000, 500, 20)
    assert c.write_time(1000) == pytest.approx(2.0)
    assert c.write_time(100) == pytest.approx(5.0)       # cache full: native speed
    c.idle(10, 50)
    assert c.free_mb == pytest.approx(500)


def test_waf_decreases_with_overprovisioning():
    assert ftl.waf_eff(7, "lazy") > ftl.waf_eff(14, "lazy") > ftl.waf_eff(28, "lazy") >= 1.0


def test_scores_bounded_and_every_failure_gets_an_explanation():
    m, b, L, sp = run("2_openworld", storage="hdd")
    assert all(0 <= v <= 100 for v in m.scores.values()) and 0 <= m.stars <= 5
    assert not m.passed and explain(m, b, L, sp)
    ok = run("1_pocket")[0]
    assert ok.passed


def test_nudge_clamps_at_ends():
    L = load_level("2_openworld")
    k = next(k for k in KNOBS if k.key == "mts")
    b = Build(**L.default)
    for _ in range(20):
        b = nudge(b, k, L, 1)
    assert b.mts == values_for(k, L)[-1]


def test_runner_hides_unloaded_obstacles_and_flags_late_hits():
    r = Runner(3)
    r.step(0.05, 6.0, False)
    far = next(o for o in r.obs)
    far["x"] = r.x + 10.0
    full = r.render(64, 40, ahead=30.0)
    r2 = Runner(3); r2.step(0.05, 6.0, False); o2 = r2.obs[0]; o2["x"] = r2.x + 10.0
    hidden = r2.render(64, 40, ahead=2.0)
    assert not np.array_equal(full, hidden) and not o2["revealed"] and far["revealed"]
    o2["x"] = r2.x + 3.0                                  # pops in right in the player's face
    r2.render(64, 40, ahead=30.0)
    assert o2["late"]


def test_runner_jump_clears_obstacle_and_ground_hit_costs_hp():
    r = Runner(0); r.obs = [dict(x=8.0, w=1.0, h=1.5, revealed=True, late=False)]; r.next_x = 999
    for _ in range(40):
        r.step(0.05, 6.0, False)
    assert r.hits == 1
    r = Runner(0); r.obs = [dict(x=8.0, w=1.0, h=1.5, revealed=True, late=False)]; r.next_x = 999
    for i in range(40):
        r.step(0.05, 6.0, jump=(i == 19))
    assert r.hits == 0


def test_dmg_palette_has_four_shades():
    img = Runner(1).render(40, 36, 30.0)
    assert len(np.unique(to_dmg(img).reshape(-1, 3), axis=0)) <= 4
