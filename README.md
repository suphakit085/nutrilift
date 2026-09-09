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

> **ห้ามส่ง `*_expert_key.csv` ให้ผู้ประเมิน** ไฟล์นั้นแมปคอลัมน์ A/B กลับไปเป็น rag/norag
> ส่งให้เมื่อไหร่การ blind ก็จบทันที — gitignore กันไว้แล้ว ส่งเฉพาะ `*_expert.csv`

---

## ตัวแปรสภาพแวดล้อม (`backend/.env`)

| ตัวแปร | ค่าเริ่มต้น | หมายเหตุ |
|---|---|---|
| `GEMINI_API_KEY` | — | **ต้องใส่** (ฟรี, จาก aistudio.google.com) |
| `LLM_MODEL` | `gemini-3.5-flash-lite` | โมเดลที่ใช้ตอบ — เปลี่ยนจาก `gemini-3.5-flash` เมื่อพบว่า free tier ของตัวนั้นจำกัดแค่ 20 requests/วันต่อโปรเจกต์ (ยืนยันจริงจาก error 429 เมื่อ 31 ส.ค. 2569) ตัว lite อยู่คนละ quota bucket และถูกกว่า ~4-5 เท่าถ้าต้องจ่ายเงิน เช็กเพดานปัจจุบันที่ aistudio.google.com/rate-limit |
| `JUDGE_MODEL` | `gemini-3.1-flash-lite` | โมเดลให้คะแนนใน eval (ต้องคนละตัวกับ generator, คนละ quota bucket ด้วย) — เปลี่ยนจาก `gemini-3.6-flash` เพราะตัวนั้นติดเพดาน**แค่ 20 requests/วัน** เจอจริงจาก dashboard ตอนรัน eval (1 ก.ย. 2569) |
| `EMBED_MODEL` / `EMBED_DIM` | `gemini-embedding-001` / `1536` | ถ้าเปลี่ยนโมเดล ต้องแก้ `EMBED_DIM` และ re-index ใหม่ทั้งหมด (`ingest --rebuild`) |
| `DATABASE_URL` | postgres ใน docker | |
| `JWT_SECRET` | — | **ต้องเปลี่ยน** ก่อน deploy |
| `RETRIEVAL_TOP_K` / `RETRIEVAL_MIN_SCORE` | `6` / `0.63` | min_score = ประตูขอบเขต ได้จาก `eval/calibrate_threshold.py` — ต้องรันซ้ำทุกครั้งที่เปลี่ยนโมเดล embedding เพราะสเกลคะแนนไม่เทียบกันข้ามโมเดล ไม่ใช่แค่เมื่อเพิ่มการ์ดเยอะ ๆ |
| `RETRIEVAL_RELATIVE_WINDOW` | `0.10` | เก็บ chunk ที่คะแนนห่างจากตัวที่ดีที่สุดไม่เกินค่านี้ |
| `HISTORY_TURNS` | `8` | จำนวนรอบสนทนาที่ส่งกลับเข้า prompt |
| `RATE_LIMIT_CHAT_PER_HOUR` / `_PER_DAY` | `20` / `60` | จำกัดต่อผู้ใช้ ป้องกันบิล API บาน |
| `RATE_LIMIT_CHAT_GLOBAL_PER_DAY` | `1500` | เพดานรวมทุกผู้ใช้ต่อวัน = เพดานค่าใช้จ่าย |
| `RATE_LIMIT_AUTH_PER_15MIN` | `60` | จำกัดการล็อกอิน/สมัคร ต่อ IP — ตั้งหลวมไว้เพราะห้องสอบ/ห้องเรียนใช้ NAT ร่วมกัน ตัวกันเดารหัสผ่านคือบรรทัดถัดไป |
| `RATE_LIMIT_LOGIN_PER_EMAIL_PER_15MIN` | `10` | จำกัดการล็อกอินต่อ 1 อีเมล = ตัวกันเดารหัสผ่านจริง |
| `CORS_ORIGINS` | `http://localhost:3000` | โดเมนของ frontend คั่นด้วย comma — ต้องแก้ตอน deploy |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` (7 วัน) | อายุ JWT |
| `RETRIEVAL_HYBRID` / `RETRIEVAL_CANDIDATE_MULTIPLIER` | `true` / `3` | ผสมคะแนน vector กับ keyword และจำนวน candidate ที่ดึงมาก่อนจัดอันดับ |

---

## โครงสร้างโปรเจก

```
backend/
  app/core/       config, JWT
  app/db/         SQLAlchemy models + session
  app/api/        auth (+ PDPA consent), profile, foods, food_log, chat (SSE)
                  deps.py = get_current_user / get_consented_user (ด่านความยินยอม)
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
frontend/         Next.js: / (หน้าแรก) /login /consent /profile /chat /log
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
ตอนนี้มีการ์ดความรู้ **26 ใบ** และ `foods.csv` **377/378 แถว**เป็นค่าจริงที่มีรหัสอ้างอิง
(เหลือ 1 แถวเป็นค่าประมาณจากฉลาก ระบบติดธง `estimated` ไว้และไม่หยิบไปใช้ในแผนมื้ออาหาร)

