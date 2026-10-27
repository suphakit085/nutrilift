"""Batch-2 review sheet: each rerun result next to the live (batch-1 final) verdict and answer."""
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
OUT = Path('C:/Users/porap/orca/workspaces/chat-bot-nutrition/main-3/output')
C0 = OUT / 'real-questions-final-c0201c3'
B1 = OUT / 'kb-batch1-probe'
exp = {c['id']: c for c in json.loads((C0 / 'expectations.json').read_text(encoding='utf8'))['cases']}
v0 = {k: v[:2] for k, v in json.loads((C0 / 'review-verdicts.json').read_text(encoding='utf8'))['verdicts'].items()}
b1 = json.loads((B1 / 'verdicts-real-final.json').read_text(encoding='utf8'))['final']


def base_verdict(bid):
    return b1[bid]['branch'][:2] if bid in b1 else v0[bid]


def base_record(case, rep):
    for p in (B1 / f'results-real2/{case}-branch-r{rep}.json', B1 / f'results-real/{case}-branch-r{rep}.json',
              C0 / f'results/{case}-r{rep}.json'):
        if p.exists():
            return json.loads(p.read_text(encoding='utf8'))


def ans(r):
    return ''.join(e.get('text', '') for e in r['events'] if e.get('type') == 'delta').strip()


out, same, rows = [], [], {}
for p in sorted(glob.glob(str(HERE / 'results-real/*.json'))):
    r = json.loads(Path(p).read_text(encoding='utf8'))
    bid = f"{r['case_id']}-r{r['repeat']}"
    bv = base_verdict(bid)
    rows[bid] = bv
    br = base_record(r['case_id'], r['repeat'])
    rt = [x[0] for q in r['retrieval'] for x in q['passages']]
    if ans(r) == ans(br):
        same.append((bid, bv[0]))
        continue
    t = r['terminal']
    term = '' if t.get('type') == 'done' else f" TERMINAL={t.get('type')}:{t.get('code')} api={[x.get('code') for x in r['api_errors']]}"
    e = exp[r['case_id']]
    out.append(f"#### {bid} LIVE={bv[0]}/{bv[1]}\nQ: {e['question'][:200]}\nEXP: {e['expected'][:300]}\n"
               f"NOT: {e['must_not'][:110]}\nRET: {rt}{term}\nANS: {ans(r)[:1100]}\n")
(HERE / 'review-real.txt').write_text('\n'.join(out), encoding='utf8')
json.dump(rows, open(HERE / 'baseline-live.json', 'w', encoding='utf8'), ensure_ascii=False, indent=1)
print(len(out), 'to review; identical to live:', same)
