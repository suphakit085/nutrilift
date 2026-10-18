# ผลทดสอบ PostgreSQL และระบบบัญชี — 17 ตุลาคม 2026

อัปเดต 18 ต.ค. 2026: ชุด Auth + history ล่าสุดผ่าน 43 กรณี รวม upgrade จาก current production `f16c6106a002` ไป `f16c6106a001` และซ้อม restore สำเนาฐานจริงที่เข้ารหัสลง PostgreSQL 17 แล้ว migrate โดยตรวจ hash/จำนวนข้อมูลเดิมก่อน–หลังตรงกัน ดู [บันทึก release ล่าสุด](auth-release-2026-10-18.md) รายงานต่อไปนี้เก็บผลรอบ 17 ต.ค. ไว้ตามเดิม

ทดสอบกับ **PostgreSQL 16.13 + pgvector** ใน Docker แยกจากฐานข้อมูลจริงแล้ว ผ่าน **27 กรณี**, ไม่มี failure/error/skip ในชุด PostgreSQL และชุด regression ทั่วไปผ่าน **1,561 กรณี** งานโดเมน/Resend ยังพักไว้ ไม่มีอีเมลออกภายนอกและไม่มีการ deploy

## สิ่งที่พิสูจน์ได้ในรอบนี้

| การตรวจ | ผล |
| --- | --- |
| Migration จากฐานว่างถึง `f16c6106a002` | ผ่าน โดยเรียก Alembic จริง ไม่ใช้ `Base.metadata.create_all` สำหรับ PostgreSQL |
| ตรวจ schema เทียบ ORM ด้วย `alembic check` | ผ่าน ไม่พบ migration ที่ขาดจาก metadata ปัจจุบัน |
| อัปเกรดจาก `e43c6103b001` ที่มีบัญชีและโปรไฟล์เดิม | ข้อมูลเดิมอยู่ครบ ไม่ทำเครื่องหมายยืนยันอีเมลหรือสร้างประวัติเป้าหมายย้อนหลังโดยไม่มีหลักฐาน |
| JWT รุ่นเก่า/การยืนยันบัญชีเดิม/ความยินยอม | JWT ที่ไม่มี session ID ถูกปฏิเสธ ต้องยืนยันอีเมลและให้ความยินยอมฉบับปัจจุบันก่อนเข้าถึงโปรไฟล์เดิม |
| วงจรบัญชีเดิม 13 กรณีบน PostgreSQL | ผ่านการสมัคร ยืนยัน/ส่งใหม่ ลิงก์หมดอายุ เปลี่ยน/กู้รหัส ยกเลิก session เปลี่ยนอีเมล ถอนความยินยอม export/delete และเป้าหมายย้อนหลัง |
| ใช้ลิงก์ยืนยัน/รีเซ็ตรหัส/เปลี่ยนอีเมลเดียวกันพร้อมกัน | แต่ละประเภทสำเร็จได้หนึ่งคำขอ อีกคำขอได้ 400 session เก่าถูกยกเลิก |
| Login รออยู่ขณะ reset รหัสผ่าน | หลัง reset commit แล้ว login ด้วยรหัสเก่าได้ 401 ไม่เกิด session ใหม่ที่ใช้รหัสเก่า |
| เปลี่ยนรหัสสองคำขอพร้อมกันด้วยรหัสเก่าเดียวกัน | สำเร็จเพียงหนึ่งคำขอ อีกคำขอตรวจรหัสปัจจุบันไม่ผ่าน |
| Logout-all รอ login ที่กำลังออก session | session ที่เพิ่งออกก่อน logout-all ถูกยกเลิกด้วย ไม่หลุดรอดเพราะยังไม่ commit ตอนเริ่ม logout |
| ส่งลิงก์ใหม่ขณะมีคำขอใช้ลิงก์เก่ารออยู่ | เมื่อ resend commit ก่อน คำขอใช้ลิงก์เก่าได้ 400 ส่วนลิงก์ใหม่ใช้ได้ |
| สร้างโปรไฟล์ครั้งแรกพร้อมกันสองคำขอ | ได้ profile เดียวและ revision ครบสองรายการ ไม่เกิด duplicate key; revision ล่าสุดตรงกับ profile ปัจจุบัน |
| ลบบัญชีด้วย foreign-key cascade จริง | ลบ profile/history/session/action/conversation/messages และบันทึกอาหารของเจ้าของครบ โดยอาหารส่วนกลาง เอกสารความรู้ และผู้ใช้อื่นยังอยู่ |
| Guard ของเครื่องมือทดสอบ | ปฏิเสธ URL ภายนอกและชื่อฐานข้อมูลที่ไม่ลงท้าย `_test` ก่อนเชื่อมต่อ |

