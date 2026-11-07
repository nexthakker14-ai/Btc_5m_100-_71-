# -*- coding: utf-8 -*-
import json
from pathlib import Path

p = json.loads((Path(__file__).parent / "patterns.json").read_text(encoding="utf-8"))
assert len(p) == 68
assert len({x['id'] for x in p}) == 68
for x in p:
    assert len(x['positions']) == 6
    assert len(x['pattern']) == 6
    assert x['positions'] == sorted(x['positions'])
    assert x['positions'][0] == 1
    assert x['positions'][-1] >= 6
    assert x['direction'] in ('LONG', 'SHORT')
    assert x['historical_signals'] == x['historical_wins']
    assert x['historical_losses'] == 0
assert not any(x["direction"] == "SHORT" and x["pattern"] in ("RGGGRG", "GGGGRG") for x in p)
print("OK: 68 шаблонів; вилучені SHORT RGGGRG і GGGGRG; структура перевірена.")
