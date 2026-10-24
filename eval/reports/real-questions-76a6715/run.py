"""Final real-question run on latest main (76a6715): every frozen question through chat.stream_understood_chat (production entry) with the sample profile,
frozen retrieval (captured live once by freeze_contexts.py). Every result is kept, including errors
and timeouts. A daily-quota 429 is NOT recorded as a result: the attempt is archived and the item reruns on the next key; the run stops when every key is exhausted."""
import copy,logging,random,subprocess,sys,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'functional-fixes-release-20261022'))
from keyring import KeyRing
from datetime import datetime,timezone
from common import *
logging.disable(logging.CRITICAL)
MODEL='gemini-3.5-flash-lite';PACE=6.0;REPEATS=3  # same 6.0 s as the 4fca71e run after its key change
exp=read(HERE/'expectations.json');SPEC=read(HERE/'condition.json');PROFILE=SPEC['profile'];cases=[c for c in exp['cases'] if c['id'] in SPEC['items']]
mpath=HERE/'manifest.json';destdir=HERE/'results';destdir.mkdir(exist_ok=True)
services=CANDIDATE/'backend/app/services'
current={'prompt_version':prompts.PROMPT_VERSION,'model':MODEL,
  'candidate_commit':subprocess.check_output(['git','-C',str(CANDIDATE),'rev-parse','HEAD'],text=True).strip(),
  'candidate_dirty':bool(subprocess.check_output(['git','-C',str(CANDIDATE),'status','--porcelain'],text=True).strip()),
  'cases_sha256':digest(cases),'profile_sha256':digest(PROFILE),'dataset_sha256':exp['dataset_sha256'],
  'source_files':{p.name:digest(p.read_text(encoding='utf8')) for p in sorted(services.glob('*.py'))}}
if not mpath.exists():
    save(mpath,{**current,'created_utc':datetime.now(timezone.utc).isoformat(),
      'run_notes':[{'note':'Rerun on main 76a6715 (backend = deployed 40b3b7a, #32-#46); same questions, contexts, expectations and profile as the 4fca71e run; conditions and verdict rules in condition.json, frozen before the first result'}],'purpose':'Prompt-quality test on real published Thai questions (Pantip titles, YouTube comments, Dek-D titles); no AI-written questions',
      'production_entry':'app.services.chat.stream_understood_chat','repeats':REPEATS,'case_count':len(cases),'planned_results':sum(SPEC['items'].values()),
      'retrieval':'frozen: live retrieval from production knowledge base (read-only) captured once per item before the first generation; same passages for all repeats',
      'profile':PROFILE,'history':'empty (new conversation each run)',
      'pacer_interval_seconds':PACE,'order':'repeat-major; items shuffled within each repeat with seed 20261023+repeat',
      'expectations_frozen_before_first_result':True,'assessment':'Preliminary AI review (Claude); project owner and expert review pending',
      'database':'production Supabase, READ ONLY transactions'})
manifest=read(mpath)
for k in ['prompt_version','candidate_commit','cases_sha256','source_files']:assert manifest[k]==current[k],k
assert not current['candidate_dirty']
engine,Sessions=database();pacer=Pacer(PACE);ring=KeyRing(int(os.environ.get('KEY_START','0')));active={};calls_lock=threading.Lock()
def status(**kw):
    kw['updated_utc']=datetime.now(timezone.utc).isoformat()
    save(HERE/'generation-state.json',kw);print(json.dumps(kw,ensure_ascii=False),flush=True)
