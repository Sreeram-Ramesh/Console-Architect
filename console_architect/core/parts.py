"""TOML part/console loading. Parts are data, not code."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("CA_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def load_toml(path: Path | str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _resolve(kind: str, name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.suffix == ".toml" and p.exists():
        return p
    return repo_root() / kind / f"{name_or_path}.toml"


def list_parts(kind: str) -> list[str]:
    return sorted(p.stem for p in (repo_root() / kind).glob("*.toml"))


@dataclass(frozen=True)
class NandPart:
    name: str
    cell: str
    bits_per_cell: int
    t_r_us: float
    t_prog_us: float
    t_bers_ms: float
    page_bytes: int
    pe_max: int
    rber0: float
    wear_gain: float
    retention_gain: float
    pslc_write_mbps: float
    native_write_mbps: float
    usd_per_gb: float

    @classmethod
    def load(cls, name_or_path: str) -> "NandPart":
        d = load_toml(_resolve("parts/nand", name_or_path))
        return cls(
            name=d["part"]["name"], cell=d["part"]["cell"],
            bits_per_cell=d["part"]["bits_per_cell"],
            t_r_us=d["timing"]["t_r_us"], t_prog_us=d["timing"]["t_prog_us"],
            t_bers_ms=d["timing"]["t_bers_ms"], page_bytes=d["timing"]["page_bytes"],
            pe_max=d["reliability"]["pe_max"], rber0=d["reliability"]["rber0"],
            wear_gain=d["reliability"]["wear_gain"],
            retention_gain=d["reliability"]["retention_gain"],
            pslc_write_mbps=d["cache"]["pslc_write_mbps"],
            native_write_mbps=d["cache"]["native_write_mbps"],
            usd_per_gb=d["cost"]["usd_per_gb"],
        )


@dataclass(frozen=True)
class EccConfig:
    name: str
    kind: str
    codeword_bytes: int
    parity_bytes: int
    t_correct: int
    decode_base_us: float
    retry_gain: float
    max_retries: int
    soft_after: int
    soft_gain: float
    soft_decode_us: float
    power_mw: float

    @classmethod
    def load(cls, name_or_path: str) -> "EccConfig":
        d = load_toml(_resolve("parts/controllers", name_or_path))["ecc"]
        return cls(**d)


@dataclass(frozen=True)
class ConsoleSpec:
    name: str
    blurb: str
    bom_budget_usd: float
    battery_wh: float
    trace_mm: float
    mts_options: tuple[int, ...]
    mts: int
    odt: bool
    zq: bool
    mode: str
    nand: str
    ecc: str

    @classmethod
    def load(cls, name_or_path: str) -> "ConsoleSpec":
        d = load_toml(_resolve("consoles", name_or_path))
        c, p, df = d["console"], d["phy"], d["defaults"]
        return cls(
            name=c["name"], blurb=c["blurb"], bom_budget_usd=c["bom_budget_usd"],
            battery_wh=c["battery_wh"], trace_mm=p["trace_mm"],
            mts_options=tuple(p["mts_options"]), mts=p["mts"], odt=p["odt"],
            zq=p["zq"], mode=p["mode"], nand=df["nand"], ecc=df["ecc"],
        )
