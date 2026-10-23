"""Deterministic checks + answers dump for the AI semantic review. Does not judge content."""
import json,re,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
read=lambda p:json.loads(p.read_text(encoding='utf8'))
cases={c['id']:c for c in read(HERE/'expectations.json')['cases']}
def answer_of(r):
    t=r['terminal'];a=t.get('answer') or t.get('text') or ''
    return a or ''.join(e.get('text','') for e in r['events'] if e.get('type')=='delta')
rows=[]
for p in sorted((HERE/'results').glob('*.json')):
    r=read(p);c=cases[r['case_id']];t=r['terminal'];a=answer_of(r);f=[]
    validation_block=t.get('code') in ('answer_validation_failed','answer_review_unavailable','request_understanding_failed') and not r['api_errors'] and not r.get('runner_error')  # app-side block, provider answered normally
    service_failure=(t.get('type')!='done' or not a.strip()) and not validation_block
    outcome='validation_block' if validation_block else 'service_failure' if service_failure else 'answered'
    if validation_block:f.append('validation_block['+str(t.get('code'))+'] (user sees retry message): '+'; '.join((t.get('answer_validation') or {}).get('issues',[]))[:400])
    if service_failure:f.append('service_failure: '+str(t.get('code') or '')+' '+str(t.get('message') or r.get('runner_error') or t.get('type')))
    if a and not re.search('[ก-๙]',a):f.append('no Thai text')
    allowed={x['label'] for x in read(HERE/'contexts'/(c['id']+'.json'))['passages']};cited=set()
    for g in re.findall(r'\[(S\d+(?:\s*[,;]\s*S?\d+)*)\]',a):cited.update('S'+x for x in re.findall(r'\d+',g))
    if cited-allowed:f.append('citation label not in context: '+','.join(sorted(cited-allowed)))
    stages=[m['stage'] for m in r['model_requests']]
    rows.append({'id':r['id'],'case_id':c['id'],'repeat':r['repeat'],'outcome':outcome,'service_failure':service_failure,'validation_block':validation_block,'mechanical_findings':f,
      'mechanical_pass':not f,'stages':stages,'api_errors':r['api_errors'],'retried_429_in_run':any(e.get('code')==429 for e in r['api_errors']),
      'elapsed_excl_pacer':r['elapsed_seconds_excluding_pacer'],'first_delta_excl_pacer':r['first_delta_seconds_excluding_pacer'],
      'done_flags':{k:t.get(k) for k in ('safety_flags','answer_validation','request_understanding','use_rag') if k in t},'knowledge_citations':[{k:x.get(k) for k in ('label','title','heading','document_slug','source_refs')} for x in (t.get('citations') or [])],'answer':a})
(HERE/'mechanical.json').write_text(json.dumps(rows,ensure_ascii=False,indent=1),encoding='utf8')
with (HERE/'answers-for-review.md').open('w',encoding='utf8') as fh:
    for cid in cases:
        c=cases[cid];fh.write(f"\n\n## {cid}\nQ: {c['question']}\nEXPECTED: {c['expected']}\nMUST NOT: {c['must_not']}\n")
        for r in [x for x in rows if x['case_id']==cid]:
            fh.write(f"\n### {r['id']} stages={r['stages']} mech={r['mechanical_findings']} cites={[x['label']+':'+str(x['document_slug']) for x in r['knowledge_citations']]}\n{r['answer']}\n")
el=[r['elapsed_excl_pacer'] for r in rows if r['outcome']=='answered']
print(json.dumps({'results':len(rows),'service_failures':sum(r['service_failure'] for r in rows),'validation_blocks':[r['id'] for r in rows if r['validation_block']],
  'mechanical_fail':[r['id'] for r in rows if r['mechanical_findings'] and not r['service_failure']],
  'median_elapsed_excl_pacer':statistics.median(el) if el else None},ensure_ascii=False))
