"""Level definitions (TOML in levels/)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .parts import _resolve, load_toml, repo_root


@dataclass(frozen=True)
class Level:
    id: str
    name: str
    order: int
    console: str
    theme: str            # gb | deck
    blurb: str
    goals: tuple[str, ...]
    target_retail_usd: float
    markup: float
    base_bom_usd: float
    fps_goal: float
    battery_goal_h: float
    session_h: float
    real_s: float
    ambient_c: float
    game_gb: float
    patch_gb: float
    load_gb: float
    power_cut_at: float
    pe_fraction: float
    speed0: float
    speed1: float
    mb_per_col: float
    chunk_mb: float
    ahead_max: float
    autosave_mb: float
    autosave_every_s: float
    write_pressure: float
    soc_w: float
    r_base: float
    c_th: float
    throttle_c: float
    options: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)
    default: dict = field(default_factory=dict)

    @property
    def need_gb(self) -> float:
        return (self.game_gb + self.patch_gb) * 1.15


def load_level(name: str) -> Level:
    d = load_toml(_resolve("levels", name))
    lv, s, st, io, th = d["level"], d["session"], d["stream"], d["io"], d["thermal"]
    return Level(
        id=lv["id"], name=lv["name"], order=lv["order"], console=lv["console"], theme=lv["theme"],
        blurb=lv["blurb"], goals=tuple(lv["goals"]), target_retail_usd=lv["target_retail_usd"],
        markup=lv["markup"], base_bom_usd=lv["base_bom_usd"], fps_goal=lv["fps_goal"],
        battery_goal_h=lv["battery_goal_h"], session_h=s["session_h"], real_s=s["real_s"],
        ambient_c=s["ambient_c"], game_gb=s["game_gb"], patch_gb=s["patch_gb"], load_gb=s["load_gb"],
        power_cut_at=s.get("power_cut_at", 0.0), pe_fraction=s.get("pe_fraction", 0.3),
        speed0=st["speed0"], speed1=st["speed1"], mb_per_col=st["mb_per_col"], chunk_mb=st["chunk_mb"],
        ahead_max=st.get("ahead_max", 30.0), autosave_mb=io["autosave_mb"],
        autosave_every_s=io["autosave_every_s"], write_pressure=io["write_pressure"],
        soc_w=th["soc_w"], r_base=th["r_base"], c_th=th["c_th"], throttle_c=th["throttle_c"],
        options=d.get("options", {}), weights=d["weights"], default=d.get("default", {}),
    )


def list_levels() -> list[Level]:
    return sorted((load_level(p.stem) for p in (repo_root() / "levels").glob("*.toml")),
                  key=lambda l: l.order)
