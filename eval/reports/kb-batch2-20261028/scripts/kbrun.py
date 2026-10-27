"""Knowledge-base batch 1 generation run (criteria in ../CRITERIA.md).

Same production entry, model, pacing, profile and key rotation as the c0201c3 real-question run. Only the
retrieval differs: sim.search over production chunks (main arm) or production + new card chunks (branch
arm). Every result is kept; a daily-quota 429 archives the attempt and retries on the next key.

Usage: kbrun.py held   -> 22 held-out questions x {main, branch} x 1
       kbrun.py real   -> real questions whose branch retrieval changed, repeats as in c0201c3 (core 3, others 1)
"""
import copy,hashlib,json,logging,random,subprocess,sys,threading,time
from datetime import datetime,timezone
from pathlib import Path
from sim import *
sys.path.insert(0,str(ROOT/'output/functional-fixes-release-20261022'))
from keyring import KeyRing
from sqlalchemy import create_engine,event
from sqlalchemy.orm import sessionmaker
from app.services import chat,prompts
from app.services.nutrition import ProfileInput
logging.disable(logging.CRITICAL)
MODEL='gemini-3.5-flash-lite';PACE=6.0
C0=ROOT/'output/real-questions-final-c0201c3'
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def save(p,o):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(o,ensure_ascii=False,indent=1,default=str),encoding='utf8')
def digest(o):return hashlib.sha256(json.dumps(o,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()
COND=read(C0/'condition.json');PROFILE=COND['profile']
mode=sys.argv[1];ONLY=set(filter(None,os.environ.get('ONLY','').split(',')))
if mode.startswith('held'):
    rows=[l for l in (HERE/'CRITERIA.md').read_text(encoding='utf8').splitlines() if l.startswith('| K')]
    held=[{'id':r.split('|')[1].strip(),'question':r.split('|')[3].strip()} for r in rows]
    assert len(held)==16
    if ONLY:held=[h for h in held if h['id'] in ONLY]
    tasks=[(c,arm,1) for arm in (['branch'] if ONLY else ['main','branch']) for c in held]
    random.Random(20261028).shuffle(tasks)
else:
    changed=ONLY or set(read(HERE/'retrieval/summary.json')['A_changed'])
    cases=[c for c in read(C0/'expectations.json')['cases'] if c['id'] in changed]
    tasks=[]
    for rep in range(1,4):
        order=[c for c in cases if COND['items'][c['id']]>=rep];random.Random(20261028+rep).shuffle(order)
        tasks+=[(c,'branch',rep) for c in order]
destdir=HERE/f'results-{mode}';destdir.mkdir(exist_ok=True)
corpora={'main':corpus(include_new=False),'branch':corpus(include_new=True)}
cards_state={p.name:hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in sorted((CANDIDATE/'knowledge/cards').glob('*.md'))}
mpath=HERE/f'manifest-{mode}.json'
current={'mode':mode,'model':MODEL,'prompt_version':prompts.PROMPT_VERSION,
  'candidate_commit':subprocess.check_output(['git','-C',str(CANDIDATE),'rev-parse','HEAD'],text=True).strip(),
  'cards_utf8_lf_sha256':cards_state,'profile':PROFILE,'pacer_interval_seconds':PACE,'planned_results':len(tasks)}
if not mpath.exists():save(mpath,{**current,'created_utc':datetime.now(timezone.utc).isoformat(),
  'retrieval':'in-memory simulator (sim.py): production chunks read-only, plus new card chunks for the branch arm',
  'assessment':'Preliminary AI review (Claude); project owner and expert review pending'})
m=read(mpath)
for k in ['cards_utf8_lf_sha256','prompt_version','candidate_commit']:assert m[k]==current[k],k
engine=create_engine(settings.database_url,hide_parameters=True,pool_pre_ping=True,connect_args={'prepare_threshold':None,'connect_timeout':12})
@event.listens_for(engine,'begin')
def ro(conn):conn.exec_driver_sql('SET TRANSACTION READ ONLY')
Sessions=sessionmaker(engine,autoflush=False)
class Pacer:
    def __init__(s):s.last=0;s.lock=threading.Lock()
    def wait(s):
        with s.lock:
            r=PACE-(time.monotonic()-s.last)
            if r>0:time.sleep(r)
            s.last=time.monotonic()
pacer=Pacer();ring=KeyRing(int(os.environ.get('KEY_START','2')));active={};lock=threading.Lock()
def status(**kw):kw['updated_utc']=datetime.now(timezone.utc).isoformat();save(HERE/f'state-{mode}.json',kw);print(json.dumps(kw,ensure_ascii=False),flush=True)
class Models:
    def generate_content_stream(self,**kwargs):
        t=time.monotonic();pacer.wait()
        if threading.current_thread() is threading.main_thread():active['pacer_wait']+=time.monotonic()-t
        config=kwargs['config'];title=(config.response_json_schema or {}).get('title');started=time.monotonic()
        entry={'stage':'interpretation' if title=='RequestUnderstanding' else 'semantic_review' if title else 'answer','schema':title,
               'key':ring.fingerprint,'response_text':''}
        with lock:active['calls'].append(entry)
        try:
            for chunk in ring.client.models.generate_content_stream(**kwargs):
                if chunk.text:entry['response_text']+=chunk.text
                if getattr(chunk,'model_version',None):active['versions'].add(chunk.model_version)
                yield chunk
        except Exception as exc:
            with lock:active['errors'].append({'error_type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)[:300]})
            raise
        finally:entry['seconds']=round(time.monotonic()-started,3)
class Client:models=Models()
original_search=retrieval.search;original_client=chat.get_client
chat.get_client=lambda:Client()
try:
    pending=list(tasks)
    while pending:
        case,arm,rep=pending.pop(0)
        ident=f"{case['id']}-{arm}-r{rep}";dest=destdir/(ident+'.json')
        if dest.exists():continue
        if (HERE/'STOP').exists():status(phase='stopped');sys.exit(0)
        R,V=corpora[arm]
        active.update({'calls':[],'errors':[],'versions':set(),'pacer_wait':0.0,'retrieval':[]})
        def sim_search(db,query,**kw):
            ps=search(R,V,query);active['retrieval'].append({'query':query,'passages':[(p.document_slug,p.heading,round(p.score,4)) for p in ps]});return ps
        retrieval.search=sim_search
        began=datetime.now(timezone.utc).isoformat();start=time.monotonic();events=[];error=None
        status(phase='generating',item=ident,done=len(list(destdir.glob('*.json'))),total=len(tasks),key=ring.fingerprint)
        try:
            with Sessions() as db:
                for ev in chat.stream_understood_chat(db,user_message=case['question'],history=[],profile=ProfileInput(**PROFILE),use_rag=True,model=MODEL):
                    events.append(ev)
            terminal=next((e for e in reversed(events) if e['type'] in ['done','error']),{'type':'error','message':'Missing terminal event'})
        except Exception as exc:
            terminal={'type':'error'};error={'error_type':type(exc).__name__,'message':str(exc)[:300]}
        el=time.monotonic()-start
        rec={'id':ident,'case_id':case['id'],'arm':arm,'repeat':rep,'question':case['question'],'started_utc':began,
             'elapsed_seconds_excluding_pacer':round(el-active['pacer_wait'],3),'model_versions':sorted(active['versions']),
             'model_requests':active['calls'],'api_errors':active['errors'],'retrieval':active['retrieval'],
             'events':events,'terminal':terminal,'runner_error':error}
        if any(e.get('code')==429 for e in active['errors']) and terminal.get('type')!='done':
            save(HERE/f'quota-aborted-{mode}'/(ident+'-'+began.replace(':','')+'.json'),rec)
            if ring.rotate():status(phase='quota_key_switched',key=ring.fingerprint);pending.insert(0,(case,arm,rep));continue
            status(phase='quota_stop',item=ident);sys.exit(0)
        save(dest,rec)
        if any(e.get('code') in [400,401,403,404] for e in active['errors']):status(phase='api_error_stop',item=ident,errors=active['errors']);sys.exit(1)
    status(phase='complete',done=len(list(destdir.glob('*.json'))),total=len(tasks))
finally:
    retrieval.search=original_search;chat.get_client=original_client;engine.dispose()
