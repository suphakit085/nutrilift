# ระบบบัญชีและการแก้ข้อบกพร่อง — 17 ตุลาคม 2026

อัปเดต 18 ต.ค. 2026: โดเมน Verified และทดสอบ Resend จริงเข้ากล่อง Inbox ทั้งยืนยัน/กู้รหัสแล้ว แยก candidate บน main รุ่นล่าสุด ชุด backend 1,252, frontend 93, PostgreSQL 43 และ account browser 26 checks ผ่าน พร้อมสำรอง public schema/data แบบเข้ารหัสและซ้อม restore + migration บน PostgreSQL 17 โดยข้อมูลเดิมไม่เปลี่ยน ดูสถานะปัจจุบันและข้อกำหนด deployment ใน [บันทึก release ล่าสุด](auth-release-2026-10-18.md) รายละเอียด/ตัวเลขด้านล่างเป็นหลักฐานรอบก่อนหน้า

สถานะ: ทำและทดสอบใน workspace แล้ว ยังไม่ได้ deploy ไป Railway/Vercel และยังไม่ได้ส่งอีเมลผ่านผู้ให้บริการจริง

อัปเดตการตรวจ PostgreSQL: ชุด migration/วงจรบัญชี/concurrency ผ่านบน PostgreSQL 16.13 + pgvector จริง **27 กรณี** ในฐานชั่วคราวแล้ว ดู [รายงาน PostgreSQL](postgres-auth-validation-2026-10-17.md) ผล SQLite/offline SQL ด้านล่างเป็นหลักฐานรอบก่อนหน้า ไม่ใช่ข้อจำกัดล่าสุดของการทดสอบในเครื่อง

## สิ่งที่เปลี่ยน

| ประเด็นจาก audit | การแก้ในรอบนี้ |
| --- | --- |
| A01 ยืนยันอีเมล | สมัครได้เฉพาะบัญชีรอยืนยัน API ปิดโปรไฟล์/แชต/อาหารจนยืนยัน เจ้าของอีเมลตั้งรหัสผ่านจากลิงก์และยกเลิก session ก่อนยืนยันทั้งหมด เพื่อป้องกันคนอื่นสมัครอีเมลไว้ล่วงหน้า |
| A02 รหัสผ่าน | หน้าเปลี่ยนรหัส ลืมรหัส และตั้งรหัสใหม่ ลิงก์สุ่มใช้ครั้งเดียว มีอายุ เก็บเฉพาะ SHA-256 ใน DB ส่งใหม่จะยกเลิกลิงก์เดิม มี rate limit และยกเลิก session เดิมหลังเปลี่ยนรหัส |
| A03 Logout | JWT ต้องมี session ที่ยังใช้งานได้ใน DB ออกจากระบบเครื่องนี้/ทุกเครื่อง หรือยกเลิก session อื่นได้ที่เซิร์ฟเวอร์ |
| A04 บัญชีและสิทธิข้อมูล | `/account` เปลี่ยนอีเมลโดยตรวจรหัสและยืนยันกล่องใหม่ ดาวน์โหลด JSON ของตน ถอนความยินยอม และลบบัญชีพร้อมข้อมูลส่วนบุคคลผ่าน foreign-key cascade |
| D01–D03 บันทึกอาหาร | กันคำตอบของวันเก่าหรือคำค้นเก่าทับรายการล่าสุด แยกข้อผิดพลาดการค้นหาออกจากผลค้นหาว่าง และมีปุ่มลองใหม่ |
| D04 เป้าหมายย้อนหลัง | เก็บ revision ของโปรไฟล์และเป้าหมายเมื่อบันทึก เลือก revision ตามวันกรุงเทพฯ วันที่เก่าก่อนเริ่มเก็บประวัติจะแจ้งว่าไม่มีเป้าหมายย้อนหลัง แทนการนำโปรไฟล์ปัจจุบันไปคำนวณแทน |
| O01 ความพร้อมบริการ | `/health` เป็น liveness และ `/ready` ตรวจการเชื่อมต่อ DB/ข้อมูลความรู้และอาหาร/การตั้งค่าอีเมล DB ขัดข้องตอบ 503 พร้อม CORS และ Retry-After โดยไม่ส่งรายละเอียดการเชื่อมต่อให้ผู้ใช้ |
| R01 Retrieval ล่ม | แสดงคำเตือนเมื่อใช้คำตอบทั่วไปหลังค้นฐานความรู้ไม่สำเร็จ เก็บสถานะกับข้อความเพื่อให้เปิดประวัติแล้วยังเห็นคำเตือน |
| Q01 ผลประเมิน | หน้าแรกระบุว่าเป็นคะแนนจาก Gemini ของชุดทดสอบ 14 ก.ย. 2026 ไม่ใช่คะแนนสดของโค้ดปัจจุบัน และผู้ให้คะแนนไม่ได้เห็นเอกสารต้นทาง |

