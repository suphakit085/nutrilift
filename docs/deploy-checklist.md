# Deploy checklist

เอกสารนี้เตรียมไว้สำหรับตอน deploy จริง (week 9 ตามไทม์ไลน์ในแผน) — ตรวจสอบกับสถานะ repo จริง ณ 4 ก.ย. 2569
MUST ทั้ง 8 ข้อทำเสร็จในโค้ดแล้ว ยังไม่เคย deploy ที่ไหนเลย ทุกอย่างรันบน docker-compose ในเครื่องเท่านั้น

ต้องมีบัญชี (ฟรี tier พอสำหรับโปรเจกนี้): [Supabase](https://supabase.com), [Render](https://render.com)
หรือ [Railway](https://railway.app), [Vercel](https://vercel.com) — ขั้นตอนที่ต้องล็อกอิน/คลิกในเว็บ
ทำเองได้เท่านั้น (ไม่มี API ให้ Claude ทำแทน)

## 1. Database — Supabase (Postgres + pgvector)

- [ ] สร้างโปรเจกต์ใหม่ใน Supabase (เลือก region ใกล้ผู้ใช้เป้าหมาย เช่น Singapore)
- [ ] เปิด extension `vector` (Database → Extensions → เปิด `vector`) — schema เดิม assume ว่ามี
      อยู่แล้ว (migration แรกสร้าง `CREATE EXTENSION vector` เอง แต่ Supabase อาจต้องเปิดสิทธิ์ก่อน
      ถ้า migration รันไม่ผ่านเพราะ permission ให้เปิดผ่าน dashboard ก่อนแล้วรัน migrate ใหม่)
- [ ] คัดลอก connection string (แบบ **connection pooling / pgbouncer**, port 6543 ไม่ใช่ 5432 โดยตรง
      เพราะ backend จะรันบน serverless/managed host ที่เปิด-ปิด connection บ่อย) มาเป็น `DATABASE_URL`
      รูปแบบ `postgresql+psycopg://...` (ต้องมี `+psycopg` ต่อท้าย `postgresql` ตามที่โค้ดใช้ driver นี้
      อยู่แล้วใน `.env.example`)
- [ ] ไม่ต้องแก้อะไรเรื่อง prepared statement — pooler port 6543 เป็น **transaction mode** ซึ่งเข้ากันไม่ได้กับ
      prepared statement ที่ psycopg3 เปิดให้อัตโนมัติหลัง query เดิมรันครบ 5 ครั้ง (อาการคือ error
      `prepared statement "_pg3_0" does not exist` โผล่หลังใช้งานไปสักพัก ไม่ใช่ตอน deploy — เหมือน flake)
      `app/db/session.py` ปิด `prepare_threshold` ไว้แล้ว และ `alembic/env.py` ใช้ค่าเดียวกัน
      (ล็อกไว้ด้วย `tests/test_db_connect_args.py`)
- [ ] **ยังไม่ต้องรัน migration ที่นี่** — `backend/Dockerfile` รัน `alembic upgrade head` เองตอน boot
      (บรรทัด `CMD` มี `alembic upgrade head && uvicorn ...`) ต่อเมื่อ deploy backend แล้วเท่านั้น
- [ ] หลัง backend deploy และ migrate สำเร็จ (ดูขั้นตอน 2) กลับมารัน ingest จากเครื่องตัวเอง ชี้
      `DATABASE_URL` ไปที่ Supabase ชั่วคราว:
      ```
      cd backend && DATABASE_URL=<supabase-url> .venv/Scripts/python.exe -m ingest
      ```
      (ตรวจว่า `knowledge/cards/*.md` และ `knowledge/foods.csv` ครบก่อนรัน — ปัจจุบัน 26 การ์ด, 339 แถวอาหาร)
      ต้องมี `GEMINI_API_KEY` ใน env ตอนรันด้วย เพราะขั้นนี้เรียก embedding API (~144 chunks = 3 batch calls, ไม่กินโควตาแชท)
- [ ] ตรวจว่า `SELECT count(*) FROM chunks` และ `SELECT count(*) FROM foods` บน Supabase ตรงกับที่รันในเครื่อง

## 2. Backend — Render หรือ Railway

- [ ] สร้าง Web Service ใหม่ ชี้ไปที่ repo นี้ path `backend/` ใช้ `backend/Dockerfile` ที่มีอยู่แล้ว
      (มี `EXPOSE 8000` และอ่าน `${PORT}` จาก env — เข้ากับ Render/Railway ที่ inject `PORT` เองได้เลย
      ไม่ต้องแก้ Dockerfile)
- [ ] ตั้ง environment variables ให้ครบตาม `backend/.env.example` **ยกเว้น**:
  - `DATABASE_URL` → connection string จาก Supabase (ขั้นตอน 1)
  - `JWT_SECRET` → **สร้างใหม่เป็น random string จริง** (`.env.example` ใส่ `change-me-to-a-long-random-string`
    ไว้เป็น placeholder เท่านั้น ห้ามใช้ค่านี้ใน prod) — สร้างด้วย `openssl rand -hex 32` หรือเทียบเท่า
  - `GEMINI_API_KEY` → ใช้ key จริงเดียวกับที่ใช้รัน eval (อยู่ใน `backend/.env` ปัจจุบัน)
  - `ENVIRONMENT=production` (Render ตั้ง env `RENDER` ให้เองอยู่แล้ว แต่ตั้งไว้ให้ชัด)
  - `CORS_ORIGINS` → **ใส่ placeholder ไปก่อน** (เช่น `https://localhost`) เพราะยังไม่รู้ URL ของ Vercel
    จนกว่าจะ deploy frontend เสร็จ (ขั้นตอน 3) — ต้องกลับมาแก้เป็น URL จริงทีหลัง แล้ว redeploy
- [ ] Deploy แล้วดู log ว่า `alembic upgrade head` ผ่าน (ไม่มี error เรื่อง `CREATE EXTENSION vector`
      permission — ถ้ามี กลับไปเปิด extension ผ่าน Supabase dashboard ก่อนแล้ว trigger deploy ใหม่)
- [ ] ทดสอบ `GET /health` (หรือ endpoint สุขภาพที่มี) ผ่าน URL public ของ Render/Railway
- [ ] **สำคัญ**: ตั้งจำนวน worker/instance = **1 เท่านั้น** — `docs/architecture.md` หัวข้อ 7 บันทึกไว้ชัดว่า
      rate limiter เก็บตัวนับใน memory ของโปรเซส ถ้ารันหลาย worker เพดานจริงจะคูณตามจำนวน worker
      (เพดานที่ตั้งใจไว้คือเพดานค่าใช้จ่ายรวม ไม่ใช่แค่กันสแปม จึงพลาดไม่ได้)
- [ ] เช็คว่า free tier ของ Render **sleep เมื่อไม่มีการใช้งาน** (cold start ~30-60 วิ) — ถ้าจะเก็บ SUS
      จากผู้ใช้จริง ควรรู้ล่วงหน้าว่าอาจมีดีเลย์รอบแรก หรือพิจารณาจ่ายเพื่อกันไม่ให้ sleep ช่วงเก็บข้อมูล

## 3. Frontend — Vercel

- [ ] Import repo เข้า Vercel, ตั้ง root directory เป็น `frontend/`
- [ ] ตั้ง env var `NEXT_PUBLIC_API_BASE` = URL ของ backend จากขั้นตอน 2 (ต้องมี `https://` ไม่มี trailing slash
      — ดูรูปแบบใน `frontend/.env.local.example`)
- [ ] Deploy แล้วได้ URL Vercel (เช่น `https://xxx.vercel.app`)
- [ ] **กลับไปที่ backend (ขั้นตอน 2)** แก้ `CORS_ORIGINS` เป็น URL Vercel จริง แล้ว redeploy backend
      (ระบบใช้ Bearer token ผ่าน `Authorization` header เก็บใน `localStorage` ไม่ใช่ cookie จึงไม่มีปัญหา
      SameSite/credentials ข้าม origin แต่ CORS origin ต้องตรงเป๊ะ)

## 4. Smoke test บนของจริง (ตามหัวข้อ 8 ใน `docs/architecture.md`)

- [ ] สมัครบัญชีใหม่ผ่านหน้าเว็บจริง → login → กรอกโปรไฟล์
- [ ] ถามคำถามที่ควรใช้ RAG (เช่น "ครีเอทีนกินยังไง") → ได้คำตอบ streaming พร้อม `[S1]` citations และแผง
      แหล่งอ้างอิงแสดงถูก
- [ ] ถามคำถามที่ควรเรียก `lookup_food` (เช่น "ข้าวสวย 1 ทัพพีให้พลังงานเท่าไหร่") → ตรวจว่ายังเรียกเครื่องมือ
      ถูกต้องบน production (ไม่ใช่แค่ในเครื่อง — เพิ่งแก้บั๊กนี้ไปเมื่อ 2 ก.ย. บน `baseline-v5`)
- [ ] ถามคำถามนอกขอบเขต/เสี่ยง (เช่นเรื่องสเตียรอยด์) → ต้องปฏิเสธถูกต้อง
- [ ] ทดสอบ SSE streaming ผ่าน Vercel → Render จริง (ไม่ใช่ localhost) — เคยมีบั๊ก CRLF frame-splitting
      ที่บันทึกไว้ในสถาปัตยกรรม ควรตรวจว่า reverse proxy ของ Render/Vercel ไม่ buffer/แก้ line ending
      จนพัง SSE parser ฝั่ง frontend อีกรอบ
- [ ] เปิดจากมือถือ/browser อื่นดูว่า layout ไม่พัง (responsive)

## 5. หลัง deploy สำเร็จ

- [ ] บันทึก URL จริง + วันที่ deploy ไว้ใน `docs/architecture.md` (ตามธรรมเนียมที่บันทึกทุกอย่างที่วัดจริง)
- [ ] ส่ง `eval/reports/baseline-v9_expert.csv` ให้ผู้เชี่ยวชาญ/นักกำหนดอาหาร/เทรนเนอร์ให้คะแนน blind
      **ส่งไฟล์นี้ไฟล์เดียว** — `baseline-v9_expert_key.csv` คือไฟล์เฉลยที่แมปคอลัมน์ A/B กลับไปเป็น
      rag/no-RAG ถ้าผู้ให้คะแนนเห็น การ blind จะเสียทันทีและผลที่ได้ใช้อ้างอิงไม่ได้
      (ไฟล์ key ถูก gitignore ไว้แล้ว เก็บไว้ในเครื่องเท่านั้น) — อย่าส่ง `baseline-v7` ซึ่งเป็นชุดเก่า
- [ ] เตรียมแบบสอบถาม SUS + แผนเก็บข้อมูลผู้ใช้จริง 20-30 คน (เวทเทรนนิ่ง) ตามหัวข้อ 4 ข้อ 6 ในแผน — ต้อง
      รอระบบ deploy เสถียรระยะหนึ่งก่อน (คำแนะนำในแผน: 1-2 สัปดาห์)
- [ ] เมื่อรวบรวมผลผู้เชี่ยวชาญ + SUS ครบ ค่อยรัน Wilcoxon signed-rank บนคะแนน**ของผู้เชี่ยวชาญ**
      (ฝั่ง LLM-judge รันไปแล้วบน baseline-v9: 150 คู่ correctness +0.19 p=0.0019)

## ผลตรวจก่อน deploy (4 ก.ย. 2569)

รีวิวโค้ดทั้ง 3 ชั้น (backend infra, frontend, services/safety) ก่อน deploy ครั้งแรก ทุกข้อด้านล่าง
ถูกทำซ้ำให้เห็นก่อนแก้ และมีเทสต์ล็อกไว้ (`tests/test_guardrails_hidden_bugs.py`,
`tests/test_review_regressions.py`, `tests/test_db_connect_args.py`, `frontend/src/lib/api.test.ts`)

**Safety (ต้องรู้ก่อนให้ผู้ใช้จริงลอง)**
- zero-width character (U+200B ฯลฯ ที่ติดมากับข้อความจาก LINE/เว็บ) แทรกกลางคำทำให้ "สเตีย​รอยด์"
  และ "เบา​หวาน" หลุดกฎ PED/MEDICAL — ตอนนี้ `normalize_thai` ตัดอักขระกลุ่ม Cf ทิ้งก่อนจับคู่
- คำถามเรื่อง **ยา/อาการ/ค่าแล็บ** ส่วนใหญ่ไม่เคยติดกฎ deterministic (รายการเดิมเป็นชื่อโรค) —
  เพิ่มยาตามกลุ่ม (ยาคุม ยาแก้ ยาปฏิชีวนะ ...), อาการ (เจ็บหน้าอก หน้ามืด ท้องเสีย ...), ค่าแล็บ
  (น้ำตาลในเลือดสูง ค่าคอเลสเตอรอล) และ phrasing ภาษาอังกฤษ (diabetic, my doctor said)
- **false positive ที่ค้าง 8 เทิร์น**: "anabolic window", "กินยาก", "ราคาของขึ้น", "is arm day"
  (squash แล้วได้ "sarm"), "เล่นเวทมา 8 ปี" → MINOR, "ลดวันละ 500 แคล" → DISORDERED_EATING,
  "ตลอด" → "อด…" — แก้ด้วยรายการ false-friend, ยกเลิก squash สำหรับ pattern ภาษาอังกฤษ,
  regex อายุต้องมีคำว่าอายุ/สรรพนาม, และกฎแคลต่อวันต้องเป็นปริมาณที่ *กิน* ไม่ใช่ที่ *ลด*
- อายุคำนวณจากปีเกิดอย่างเดียว → คนเกิด ธ.ค. 2008 นับเป็น 18 ตั้งแต่ 1 ม.ค. 2026 — เพิ่ม
  `birth_month` (migration `b7d2e41c9f10`, ฟอร์มโปรไฟล์บังคับกรอก) และปัดอายุลงเมื่อยังไม่ถึงเดือนเกิด
- ปี พ.ศ. (2547) เคยได้ 422 ภาษาอังกฤษ → แปลงเป็น ค.ศ. ให้อัตโนมัติ
- แผนอาหาร: ฮาลาลไม่ได้ตัดเลือด/กบ/เขียด; มังสวิรัติเคยได้ **ไข่เต่าตนุ** (แถวจริงในตาราง ASEAN
  หมวดไข่) เป็นโปรตีนมื้อเที่ยง — เพิ่มรายการห้ามแนะนำ
- คาร์บเหลือ ~5 g ที่ BMI สูงโดยไม่มีคำเตือน (โปรตีน/ไขมันคิดต่อน้ำหนักตัวทั้งหมด) — เพิ่มคำเตือนเมื่อ
  คาร์บต่ำกว่า 100 g; ตัวเลขไม่เปลี่ยน
- `lookup_food` หาแถวที่สะกด "นํ้า"/"ดํา" (นิคหิต+สระอา) ไม่เจอ 20/28 แถว — แก้ที่ `foods.csv`
  (47 แถว เปลี่ยนเฉพาะคอลัมน์ `name_th`), ที่ ingest และที่ query; escape `%`/`_` ใน ILIKE

**Backend infra**
- Supabase pooler port 6543 + psycopg3 prepared statement (ดูข้อ 1)
- `JWT_SECRET`/`GEMINI_API_KEY` ไม่มี guard — ตอนนี้ถ้าตรวจพบว่าเป็น production (`ENVIRONMENT=production`
  หรือมี env `RENDER`/`RAILWAY_*`) จะไม่ยอมบูตถ้าค่าเป็น placeholder
- แต่ละแชตที่กำลัง stream ค้าง DB connection 2 ตัวในสถานะ idle-in-transaction จนจบ (วัดจริงบน image):
  FastAPI ≥0.118 ปิด `get_db` หลัง response จบ + session ของ generator ไม่ commit หลัง retrieval —
  แก้ทั้งสองจุด
- limiter auth ต่อ IP 10/15 นาที: นักศึกษาบน Wi-Fi มหาลัยใช้ IP เดียวกันหมด คนที่ 11 จะโดนบล็อก —
  เปลี่ยนเป็น login จำกัดต่ออีเมล + ต่อ IP 60
- exception นอก try ใน generator (เช่น commit ล้ม) ทำ stream ขาดโดยไม่มี `error` event → UI ค้าง
- ข้อความ assistant ว่างเปล่าถูกเก็บแล้ว replay ให้ Gemini → 400 ทุกเทิร์นถัดไปในห้องนั้น
- `ingest --rebuild` ลบข้อมูลก่อน embed → ถ้า 429 กลางทาง production เหลือ 0 chunks
- CORS origin ไม่ normalise trailing slash; `Retry-After` ไม่ถูก expose ข้าม origin

**Frontend**
- กด "แชตใหม่"/ลบห้อง/สลับห้อง ระหว่าง streaming → TypeError ทั้งหน้า (ไม่มี error.tsx) หรือ token
  ของห้อง A ไปต่อท้ายห้อง B — ตอนนี้ abort stream และ ignore callback จาก stream เก่า
- token หมดอายุ (7 วัน) ไม่เคย redirect ไป login; บนมือถือไม่มีปุ่ม logout/แชตใหม่/ประวัติเลย
  (sidebar ซ่อนต่ำกว่า md) — เพิ่ม drawer
- `NEXT_PUBLIC_API_BASE` มี trailing slash → ทุก request 404; ถ้าลืมตั้งตอน build จะ bake localhost
  เงียบ ๆ — ตอนนี้ build fail ทันที
- stream จบโดยไม่มี `done` → ปุ่มส่งค้างตลอด; บันทึกอาหาร save/ลบ ล้มเหลวเงียบ; iOS zoom ตอนโฟกัส input

## ข้อจำกัดที่ควรรู้ก่อนเริ่ม

- เพดาน Gemini free tier (`gemini-3.5-flash-lite` 15 RPM / 500 RPD) ยังใช้ร่วมกันระหว่าง dev, eval,
  และผู้ใช้จริงที่ทดสอบ — ถ้าเก็บ SUS พร้อมกัน 20-30 คนในวันเดียวอาจชนเพดาน ควรกระจายวันทดสอบ
- ข้อมูลผู้ใช้บน Gemini free tier อาจถูกนำไปพัฒนาผลิตภัณฑ์/มีทีมรีวิวอ่านได้ (ต่างจาก paid tier) — ต้องมี
  consent/disclaimer แจ้งผู้ใช้ก่อนเริ่มทดสอบจริง (บันทึกไว้แล้วใน `docs/architecture.md` หัวข้อ 7)
