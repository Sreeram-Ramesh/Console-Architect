"""Braille-dot canvas: 2x4 dots per terminal cell. No GUI toolkit needed."""
from __future__ import annotations

import numpy as np

# dot (x%2, y%4) -> Unicode braille bit
_BIT = np.array([[0x01, 0x02, 0x04, 0x40],    # x even
                 [0x08, 0x10, 0x20, 0x80]],   # x odd
                dtype=np.uint8)


class BrailleCanvas:
    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = cols, rows
        self.w, self.h = cols * 2, rows * 4
        self.grid = np.zeros((rows, cols), dtype=np.uint8)

    def clear(self) -> None:
        self.grid[:] = 0

    def plot(self, xs, ys) -> None:
        xs = np.asarray(xs, dtype=int)
        ys = np.asarray(ys, dtype=int)
        m = (xs >= 0) & (xs < self.w) & (ys >= 0) & (ys < self.h)
        xs, ys = xs[m], ys[m]
        np.bitwise_or.at(self.grid, (ys // 4, xs // 2), _BIT[xs % 2, ys % 4])

    def set(self, x: int, y: int) -> None:
        self.plot([x], [y])

    def polyline(self, xs, ys) -> None:
        """Connect successive integer dot coordinates with straight segments."""
        xs = np.asarray(xs, dtype=int)
        ys = np.asarray(ys, dtype=int)
        for i in range(len(xs) - 1):
            n = int(max(abs(xs[i + 1] - xs[i]), abs(ys[i + 1] - ys[i]))) + 1
            self.plot(np.linspace(xs[i], xs[i + 1], n).round(), np.linspace(ys[i], ys[i + 1], n).round())

    def lines(self) -> list[str]:
        return ["".join(chr(0x2800 + int(c)) for c in row) for row in self.grid]

    def render(self) -> str:
        return "\n".join(self.lines())


def draw_eye(canvas: BrailleCanvas, t_ui: np.ndarray, v: np.ndarray, vlim: float = 1.25) -> None:
    """Overlay all traces (v: n_traces x n_samples) into the canvas."""
    canvas.clear()
    x = np.round(np.interp(t_ui, (t_ui[0], t_ui[-1]), (0, canvas.w - 1))).astype(int)
    for tr in v:
        y = np.round((1.0 - (np.clip(tr, -vlim, vlim) + vlim) / (2 * vlim)) * (canvas.h - 1)).astype(int)
        canvas.polyline(x, y)
