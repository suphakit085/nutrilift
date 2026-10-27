import json,logging,sys
from sim import *
logging.disable(logging.CRITICAL)
mR,mV=corpus(False);bR,bV=corpus(True)
qs={json.loads(open(f'../retrieval/real-{c}.json',encoding='utf8').read())['case_id']:json.loads(open(f'../retrieval/real-{c}.json',encoding='utf8').read())['query'] for c in sys.argv[1:]}
for c,q in qs.items():
    print(c,'main',[p.document_slug for p in search(mR,mV,q)]);print('   br  ',[p.document_slug for p in search(bR,bV,q)])