Supabase ยังเป็นฐานข้อมูล PostgreSQL ระบบบัญชียังคงเป็น FastAPI + bcrypt + JWT ของโปรเจกต์ ไม่ได้เปลี่ยนเป็น Supabase Auth ดังนั้นการเปิด email confirmation ใน Supabase Dashboard อย่างเดียวไม่ทำให้ระบบนี้ส่งอีเมล

## ตั้งค่าอีเมลก่อน deploy

อัปเดต: รองรับ **Resend HTTPS API** แล้ว สำหรับ Railway Free/Trial/Hobby ให้ใช้วิธีนี้ตาม [คู่มือ Resend](resend-setup.md) ค่า `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, `EMAIL_FROM` และ `FRONTEND_URL` แทนการตั้ง SMTP ก่อนเปิดรับผู้ใช้จริงต้องยืนยันโดเมนผู้ส่งด้วย

ตัวอย่าง SMTP ด้านล่างใช้กับเครื่องทดสอบหรือ host/แพ็กเกจที่เปิด outbound SMTP เท่านั้น ตาม [ข้อจำกัด Railway](https://docs.railway.com/networking/outbound-networking)

ตั้งที่ environment ของ **backend** โดยใช้ค่าจริงจากผู้ให้บริการ SMTP:

```dotenv
FRONTEND_URL=https://nutrilift-azure.vercel.app
EMAIL_PROVIDER=smtp
SMTP_HOST=<SMTP host>
SMTP_PORT=587
SMTP_USERNAME=<SMTP username>
SMTP_PASSWORD=<SMTP password>
SMTP_FROM_EMAIL=<sender address ที่ผู้ให้บริการอนุญาต>
SMTP_STARTTLS=true
SMTP_SSL=false
EMAIL_VERIFICATION_EXPIRE_MINUTES=60
PASSWORD_RESET_EXPIRE_MINUTES=30
```

ถ้าใช้ implicit TLS ที่พอร์ต 465 ให้ตั้ง `SMTP_SSL=true` และ `SMTP_STARTTLS=false` เลือกอย่างใดอย่างหนึ่ง เก็บรหัสและ API key ใน environment ของ host เท่านั้น ตัวอย่างทั้งหมดอยู่ใน `backend/.env.example`

`CORS_ORIGINS` ต้องมี origin ของ frontend และ `NEXT_PUBLIC_API_BASE` ของ frontend ต้องเป็น URL backend ตัวเดิม ตรวจด้วยว่าผู้ให้บริการอนุญาต sender นี้และอีเมลถึงกล่องจริง/สแปมได้

production จะไม่เริ่มบริการหากตั้งผู้ให้บริการที่เลือกไม่ครบ หรือใช้ FRONTEND_URL ที่ไม่ใช่ HTTPS สำหรับ SMTP ต้องเปิด TLS อย่างใดอย่างหนึ่ง สำหรับ Resend จะไม่ยอมใช้ sender ทดสอบ `@resend.dev` บน production `/auth/email-status` บอกเพียงว่าตั้งค่าอีเมลแล้ว ไม่ได้ยืนยันว่าผู้ให้บริการรับส่งสำเร็จ และ `/ready` ไม่เรียกบริการส่งอีเมล/Gemini ทุกครั้งที่ probe

อีเมลส่งด้วย background task ภายใน process ถ้า SMTP ส่งไม่สำเร็จจะบันทึก error ที่ไม่มีอีเมล/โทเคนและให้ผู้ใช้ขอลิงก์ใหม่ ยังไม่มี durable outbox หรือระบบส่งซ้ำข้ามการ restart

## Migration และผลต่อบัญชีเดิม

เพิ่ม migration สองตัวต่อจาก `e43c6103b001`:

1. `f16c6106a002`: `profile_revisions` และดัชนีสำหรับเลือกเป้าหมายตามวัน แยกให้ปล่อยก่อนงาน Auth ได้
2. `f16c6106a001`: `users.email_verified_at`, `users.consent_withdrawn_at`, `auth_sessions`, `auth_action_tokens` ต่อจาก history migration ข้างต้น

คำสั่งจาก `backend/`:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
```

Dockerfile เดิมเรียก `alembic upgrade head` ก่อนเริ่ม API อยู่แล้ว ต้องตั้งผู้ให้บริการส่งอีเมลให้ครบก่อนนำ image ใหม่ขึ้นบริการ

บัญชีเดิมยังอยู่ แต่ไม่มีบัญชีใดถูกทำเครื่องหมายว่ายืนยันอีเมลโดยไม่มีหลักฐาน JWT เดิมที่ไม่มี session ID ใช้ต่อไม่ได้ ผู้ใช้ต้อง login อีกครั้งและเปิดลิงก์ยืนยันเพื่อตั้งรหัสผ่าน หากลืมรหัสสามารถใช้หน้าลืมรหัสผ่านได้ หลังพิสูจน์สิทธิ์อีเมลแล้วต้องอ่านความยินยอมฉบับ `2026-10-17` ก่อนใช้ข้อมูลส่วนบุคคล

