"""Round 2 (whey-vs-whole-food v1 + resistance-training paragraph). Final = round 2 for the 29 rerun
questions, round 1 for the other changed questions (their retrieval did not change with the edit)."""
import collections
import glob
import json
from pathlib import Path

C0 = Path('C:/Users/porap/orca/workspaces/chat-bot-nutrition/main-3/output/real-questions-final-c0201c3')
V = json.loads((C0 / 'review-verdicts.json').read_text(encoding='utf8'))['verdicts']
R1 = json.loads(Path('verdicts-real.json').read_text(encoding='utf8'))['verdicts']
P, F = 'pass', 'fail'
J = {
    'TH05-r1': (P, None, ''), 'TH05-r2': (P, None, ''), 'TH05-r3': (P, None, ''), 'TH06-r1': (P, None, ''),
    'TH08-r1': (P, None, 'fixed: whey does not build muscle by itself; resistance training + total protein + energy; ISSN synergy; 1.4-2.0 g/kg'),
    'TH08-r2': (P, None, 'fixed (same points)'), 'TH08-r3': (P, None, 'fixed (same points)'),
    'TH11-r1': (P, None, ''), 'TH11-r2': (P, None, 'adds "soy has no lactose" (not in a card, true)'), 'TH11-r3': (P, None, ''),
    'TH12-r1': (P, None, ''), 'TH17-r1': (P, None, ''),
    'TH21-r1': (P, None, 'recomposition: maintenance targets, protein with resistance training, track 2-4 weeks'),
    'TH25-r1': (P, None, 'beginners, returning and higher-fat people; deficit + training + protein; harder when advanced'),
    'TH26-r1': (P, None, 'opening sentence trimmed but both times answered'), 'TH26-r2': (P, None, ''), 'TH26-r3': (P, None, ''),
    'TH27-r1': (F, 'missing_key_point', 'only "keep protein steady" survives trimming; retrieval has no new card (variance / trimming)'),
    'TH28-r1': (P, None, 'fixed'),
    'TH29-r1': (P, None, 'fixed'), 'TH29-r2': (P, None, 'fixed'), 'TH29-r3': (P, None, 'fixed (opens with a hedge, then lactose and energy)'),
    'TH30-r1': (P, None, 'fixed (opens with a hedge, then water / milk / fruit, oats)'),
    'TH34-r1': (P, None, 'fixed, borderline: says 100 baht "may be rather little but can work" without price data; gives cheap foods and price-per-gram method'),
    'TH39-r1': (P, None, ''),
    'TH42-r1': (F, 'not_answered', 'food-suggestion route, no retrieval (interpreter)'),
    'TH42-r2': (F, 'not_answered', 'food-suggestion route, no retrieval (interpreter)'),
    'TH42-r3': (P, None, 'fixed: whey, mixing, creatine, BCAA not needed'),
    'YT01-r1': (F, 'validation_block', 'whole answer withheld'),
    'YT01-r2': (P, None, 'fixed'), 'YT01-r3': (P, None, ''),
    'YT02-r1': (P, None, ''), 'YT05-r1': (P, None, 'fixed'), 'YT07-r1': (P, None, ''),
}
r2 = {}
for p in sorted(glob.glob('results-real2/*.json')):
    r = json.loads(Path(p).read_text(encoding='utf8'))
    bid = f"{r['case_id']}-r{r['repeat']}"
    b = J.get(bid, (V[bid][0], V[bid][1], 'identical answer to c0201c3 (rule route, no retrieval)'))
    r2[bid] = {'baseline': V[bid][:2], 'branch': list(b)}
final = {k: (r2[k] | {'round': 2}) if k in r2 else (v | {'round': 1}) for k, v in R1.items()}
json.dump({'reviewer': 'Claude (AI), preliminary; owner and expert review pending', 'round2': r2, 'final': final},
          open('verdicts-real-final.json', 'w', encoding='utf8'), ensure_ascii=False, indent=1)


def ok(v):
    return v in ('pass', 'pass_by_policy')


svc = [k for k, v in final.items() if v['branch'][0] == 'service']
print('final changed results', len(final), 'baseline pass', sum(ok(v['baseline'][0]) for v in final.values()),
      'branch pass', sum(ok(v['branch'][0]) for v in final.values()), 'service', svc)
print('pass->fail', [k for k, v in final.items() if ok(v['baseline'][0]) and v['branch'][0] == 'fail'])
print('fail->pass', [k for k, v in final.items() if not ok(v['baseline'][0]) and ok(v['branch'][0])])
print('policy', collections.Counter(v['branch'][0] for v in final.values() if v['baseline'][0] == 'pass_by_policy'))
print('round2 only: baseline', sum(ok(v['baseline'][0]) for v in r2.values()), 'branch', sum(ok(v['branch'][0]) for v in r2.values()), 'of', len(r2))
# whole 101-result set: unchanged items keep their c0201c3 verdicts
allv = {k: (final[k]['branch'][0] if k in final else v[0]) for k, v in V.items()}
print('whole set (101):', sum(ok(x) for x in allv.values()), 'baseline whole set:', sum(ok(v[0]) for v in V.values()))