class Models:
    def generate_content_stream(self,**kwargs):
        t=time.monotonic();pacer.wait();waited=time.monotonic()-t
        if threading.current_thread() is threading.main_thread():active['pacer_wait']+=waited
        config=kwargs['config'];system=config.system_instruction;request_started=time.monotonic()
        title=(config.response_json_schema or {}).get('title')
        entry={'system_sha256':digest(system),'schema':title,
            'stage':'interpretation' if title=='RequestUnderstanding' else 'semantic_review' if title else 'answer',
            'key':ring.fingerprint,'response_text':'','contents_sha256':digest([c.model_dump(mode='json',exclude_none=True) for c in kwargs['contents']]),
            'generation_config':config.model_dump(mode='json',exclude_none=True,exclude={'system_instruction'})}
        with calls_lock:active['calls'].append(entry)
        try:
            for chunk in ring.client.models.generate_content_stream(**kwargs):
                entry.setdefault('finish_reasons',[]).extend(str(c.finish_reason) for c in (chunk.candidates or []) if c.finish_reason)
                if chunk.usage_metadata:entry['usage']=chunk.usage_metadata.model_dump(mode='json',exclude_none=True)
                if chunk.text:
                    entry.setdefault('first_text_seconds',round(time.monotonic()-request_started,3))
                    entry['response_text']+=chunk.text
                if getattr(chunk,'model_version',None):active['versions'].add(chunk.model_version)
                yield chunk
        except Exception as exc:
            with calls_lock:active['errors'].append({'error_type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)[:300]})
            raise
        finally:
            entry['provider_seconds_excluding_pacer']=round(time.monotonic()-request_started,3)
class Client:models=Models()
original_search=retrieval.search;original_client=chat.get_client
chat.get_client=lambda:Client()
tasks=[]
for repeat in range(1,REPEATS+1):
    order=list(cases);random.Random(20261023+repeat).shuffle(order)
    order=[c for c in order if SPEC['items'][c['id']]>=repeat]
    tasks.extend((c,repeat) for c in order)
try:
    pending=list(tasks)
    while pending:
        case,repeat=pending.pop(0)
        if (HERE/'STOP').exists():status(phase='stopped_between_cases',completed=len(list(destdir.glob('*.json'))));sys.exit(0)
        ident=f"{case['id']}-r{repeat}";dest=destdir/(ident+'.json')
        if dest.exists():continue
        active={'calls':[],'errors':[],'versions':set(),'pacer_wait':0.0,'retrieval_queries':[]}
        frozen=read(HERE/'contexts'/(case['id']+'.json'));assert digest(frozen['passages'])==frozen['sha256']
        def frozen_search(db,query,**kwargs):
            active['retrieval_queries'].append(query)
            if query!=case['question']:raise RuntimeError('Unexpected retrieval query (frozen context mismatch)')
            return [retrieval.Passage(**copy.deepcopy(p)) for p in frozen['passages']]
        retrieval.search=frozen_search
        began=datetime.now(timezone.utc).isoformat();start=time.monotonic();events=[];error=None;first_delta=None
        status(phase='generating',case=case['id'],repeat=repeat,completed=len(list(destdir.glob('*.json'))),total=manifest['planned_results'])
        try:
            with Sessions() as db:
                for event in chat.stream_understood_chat(db,user_message=case['question'],history=[],profile=ProfileInput(**PROFILE),use_rag=True,model=MODEL):
                    if event.get('type')=='delta' and first_delta is None:first_delta=time.monotonic()-start-active['pacer_wait']
                    events.append(event)
            terminal=next((e for e in reversed(events) if e['type'] in ['done','error']),{'type':'error','message':'Missing terminal event'})
        except Exception as exc:
            terminal={'type':'error'};error={'error_type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)[:300]}
        elapsed=time.monotonic()-start
        record={'id':ident,'case_id':case['id'],'repeat':repeat,'started_utc':began,
            'elapsed_seconds_including_pacer':round(elapsed,3),'pacer_wait_seconds':round(active['pacer_wait'],3),
            'elapsed_seconds_excluding_pacer':round(elapsed-active['pacer_wait'],3),
            'first_delta_seconds_excluding_pacer':None if first_delta is None else round(first_delta,3),
            'prompt_version':prompts.PROMPT_VERSION,'candidate_commit':manifest['candidate_commit'],'context_sha256':frozen['sha256'],
            'question_sha256':digest(case['question']),'generation_model_requested':MODEL,'model_versions_returned':sorted(active['versions']),
            'model_called':bool(active['calls']),'model_requests':active['calls'],'api_errors':active['errors'],
            'retrieval_queries':active['retrieval_queries'],'events':events,'terminal':terminal,'runner_error':error}
        quota=any(e.get('code')==429 for e in active['errors']) and terminal.get('type')!='done'
        if quota:
            save(HERE/'quota-aborted'/(ident+'-'+began.replace(':','')+'.json'),record)
            if ring.rotate():
                status(phase='quota_key_switched',case=case['id'],repeat=repeat,key=ring.fingerprint)
                pending.insert(0,(case,repeat));continue
            status(phase='quota_stop',case=case['id'],repeat=repeat,api_errors=active['errors']);sys.exit(0)
        save(dest,record)
        if any(e.get('code') in [400,401,403,404] for e in active['errors']):
            status(phase='generation_error_stop',case=case['id'],repeat=repeat,api_errors=active['errors']);sys.exit(1)
    status(phase='generation_complete',completed=len(list(destdir.glob('*.json'))),total=manifest['planned_results'])
finally:
    retrieval.search=original_search;chat.get_client=original_client;engine.dispose()
