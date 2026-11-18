# -*- coding: utf-8 -*-
import json
from pathlib import Path
p = json.loads((Path(__file__).parent / "patterns.json").read_text(encoding="utf-8"))
expected = {
    "GRRGGG", "RGRRRR", "RGRRRG", "GRGGGG",
    "RRGGGR", "GGRRGG", "RGGGGR", "RRGGGG", "GGGGGR",
}
assert len(p) == 9, len(p)
assert {x["pattern"] for x in p} == expected
assert len({x["pattern"] for x in p}) == 9
for x in p:
    assert len(x["positions"]) == 6
    assert len(x["pattern"]) == 6
    assert x["positions"] == sorted(x["positions"])
    assert x["positions"][0] == 1
    assert x["positions"][-1] >= 6
    assert x["direction"] in ("LONG", "SHORT")
print("OK: рівно 9 унікальних шаблонів; UTF-8 та структура перевірені.")

expected_directions = {"P01": ("LONG", "SHORT"), "P02": ("SHORT", "LONG"), "P04": ("LONG", "SHORT"), "P06": ("LONG", "SHORT"), "P07": ("LONG", "SHORT"), "P08": ("LONG", "SHORT"), "P09": ("LONG", "SHORT"), "P10": ("LONG", "SHORT"), "P12": ("SHORT", "LONG")}
for x in p:
    assert (x["confirmation"], x["direction"]) == expected_directions[x["id"]]
print("OK: напрямок підтвердження та фінальний сигнал відповідають усім 9 правилам.")
