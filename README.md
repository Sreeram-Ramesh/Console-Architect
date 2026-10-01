# Console Architect

Design the memory pipeline of a handheld. Terminal-only, Linux-native, built for chip designers.

```
uv sync --group dev
make run                     # TUI, Handheld PC (or: uv run ca tui --console gameboy)
make test
uv run ca sweep --mts 800,1600,3200 --odt on,off --zq on,off --temp 25,85 > sweep.csv
uv run ca report --mts 3200 --temp 85 --no-zq      # per-lane setup/hold slack
```

## TUI keys
`o` ODT · `z` ZQ · `m` ONFI/Toggle · `+`/`-` MT/s · `[`/`]` temperature · `c` process corner ·
`v` Vdd corner · `n` NAND part · `e` ECC · `p` wear · `q` quit

## Layout
- `console_architect/core/` pure library (numpy + stdlib): `phy.py` eye/BER/slack, `nand.py` read pipeline,
  `ecc.py`, `power.py`, `parts.py` TOML loaders. No UI imports.
- `console_architect/tui/` Textual app, braille canvas, mascot.
- `parts/`, `consoles/` TOML data. Drop in a new `.toml` and it shows up (`n`/`e` cycle parts).

## Model notes
- Eye: `W = UI - (2Q*sigma + DJ + skew + ISI(Gamma, L) + ZQ drift)`, `BER = 1/2 erfc(Q/sqrt2)` on time and voltage.
- Read-retry improves the *cell* RBER only. PHY errors persist across retries, so a bad eye keeps retries failing.
- Constants are game-tuned, not silicon-calibrated. They live at the top of `core/phy.py`.

## Roadmap
FTL/GC + QLC pSLC cache state machine, 1 ms tick engine, thermal RC loop, telemetry (psutil/fio),
VCD export, PVT-corner scoring, campaign and boss levels.
