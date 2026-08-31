# NutriLift — แชตบอทแนะนำโภชนาการสำหรับเวทเทรนนิ่ง

โปรเจกจบ: แชตบอทภาษาไทยที่ตอบคำถามโภชนาการสำหรับผู้ฝึกเวทเทรนนิ่ง
โดย **อ้างอิงฐานความรู้ที่คัดมา (RAG)** และ **คำนวณพลังงาน/สารอาหารด้วยโค้ด ไม่ใช่ด้วย LLM**

- **ความคืบหน้าและงานที่เหลือ → [`TASKS.md`](TASKS.md)**
- สถาปัตยกรรมและเหตุผลเชิงออกแบบ → [`docs/architecture.md`](docs/architecture.md)
- งานที่เกี่ยวข้อง / แชตบอทแนวเดียวกันใช้ข้อมูลจากไหน → [`docs/related-work.md`](docs/related-work.md)
- ฐานความรู้และวิธีเพิ่มการ์ด → [`knowledge/README.md`](knowledge/README.md)
- บรรณานุกรม/เช็กลิสต์เอกสาร → [`knowledge/SOURCES.md`](knowledge/SOURCES.md)

---

## เริ่มใช้งาน (ครั้งแรก)

ต้องมี: Python 3.11+, Node.js 20+, Docker Desktop

### 1. ฐานข้อมูล

```bash
docker compose up -d
```

Postgres 16 + pgvector จะขึ้นที่ `localhost:5432` (user/pass/db = `nutrition`)

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"     # Windows
# source .venv/bin/activate && pip install -e ".[dev]"  # macOS / Linux

cp .env.example .env        # แล้วใส่ GEMINI_API_KEY กับ JWT_SECRET ของจริง
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

เปิด http://localhost:8000/docs เพื่อดู API

### 3. นำความรู้เข้าฐานข้อมูล

```bash
cd backend
.venv/Scripts/python.exe -m ingest          # embed การ์ดที่เปลี่ยน + โหลด foods.csv
.venv/Scripts/python.exe -m ingest --rebuild  # embed ใหม่ทั้งหมด
```

