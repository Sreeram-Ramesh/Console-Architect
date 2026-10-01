import math
from hypothesis import given, settings, strategies as st

from console_architect.core.ecc import decode_latency_us, poisson_tail
from console_architect.core.nand import (bus_mbps, expected_read_latency, rber_cell, t_dma_us)
from console_architect.core.parts import EccConfig, NandPart
from console_architect.core.power import phy_power_mw

TLC, QLC, SLC = NandPart.load("tlc"), NandPart.load("qlc"), NandPart.load("slc")
BCH, LDPC = EccConfig.load("bch40"), EccConfig.load("ldpc")


def test_poisson_tail_sanity():
    assert poisson_tail(0.0, 5) == 0.0
    assert abs(poisson_tail(1.0, 0) - (1 - math.exp(-1))) < 1e-12
    assert poisson_tail(200.0, 10) > 0.999999


@settings(max_examples=50, deadline=None)
@given(a=st.floats(1e-7, 1e-2), b=st.floats(1e-7, 1e-2))
def test_tail_monotonic_in_rber(a, b):
    lo, hi = sorted((a, b))
    assert poisson_tail(9000 * hi, 40) >= poisson_tail(9000 * lo, 40) - 1e-15


def test_ldpc_stronger_but_slower_than_bch():
    r = 3e-3
    assert poisson_tail(9000 * r, int(LDPC.t_correct)) < poisson_tail(9000 * r, int(BCH.t_correct))
    assert LDPC.decode_base_us > BCH.decode_base_us


def test_decode_latency_grows_with_rber():
    assert decode_latency_us(BCH, 1e-3) > decode_latency_us(BCH, 1e-5)


def test_cell_physics_ordering():
    assert SLC.t_r_us < TLC.t_r_us < QLC.t_r_us
    assert SLC.pe_max > TLC.pe_max > QLC.pe_max
    assert rber_cell(QLC, 0) > rber_cell(TLC, 0) > rber_cell(SLC, 0)


@given(a=st.floats(0, 3000), b=st.floats(0, 3000))
def test_rber_monotonic_in_wear_and_retention(a, b):
    lo, hi = sorted((a, b))
    assert rber_cell(TLC, hi) >= rber_cell(TLC, lo)
    assert rber_cell(TLC, 100, hi) >= rber_cell(TLC, 100, lo)


def test_dma_time_and_bandwidth():
    assert abs(t_dma_us(16384, 1600, 8) - 10.24) < 1e-9
    assert bus_mbps(1600, 8) == 1600


def test_read_latency_components_sum_and_floor():
    r = expected_read_latency(TLC, LDPC, 1600, 1e-30)
    assert abs(r.total_us - (r.t_cmd_us + r.t_r_us + r.t_dma_us + r.t_ecc_us + r.t_retry_us + r.t_gc_us)) < 1e-9
    assert r.total_us >= TLC.t_r_us and r.p_uncorrectable == 0.0


def test_bad_phy_blows_up_latency_and_fails_reads():
    good = expected_read_latency(QLC, LDPC, 3200, 1e-30, pe_cycles=500)
    bad = expected_read_latency(QLC, LDPC, 3200, 1.5e-2, pe_cycles=500)
    assert bad.total_us > 10 * good.total_us
    assert bad.p_uncorrectable > good.p_uncorrectable


def test_worn_qlc_needs_retries_and_gc_adds_expected_stall():
    fresh = expected_read_latency(QLC, BCH, 1600, 1e-30, pe_cycles=0)
    worn = expected_read_latency(QLC, BCH, 1600, 1e-30, pe_cycles=1000)
    assert worn.mean_retries >= fresh.mean_retries
    gc = expected_read_latency(TLC, LDPC, 1600, 1e-30, p_gc=0.01, gc_stall_us=100_000)
    assert abs(gc.t_gc_us - 1000.0) < 1e-9


def test_toggle_idle_below_onfi_idle_and_power_monotonic():
    assert phy_power_mw("Toggle", 1600, 40, True, 0.0) < phy_power_mw("ONFI", 1600, 40, True, 0.0)
    assert phy_power_mw("ONFI", 3200, 40, True, 0.3) > phy_power_mw("ONFI", 1600, 40, True, 0.3)
