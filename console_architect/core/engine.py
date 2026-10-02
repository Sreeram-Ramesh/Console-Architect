"""Session engine: power, thermal, streaming, GC/save hitches, crashes. Pure, seeded, UI-free.

The same Engine drives the playable TUI and the headless `ca run` / pytest scoring.
One call to step(dt) advances `dt` REAL seconds of play; power/thermal/battery integrate
over dt * time_scale simulated seconds (a 3 h session is compressed into ~100 s).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import ftl
from .build import Build
from .levels import Level
from .storage import StoragePerf, chunk_bw, perf

COOLING_R = {"passive": 1.0, "heatsink": 0.75, "fan": 0.5}
BASE_FRAME_MS = 1000.0 / 60.0
VISIBLE_AHEAD_COLS = 14.0
NAND_RISE_K_PER_W = 4.0
P_CORRUPT = {"hdd": 0.15, "sata": 0.6, "nvme": 0.6}


@dataclass
class Tick:
    events: list = field(default_factory=list)   # (kind, text)
    hitch_ms: float = 0.0


@dataclass
class Boot:
    patch_s: float
    load_s: float
    patch_limiter: str
    cache_filled: bool


class Engine:
    def __init__(self, b: Build, level: Level, seed: int = 0):
        self.b, self.L = b, level
        self.rng = np.random.default_rng(seed)
        self.scale = level.session_h * 3600.0 / level.real_s
        self.t = 0.0
        self.temp_case = level.ambient_c + 2.0
        self.temp_nand = self.temp_case
        self.speed = level.speed0
        self.ahead = level.ahead_max
        self.energy_wh = {"soc": 0.0, "storage": 0.0}
        self.frames: list[float] = []
        self.hitch_left = 0.0
        self.hitch_log: list[tuple[float, float, str]] = []
        self.counts = {"gc": 0, "save": 0, "seek": 0, "read_error": 0}
        self.stutters = 0
        self.pop_acc = 0.0
        self.throttle_acc = 0.0
        self.temp_peak = self.temp_case
        self.nand_peak = self.temp_nand
        self.crashed = False
        self.crash_reason = ""
        self.battery_dead = False
        self.save_status = ""          # "", "ok", "corrupt", "lost"
        self._cut_done = False
        self._next_save = level.autosave_every_s
        self.fps_factor = 1.0
        self.util = 0.0
        self.storage_w = 0.0
        self.total_w = 0.0
        self.supply_mbps = 0.0
        p0 = self.perf(self.temp_nand)
        self.cache = ftl.PslcCache(p0.pslc_gb * 1024.0, p0.write_pslc_mbps, p0.write_native_mbps)

    # ---- helpers ----
    def perf(self, temp: float) -> StoragePerf:
        return perf(self.b, float(round(temp / 2.0) * 2), self.L.pe_fraction)

    @property
    def frozen(self) -> bool:
        return self.hitch_left > 0.0

    @property
    def finished(self) -> bool:
        return self.t >= self.L.real_s or self.crashed or self.battery_dead

    @property
    def battery_pct(self) -> float:
        used = sum(self.energy_wh.values())
        return max(0.0, 100.0 * (1.0 - used / self.b.battery_wh))

    def boot(self) -> Boot:
        p = self.perf(self.temp_nand)
        patch_s = self.cache.write_time(self.L.patch_gb * 1024.0) if self.L.patch_gb > 0 else 0.0
        load_s = self.L.load_gb * 1024.0 / p.seq_read_mbps + p.first_byte_ms / 1000.0
        filled = self.cache.size_mb > 0 and self.cache.free_mb <= 0
        lim = "pSLC cache full -> native NAND speed" if filled else "pSLC / write path"
        if self.b.storage in ("hdd", "ramdisk"):
            lim = "sequential write speed"
        return Boot(patch_s, load_s, lim, filled)

    def _hitch(self, ms: float, cause: str, tick: Tick, blocks_reads: bool = True) -> None:
        ms = float(ms)
        self.hitch_left += ms
        self.frames.append(ms + BASE_FRAME_MS)
        self.hitch_log.append((self.t, ms, cause))
        self.counts[cause] = self.counts.get(cause, 0) + 1
        if ms >= 50.0:
            self.stutters += 1
        if blocks_reads:
            self.ahead = max(0.0, self.ahead - self.speed * ms / 1000.0)
        tick.hitch_ms += ms

    # ---- main step ----
    def step(self, dt: float) -> Tick:
        L, b = self.L, self.b
        tick = Tick()
        if self.finished:
            return tick
        self.t += dt
        sim_dt = dt * self.scale
        self.speed = L.speed0 + (L.speed1 - L.speed0) * min(1.0, self.t / L.real_s)

        self.temp_nand = self.temp_case + NAND_RISE_K_PER_W * self.storage_w
        p = self.perf(self.temp_nand)
        demand = self.speed * L.mb_per_col
        bw_seq = p.seq_read_mbps
        self.supply_mbps = chunk_bw(p, L.chunk_mb)
        self.util = min(1.0, demand / max(1.0, bw_seq))
        self.storage_w = p.idle_w + (p.active_w - p.idle_w) * self.util + (p.gc_bg_w if b.nand_based else 0.0)

        # thermal + power
        thr = 1.0 if self.temp_case <= L.throttle_c else max(0.35, 1.0 - 0.04 * (self.temp_case - L.throttle_c))
        self.fps_factor = thr
        soc_w = L.soc_w * (0.6 + 0.4 * thr)
        self.total_w = soc_w + self.storage_w
        R = L.r_base * COOLING_R[b.cooling]
        t_inf = L.ambient_c + R * self.total_w
        self.temp_case += (t_inf - self.temp_case) * (1.0 - math.exp(-sim_dt / (R * L.c_th)))
        self.energy_wh["soc"] += soc_w * sim_dt / 3600.0
        self.energy_wh["storage"] += self.storage_w * sim_dt / 3600.0
        self.temp_peak = max(self.temp_peak, self.temp_case)
        self.nand_peak = max(self.nand_peak, self.temp_nand)
        if thr < 0.98:
            self.throttle_acc += dt
        if sum(self.energy_wh.values()) >= b.battery_wh:
            self.battery_dead = True
            tick.events.append(("battery", "Battery empty"))

        # streaming buffer
        supply_cols = self.supply_mbps / L.mb_per_col
        self.ahead = float(np.clip(self.ahead + (supply_cols - self.speed) * dt, 0.0, L.ahead_max))
        self.pop_acc += float(np.clip((VISIBLE_AHEAD_COLS - self.ahead) / VISIBLE_AHEAD_COLS, 0, 1)) * dt

        # hitch sources
        if b.nand_based:
            iv = ftl.gc_interval_s(b.op_pct, b.gc, L.write_pressure)
            if self.rng.random() < dt / iv:
                ms = ftl.gc_stall_ms(b.op_pct, b.gc)
                self._hitch(ms, "gc", tick)
                tick.events.append(("gc", f"GC stall {ms:.0f} ms ({b.gc} policy)"))
        if b.storage == "hdd" and demand > 0.4 * self.supply_mbps:
            if self.rng.random() < dt * 0.5:
                ms = float(self.rng.uniform(60, 160))
                self._hitch(ms, "seek", tick)
                tick.events.append(("seek", f"Seek storm {ms:.0f} ms (HDD head moving)"))
        if p.p_uncorr_page > 0:
            pages = L.chunk_mb * 1048576 / 16384.0
            p_chunk = -math.expm1(pages * math.log1p(-min(p.p_uncorr_page, 0.999999)))
            if self.rng.random() < (demand / L.chunk_mb) * dt * p_chunk:
                self._hitch(400, "read_error", tick)
                tick.events.append(("read_error", "Uncorrectable read, host retry 400 ms"))
        self.cache.idle(dt * (1.0 - self.util), p.write_native_mbps * 0.5)
        if self.t >= self._next_save:
            self._next_save += L.autosave_every_s
            wt = self.cache.write_time(L.autosave_mb)
            ms = min(3000.0, wt * 1000.0 * 0.3)
            if ms > 50.0:
                self._hitch(ms, "save", tick, blocks_reads=False)
                tick.events.append(("save", f"Autosave stall {ms:.0f} ms ({L.autosave_mb:.0f} MB, "
                                            f"cache {self.cache.fill:.0%} full)"))

        # power cut
        if L.power_cut_at > 0 and not self._cut_done and self.t >= L.power_cut_at * L.real_s:
            self._cut_done = True
            if p.volatile:
                self.save_status = "lost"
            elif b.plp:
                self.save_status = "ok"
            else:
                self.save_status = "corrupt" if self.rng.random() < P_CORRUPT[b.storage] else "ok"
            tick.events.append(("power_cut", f"POWER LOST -> save {self.save_status}"))

        # crash from a closed eye
        if p.crash_p_per_s > 0 and self.rng.random() < p.crash_p_per_s * 0.3 * dt:
            self.crashed = True
            e = p.eye
            why = ("ODT off: reflections close the eye" if not b.odt else
                   f"ZQ off: impedance drifted at {self.temp_nand:.0f} C" if not b.zq else
                   "link too fast for the eye margin")
            self.crash_reason = f"DQ setup/hold violation. {why}."
            tick.events.append(("crash", self.crash_reason))

        # virtual frames for 1% lows
        dt_ms = dt * 1000.0
        frozen = min(self.hitch_left, dt_ms)
        self.hitch_left -= frozen
        ft = BASE_FRAME_MS / self.fps_factor
        n = int(max(0.0, dt_ms - frozen) / ft)
        self.frames.extend([ft] * n)
        return tick

    # ---- results ----
    def fps(self) -> tuple[float, float]:
        if not self.frames:
            return 0.0, 0.0
        f = np.asarray(self.frames)
        k = max(1, int(len(f) * 0.01))
        low = float(np.sort(f)[-k:].mean())
        return len(f) / max(self.t, 1e-6), 1000.0 / low

    def mean_power_w(self) -> float:
        sim_h = max(1e-9, self.t * self.scale / 3600.0)
        return sum(self.energy_wh.values()) / sim_h
