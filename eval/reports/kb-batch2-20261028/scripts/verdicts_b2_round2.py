"""Batch 2 round 2: final = round 2 where rerun, round 1 elsewhere."""
import collections
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R1 = json.loads((HERE / 'verdicts-real.json').read_text(encoding='utf8'))['verdicts']
LIVE = json.loads((HERE / 'baseline-live.json').read_text(encoding='utf8'))
P, F = 'pass', 'fail'
J = {
    'DD01-r1': (P, None, ''),
    'TH05-r1': (P, None, ''), 'TH05-r2': (P, None, ''),
    'TH05-r3': (F, 'validation_block', 'whole answer withheld; no batch-2 card in retrieval (variance)'),
    'TH08-r1': (P, None, ''), 'TH08-r2': (P, None, ''), 'TH08-r3': (P, None, ''),
    'TH13-r1': (P, None, 'no brands; label, price per gram, FDA number'),
    'TH14-r1': (P, None, 'adaptation, estimation error, weekly average'), 'TH14-r2': (P, None, 'thin: TDEE estimate, tracking'),
    'TH14-r3': (P, None, 'estimation error, TDEE overestimate, water, 2-4 weeks'),
    'TH15-r1': (F, 'missing_key_point', 'hedges; targets and tracking only, no causes; one diet-breaks chunk retrieved but not used (variance)'),
    'TH16-r1': (P, None, ''),
    'TH17-r1': (P, None, 'calls the >=75 class "PDCAAS" where the card says DIAAS (minor mislabel)'),
    'TH19-r1': (F, 'missing_key_point', 'tracking only, no causes (live result was also a fail)'),
    'TH19-r2': (P, None, 'estimation error, adaptation, water; does not push eating less'),
    'TH19-r3': (P, None, 'estimation error, unnoticed intake, adaptation'),
    'TH20-r1': (F, 'missing_key_point', 'tracking and training only, no causes; one diet-breaks chunk at rank 5'),
    'TH20-r2': (F, 'missing_key_point', 'tracking and targets only, no causes; one diet-breaks chunk at rank 5'),
    'TH20-r3': (P, None, 'portion-estimation error, weekly average, protein and training (live result was a fail)'),
    'TH21-r1': (P, None, ''), 'TH25-r1': (P, None, 'borderline after trimming: beginners and heavier people, with training'),
    'TH26-r1': (P, None, ''), 'TH26-r2': (P, None, ''),
    'TH26-r3': (F, 'validation_block', 'whole answer withheld'),
    'TH27-r1': (P, None, ''),
    'TH38-r1': (F, 'missing_key_point', 'general cut guidance but never says the plan was not received (live result was also a fail)'),
    'TH41-r1': (P, None, ''), 'TH47-r1': (P, None, ''),
    'TH49-r1': (P, None, ''), 'TH49-r2': (P, None, ''),
    'YT02-r1': (P, None, 'same 117 g on rest days, not 60 g'),
}
r2 = {}
for p in sorted(glob.glob(str(HERE / 'results-real2/*.json'))):
    r = json.loads(Path(p).read_text(encoding='utf8'))
    bid = f"{r['case_id']}-r{r['repeat']}"
    r2[bid] = {'live': LIVE[bid], 'branch': list(J.get(bid, (LIVE[bid][0], LIVE[bid][1], 'identical answer to live')))}
final = {k: (r2[k] | {'round': 2}) if k in r2 else (v | {'round': 1}) for k, v in R1.items()}
json.dump({'reviewer': 'Claude (AI), preliminary', 'round2': r2, 'final': final},
          open(HERE / 'verdicts-real-final.json', 'w', encoding='utf8'), ensure_ascii=False, indent=1)


def ok(v):
    return v in ('pass', 'pass_by_policy')


print('final', len(final), 'live pass', sum(ok(v['live'][0]) for v in final.values()),
      'branch pass', sum(ok(v['branch'][0]) for v in final.values()))
print('round2 subset', len(r2), 'live', sum(ok(v['live'][0]) for v in r2.values()), 'branch', sum(ok(v['branch'][0]) for v in r2.values()))
print('pass->fail', [k for k, v in final.items() if ok(v['live'][0]) and v['branch'][0] == 'fail'])
print('fail->pass', [k for k, v in final.items() if not ok(v['live'][0]) and ok(v['branch'][0])])
print('policy', collections.Counter(v['branch'][0] for v in final.values() if v['live'][0] == 'pass_by_policy'))
