"""Terminal art: device shells, half-block framebuffer -> Rich Text, text screens, bars."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from rich.style import Style
from rich.text import Text


@lru_cache(maxsize=8192)
def _style(f: tuple, b: tuple) -> Style:
    return Style.parse(f"rgb({f[0]},{f[1]},{f[2]}) on rgb({b[0]},{b[1]},{b[2]})")


def frame_to_text(img: np.ndarray) -> Text:
    """RGB uint8 (H, W, 3), H even -> Text using upper-half blocks (2 pixels per cell)."""
    h, w, _ = img.shape
    top, bot = img[0:h:2], img[1:h:2]
    out = Text(no_wrap=True, overflow="crop")
    for r in range(h // 2):
        pairs = np.concatenate([top[r], bot[r]], axis=1)
        idx = np.flatnonzero(np.any(pairs[1:] != pairs[:-1], axis=1)) + 1
        starts = np.concatenate([[0], idx])
        ends = np.concatenate([idx, [w]])
        for s, e in zip(starts, ends):
            st = _style(tuple(int(v) for v in top[r][s]), tuple(int(v) for v in bot[r][s]))
            n = int(e - s)
            while n > 0:                      # short runs keep exporters/terminals from drifting
                out.append("\u2580" * min(8, n), style=st)
                n -= 8
        if r < h // 2 - 1:
            out.append("\n")
    return out


def text_screen(cols: int, rows: int, lines: list, fg: str, bg: str, bold_first: bool = True) -> Text:
    """Centered text on a solid background, exactly cols x rows cells. lines may be (str, style) pairs."""
    out = Text(no_wrap=True, overflow="crop")
    pad_top = max(0, (rows - len(lines)) // 2)
    seq = [""] * pad_top + list(lines) + [""] * (rows - pad_top - len(lines))
    for i, ln in enumerate(seq[:rows]):
        s, st = (ln if isinstance(ln, tuple) else (ln, ""))
        s = s[:cols]
        left = (cols - len(s)) // 2
        out.append(" " * left, style=f"{fg} on {bg}")
        out.append(s, style=f"{st or fg} on {bg}" if not st else f"{st} on {bg}")
        out.append(" " * (cols - left - len(s)), style=f"{fg} on {bg}")
        if i < rows - 1:
            out.append("\n")
    return out


def bar(frac: float, width: int = 14) -> str:
    n = int(round(max(0.0, min(1.0, frac)) * width))
    return "\u2588" * n + "\u2591" * (width - n)


def score_style(s: float) -> str:
    return "green" if s >= 70 else "yellow" if s >= 40 else "red"


# ------------------------------- device art -------------------------------
GB_BRAND = "A R C H I T E C T   B O Y"
GB_CAPTION = "DOT MATRIX WITH PHY SIGNAL INTEGRITY"


def gb_dpad() -> Text:
    rows = ["    \u2584\u2588\u2588\u2588\u2584    ",
            "  \u2584\u2584\u2588 \u25b2 \u2588\u2584\u2584  ",
            "  \u2588\u2588\u2588\u25c4 \u25ba\u2588\u2588\u2588  ",
            "  \u2580\u2580\u2588 \u25bc \u2588\u2580\u2580  ",
            "    \u2580\u2588\u2588\u2588\u2580    "]
    return Text("\n".join(rows), style="#2a2c35")


def gb_ab(flash: bool) -> Text:
    a = "bold white on #d2236b" if flash else "bold #7a1040"
    t = Text("\n")
    t.append("  \u256d\u2500\u2500\u2500\u256e ", style="#7a1040"); t.append("\u256d\u2500\u2500\u2500\u256e\n", style="#7a1040")
    t.append("  \u2502 B \u2502 ", style="bold #7a1040"); t.append("\u2502 A \u2502\n", style=a)
    t.append("  \u2570\u2500\u2500\u2500\u256f ", style="#7a1040"); t.append("\u2570\u2500\u2500\u2500\u256f", style="#7a1040")
    return t


def gb_selstart() -> Text:
    return Text("   \u2571 SELECT \u2571     \u2571 START \u2571", style="#4a4c58")


def deck_left() -> Text:
    rows = ["  \u256d\u2500\u2500\u2500\u2500\u2500\u256e  ", "  \u2502  \u25c9  \u2502  ", "  \u2570\u2500\u2500\u2500\u2500\u2500\u256f  ", "",
            "     \u25b2     ", "   \u25c4 \u25aa \u25ba   ", "     \u25bc     ", "",
            " \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510 ", " \u2502 pad   \u2502 ", " \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518 "]
    return Text("\n".join(rows), style="#8b93a7")


def deck_right(flash: bool) -> Text:
    t = Text()
    t.append("      (Y)      \n", style="#e8c547")
    t.append("    (X) ", style="#4a8fe8"); t.append("(B)    \n", style="#e84a4a")
    t.append("      ", style=""); t.append("(A)", style="bold white on #2e9e4a" if flash else "bold #3fcf5f"); t.append("      \n\n")
    t.append("  \u256d\u2500\u2500\u2500\u2500\u2500\u256e  \n  \u2502  \u25c9  \u2502  \n  \u2570\u2500\u2500\u2500\u2500\u2500\u256f  \n\n", style="#8b93a7")
    t.append(" \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510 \n \u2502 pad   \u2502 \n \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518 ", style="#8b93a7")
    return t


def deck_shoulders(width: int) -> Text:
    mid = "ARCHITECT DECK"
    side = max(4, (width - len(mid) - 12) // 2)
    t = Text(no_wrap=True, overflow="crop")
    t.append("\u2590" + "\u2580" * side + " L1 ", style="#6b7388")
    t.append(mid, style="bold #9aa3b8")
    t.append(" R1 " + "\u2580" * side + "\u258c", style="#6b7388")
    return t
