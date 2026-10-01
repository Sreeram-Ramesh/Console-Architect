"""PHY power. P = alpha * C * V^2 * f  (+ static ODT). ONFI clock free-runs, Toggle does not."""
from __future__ import annotations

C_PIN_PKG_PF = 2.0
C_PIN_PF_PER_MM = 0.10
VCCQ = 1.2
N_DQ = 8


def phy_power_mw(mode: str, mts: float, trace_mm: float, odt: bool, util: float) -> float:
    """util = fraction of time the bus is actually transferring (0..1)."""
    cv2 = (C_PIN_PKG_PF + C_PIN_PF_PER_MM * trace_mm) * 1e-12 * VCCQ ** 2  # J per swing
    f_clk = mts * 1e6 / 2.0
    p_dq = N_DQ * 0.5 * (mts * 1e6) * util * cv2       # data toggles at 50% activity
    if mode.upper() == "ONFI":
        p_clk = f_clk * cv2                            # alpha = 1: always toggling
    elif mode.upper() == "TOGGLE":
        p_clk = f_clk * util * cv2                     # alpha = DQS duty
    else:
        raise ValueError(f"unknown mode {mode!r}")
    p_odt = (N_DQ * VCCQ ** 2 / 100.0 * 0.5 * util) if odt else 0.0
    return (p_dq + p_clk + p_odt) * 1e3
