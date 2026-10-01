import asyncio

from console_architect.core.parts import ConsoleSpec, list_parts
from console_architect.tui.braille import BrailleCanvas
from console_architect.tui.app import ConsoleArchitectApp


def test_braille_bits():
    c = BrailleCanvas(2, 1)
    c.set(0, 0); assert c.lines()[0][0] == "\u2801"
    c.set(1, 0); assert c.lines()[0][0] == "\u2809"
    full = BrailleCanvas(1, 1)
    for x in range(2):
        for y in range(4):
            full.set(x, y)
    assert full.render() == "\u28ff"
    c.set(99, 99)  # out of range is ignored
    assert len(c.lines()) == 1 and len(c.lines()[0]) == 2


def test_polyline_connects_vertical_edge():
    c = BrailleCanvas(1, 3)
    c.polyline([0, 0], [0, 11])
    assert all(ch != "\u2800" for ch in c.lines()[0] + c.lines()[1] + c.lines()[2])


def test_all_parts_and_consoles_load():
    from console_architect.core.parts import EccConfig, NandPart
    for n in list_parts("parts/nand"): NandPart.load(n)
    for n in list_parts("parts/controllers"): EccConfig.load(n)
    for n in list_parts("consoles"): ConsoleSpec.load(n)


def test_tui_smoke_knobs_change_state():
    async def go():
        app = ConsoleArchitectApp("deck")
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            assert app.cfg.odt is True
            await pilot.press("o", "z", "plus", "n", "e", "p", "m", "c", "v", "right_square_bracket")
            await pilot.pause()
            assert app.cfg.odt is False and app.cfg.zq is False
            assert app.cfg.mts == 2400.0
            assert app.mode == "ONFI" and app.cfg.corner.process != "TT"
    asyncio.run(go())
