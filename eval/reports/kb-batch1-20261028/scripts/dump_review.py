"""Write answers side by side for AI review. held: main vs branch. real: c0201c3 baseline (answer + verdict) vs branch."""
import json,sys,glob
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];C0=Path('C:/Users/porap/orca/workspaces/chat-bot-nutrition/main-3/output/real-questions-final-c0201c3')
def ans(r):return ''.join(e.get('text','') for e in r['events'] if e.get('type')=='delta').strip() or json.dumps(r['terminal'],ensure_ascii=False)[:300]
def cites(r):
    d=next((e for e in r['events'] if e.get('type')=='done'),{})
    return [c.get('document_slug') for c in (d.get('citations') or d.get('sources') or []) if isinstance(c,dict)]
mode=sys.argv[1];out=[]
if mode=='held':
    crit={l.split('|')[1].strip():l for l in (HERE/'CRITERIA.md').read_text(encoding='utf8').splitlines() if l.startswith('| H')}
    for h in sorted(crit):
        out.append('='*100+'\n'+crit[h])
        for arm in ['main','branch']:
            p=HERE/f'results-held/{h}-{arm}-r1.json'
            if not p.exists():out.append(f'--- {arm}: MISSING');continue
            r=json.loads(p.read_text(encoding='utf8'))
            out.append(f"--- {arm} | terminal={r['terminal'].get('type')} | retrieved={[x[0] for q in r['retrieval'] for x in q['passages']]} | cites={cites(r)}\n{ans(r)}")
else:
    exp={c['id']:c for c in json.loads((C0/'expectations.json').read_text(encoding='utf8'))['cases']}
    vmap={k:{'verdict':v[0],'failure_type':v[1],'reason':v[2]} for k,v in json.loads((C0/'review-verdicts.json').read_text(encoding='utf8'))['verdicts'].items()}
    for p in sorted(glob.glob(str(HERE/'results-real/*.json'))):
        r=json.loads(Path(p).read_text(encoding='utf8'));cid=r['case_id'];rep=r['repeat'];base_id=f'{cid}-r{rep}'
        b=json.loads((C0/f'results/{base_id}.json').read_text(encoding='utf8'))
        e=exp[cid];v=vmap.get(base_id,{})
        out.append('='*100+f"\n{base_id} | Q: {e['question']}\nEXPECT: {e['expected']}\nMUST NOT: {e['must_not']}")
        out.append(f"--- BASELINE c0201c3 verdict={v.get('verdict')} type={v.get('failure_type')} reason={str(v.get('reason'))[:300]}\n{ans(b)[:2500]}")
        out.append(f"--- BRANCH terminal={r['terminal'].get('type')} retrieved={[x[0] for q in r['retrieval'] for x in q['passages']]}\n{ans(r)[:2500]}")
(HERE/f'review-{mode}.txt').write_text('\n'.join(out),encoding='utf8');print(len(out))
