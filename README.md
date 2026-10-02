# Console Architect

Design the memory system of a handheld console, then **play a game on it** and feel what every choice did
to load times, smoothness, battery, reliability and price. Terminal-only, Linux-native, built for chip designers.

#### Requirements:

1. A linux based machine or terminal, uses tui.
2. Clone this repository into your local linux base env.
3. Install `uv` in-order to create the project virtual env and match the lockfile `uv.lock`.

```
 curl -LsSf https://astral.sh/uv/install.sh | sh 
```
4. Once successfully installed run the following to build and run the Console Architect simulator.
```
uv sync --group dev
make run                     # the game (or: uv run ca play --level 2_openworld)
make test
uv run ca run 2_openworld --set storage=hdd cell=qlc    # headless: simulate + scorecard + explanations
uv run ca sweep --mts 800,1600,3200 --odt on,off --zq on,off --temp 25,85 > sweep.csv
uv run ca report --mts 3200 --temp 85 --no-zq           # per-lane setup/hold slack
uv run ca lab                                           # PHY eye-scope sandbox
```

## How a round works
1. **Pick a level.** Each has a price target, goals and an event (day-one patch, 55 C hot car, brownout).
2. **Build.** 17 knobs across storage, interface, controller and power. A live spec sheet shows boot time,
   streaming bandwidth vs demand, freezes/min, battery, temperature, PVT-corner check, lifespan and price,
   with green/red deltas when you change a knob. The bottom card explains the highlighted knob (WHAT / FEEL / COST).
3. **Tape out and play.** A Game Boy-style or Steam Deck-style device boots (patch + load), then you run a
   side-scroller whose world streams from your storage. Slow reads make tiles pop in late and hide obstacles.
   GC stalls and saves freeze the screen (and drop your jump input). Heat throttles FPS. A closed eye crashes the console.
   The telemetry panel names the cause of every freeze as it happens.
4. **Scorecard.** Seven scores, customer reviews, an itemized BOM, and "Why did that happen? / Try" lessons.

Keys: Build `up/down` select, `left/right` change, `Enter` tape out, `r` reset, `Esc` back.
Play: `Space/Up/Enter` jump, `P` pause, `Esc` abort. Needs a terminal of about 100x32 or larger (truecolor recommended).

## Layout
- `console_architect/core/` pure library, no UI imports: `phy.py` (eye/BER/slack/PVT), `nand.py`, `ecc.py`, `ftl.py`
  (WAF, GC, pSLC cache), `storage.py`, `power.py`, `bom.py`, `engine.py` (seeded session sim), `spec.py`, `verdict.py`
  (scoring + explanations), `options.py` (knobs + lessons), `runner.py` (the game).
- `console_architect/tui/` Textual screens (`game.py`), device art, half-block renderer, braille eye scope.
- `parts/`, `levels/`, `consoles/` TOML data. Add a level or part by dropping in a file.

## Roadmap
telemetry mode (psutil/fio vs the simulated drive), VCD export of the bus, more levels, seeded leaderboards.
