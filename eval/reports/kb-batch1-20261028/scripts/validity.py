"""Validity gate: simulator over production chunks only must reproduce the frozen c0201c3 contexts."""
import json,sys,logging
from pathlib import Path
from sim import *
logging.disable(logging.CRITICAL)
R,V=corpus(include_new=False)
print('production chunks',len(R),'documents',len({r['slug'] for r in R}))
ctx=Path('C:/Users/porap/orca/workspaces/chat-bot-nutrition/main-3/output/real-questions-final-c0201c3/contexts')
bad=0;n=0;maxdiff=0
for p in sorted(ctx.glob('*.json')):
    f=json.loads(p.read_text(encoding='utf8'));n+=1
    got=[x.as_dict() for x in search(R,V,f['query'])]
    a=[(x['document_slug'],x['heading'],x['chunk_id']) for x in f['passages']];b=[(x['document_slug'],x['heading'],x['chunk_id']) for x in got]
    for x,y in zip(f['passages'],got):maxdiff=max(maxdiff,abs(x['score']-y['score']))
    if a!=b:
        bad+=1;print('MISMATCH',f['case_id'],'\n  frozen',[(s,round(x['score'],4)) for (s,_,_),x in zip(a,f['passages'])],'\n  sim   ',[(s,round(x['score'],4)) for (s,_,_),x in zip(b,got)])
print(f'{n-bad}/{n} identical; max score diff {maxdiff:.2e}')
