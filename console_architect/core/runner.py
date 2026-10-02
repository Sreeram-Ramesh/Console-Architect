"""The little streaming runner the player actually plays. Pure numpy, no UI imports.

World units: one 'column' = 1/14 of the screen height. The player stands at screen column PX.
Obstacles that are not yet streamed in (beyond `ahead` columns) are NOT drawn: pop-in hides hazards.
Frozen frames (GC stalls, saves) are handled by the caller: the world keeps moving while the
screen and input are frozen, exactly like a real storage hitch.
"""
from __future__ import annotations

import numpy as np

PX = 3.0
GRAVITY = 45.5
JUMP_V = 17.1
LATE_COLS = 7.0
DMG = np.array([(15, 56, 15), (48, 98, 48), (139, 172, 15), (155, 188, 15)], dtype=np.uint8)


class Runner:
    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed + 1000)
        self.x = 0.0
        self.y = 0.0
        self.vy = 0.0
        self.hp = 3
        self.inv = 0.0
        self.deaths = 0
        self.hits = 0
        self.late_hits = 0
        self.obs: list[dict] = []
        self.next_x = 14.0
        self.phase = 0.0

    @property
    def on_ground(self) -> bool:
        return self.y <= 0.0 and self.vy <= 0.0

    def _spawn(self, speed: float) -> None:
        while self.next_x < self.x + 70:
            h = float(self.rng.choice([1.5, 2.0]))
            self.obs.append(dict(x=self.next_x, w=1.0, h=h, revealed=False, late=False))
            self.next_x += max(8.0, float(self.rng.uniform(speed * 1.2, speed * 2.0)))

    def step(self, dt: float, speed: float, jump: bool) -> None:
        self.x += speed * dt
        self.phase += dt * speed * 0.9
        if jump and self.on_ground:
            self.vy = JUMP_V
        self.vy -= GRAVITY * dt
        self.y += self.vy * dt
        if self.y <= 0.0:
            self.y, self.vy = 0.0, 0.0
        self.inv = max(0.0, self.inv - dt)
        self._spawn(speed)
        for o in self.obs:
            if o["x"] < self.x + 1.0 and o["x"] + o["w"] > self.x and self.y < o["h"] - 0.2 and self.inv <= 0.0:
                self.hits += 1
                self.late_hits += int(o["late"])
                self.hp -= 1
                self.inv = 1.2
                if self.hp <= 0:
                    self.deaths += 1
                    self.hp = 3
        self.obs = [o for o in self.obs if o["x"] + o["w"] > self.x - 6]

    # ---------------- rendering ----------------
    def render(self, w: int, h: int, ahead: float, hurt_flash: bool = True) -> np.ndarray:
        col = h / 14.0
        ys = np.arange(h, dtype=np.float32)[:, None]
        xs = np.arange(w, dtype=np.float32)[None, :]
        up = (h - ys) / col                                   # height above bottom, in units
        img = np.zeros((h, w, 3), dtype=np.float32)

        top, bot = np.array([40, 60, 120], np.float32), np.array([150, 190, 230], np.float32)
        t = (ys / h)[..., None]
        img[:] = top * (1 - t) + bot * t

        for par, base, amp, f, color in ((0.15, 5.5, 1.8, 0.35, (70, 90, 150)), (0.35, 4.2, 1.3, 0.8, (50, 120, 110))):
            xw = (xs + self.x * col * par) / col
            ridge = base + amp * np.sin(xw * f) + 0.5 * amp * np.sin(xw * f * 2.3 + 1.0)
            img = np.where((up < ridge)[..., None], np.array(color, np.float32), img)

        gtop = h - 3.0 * col
        ground = ys >= gtop
        xw = (xs + self.x * col) / col
        yw = (ys - gtop) / col
        tex = ((np.floor(xw) + np.floor(yw * 1.3)) % 2) == 1
        dirt = np.where(tex[..., None], np.array([95, 62, 34], np.float32), np.array([120, 80, 45], np.float32))
        grass = (ys < gtop + 0.6 * col)[..., None]
        gcol = np.where(grass, np.array([70, 160, 70], np.float32), dirt)
        img = np.where(ground[..., None], gcol, img)

        img = np.clip(img, 0, 255).astype(np.uint8)
        bx = int(round((PX + ahead) * col))
        if 0 <= bx < w:                                       # low-res "mip" for unstreamed tiles
            b = max(3, int(col * 1.8))
            reg = img[:, bx:, :].astype(np.float32)
            ph = (-reg.shape[0]) % b
            pw = (-reg.shape[1]) % b
            reg = np.pad(reg, ((0, ph), (0, pw), (0, 0)), mode="edge")
            m = reg.reshape(reg.shape[0] // b, b, reg.shape[1] // b, b, 3).mean(axis=(1, 3))
            m = np.repeat(np.repeat(m, b, 0), b, 1)[: h, : w - bx]
            img[:, bx:, :] = m.astype(np.uint8)

        gt = int(round(gtop))
        for o in self.obs:
            rel = o["x"] - self.x
            if rel > ahead or rel * col + PX * col > w or rel + o["w"] < -PX:
                continue
            if not o["revealed"] and 0 <= rel <= (w / col - PX):
                o["revealed"], o["late"] = True, rel < LATE_COLS
            x0 = int(round((rel + PX) * col))
            x1 = max(x0 + 2, int(round((rel + PX + o["w"]) * col)))
            y1 = gt
            y0 = int(round(gtop - o["h"] * col))
            img[max(0, y0): max(0, y1), max(0, x0): max(0, x1)] = (170, 110, 50)
            img[max(0, y0): max(0, y0) + 1, max(0, x0): max(0, x1)] = (230, 170, 90)
            img[max(0, y0): max(0, y1), max(0, x0): max(0, x0) + 1] = (90, 55, 25)
            img[max(0, y0): max(0, y1), max(0, x1) - 1: max(0, x1)] = (90, 55, 25)
            if o["h"] > 1.8:
                img[(y0 + y1) // 2: (y0 + y1) // 2 + 1, max(0, x0): max(0, x1)] = (90, 55, 25)

        # player
        blink = self.inv > 0 and int(self.inv * 12) % 2 == 0
        if not blink:
            px0 = int(round(PX * col))
            pw = max(2, int(round(1.2 * col)))
            pb = int(round(gtop - self.y * col))
            ph_ = max(4, int(round(2.0 * col)))
            py0 = pb - ph_
            img[max(0, py0): pb, px0: px0 + pw] = (235, 70, 55)
            hh = max(1, int(round(0.7 * col)))
            img[max(0, py0): max(0, py0) + hh, px0: px0 + pw] = (255, 214, 160)
            ey = max(0, py0) + max(0, hh // 2)
            img[ey: ey + 1, min(w - 1, px0 + pw - 1): min(w, px0 + pw)] = (20, 20, 20)
            legs = max(1, int(round(0.5 * col)))
            if self.on_ground:
                gap = pw // 2
                if int(self.phase * 2) % 2:
                    img[pb - legs: pb, px0: px0 + gap] = (40, 40, 140)
                else:
                    img[pb - legs: pb, px0 + gap: px0 + pw] = (40, 40, 140)
            else:
                img[pb - legs: pb, px0: px0 + pw] = (40, 40, 140)
        return img


def to_dmg(img: np.ndarray) -> np.ndarray:
    lum = img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114
    idx = np.digitize(lum, [70, 110, 150])
    return DMG[idx]
