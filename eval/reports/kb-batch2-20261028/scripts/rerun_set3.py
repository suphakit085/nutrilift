import json,glob,logging
from pathlib import Path
from sim import *
logging.disable(logging.CRITICAL)
R,V=corpus(True)
real=set();held=set()
for p in glob.glob(str(HERE/'results-real/*.json')):
    q2=Path(p.replace('results-real','results-real2'))
    p=str(q2) if q2.exists() else p
    r=json.loads(Path(p).read_text(encoding='utf8'))
    if not r['retrieval']:continue
    old=[(x[0],x[1]) for q in r['retrieval'] for x in q['passages']]
    new=[(x.document_slug,x.heading) for x in search(R,V,r['retrieval'][0]['query'])]
    if old!=new:real.add(r['case_id'])
for p in glob.glob(str(HERE/'results-held/*-branch-r1.json')):
    q2=Path(p.replace('results-held','results-held2'))
    p=str(q2) if q2.exists() else p
    r=json.loads(Path(p).read_text(encoding='utf8'))
    if not r['retrieval']:continue
    old=[(x[0],x[1]) for q in r['retrieval'] for x in q['passages']]
    new=[(x.document_slug,x.heading) for x in search(R,V,r['retrieval'][0]['query'])]
    if old!=new:held.add(r['case_id'])
print('REAL',','.join(sorted(real)));print('HELD',','.join(sorted(held)))
