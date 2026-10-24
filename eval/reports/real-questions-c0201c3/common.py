# Adapted from output/prompt-functional-fixes-20261022/common.py (same production entry, same read-only DB guard).
import os,sys,json,hashlib,time
from pathlib import Path
from dotenv import load_dotenv,dotenv_values
from sqlalchemy import create_engine,event
from sqlalchemy.orm import sessionmaker

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
CANDIDATE=ROOT/'output/ci-cd/real-questions-test-c0201c3'   # dedicated detached worktree at origin/main c0201c3 (backend = deployed 095b9b6); do not move
load_dotenv(ROOT/'backend/.env',override=False)
test_api=dotenv_values(ROOT/'output/prompt-functional-fixes-20261022/test-api.env')
if test_api.get('GEMINI_API_KEY'):os.environ['GEMINI_API_KEY']=test_api['GEMINI_API_KEY']
prod=dotenv_values(Path('C:/project_1/chat-bot-nutrition/backend/supabase.env'))
if prod.get('DATABASE_URL'):os.environ['DATABASE_URL']=prod['DATABASE_URL']
sys.path.insert(0,str(CANDIDATE/'backend'))
from app.core.config import settings
from app.services import chat,prompts,retrieval,guardrails
from app.services.llm import get_client
from app.services.nutrition import ProfileInput

def digest(value):
    if not isinstance(value,str):value=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(value.encode('utf8')).hexdigest()
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf8')
def read(path):return json.loads(path.read_text(encoding='utf8'))
def database():
    engine=create_engine(settings.database_url,hide_parameters=True,pool_pre_ping=True,connect_args={'prepare_threshold':None,'connect_timeout':12})
    @event.listens_for(engine,'begin')
    def readonly(connection):connection.exec_driver_sql('SET TRANSACTION READ ONLY')
    return engine,sessionmaker(engine,autoflush=False)
import threading
class Pacer:
    def __init__(self,interval):self.interval=interval;self.last=0;self.lock=threading.Lock()
    def wait(self):
        with self.lock:
            remaining=self.interval-(time.monotonic()-self.last)
            if remaining>0:time.sleep(remaining)
            self.last=time.monotonic()
