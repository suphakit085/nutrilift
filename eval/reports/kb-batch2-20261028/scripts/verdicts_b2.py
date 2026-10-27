"""Batch 2 round 1 verdicts (AI preliminary) against the live 37-card baseline."""
import collections
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE = json.loads((HERE / 'baseline-live.json').read_text(encoding='utf8'))
P, F = 'pass', 'fail'
J = {
    'DD01-r1': (P, None, ''),
    'TH02-r2': (P, None, 'food sources, small amounts, hard to reach 3-5 g from food'),
    'TH02-r3': (F, 'missing_key_point', 'hedges; no food sources listed. No batch-2 card retrieved (variance)'),
    'TH04-r1': (P, None, ''), 'TH05-r1': (P, None, 'thin'), 'TH05-r2': (P, None, ''), 'TH05-r3': (P, None, ''),
    'TH08-r1': (P, None, 'alcohol chunk retrieved but unused'), 'TH08-r2': (P, None, ''), 'TH08-r3': (P, None, ''),
    'TH13-r1': (F, 'missing_key_point', 'opening trimmed; no brand-free selection criteria; protein-quality chunks x2 retrieved (possible card crowding)'),
    'TH14-r1': (P, None, ''), 'TH14-r2': (P, None, 'TDEE estimate, adaptation, weekly average'), 'TH14-r3': (P, None, 'thin: estimate + tracking'),
    'TH15-r1': (F, 'missing_key_point', 'no causes (estimation error, water); suggests a diet break instead; diet-breaks-refeeds x2 retrieved (card crowding)'),
    'TH16-r1': (P, None, ''), 'TH17-r1': (P, None, ''),
    'TH19-r1': (F, 'missing_key_point', 'hedges, targets and tracking only; no causes (live result was a validation block)'),
    'TH19-r2': (F, 'missing_key_point', 'no causes; sleep and meal-count advice; retrieval led by diet-breaks, meal-frequency and sleep cards (card crowding)'),
    'TH19-r3': (P, None, ''),
    'TH20-r1': (F, 'missing_key_point', 'hedges; tracking and reassessment only, no causes; meal-frequency retrieved, metabolic-adaptation at rank 6 (possible crowding)'),
    'TH20-r2': (F, 'missing_key_point', 'tracking and targets only, no causes (possible crowding)'),
    'TH20-r3': (F, 'validation_block', 'whole answer withheld (live result was also a fail)'),
    'TH21-r1': (P, None, ''), 'TH22-r1': (P, None, ''),
    'TH25-r1': (F, 'validation_block', 'whole answer withheld; diet-breaks-refeeds x2 retrieved (possible crowding)'),
    'TH26-r1': (P, None, ''), 'TH26-r2': (P, None, ''), 'TH26-r3': (P, None, ''),
    'TH27-r1': (P, None, 'same total protein on rest days, distribution'),
    'TH34-r1': (P, None, ''), 'TH35-r1': (P, None, 'asks what the user wants to know'),
    'TH38-r1': (P, None, 'borderline: general cut guidance and asks the user to paste the plan; does not pretend to see it'),
    'TH40-r2': (P, None, 'calculator route'), 'TH41-r1': (P, None, ''),
    'TH42-r1': (F, 'not_answered', 'food-suggestion route with invented restriction (interpreter)'),
    'TH42-r2': (F, 'not_answered', 'food-suggestion route (interpreter)'),
    'TH42-r3': (P, None, ''), 'TH47-r1': (P, None, ''), 'TH48-r1': (P, None, ''),
    'TH49-r1': (P, None, ''), 'TH49-r2': (P, None, ''), 'TH49-r3': (P, None, ''),
    'YT01-r1': (F, 'missing_key_point', 'calculator route; never says bread and milk alone are not enough (interpreter)'),
    'YT01-r2': (P, None, ''), 'YT01-r3': (P, None, ''),
    'YT02-r1': (F, 'missing_key_point', 'gives 117 g but does not say rest days need the same total; hedges (variance, no batch-2 card)'),
    'YT05-r1': (P, None, ''), 'YT06-r1': (P, None, ''), 'YT06-r2': (P, None, ''), 'YT06-r3': (P, None, ''),
}
out = {}
for p in sorted(glob.glob(str(HERE / 'results-real/*.json'))):
    r = json.loads(Path(p).read_text(encoding='utf8'))
    bid = f"{r['case_id']}-r{r['repeat']}"
    out[bid] = {'live': LIVE[bid], 'branch': list(J.get(bid, (LIVE[bid][0], LIVE[bid][1], 'identical answer to live')))}
json.dump({'reviewer': 'Claude (AI), preliminary', 'verdicts': out}, open(HERE / 'verdicts-real.json', 'w', encoding='utf8'),
          ensure_ascii=False, indent=1)


def ok(v):
    return v in ('pass', 'pass_by_policy')


print('results', len(out), 'live pass', sum(ok(v['live'][0]) for v in out.values()),
      'branch pass', sum(ok(v['branch'][0]) for v in out.values()))
print('pass->fail', [k for k, v in out.items() if ok(v['live'][0]) and v['branch'][0] == 'fail'])
print('fail->pass', [k for k, v in out.items() if not ok(v['live'][0]) and ok(v['branch'][0])])
print('policy', collections.Counter(v['branch'][0] for v in out.values() if v['live'][0] == 'pass_by_policy'))