### 4. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # ชี้ NEXT_PUBLIC_API_BASE ไปที่ backend
npm run dev                        # http://localhost:3000
```

---

## คำสั่งที่ใช้บ่อย

| งาน | คำสั่ง (รันจาก `backend/`) |
|---|---|
| รันเทส | `.venv/Scripts/python.exe -m pytest -q` |
| ตรวจ lint | `.venv/Scripts/ruff.exe check .` |
| สร้าง migration ใหม่ | `.venv/Scripts/alembic.exe revision --autogenerate -m "..."` |
| เช็กว่า model กับ DB ตรงกัน | `.venv/Scripts/alembic.exe check` |
| นำความรู้เข้า | `.venv/Scripts/python.exe -m ingest` |
| รันเทส frontend | `npm test` (จาก `frontend/`) |

รันการประเมิน (จาก root ของ repo):

```bash
backend/.venv/Scripts/python.exe eval/run_eval.py --mode both --judge
```

ปรับ threshold ของ retrieval ให้เข้ากับฐานความรู้ปัจจุบัน:

```bash
backend/.venv/Scripts/python.exe eval/calibrate_threshold.py --verbose
```

ผลลัพธ์อยู่ใน `eval/reports/` — `*_answers.csv`, `*_summary.md`, `*_expert.csv` (แบบ blinded)

---

## ตัวแปรสภาพแวดล้อม (`backend/.env`)

| ตัวแปร | ค่าเริ่มต้น | หมายเหตุ |
|---|---|---|
| `GEMINI_API_KEY` | — | **ต้องใส่** (ฟรี, จาก aistudio.google.com) |
| `LLM_MODEL` | `gemini-3.5-flash` | โมเดลที่ใช้ตอบ — **free tier จำกัด 20 requests/วันต่อโปรเจกต์** (ยืนยันจริงจาก error 429 เมื่อ 31 ส.ค. 2569) เช็กเพดานปัจจุบันที่ aistudio.google.com/rate-limit |
| `JUDGE_MODEL` | `gemini-3.6-flash` | โมเดลให้คะแนนใน eval (ต้องคนละตัวกับ generator, คนละ quota bucket ด้วย) |
| `EMBED_MODEL` / `EMBED_DIM` | `gemini-embedding-001` / `1536` | ถ้าเปลี่ยนโมเดล ต้องแก้ `EMBED_DIM` และ re-index ใหม่ทั้งหมด (`ingest --rebuild`) |
| `DATABASE_URL` | postgres ใน docker | |
| `JWT_SECRET` | — | **ต้องเปลี่ยน** ก่อน deploy |
| `RETRIEVAL_TOP_K` / `RETRIEVAL_MIN_SCORE` | `6` / `0.63` | min_score = ประตูขอบเขต ได้จาก `eval/calibrate_threshold.py` — ต้องรันซ้ำทุกครั้งที่เปลี่ยนโมเดล embedding เพราะสเกลคะแนนไม่เทียบกันข้ามโมเดล ไม่ใช่แค่เมื่อเพิ่มการ์ดเยอะ ๆ |
| `RETRIEVAL_RELATIVE_WINDOW` | `0.10` | เก็บ chunk ที่คะแนนห่างจากตัวที่ดีที่สุดไม่เกินค่านี้ |
| `HISTORY_TURNS` | `8` | จำนวนรอบสนทนาที่ส่งกลับเข้า prompt |
| `RATE_LIMIT_CHAT_PER_HOUR` / `_PER_DAY` | `20` / `60` | จำกัดต่อผู้ใช้ ป้องกันบิล API บาน |
| `RATE_LIMIT_CHAT_GLOBAL_PER_DAY` | `1500` | เพดานรวมทุกผู้ใช้ต่อวัน = เพดานค่าใช้จ่าย |
| `RATE_LIMIT_AUTH_PER_15MIN` | `10` | จำกัดการล็อกอิน/สมัคร ต่อ IP |

---

## โครงสร้างโปรเจก

```
backend/
  app/core/       config, JWT
  app/db/         SQLAlchemy models + session
  app/api/        auth, profile, conversations, chat (SSE)
  app/services/
    nutrition.py  BMR/TDEE/มาโคร (pure functions + unit tests)  ← ตัวเลขทั้งหมดมาจากที่นี่
    foods.py      lookup_food
    retrieval.py  embed + pgvector search
    guardrails.py กฎความปลอดภัย (ไม่ใช้ LLM)
    prompts.py    system prompt ภาษาไทย + PROMPT_VERSION
    chat.py       orchestrator: retrieve → prompt → tool loop → stream
  ingest/         CLI นำการ์ดความรู้ + foods.csv เข้า DB
  alembic/        migrations
  tests/          pytest
frontend/         Next.js: /login /profile /chat
knowledge/        การ์ดความรู้ (.md), foods.csv, SOURCES.md
eval/             ชุดคำถาม + harness ประเมิน RAG vs no-RAG
docs/             architecture.md
```

---

## สถานะปัจจุบัน

ดูรายการงานและความคืบหน้าแบบละเอียดที่ [`TASKS.md`](TASKS.md)

สรุปสั้น: ระบบย้ายจาก OpenAI ไป **Gemini free tier** แล้ว (ทดสอบ end-to-end กับ Gemini จริง
31 ส.ค. 2569 — RAG พร้อมอ้างอิง, tool calling, ปฏิเสธนอกขอบเขต, safety flag ผ่านหมด)
เหตุผลของการย้าย งบ/ความเป็นส่วนตัว/เพดาน request ที่ตรวจพบจริง ดู
[`docs/architecture.md`](docs/architecture.md#gemini-free-tier)
งานที่เหลือส่วนใหญ่เป็นการเขียนเนื้อหา — การ์ดความรู้ 12 ใบ และ `foods.csv` 312/339 แถวเป็นค่าจริงแล้ว

---

## ข้อจำกัดของระบบ (ต้องระบุในเล่ม)

ระบบนี้ให้ข้อมูลเพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำทางการแพทย์
ไม่วินิจฉัยโรค ไม่ให้ข้อมูลสารต้องห้าม และส่งต่อผู้เชี่ยวชาญเมื่อผู้ใช้มีโรคประจำตัว
ตั้งครรภ์ ให้นมบุตร หรืออายุต่ำกว่า 18 ปี
