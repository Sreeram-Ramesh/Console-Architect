"""Mascot callouts. Pure function of the simulation state, easy to test."""
from __future__ import annotations

from ..core.nand import ReadLatency
from ..core.phy import EyeResult, PhyConfig


def mascot(cfg: PhyConfig, eye: EyeResult, lat: ReadLatency, mode: str,
           bom_budget_usd: float, part_usd_per_gb: float, capacity_gb: float = 512) -> tuple[str, str]:
    if eye.crash_prob_per_s >= 0.5:
        return "x_x", "Kernel panic incoming. Setup slack is negative, the eye is shut."
    if eye.closed:
        if not cfg.odt:
            return "(>_<)", "Ringing everywhere! Terminate the bus, turn ODT on."
        if not cfg.zq:
            return "(o_O)", "Impedance drifted with temperature. ZQ calibration exists for a reason."
        return "(o_o;)", "Eye is closed. Back the link speed off."
    if lat.p_uncorrectable > 1e-6:
        return "(;o;)", "ECC is drowning. Retries are eating your latency."
    if part_usd_per_gb * capacity_gb > bom_budget_usd * 4:
        return "(@_@)", "Great specs. Who is paying for this? Check the BOM."
    if eye.setup_slack_ps < 25:
        return "(-_-)", "It closes at other corners. Works on my bench is not signoff."
    if not cfg.odt and cfg.mts <= 400:
        return "(^_~)", "Low speed, so unterminated is fine. Cheap and cheerful."
    return "(^o^)", "Eye looks open. Ship it!" + (" Toggle keeps idle power low." if mode == "Toggle" else "")