---

## ความยินยอม (PDPA)

ระบบเก็บข้อมูลสุขภาพ (เพศ วันเกิด ส่วนสูง น้ำหนัก เปอร์เซ็นต์ไขมัน) จึงขอความยินยอมแบบชัดแจ้ง

- ตอนสมัครต้องติ๊ก 2 ช่องแยกกัน: อายุ 18+ และยินยอมให้เก็บ/ใช้ข้อมูล
  ทั้งคู่เป็น field ที่ **ไม่มีค่า default** ใน `RegisterRequest` — ถ้า client ไม่ส่งมาเลยจะได้ 422
  ไม่ใช่ผ่านไปเงียบ ๆ
- เมื่อสมัครสำเร็จ ระบบบันทึก `users.consented_at` และ `users.consent_version`
  ใน transaction เดียวกับที่สร้างบัญชี
- route ที่แตะข้อมูลส่วนบุคคลใช้ `get_consented_user` ถ้ายังไม่ยินยอมจะได้ **403 + header
  `X-Consent-Required`** แล้ว frontend พาไปหน้า `/consent` (`/auth/me` กับ `/auth/consent`
  ไม่ติดด่าน ไม่งั้นจะไปหน้ายินยอมไม่ได้)
- ข้อความประกาศอยู่ที่ `frontend/src/components/ConsentNotice.tsx` ที่เดียว ใช้ร่วมกันทั้ง
  หน้าสมัครและหน้า `/consent`

**แก้ข้อความประกาศเมื่อไหร่ ต้องเลื่อน `CONSENT_VERSION` ใน `backend/app/api/schemas.py` ด้วย**
(ปัจจุบัน `2026-09-08`) ไม่งั้นคนที่ยินยอมไปแล้วจะถูกนับว่ายอมรับข้อความที่ไม่เคยเห็น
พอเลื่อนเวอร์ชันแล้ว ระบบจะขอความยินยอมใหม่เฉพาะคนที่ยังค้างเวอร์ชันเก่าโดยอัตโนมัติ

บัญชีที่สมัครก่อนมีฟีเจอร์นี้จะมีค่าเป็น `NULL` และต้องยินยอมก่อนใช้งานต่อ — ตั้งใจไม่เติมย้อนหลัง
เพราะการเติมเท่ากับกุความยินยอมที่ไม่มีใครให้

---

## ข้อจำกัดของระบบ (ต้องระบุในเล่ม)

ระบบนี้ให้ข้อมูลเพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำทางการแพทย์
ไม่วินิจฉัยโรค ไม่ให้ข้อมูลสารต้องห้าม และส่งต่อผู้เชี่ยวชาญเมื่อผู้ใช้มีโรคประจำตัว
ตั้งครรภ์ ให้นมบุตร หรืออายุต่ำกว่า 18 ปี

กฎความปลอดภัยมี 8 ข้อ (`Flag` ใน `guardrails.py`) แต่ **บังคับไม่เท่ากัน** และหน้าเว็บก็แยกให้เห็น:

- **6 ข้อตัดสินในโปรแกรม** โมเดลเปลี่ยนไม่ได้ — โรค/อาการป่วย และสารเร่งกล้ามเนื้อ ตอบด้วย
  ข้อความปฏิเสธสำเร็จรูปโดยไม่เรียกโมเดลเลย, อายุต่ำกว่า 18 ไม่ผ่าน `_validate`,
  นอกขอบเขตปฏิเสธก่อนเรียกโมเดล, น้ำหนักต่ำกว่าเกณฑ์เปลี่ยน cut เป็น maintain,
  และพลังงานต่ำกว่า 1,200 kcal แนบคำเตือน (**ไม่ได้ปรับตัวเลขขึ้นให้**)
- **2 ข้อเป็นคำสั่งใน prompt** (พฤติกรรมการกินผิดปกติ, ตั้งครรภ์/ให้นมบุตร) ถ้อยคำจึงมาจากโมเดล

ยังไม่มีระบบรีเซ็ตรหัสผ่านและปุ่มลบบัญชีด้วยตนเอง — ต้องติดต่อผู้จัดทำ