การทดสอบคำขอพร้อมกันใช้ connection แยกจริง มี transaction ควบคุมให้รอ row lock และตรวจ `pg_stat_activity.wait_event_type = 'Lock'` ก่อนปล่อย transaction ไม่อาศัยการหน่วงเวลาอย่างเดียวแล้วคาดว่าคำขอชนกัน

Downgrade/upgrade ถูกทดสอบเฉพาะฐานชั่วคราว ข้อมูลบัญชี/โปรไฟล์เดิมยังอยู่ แต่ downgrade ลบตาราง session/token/history และคอลัมน์ใหม่ตามที่ migration กำหนด จึงไม่ใช่คำแนะนำให้ downgrade ฐาน production โดยไม่มีแผนสำรองข้อมูล

## วิธีรันซ้ำ

จากโฟลเดอร์หลักบน Windows ที่ Docker Desktop พร้อมใช้งาน:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/test_accounts_postgres.ps1
```

คำสั่งนี้จะสร้าง container ชื่อสุ่ม ใช้ image `pgvector/pgvector:pg16`, ผูกพอร์ตสุ่มกับ `127.0.0.1`, ใช้ข้อมูลใน tmpfs และสร้าง database ชื่อ `nl_test_<UUID>` แยกสำหรับแต่ละกรณี จากนั้นหยุดและลบ container ที่มี label ตรงกับรอบนั้นเท่านั้น ค่าฐานข้อมูลของ process ทดสอบถูกแทนด้วย URL ชั่วคราวและคืนค่าหลังจบ ไม่แก้ `backend/.env`

หลักฐานรอบที่ตรวจสำเร็จอยู่ในเครื่อง:

- `output/postgres-auth/b5891ca80df94cf1861331fd6c7e5d09/summary.json`
- `output/postgres-auth/b5891ca80df94cf1861331fd6c7e5d09/pytest.xml`
- image ID: `sha256:7d400e340efb42f4d8c9c12c6427adb253f726881a9985d2a471bf0eed824dff`
- `container_removed=true`, `exit_code=0`, PostgreSQL 27 passed ใน 36.52 วินาที

โฟลเดอร์หลักฐานถูก gitignore ไว้ script จะสร้างโฟลเดอร์ใหม่ทุกครั้ง ชื่อ database/รหัสผ่าน/บัญชีในชุดนี้เป็นข้อมูลทดสอบ ไม่ใช้ key ของ Resend/Gemini และไม่ใช้ URL ของ Supabase จริง

รัน regression ทั่วไปจาก `backend/` โดยไม่ต้องเปิด PostgreSQL:

```powershell
.venv/Scripts/python.exe -m pytest tests -m "not postgres" -q -p no:cacheprovider
```

ชุด PostgreSQL มี marker `postgres` หากรัน pytest ปกติโดยไม่ตั้ง `NUTRILIFT_PG_TEST_URL` กรณีที่ต้องใช้ PostgreSQL จะถูก skip; guard บางกรณีรันได้โดยไม่เชื่อมต่อ DB จึงควรใช้ script ข้างต้นเมื่อจะยืนยันผล PostgreSQL

## ขอบเขตของผลและสิ่งที่ยังเหลือ

รอบนี้ไม่พบข้อบกพร่องใหม่ที่ต้องแก้ในโค้ดระบบบัญชี เพิ่มชุดทดสอบ PostgreSQL, แยก fixture ให้รันทดสอบวงจรเดิมได้ทั้ง SQLite/PostgreSQL และเพิ่ม script สำหรับรันซ้ำ ผลนี้ใช้กับ PostgreSQL ในเครื่องทดสอบ ไม่ได้ตรวจการเชื่อมต่อ สิทธิ์ หรือพฤติกรรม transaction pooler ของ Supabase/Railway จริง

ก่อนเปิด auth ใหม่ยังต้องยืนยันโดเมน ตั้งผู้ให้บริการอีเมลและทดสอบการส่งจริง ทดสอบ migration บน staging ที่ใช้ค่าตั้งใกล้ production สำรองข้อมูล production แล้ว deploy frontend/backend และตรวจบนเว็บจริงตาม [เอกสาร rollout](account-security-rollout-2026-10-17.md)

งานอื่นที่ยังไม่ได้ทำในรอบนี้คือ แยกชุดปล่อยแก้บั๊กออกจาก auth, CI/lockfile, shared rate limiter และ durable mail queue การผ่านชุดนี้ไม่เท่ากับยืนยันว่าระบบ production ทุกส่วนพร้อมแล้ว
