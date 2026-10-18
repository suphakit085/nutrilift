"""Loopback-only browser UAT: disposable SQLite + an actual SMTP capture server.

Run with backend/.venv/Scripts/python.exe eval/uat_browser/local_accounts.py.
No production database, Gemini calls, credentials, or outbound mail are used.
The test mail endpoint is defined here only, never in the production app.
"""

import asyncio
import os
import re
import sys
import threading
from email import policy
from email.parser import BytesParser
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

# Override even an existing developer .env; this process must stay isolated.
os.environ.update(
    DATABASE_URL="postgresql+psycopg://test:test@127.0.0.1:1/test",
    JWT_SECRET="local-browser-uat-only-never-use-in-production",
    GEMINI_API_KEY="",
    ENVIRONMENT="development",
    EMAIL_PROVIDER="smtp",
    EMAIL_FROM="",
    RESEND_API_KEY="",
    SMTP_HOST="127.0.0.1",
    SMTP_PORT="1026",
    SMTP_FROM_EMAIL="accounts@example.com",
    SMTP_USERNAME="",
    SMTP_PASSWORD="",
    SMTP_STARTTLS="false",
    SMTP_SSL="false",
    FRONTEND_URL="http://127.0.0.1:3026",
    CORS_ORIGINS="http://127.0.0.1:3026",
)

import uvicorn  # noqa: E402
from sqlalchemy import ARRAY, JSON, create_engine, event  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.main as main  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402

MAIL = []


async def capture_smtp(reader, writer):
    """Minimal SMTP transport, bound to loopback and storing mail only in memory."""
    writer.write(b"220 localhost UAT SMTP\r\n")
    await writer.drain()
    try:
        while line := await reader.readline():
            command = line.split(b" ", 1)[0].strip().upper()
            if command in (b"EHLO", b"HELO"):
                writer.write(b"250 localhost\r\n")
            elif command in (b"MAIL", b"RCPT", b"RSET", b"NOOP"):
                writer.write(b"250 OK\r\n")
            elif command == b"DATA":
                writer.write(b"354 End with dot\r\n")
                await writer.drain()
                data = bytearray()
                while (part := await reader.readline()) not in (b".\r\n", b""):
                    data.extend(part[1:] if part.startswith(b"..") else part)
                message = BytesParser(policy=policy.default).parsebytes(bytes(data))
                body = message.get_body(preferencelist=("plain",)).get_content()
                links = re.findall(r"http://127\.0\.0\.1:3026/\S+", body)
                MAIL.append(
                    {"to": str(message["To"]), "subject": str(message["Subject"]), "links": links}
                )
                writer.write(b"250 Captured locally\r\n")
            elif command == b"QUIT":
                writer.write(b"221 Bye\r\n")
                await writer.drain()
                break
            else:
                writer.write(b"502 Unsupported\r\n")
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def serve_mail(ready):
    server = await asyncio.start_server(capture_smtp, "127.0.0.1", 1026)
    ready.set()
    async with server:
        await server.serve_forever()


def run():
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, (ARRAY, JSONB)):
                column.type = column.type.with_variant(JSON(), "sqlite")
    temporary = TemporaryDirectory(prefix="nutrilift-browser-uat-")
    engine = create_engine(
        "sqlite:///" + str(Path(temporary.name) / "accounts.sqlite"),
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    def database():
        with Session(engine) as db:
            yield db

    main.app.dependency_overrides[get_db] = database
    main.engine = engine

    @main.app.get("/__test/mail", include_in_schema=False)
    def captured_mail():
        return MAIL

    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=8026, access_log=False))

    @main.app.post("/__test/shutdown", include_in_schema=False)
    def shutdown():
        server.should_exit = True
        return {"stopping": True}

    ready = threading.Event()
    threading.Thread(target=lambda: asyncio.run(serve_mail(ready)), daemon=True).start()
    if not ready.wait(5):
        raise RuntimeError("Local SMTP capture server did not start")
    try:
        server.run()
    finally:
        engine.dispose()
        temporary.cleanup()


if __name__ == "__main__":
    run()
