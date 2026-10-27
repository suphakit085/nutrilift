import json,glob
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];C0=Path('C:/Users/porap/orca/workspaces/chat-bot-nutrition/main-3/output/real-questions-final-c0201c3')
exp={c['id']:c for c in json.loads((C0/'expectations.json').read_text(encoding='utf8'))['cases']}
V=json.loads((C0/'review-verdicts.json').read_text(encoding='utf8'))['verdicts']
def ans(r):return ''.join(e.get('text','') for e in r['events'] if e.get('type')=='delta').strip()
out=[];same=[]
for p in sorted(glob.glob(str(HERE/'results-real/*.json'))):
    r=json.loads(Path(p).read_text(encoding='utf8'));bid=f"{r['case_id']}-r{r['repeat']}";e=exp[r['case_id']];v=V[bid]
    b=json.loads((C0/f'results/{bid}.json').read_text(encoding='utf8'))
    rt=[x[0] for q in r['retrieval'] for x in q['passages']];a=ans(r)
    if not rt and a==ans(b):same.append((bid,v[0]));continue
    if bid<'TH10-r3':continue
    t=r['terminal'];term='' if t.get('type')=='done' else f" TERMINAL={t.get('type')}:{t.get('code')} api={[x.get('code') for x in r['api_errors']]}"
    out.append(f"#### {bid} BASE={v[0]}/{v[1]} :: {v[2][:150]}\nQ: {e['question'][:200]}\nEXP: {e['expected'][:300]}\nNOT: {e['must_not'][:110]}\nRET: {rt}{term}\nANS: {a[:1100]}\n")
(HERE/'review-real-compact2.txt').write_text('\n'.join(out),encoding='utf8');print(len(out),'identical-rule:',same)
