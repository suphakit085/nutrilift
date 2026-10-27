"""Section A (which real questions change), C1 (off-topic leak), C2 (hit@k displacement), plus held-out retrieval."""
import json,re,sys,logging
from pathlib import Path
from sim import *
logging.disable(logging.CRITICAL)
OUT=HERE/'retrieval';OUT.mkdir(exist_ok=True)
main_R,main_V=corpus(include_new=False);br_R,br_V=corpus(include_new=True)
print('main chunks',len(main_R),'branch chunks',len(br_R),'new slugs',sorted({r['slug'] for r in br_R}-{r['slug'] for r in main_R}))
def sig(ps):return [(p.document_slug,p.heading) for p in ps]
res={}
# A: real questions
ctx=Path('C:/Users/porap/orca/workspaces/chat-bot-nutrition/main-3/output/real-questions-final-c0201c3/contexts')
changed=[]
for p in sorted(ctx.glob('*.json')):
    f=json.loads(p.read_text(encoding='utf8'))
    m=search(main_R,main_V,f['query']);b=search(br_R,br_V,f['query'])
    json.dump({'case_id':f['case_id'],'query':f['query'],'passages':[x.as_dict() for x in b]},open(OUT/f"real-{f['case_id']}.json",'w',encoding='utf8'),ensure_ascii=False,indent=1)
    if sig(m)!=sig(b):changed.append(f['case_id']);print('A changed',f['case_id'],[s for s,_ in sig(m)],'->',[s for s,_ in sig(b)])
res['A_changed']=changed
# C1
calib=(CANDIDATE/'eval/calibrate_threshold.py').read_text(encoding='utf8')
off=re.findall(r'^\s+"([^"]+)",$',calib.split('OFF_TOPIC_QUERIES = [')[1].split(']')[0],re.M)
qs=[json.loads(l) for l in (CANDIDATE/'eval/questions.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
off+= [q['question'] for q in qs if q['category']=='out-of-scope']
lm=sum(bool(search(main_R,main_V,q)) for q in off);lb=sum(bool(search(br_R,br_V,q)) for q in off)
for q in off:
    b=search(br_R,br_V,q)
    if b:print('C1 branch passes gate:',q,[x.document_slug for x in b][:3])
res['C1']={'queries':len(off),'main_pass_gate':lm,'branch_pass_gate':lb}
# C2
hm=hb=0;n=0;lost=[]
for q in qs:
    if not q.get('relevant_doc_slugs'):continue
    n+=1;rel=set(q['relevant_doc_slugs'])
    a=bool(rel&{x.document_slug for x in search(main_R,main_V,q['question'])});b=bool(rel&{x.document_slug for x in search(br_R,br_V,q['question'])})
    hm+=a;hb+=b
    if a and not b:lost.append(q['id'])
res['C2']={'items':n,'main_hits':hm,'branch_hits':hb,'lost':lost}
print(json.dumps(res,ensure_ascii=False,indent=1))
json.dump(res,open(OUT/'summary.json','w',encoding='utf8'),ensure_ascii=False,indent=1)