ประวัติเป้าหมายเริ่มจากการบันทึกโปรไฟล์หลังอัปเดต ไม่สร้างค่าทางประวัติศาสตร์ที่ระบบเดิมไม่เคยเก็บ การบันทึกหลายครั้งในวันเดียวกันใช้รายการล่าสุดของวันนั้นสำหรับยอดรายวัน

## การตรวจในเครื่อง

- Backend ชุดเต็ม: **1,540 passed** รวมวงจรบัญชีผ่าน HTTP/SQLite พร้อม foreign keys, แยกสิทธิ์ผู้ใช้, ลิงก์หมดอายุ/ใช้ซ้ำ/ผิดประเภท, การจำกัดการลองรหัสผ่าน และความพร้อม/CORS เมื่อ DB ขัดข้อง
- Frontend: **76 passed** รวมการส่งสถานะ retrieval ขัดข้องผ่าน SSE; lint, TypeScript และ production build ผ่าน
- Playwright ใช้ frontend/API ใน loopback และ SMTP capture server ที่รับ MIME ผ่าน SMTP จริง ไม่มีอีเมลออกภายนอกหรือข้อมูล production ถูกเขียน
- ผ่านหน้าสมัคร/ยืนยัน/เปลี่ยนรหัส/กู้รหัส/เปลี่ยนอีเมล/ดาวน์โหลด/ถอนความยินยอม/ลบ และตรวจหน้าบัญชีขนาด 390px
- ผ่านกรณีเปิดลิงก์ยืนยันบัญชี B ขณะมี session ของบัญชี A อยู่ หน้าจอใช้สิทธิ์จากลิงก์ที่เปิด และ session ของ A ไม่ถูกยกเลิกจากการยืนยันบัญชี B
- ผ่านประวัติโปรไฟล์หลังบันทึกสองครั้งและ reload, บั๊กวัน/คำค้นแข่งกันทั้งสามกรณี และคำเตือน retrieval ทั้งตอน streaming และเปิดประวัติ
- Alembic สร้าง SQL ของสอง migration สำหรับ PostgreSQL แบบ offline ได้ ยังไม่ได้ execute migration หรือพิสูจน์ concurrency ของ row lock บน PostgreSQL จริง

หลักฐานในเครื่อง: `output/playwright/accounts-20261017/results.json` และภาพในโฟลเดอร์เดียวกัน โฟลเดอร์นี้ถูก gitignore ไว้ ไม่มีโทเคนหรือรหัสจริงในรายงาน

คำสั่งทดสอบ backend ให้ใช้ Python ของโปรเจกต์ ไม่ใช่ Python global ที่อาจมี FastAPI คนละเวอร์ชัน:

```powershell
cd backend
.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider
```

ทดสอบ browser ซ้ำด้วย backend ชั่วคราวที่ผูกเฉพาะ loopback:

```powershell
backend/.venv/Scripts/python.exe eval/uat_browser/local_accounts.py
```

เปิดอีก terminal จาก `frontend/`:

```powershell
$env:NEXT_PUBLIC_API_BASE='http://127.0.0.1:8026'
npm.cmd run dev -- --hostname 127.0.0.1 --port 3026
```

harness ใช้ SQLite ใน temporary directory และ SMTP พอร์ต 1026 มี `/__test/mail` เพื่ออ่านลิงก์เฉพาะการทดสอบ เส้นทางนี้ถูกสร้างใน harness เท่านั้น ไม่ได้อยู่ใน production app ห้ามนำ harness ขึ้น host

## ก่อนเปิดใช้จริงและงานที่ยังเหลือ

1. ตั้ง Resend API หรือ SMTP ตามที่ host รองรับ และยืนยันการส่งกับผู้ให้บริการจริง รวมกล่องสแปมและลิงก์ที่ชี้ frontend ถูกต้อง
2. สำรองฐานข้อมูล ทดสอบ migrations กับ PostgreSQL staging และตรวจ session/token replay แบบพร้อมกัน ก่อนรันกับ production
3. นำ backend/frontend ที่เข้าคู่กันขึ้นบริการ แล้วทดสอบบัญชีทดสอบใน staging/production ตามที่อนุญาต ทั้งยืนยัน ส่งใหม่ กู้รหัส เปลี่ยนอีเมล และ logout
4. ใช้ `/health` สำหรับตรวจว่า process อยู่ และ `/ready` สำหรับตรวจ dependency; การตอบ 200 ของ health อย่างเดียวไม่ได้แปลว่า login ใช้ได้

CI/lockfile และชุด PostgreSQL ใน pipeline เตรียมและทดสอบในเครื่องแล้ว ดู [ci-cd.md](ci-cd.md) แต่ยังต้อง push และยืนยัน run บน GitHub รวมถึงตั้งค่า staging ก่อนเปิด CD ส่วน O02 (rate limiter ใช้หน่วยความจำ process), Q02 (ผู้ตรวจอิสระ/ผู้เชี่ยวชาญและ SUS) และ durable mail retry ยังเหลือ งานรอบนี้ไม่อ้างว่าเว็บ production อัปเดตหรือระบบทุกส่วนผ่านการรับรองแล้ว
