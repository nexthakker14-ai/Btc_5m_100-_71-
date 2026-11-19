# -*- coding: utf-8 -*-
"""Configuration checks for the nine exact 11-candle patterns."""
import json
from pathlib import Path

patterns = json.loads((Path(__file__).parent / "patterns.json").read_text(encoding="utf-8"))
expected = {
    "GRRRRGGGGRR": ("SHORT", "🟢🔴🔴🔴🔴🟢🟢🟢🟢🔴🔴"),
    "GGGRGGGGGGG": ("SHORT", "🟢🟢🟢🔴🟢🟢🟢🟢🟢🟢🟢"),
    "RRRGGRGGGGG": ("SHORT", "🔴🔴🔴🟢🟢🔴🟢🟢🟢🟢🟢"),
    "RRRRGGGGGRR": ("SHORT", "🔴🔴🔴🔴🟢🟢🟢🟢🟢🔴🔴"),
    "GGRGGGGGGGG": ("SHORT", "🟢🟢🔴🟢🟢🟢🟢🟢🟢🟢🟢"),
    "GRGGRRRRRRR": ("LONG", "🟢🔴🟢🟢🔴🔴🔴🔴🔴🔴🔴"),
    "RGRRRRRRRRR": ("LONG", "🔴🟢🔴🔴🔴🔴🔴🔴🔴🔴🔴"),
    "GRGGGGGGGGG": ("SHORT", "🟢🔴🟢🟢🟢🟢🟢🟢🟢🟢🟢"),
    "RGGGGRGGGGG": ("SHORT", "🔴🟢🟢🟢🟢🔴🟢🟢🟢🟢🟢"),
}

assert len(patterns) == 9, len(patterns)
assert len({p["id"] for p in patterns}) == 9
assert len({p["pattern"] for p in patterns}) == 9
assert {p["pattern"]: (p["direction"], p["emoji"]) for p in patterns} == expected
for p in patterns:
    assert len(p["pattern"]) == 11
    assert p["direction"] in ("LONG", "SHORT")
    assert set(p["pattern"]) <= {"G", "R"}
    assert len(p["emoji"]) == 11

# Result-window logic: first favorable candle wins at its exact position.
def result(direction, colors):
    wanted = "G" if direction == "LONG" else "R"
    opposite = "R" if wanted == "G" else "G"
    for i, value in enumerate(colors, start=1):
        if value == wanted:
            return f"WIN {i}/5"
    if all(value == opposite for value in colors):
        return "LOSS 5/5"
    return "VOID"

for direction, wanted in (("LONG", "G"), ("SHORT", "R")):
    for n in range(1, 6):
        seq = ["R" if wanted == "G" else "G"] * (n - 1) + [wanted] + ["D"] * (5 - n)
        assert result(direction, seq) == f"WIN {n}/5"
assert result("LONG", ["R"] * 5) == "LOSS 5/5"
assert result("SHORT", ["G"] * 5) == "LOSS 5/5"
assert result("LONG", ["R", "D", "R", "D", "R"]) == "VOID"
print("OK: рівно 9 унікальних 11-свічкових патернів; напрямки, емодзі та логіка WIN 1/5–5/5 перевірені.")
