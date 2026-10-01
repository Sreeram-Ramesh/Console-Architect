import numpy as np
from hypothesis import given, settings, strategies as st

from console_architect.core.phy import (Corner, PhyConfig, analyze, eye_traces,
                                        lane_slacks, reflection_coeff, unit_interval_ps)

MTS = st.sampled_from([200, 400, 800, 1200, 1600, 2400, 3200, 3600, 4800])


def test_unit_interval():
    assert unit_interval_ps(1600) == 625.0


def test_gamma_odt_on_vs_off():
    on = analyze(PhyConfig(odt=True))
    off = analyze(PhyConfig(odt=False))
    assert abs(on.gamma) < 1e-9
    assert off.gamma > 0.9
    assert reflection_coeff(50.0) == 0.0


def test_odt_off_closes_eye_at_speed_but_not_slow():
    assert not analyze(PhyConfig(mts=400, odt=False)).closed
    assert analyze(PhyConfig(mts=3200, odt=False)).closed
    assert not analyze(PhyConfig(mts=3200, odt=True)).closed


def test_zq_off_thermal_drift_crashes_hot_only():
    hot = PhyConfig(mts=3600, zq=False, trace_mm=45, corner=Corner(temp_c=85))
    cool = hot.with_(corner=Corner(temp_c=25))
    assert analyze(hot).crash_prob_per_s > 0
    assert analyze(cool).crash_prob_per_s == 0
    assert analyze(hot.with_(zq=True)).crash_prob_per_s == 0


def test_crash_only_with_negative_slack():
    for mts in (800, 1600, 3200, 4800):
        for odt in (True, False):
            r = analyze(PhyConfig(mts=mts, odt=odt))
            assert (r.crash_prob_per_s > 0) == (min(r.setup_slack_ps, r.hold_slack_ps) < 0)


@settings(max_examples=60, deadline=None)
@given(a=MTS, b=MTS, odt=st.booleans(), zq=st.booleans(), t=st.sampled_from([-10, 25, 70, 85]))
def test_ber_and_eye_monotonic_in_speed(a, b, odt, zq, t):
    lo, hi = sorted((a, b))
    kw = dict(odt=odt, zq=zq, corner=Corner(temp_c=t))
    r_lo, r_hi = analyze(PhyConfig(mts=lo, **kw)), analyze(PhyConfig(mts=hi, **kw))
    assert r_hi.ber >= r_lo.ber * (1 - 1e-9)
    assert r_hi.w_eye_pct <= r_lo.w_eye_pct + 1e-9


@settings(max_examples=60, deadline=None)
@given(mts=MTS, odt=st.booleans(), t1=st.sampled_from([25, 45, 70, 85, 105]),
       t2=st.sampled_from([25, 45, 70, 85, 105]))
def test_ber_monotonic_in_temperature_with_zq_off(mts, odt, t1, t2):
    lo, hi = sorted((t1, t2))
    mk = lambda t: analyze(PhyConfig(mts=mts, odt=odt, zq=False, corner=Corner(temp_c=t)))
    assert mk(hi).ber >= mk(lo).ber * (1 - 1e-9)


def test_lane_slacks_deterministic_and_sized():
    cfg = PhyConfig(mts=3200)
    assert lane_slacks(cfg, 1) == lane_slacks(cfg, 1)
    assert len(lane_slacks(cfg)) == cfg.bus_bits


def test_eye_traces_shape_finite_and_seeded():
    cfg = PhyConfig(mts=1600)
    t, v = eye_traces(cfg, n_traces=30, n_samples=64, seed=3)
    assert t.shape == (64,) and v.shape == (30, 64)
    assert np.isfinite(v).all() and t[0] == 0.0 and abs(t[-1] - 2.0) < 1e-9
    _, v2 = eye_traces(cfg, n_traces=30, n_samples=64, seed=3)
    assert np.array_equal(v, v2)


def test_open_eye_is_visibly_more_open_than_reflective_eye():
    def mid_gap(cfg):
        t, v = eye_traces(cfg, n_traces=200, n_samples=97, seed=0)
        col = v[:, 48]  # center of a UI at t=1.0? use sample at t=0.5UI
        k = int(np.argmin(np.abs(t - 0.5)))
        col = v[:, k]
        return col[col > 0].min() - col[col < 0].max() if (col > 0).any() and (col < 0).any() else 0.0
    assert mid_gap(PhyConfig(mts=3200, odt=True)) > mid_gap(PhyConfig(mts=3200, odt=False))
