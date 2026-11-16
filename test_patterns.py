# -*- coding: utf-8 -*-
import json
from pathlib import Path
p = json.loads((Path(__file__).parent / "patterns.json").read_text(encoding="utf-8"))
expected = {
    "GRRGGG", "RGRRRR", "RGRRRG", "GRGGGG",
    "RRGGGR", "GGRRGG", "RGGGGR", "RRGGGG", "GGGGGR",
}
assert len(p) == 10, len(p)
assert {x["pattern"] for x in p} == expected
assert len({x["pattern"] for x in p}) == 10
for x in p:
    assert len(x["positions"]) == 6
    assert len(x["pattern"]) == 6
    assert x["positions"] == sorted(x["positions"])
    assert x["positions"][0] == 1
    assert x["positions"][-1] >= 6
    assert x["direction"] in ("LONG", "SHORT")
print("OK: рівно 10 унікальних шаблонів; UTF-8 та структура перевірені.")
