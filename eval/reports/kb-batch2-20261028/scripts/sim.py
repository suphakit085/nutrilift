"""In-memory retrieval simulator for knowledge-base batch 1.

Production chunks are read once (read-only transaction) and cached; new or changed cards in CANDIDATE are
chunked with ingest.chunk_card and embedded with the same embed_texts. search() mirrors retrieval.search:
dense cosine order, fetch = top_k * multiplier, domain gate + relative window (score_cutoff), BM25 fusion,
window re-applied, top_k. Nothing is written to the database.
"""
import os,sys,json,hashlib
from pathlib import Path
from types import SimpleNamespace
from dotenv import load_dotenv,dotenv_values
ROOT=Path('C:/Users/porap/orca/workspaces/chat-bot-nutrition/main-3')
HERE=Path(__file__).resolve().parents[1]
CANDIDATE=Path(os.environ.get('CANDIDATE',str(ROOT/'output/ci-cd/kb-batch2')))
load_dotenv(ROOT/'backend/.env',override=False)
_keys=dotenv_values(ROOT/'output/prompt-functional-fixes-20261022/test-api.env')
_kname='GEMINI_API_KEY_'+os.environ.get('EMBED_KEY','2')
os.environ['GEMINI_API_KEY']=_keys[_kname]
_prod=dotenv_values(Path('C:/project_1/chat-bot-nutrition/backend/supabase.env'))
os.environ['DATABASE_URL']=_prod['DATABASE_URL']
sys.path.insert(0,str(CANDIDATE/'backend'))
import numpy as np
import frontmatter
from app.core.config import settings
from app.services import retrieval
from app.services.llm import embed_texts,embed_text
from ingest.__main__ import chunk_card,content_hash,card_paths
CACHE=HERE/'cache';CACHE.mkdir(exist_ok=True)
def sha(s):return hashlib.sha256(s.encode()).hexdigest()

def load_production():
    meta_p=CACHE/'prod-chunks.json';vec_p=CACHE/'prod-vectors.npy'
    if meta_p.exists():return json.loads(meta_p.read_text(encoding='utf8')),np.load(vec_p)
    from sqlalchemy import create_engine,event,select
    from sqlalchemy.orm import Session
    from app.db.models import Chunk,Document
    eng=create_engine(settings.database_url,hide_parameters=True,connect_args={'prepare_threshold':None,'connect_timeout':15})
    @event.listens_for(eng,'begin')
    def ro(conn):conn.exec_driver_sql('SET TRANSACTION READ ONLY')
    rows=[];vecs=[]
    with Session(eng) as db:
        for c,d in db.execute(select(Chunk,Document).join(Document,Chunk.document_id==Document.id).order_by(Document.slug,Chunk.chunk_index)).all():
            rows.append({'chunk_id':str(c.id),'document_id':str(d.id),'slug':d.slug,'title':d.title,'heading':c.heading,'content':c.content,
                         'source_refs':d.source_refs,'content_hash':d.content_hash,'chunk_index':c.chunk_index})
            vecs.append(np.asarray(c.embedding,dtype=np.float32))
    eng.dispose()
    meta_p.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf8');np.save(vec_p,np.stack(vecs))
    return rows,np.stack(vecs)

def card_chunks(include_new=True):
    """Chunks of cards whose content differs from production (new or edited), embedded and cached."""
    rows,_=load_production()
    prod_hash={r['slug']:r['content_hash'] for r in rows}
    out=[]
    for path in card_paths():
        post=frontmatter.load(path);slug=post.get('slug') or path.stem;title=post.get('title') or slug
        if prod_hash.get(slug)==content_hash(post):continue
        if not include_new:continue
        pieces=chunk_card(title,post.content)
        cache=CACHE/f'card-{slug}-{content_hash(post)[:16]}.npy'
        if cache.exists():vecs=np.load(cache)
        else:
            vecs=np.asarray(embed_texts([t for _,t in pieces]),dtype=np.float32);np.save(cache,vecs)
        for i,((heading,text),v) in enumerate(zip(pieces,vecs)):
            out.append(({'chunk_id':f'new-{slug}-{i}','document_id':f'new-{slug}','slug':slug,'title':title,'heading':heading,'content':text,
                         'source_refs':post.get('sources') or [],'content_hash':content_hash(post),'chunk_index':i},v))
    return out,{s for s in prod_hash}

def corpus(include_new=True):
    rows,vecs=load_production()
    extra,_=card_chunks(include_new)
    changed={r['slug'] for r,_ in extra}
    keep=[i for i,r in enumerate(rows) if r['slug'] not in changed]
    # Cards deleted from the candidate checkout would be pruned by ingest; mirror that.
    on_disk={(frontmatter.load(p).get('slug') or p.stem) for p in card_paths()}
    keep=[i for i in keep if rows[i]['slug'] in on_disk] if include_new else keep
    R=[rows[i] for i in keep]+[r for r,_ in extra]
    V=np.concatenate([vecs[keep]]+([np.stack([v for _,v in extra])] if extra else []))
    return R,V

_qcache_p=CACHE/'query-vectors.json'
_qcache=json.loads(_qcache_p.read_text(encoding='utf8')) if _qcache_p.exists() else {}
def query_vector(q):
    k=sha(q)
    if k not in _qcache:
        _qcache[k]=embed_text(q);_qcache_p.write_text(json.dumps(_qcache),encoding='utf8')
    return np.asarray(_qcache[k],dtype=np.float32)

def search(R,V,query,top_k=None):
    k=top_k or settings.retrieval_top_k
    qv=query_vector(query)
    sims=(V@qv)/(np.linalg.norm(V,axis=1)*np.linalg.norm(qv))
    fetch=k*settings.retrieval_candidate_multiplier if settings.retrieval_hybrid else k
    order=np.argsort(-sims,kind='stable')[:fetch]
    scored=[(SimpleNamespace(**{'id':R[i]['chunk_id'],'content':R[i]['content'],'heading':R[i]['heading']}),
             SimpleNamespace(**{'id':R[i]['document_id'],'slug':R[i]['slug'],'title':R[i]['title'],'source_refs':R[i]['source_refs']}),float(sims[i])) for i in order]
    if not scored:return []
    cutoff=retrieval.score_cutoff(scored[0][2],settings.retrieval_min_score,settings.retrieval_relative_window)
    if cutoff is None:return []
    ranked=retrieval._fuse_with_bm25(query,scored) if settings.retrieval_hybrid and len(scored)>1 else scored
    kept=[x for x in ranked if x[2]>=cutoff][:k]
    return [retrieval.Passage(label=f'S{n+1}',score=s,chunk_id=str(c.id),document_id=str(d.id),document_slug=d.slug,title=d.title,
                              heading=c.heading,content=c.content,source_refs=d.source_refs) for n,(c,d,s) in enumerate(kept)]
