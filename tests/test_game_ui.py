import asyncio

import pytest

from console_architect.tui.game import ArchitectApp, BuildScreen, PlayScreen, ResultScreen, TitleScreen


@pytest.mark.parametrize("level,size", [("1_pocket", (110, 40)), ("2_openworld", (130, 44)), ("2_openworld", (100, 32))])
def test_full_flow_title_build_play_result(level, size, tmp_path, monkeypatch):
    monkeypatch.setenv("CA_SAVE_DIR", str(tmp_path))

    async def go():
        app = ArchitectApp(level)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, BuildScreen)
            await pilot.press("down", "right", "left", "r")          # poke the knobs
            await pilot.press("enter")                               # tape out
            await pilot.pause()
            ps = app.screen
            assert isinstance(ps, PlayScreen)
            ps._timer.pause()
            for i in range(4000):
                if i % 20 == 3:
                    ps.jump_pending = True
                ps.advance(0.05)
                if not isinstance(app.screen, PlayScreen):
                    break
            await pilot.pause()
            assert isinstance(app.screen, ResultScreen)
            await pilot.press("r")                                   # redesign -> back to build
            await pilot.pause()
            assert isinstance(app.screen, BuildScreen)
    asyncio.run(go())


def test_title_navigation_and_doesnt_fit_blocks_tapeout():
    async def go():
        app = ArchitectApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, TitleScreen)
            await pilot.press("down", "enter")
            await pilot.pause()
            bs = app.screen
            assert isinstance(bs, BuildScreen) and bs.level.id == "2_openworld"
            from console_architect.core.spec import estimate
            bs.build = bs.build.with_(capacity_gb=64)
            bs.spec = estimate(bs.build, bs.level)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, BuildScreen)   # refused: the game doesn't fit
    asyncio.run(go())
