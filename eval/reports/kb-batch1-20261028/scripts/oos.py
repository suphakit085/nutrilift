import json,re,logging
from sim import *
logging.disable(logging.CRITICAL)
mR,mV=corpus(False);bR,bV=corpus(True)
calib=(CANDIDATE/'eval/calibrate_threshold.py').read_text(encoding='utf8')
off=re.findall(r'^\s+"([^"]+)",$',calib.split('OFF_TOPIC_QUERIES = [')[1].split(']')[0],re.M)
qs=[json.loads(l) for l in (CANDIDATE/'eval/questions.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
off+=[q['question'] for q in qs if q['category']=='out-of-scope']
def best(R,V,q):
    qv=query_vector(q);s=(V@qv)/(np.linalg.norm(V,axis=1)*np.linalg.norm(qv));i=int(np.argmax(s));return round(float(s[i]),3),R[i]['slug']
for q in off:
    a=best(mR,mV,q);b=best(bR,bV,q);flag='  <-- crosses 0.66' if a[0]<0.66<=b[0] else ''
    print(a,b,q[:50],flag)
