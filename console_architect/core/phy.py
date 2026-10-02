"""PHY signal integrity: unit interval, reflections, eye, BER, slack, crash risk.

Pure library: numpy + stdlib only, no UI imports.

Model summary
-------------
UI     = 1e6 / MT/s                                  [ps]
Gamma  = (R_term - Z0) / (R_term + Z0)
W_eye  = UI - (2 Q sigma_rj + DJ + skew + ISI(Gamma, L) + ZQ drift)
H_eye  = Vswing (1 - k |Gamma| tanh(1.5 t_rt/UI)) - 2 Vnoise
BER    = 1/2 erfc(Qt/sqrt2) + 1/2 erfc(Qv/sqrt2)     (clamped to [1e-30, 0.5])
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

# ---- constants (tuned for game feel, physically plausible) -------------------
Z0_OHM = 50.0
R_TERM_NOM = 50.0
R_OPEN = 5000.0            # "ODT off": receiver looks like a high-Z open end
Q_TARGET = 7.034           # Q for BER = 1e-12
PS_PER_MM = 6.7            # FR4 stripline propagation delay
T_REF_C = 25.0
ALPHA_R = 0.005            # 1/degC, uncalibrated impedance drift
ZQ_PS_PER_C = 1.6          # ps of timing drift per degC away from 25C with ZQ off
RJ0_PS = 5.0
DJ0_PS = 18.0
SKEW0_PS = 10.0
SKEW_PS_PER_MM = 0.15
LOSS_PS_PER_MM_GBPS = 0.04
K_REFL_T = 0.5
K_REFL_V = 0.5
V_NOISE_MV = 35.0
SIGMA_V_MV = 22.0
T_HOLD_PS = 40.0
BER_FLOOR = 1e-30

PROCESS_TIMING = {"SS": 1.25, "TT": 1.00, "FF": 0.90}
PROCESS_R = {"SS": 0.15, "TT": 0.0, "FF": -0.15}   # uncalibrated R offset
VDD_SCALE = {"Vmin": 0.95, "Vnom": 1.00, "Vmax": 1.05}


@dataclass(frozen=True)
class Corner:
    process: str = "TT"
    vdd: str = "Vnom"
    temp_c: float = 25.0

    @property
    def name(self) -> str:
        return f"{self.process}/{self.vdd}/{self.temp_c:g}C"


@dataclass(frozen=True)
class PhyConfig:
    mts: float = 1600.0
    odt: bool = True
    zq: bool = True
    corner: Corner = field(default_factory=Corner)
    trace_mm: float = 40.0
    bus_bits: int = 8
    v_swing_mv: float = 600.0
    t_setup_ps: float = 40.0

    def with_(self, **kw) -> "PhyConfig":
        return replace(self, **kw)


@dataclass(frozen=True)
class EyeResult:
    ui_ps: float
    r_term_ohm: float
    gamma: float
    t_rt_ps: float
    sigma_rj_ps: float
    dj_ps: float
    skew_ps: float
    isi_ps: float
    zq_drift_ps: float
    w_eye_ps: float
    w_eye_pct: float
    h_eye_mv: float
    swing_mv: float
    q_t: float
    q_v: float
    ber: float
    setup_slack_ps: float
    hold_slack_ps: float
    crash_prob_per_s: float

    @property
    def closed(self) -> bool:
        return self.setup_slack_ps < 0 or self.hold_slack_ps < 0 or self.h_eye_mv <= 0


def unit_interval_ps(mts: float) -> float:
    return 1e6 / mts


def reflection_coeff(r_term: float, z0: float = Z0_OHM) -> float:
    return (r_term - z0) / (r_term + z0)


def termination_ohm(cfg: PhyConfig) -> float:
    """Effective termination seen by the wave at the receiver."""
    if not cfg.odt:
        return R_OPEN
    if cfg.zq:
        return R_TERM_NOM  # calibrated: within noise of nominal
    c = cfg.corner
    drift = ALPHA_R * (c.temp_c - T_REF_C) + PROCESS_R[c.process]
    return R_TERM_NOM * (1.0 + drift)


def _qfunc(q: float) -> float:
    return 0.5 * math.erfc(q / math.sqrt(2.0))


def analyze(cfg: PhyConfig) -> EyeResult:
    c = cfg.corner
    vdd = VDD_SCALE[c.vdd]
    ui = unit_interval_ps(cfg.mts)
    r_term = termination_ohm(cfg)
    gamma = reflection_coeff(r_term)
    t_rt = 2.0 * cfg.trace_mm * PS_PER_MM

    proc = PROCESS_TIMING[c.process]
    hot = 1.0 + 0.004 * max(0.0, c.temp_c - T_REF_C)
    sigma = RJ0_PS * proc * hot / vdd
    dj = DJ0_PS * proc
    skew = SKEW0_PS + SKEW_PS_PER_MM * cfg.trace_mm
    isi = (K_REFL_T * abs(gamma) * ui * math.tanh(t_rt / ui)
           + LOSS_PS_PER_MM_GBPS * cfg.trace_mm * (cfg.mts / 1000.0))
    zq_drift = 0.0 if cfg.zq else ZQ_PS_PER_C * abs(c.temp_c - T_REF_C)

    fixed = dj + skew + isi + zq_drift
    w_eye = ui - (2.0 * Q_TARGET * sigma + fixed)
    q_t = (ui - fixed) / (2.0 * sigma)

    swing = cfg.v_swing_mv * vdd
    refl_v = K_REFL_V * abs(gamma) * math.tanh(1.5 * t_rt / ui)
    h_eye = swing * (1.0 - refl_v) - 2.0 * V_NOISE_MV / vdd
    q_v = h_eye / (2.0 * SIGMA_V_MV)

    ber = min(0.5, max(BER_FLOOR, _qfunc(q_t) + _qfunc(q_v)))
    setup = w_eye / 2.0 - cfg.t_setup_ps
    hold = w_eye / 2.0 - T_HOLD_PS
    worst = min(setup, hold)
    crash = 0.0 if worst >= 0 else min(1.0, 0.02 + 5.0 * (-worst) / ui)

    return EyeResult(
        ui_ps=ui, r_term_ohm=r_term, gamma=gamma, t_rt_ps=t_rt, sigma_rj_ps=sigma,
        dj_ps=dj, skew_ps=skew, isi_ps=isi, zq_drift_ps=zq_drift, w_eye_ps=w_eye,
        w_eye_pct=100.0 * w_eye / ui, h_eye_mv=h_eye, swing_mv=swing, q_t=q_t, q_v=q_v,
        ber=ber, setup_slack_ps=setup, hold_slack_ps=hold, crash_prob_per_s=crash,
    )


def lane_slacks(cfg: PhyConfig, seed: int = 0) -> list[tuple[float, float]]:
    """Per-DQ-lane (setup, hold) slack, like a fake report_timing. Deterministic per seed."""
    res = analyze(cfg)
    rng = np.random.default_rng(seed)
    spread = res.skew_ps / 2.0
    out = []
    for _ in range(cfg.bus_bits):
        d = float(rng.uniform(-spread, spread))
        out.append((res.w_eye_ps / 2.0 - cfg.t_setup_ps - d,
                    res.w_eye_ps / 2.0 - T_HOLD_PS + d))
    return out


def eye_traces(cfg: PhyConfig, res: EyeResult | None = None, n_traces: int = 120,
               n_samples: int = 96, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Synthesize an eye diagram. Returns (t_ui[n_samples] in 0..2, v[n_traces, n_samples]).

    Random NRZ bits, tanh edges, edge jitter (random + deterministic + ZQ drift),
    a reflection echo delayed by the round-trip time, and additive voltage noise.
    Voltage is normalized so a clean signal spans roughly -1..+1.
    """
    res = res or analyze(cfg)
    rng = np.random.default_rng(seed)
    ui = res.ui_ps
    n_bits = 8
    tr = 80.0  # ps edge time

    bits = rng.choice([-1.0, 1.0], size=(n_traces, n_bits))
    dv = bits[:, 1:] - bits[:, :-1]                        # (N, 7)
    nominal = np.arange(1, n_bits) * ui                    # edges 1..7
    spread = res.dj_ps + res.zq_drift_ps
    jit = (rng.normal(0.0, res.sigma_rj_ps, (n_traces, n_bits - 1))
           + rng.uniform(-0.5, 0.5, (n_traces, n_bits - 1)) * spread)
    edges = nominal[None, :] + jit                         # (N, 7)

    def wave(tt: np.ndarray) -> np.ndarray:
        x = (tt[None, :, None] - edges[:, None, :]) / (0.5 * tr)
        step = 0.5 * (1.0 + np.tanh(x))
        return bits[:, :1] + (step * dv[:, None, :]).sum(-1)

    t = np.linspace(3.0 * ui, 5.0 * ui, n_samples)
    v = wave(t)
    if abs(res.gamma) > 1e-3:
        d = min(res.t_rt_ps, 2.9 * ui)
        v = v + res.gamma * wave(t - d)
        v = v / (1.0 + abs(res.gamma))
    v = v + rng.normal(0.0, SIGMA_V_MV / (res.swing_mv / 2.0), v.shape)
    return (t - 3.0 * ui) / ui, v


def corner_sweep(cfg: PhyConfig, temps=(-10.0, 25.0, 85.0)) -> tuple[int, int, float, str]:
    """Evaluate all PVT corners. Returns (n_fail, n_total, worst_slack_ps, worst_corner_name)."""
    fail, total, worst, wname = 0, 0, float("inf"), ""
    for p in PROCESS_TIMING:
        for v in VDD_SCALE:
            for t in temps:
                c = Corner(p, v, float(t))
                r = analyze(cfg.with_(corner=c))
                s = min(r.setup_slack_ps, r.hold_slack_ps)
                total += 1
                fail += int(r.closed)
                if s < worst:
                    worst, wname = s, c.name
    return fail, total, worst, wname
