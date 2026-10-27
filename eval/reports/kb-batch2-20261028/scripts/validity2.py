"""Validity gate for batch 2: production (now 37 cards) via the simulator must reproduce the batch-1 final
retrieval (kb-batch1-probe/retrieval/real-*.json, computed from the same 37 cards before ingest)."""
import json,logging
from pathlib import Path
from sim import *
logging.disable(logging.CRITICAL)
R,V=corpus(include_new=False)
print('production chunks',len(R),'documents',len({r['slug'] for r in R}))
ref=Path('C:/Users/porap/orca/workspaces/chat-bot-nutrition/main-3/output/kb-batch1-probe/retrieval')
bad=0;n=0;md=0
for p in sorted(ref.glob('real-*.json')):
    f=json.loads(p.read_text(encoding='utf8'));n+=1
    got=search(R,V,f['query'])
    a=[(x['document_slug'],x['heading']) for x in f['passages']];b=[(x.document_slug,x.heading) for x in got]
    for x,y in zip(f['passages'],got):md=max(md,abs(x['score']-y.score))
    if a!=b:bad+=1;print('MISMATCH',f['case_id'],a,b)
print(f'{n-bad}/{n} identical; max score diff {md:.2e}')
