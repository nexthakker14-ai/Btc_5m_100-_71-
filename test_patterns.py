# -*- coding: utf-8 -*-
import json
from pathlib import Path

p = json.loads((Path(__file__).parent / "patterns.json").read_text(encoding="utf-8"))
assert len(p) == 71
assert len({x['id'] for x in p}) == 71
for x in p:
    assert len(x['positions']) == 6
    assert len(x['pattern']) == 6
    assert x['positions'] == sorted(x['positions'])
    assert x['positions'][0] == 1
    assert x['positions'][-1] >= 6
    assert x['direction'] in ('LONG', 'SHORT')
    assert x['historical_signals'] == x['historical_wins']
    assert x['historical_losses'] == 0
print('OK: 71 шаблонів, структура та історичні лічильники перевірені.')
