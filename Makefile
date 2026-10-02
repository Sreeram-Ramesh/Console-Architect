.PHONY: run test sweep report demo
run:      ; uv run ca play
test:     ; uv run pytest -q
sweep:    ; uv run ca sweep --mts 800,1600,2400,3200,3600 --odt on,off --zq on,off --temp 25,85
report:   ; uv run ca report --mts 3200 --temp 85 --no-zq
demo:     ; asciinema rec demo.cast -c "uv run ca play"
