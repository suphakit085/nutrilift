"""Generate full answers through the production entry (chat.stream_understood_chat) for one checkout.

Usage: CANDIDATE=<checkout> python generate.py <cases.json> <out-dir> [ids...]
Retrieval and food data come from the production database in READ ONLY transactions; nothing is written.
Profile: the sample profile of the c0201c3 real-question run. Keys from the local test keyring, never printed.
"""
import json
import os
import sys
import time
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

ROOT = Path("C:/Users/porap/orca/workspaces/chat-bot-nutrition/main-3")
CANDIDATE = Path(os.environ["CANDIDATE"])
load_dotenv(ROOT / "backend/.env", override=False)
os.environ["DATABASE_URL"] = dotenv_values(Path("C:/project_1/chat-bot-nutrition/backend/supabase.env"))["DATABASE_URL"]
keys = dotenv_values(ROOT / "output/prompt-functional-fixes-20261022/test-api.env")
os.environ["GEMINI_API_KEY"] = keys["GEMINI_API_KEY_" + os.environ.get("EMBED_KEY", "2")]
sys.path.insert(0, str(CANDIDATE / "backend"))
sys.path.insert(0, str(ROOT / "output/functional-fixes-release-20261022"))
import logging  # noqa: E402

from keyring import KeyRing  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services import chat  # noqa: E402
from app.services.nutrition import ProfileInput  # noqa: E402

logging.disable(logging.CRITICAL)
PROFILE = json.loads((ROOT / "output/real-questions-final-c0201c3/condition.json").read_text(encoding="utf8"))["profile"]
cases = {c["id"]: c for c in json.loads(Path(sys.argv[1]).read_text(encoding="utf8"))}
out = Path(sys.argv[2])
out.mkdir(exist_ok=True)
ids = sys.argv[3:] or list(cases)
ring = KeyRing(int(os.environ.get("KEY_START", "2")))
calls = []


class Models:
    def generate_content_stream(self, **kwargs):
        time.sleep(4)
        calls.append(1)
        yield from ring.client.models.generate_content_stream(**kwargs)


class Client:
    models = Models()


chat.get_client = lambda: Client()
engine = create_engine(settings.database_url, hide_parameters=True, pool_pre_ping=True,
                       connect_args={"prepare_threshold": None, "connect_timeout": 12})


@event.listens_for(engine, "begin")
def read_only(conn):
    conn.exec_driver_sql("SET TRANSACTION READ ONLY")


Sessions = sessionmaker(engine, autoflush=False)
for cid in ids:
    dest = out / f"{cid}.json"
    if dest.exists():
        continue
    case = cases[cid]
    for attempt in range(4):
        calls.clear()
        events, error = [], None
        start = time.monotonic()
        try:
            with Sessions() as db:
                for ev in chat.stream_understood_chat(db, user_message=case["message"], history=case.get("history", []),
                                                      profile=ProfileInput(**PROFILE), use_rag=True,
                                                      model="gemini-3.5-flash-lite"):
                    events.append(ev)
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
        terminal = next((e for e in reversed(events) if e.get("type") in ("done", "error")), {"type": "error"})
        if terminal.get("type") == "done" or attempt == 3:
            break
        if "429" in str(error) or "429" in json.dumps(terminal, default=str):
            ring.rotate()
        time.sleep(15)
    rec = {"id": cid, "question": case["message"], "history": case.get("history", []), "attempts": attempt + 1,
           "seconds": round(time.monotonic() - start, 1), "model_calls": len(calls), "runner_error": error,
           "model": terminal.get("model"), "text": terminal.get("text"),
           "citations": [c.get("title") for c in terminal.get("citations") or []],
           "tools": [t.get("name") for t in terminal.get("tool_calls") or []], "terminal_type": terminal.get("type"),
           "terminal": terminal if terminal.get("type") != "done" else None}
    dest.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str), encoding="utf8")
    print(cid, rec["terminal_type"], rec["model"], rec["seconds"], "s", flush=True)
engine.dispose()
