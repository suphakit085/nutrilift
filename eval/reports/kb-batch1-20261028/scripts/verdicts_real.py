import collections
import glob
import json
from pathlib import Path

C0 = Path('C:/Users/porap/orca/workspaces/chat-bot-nutrition/main-3/output/real-questions-final-c0201c3')
V = json.loads((C0 / 'review-verdicts.json').read_text(encoding='utf8'))['verdicts']
P, F = 'pass', 'fail'
# Branch verdicts (AI preliminary). Causes noted: card / variance / route / service.
J = {
    'DD01-r1': (P, None, ''), 'TH01-r1': (P, None, ''),
    'TH02-r1': ('service', None, 'provider 503 x2 during answer review'),
    'TH02-r2': (F, 'missing_key_point', 'names meat and fish, then says amounts are not covered; no "food amounts are small" point. creatine chunks still retrieved; bcaa chunk at rank 2 (variance, possibly crowding)'),
    'TH02-r3': (P, None, ''),
    'TH04-r1': (P, None, 'carbs card: glycogen, very low carb may cut reps, protein first, carbs around training'),
    'TH05-r1': (P, None, ''), 'TH05-r2': (P, None, ''), 'TH05-r3': (P, None, ''), 'TH06-r1': (P, None, ''),
    'TH08-r1': (F, 'missing_key_point', 'whey helps as quality protein and convenience, but never says muscle comes from resistance training; retrieval now led by whey-vs-whole-food (card)'),
    'TH08-r2': (F, 'missing_key_point', 'same: no resistance-training point (card: whey-vs-whole-food lacks it)'),
    'TH08-r3': (F, 'missing_key_point', 'same: no resistance-training point (card)'),
    'TH11-r1': (P, None, ''), 'TH11-r2': (P, None, ''), 'TH11-r3': (P, None, ''), 'TH12-r1': (P, None, ''),
    'TH13-r1': (P, None, 'criteria now include price per gram, label and FDA number (whey-types card)'),
    'TH14-r1': (P, None, 'thin: TDEE estimate, short-term weight vs fat, track trend'),
    'TH14-r2': (F, 'missing_key_point', 'only adaptation; hedges that estimation error, water and NEAT are not covered (variance)'),
    'TH14-r3': (P, None, ''), 'TH15-r1': (P, None, ''), 'TH16-r1': (P, None, ''), 'TH17-r1': (P, None, ''),
    'TH19-r1': (F, 'validation_block', 'whole answer withheld; retrieval includes weight-gain chunks twice (possible card crowding)'),
    'TH19-r2': (P, None, ''), 'TH19-r3': (P, None, ''), 'TH20-r1': (P, None, ''), 'TH20-r2': (P, None, ''),
    'TH20-r3': (F, 'missing_key_point', 'after trimming only tracking and recovery remain; no causes, protein or training (variance / trimming)'),
    'TH21-r1': (F, 'missing_key_point', 'opens with carbs-for-lifting cut text, then trimmed; no protein range, training or "not contradictory" point (card crowding: carbs-for-lifting rank 1, weight-gain x2)'),
    'TH22-r1': (P, None, 'borderline: answers the question (build muscle with training, protein 1.6-2.2, start at maintenance, small surplus later) but leans on the underweight card'),
    'TH23-r1': (P, None, ''), 'TH24-r1': (P, None, ''),
    'TH25-r1': (F, 'missing_key_point', 'says recomposition happens in beginners and higher-fat people, then trimmed; no protein, training or small-deficit point (variance / trimming)'),
    'TH26-r1': (P, None, ''), 'TH26-r2': (P, None, ''), 'TH26-r3': (P, None, ''), 'TH27-r1': (P, None, ''),
    'TH28-r1': (P, None, 'fixed: whey can replace chicken for protein but not whole meals; total protein; kidney referral'),
    'TH29-r1': (P, None, 'fixed: sources state no specific harm, lactose in WPC, count energy'),
    'TH29-r2': (F, 'validation_block', 'whole answer withheld'),
    'TH29-r3': (P, None, 'fixed'),
    'TH30-r1': (P, None, 'fixed: water, milk, fruit, oats by goal'),
    'TH31-r1': (P, None, 'fixed: whey = protein source, creatine evidence, BCAA unnecessary with enough protein, can combine (no creatine dose)'),
    'TH33-r1': (P, None, ''),
    'TH34-r1': (P, None, 'fixed: no price data, cheap foods, price-per-gram method, depends on targets'),
    'TH35-r1': (P, None, ''),
    'TH36-r1': (P, None, 'fixed: Harris-Benedict 1918, Mifflin 1990 (498), Katch-McArdle, PAL. The model added full first names "James Arthur Harris" and "Francis Gano Benedict" that are NOT in the card (initials only). They match the historical record, so not a factual error, but the claim checker let unsupported names through'),
    'TH37-r1': (P, None, 'calculator route as before'), 'TH39-r1': (P, None, ''), 'TH41-r1': (P, None, ''),
    'TH42-r1': (F, 'not_answered', 'food-suggestion route with an invented "no supplements" restriction; no retrieval (interpreter, not cards; known TH42 issue)'),
    'TH42-r2': (P, None, 'fixed: whey, creatine, BCAA not needed, label and FDA checks'),
    'TH47-r1': (P, None, ''), 'TH48-r1': (P, None, 'improved: water, milk, protein drinks, sports drinks, label'),
    'TH49-r1': (P, None, ''), 'TH49-r2': (P, None, 'calculator route (same output judged pass for r1 in c0201c3)'),
    'TH49-r3': (P, None, 'calculator route'),
    'TH50-r1': (P, None, 'fixed: low-moderate cardio, high intensity may suffer, strength mostly unchanged, hypertrophy may be blunted'),
    'TH50-r2': (P, None, ''), 'TH50-r3': (P, None, ''),
    'YT01-r1': ('service', None, 'provider 503 x2 during answer review'),
    'YT01-r2': (P, None, 'fixed: bread and milk alone not enough, 1.6-2.2 g/kg, add eggs, meat, fish, tofu'),
    'YT01-r3': (P, None, ''), 'YT02-r1': (P, None, ''), 'YT03-r1': (P, None, 'calculator route'),
    'YT05-r1': (P, None, 'fixed: still possible with energy and protein; carbs act through training quality'),
    'YT06-r1': (P, None, 'fixed: multiplying high body weight overestimates; LBM, 1.2-1.6 g/kg, target weight'),
    'YT06-r2': (P, None, 'fixed'), 'YT06-r3': (P, None, 'fixed'), 'YT07-r1': (P, None, ''),
}
out = {}
for p in sorted(glob.glob('results-real/*.json')):
    r = json.loads(Path(p).read_text(encoding='utf8'))
    bid = f"{r['case_id']}-r{r['repeat']}"
    base = V[bid]
    b = J.get(bid, (base[0], base[1], 'identical answer to c0201c3 (rule route, no retrieval)'))
    out[bid] = {'baseline': base[:2], 'branch': list(b)}
json.dump({'reviewer': 'Claude (AI), preliminary; owner and expert review pending', 'verdicts': out},
          open('verdicts-real.json', 'w', encoding='utf8'), ensure_ascii=False, indent=1)


def ok(v):
    return v in ('pass', 'pass_by_policy')


svc = [k for k, v in out.items() if v['branch'][0] == 'service']
non = [k for k in out if k not in svc]
print('changed results', len(out), 'baseline pass', sum(ok(v['baseline'][0]) for v in out.values()),
      'branch pass', sum(ok(v['branch'][0]) for v in out.values()), 'branch service', svc)
print('excluding branch service items: baseline', sum(ok(out[k]['baseline'][0]) for k in non),
      'branch', sum(ok(out[k]['branch'][0]) for k in non), 'of', len(non))
print('pass->fail', [k for k, v in out.items() if ok(v['baseline'][0]) and v['branch'][0] == 'fail'])
print('fail->pass', [k for k, v in out.items() if not ok(v['baseline'][0]) and ok(v['branch'][0])])
print('branch factual_error', [k for k, v in out.items() if v['branch'][1] == 'factual_error'])
print('policy items', collections.Counter(v['branch'][0] for v in out.values() if v['baseline'][0] == 'pass_by_policy'))
