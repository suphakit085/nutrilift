# Resend สำหรับอีเมลบัญชี NutriLift

โค้ดรองรับ Resend HTTPS API แล้ว ใช้ `httpx` ที่มีอยู่ใน backend ไม่ต้องติดตั้ง SDK เพิ่มหรือเปลี่ยนระบบบัญชี การเลือกผู้ให้บริการทำด้วย `EMAIL_PROVIDER` และ SMTP เดิมยังใช้กับ local capture ได้

อัปเดต 18 ต.ค. 2026: ผู้ใช้ตั้ง DNS ของ **`nutrilift.xyz`** แล้ว ตรวจ DNS สาธารณะพบ TXT `resend._domainkey` และ CNAME `rsend`/`send` จากนั้นภาพ Resend ของผู้ใช้ยืนยันสถานะ **Verified**, region Tokyo (`ap-northeast-1`) แล้ว ผู้ส่งที่เตรียมใช้คือ `noreply@nutrilift.xyz`; frontend ยังคงใช้ `https://nutrilift-azure.vercel.app` จนกว่าจะตั้ง custom domain ของเว็บแยกต่างหาก

ทดสอบ 18 ต.ค. 2026: key สำหรับส่งที่เก็บนอก Git ใช้ส่งอีเมลยืนยันและกู้รหัสจาก `noreply@nutrilift.xyz` ผ่าน Resend จริงได้ ผู้ใช้ยืนยันว่าทั้งสองฉบับเข้า Inbox และ browser ตรวจลิงก์จริงผ่าน 13/13 จุดบนบัญชีในฐานชั่วคราวแล้ว ผู้ใช้แจ้งว่าใส่ Variables บน Railway ครบ แต่ยังต้องตรวจ runtime หลัง deploy Auth รุ่นใหม่ ดู [บันทึก release](auth-release-2026-10-18.md) ชุด CI ใช้ SMTP capture/HTTP transport จำลองและไม่ส่งอีเมลออกภายนอก

## ยังไม่มีโดเมน: ทดสอบกับอีเมลตัวเองก่อน

Resend อนุญาต `onboarding@resend.dev` สำหรับทดสอบ โดยส่งได้เฉพาะอีเมลที่ผูกกับบัญชี Resend ของคุณ การส่งไปหาผู้ใช้คนอื่นจะถูกปฏิเสธจนกว่าจะยืนยันโดเมนผู้ส่ง ดู [ข้อจำกัดของ resend.dev](https://resend.com/docs/knowledge-base/403-error-resend-dev-domain)

1. เข้า Resend → **API Keys** → สร้าง key สำหรับส่งอีเมล ดู [คู่มือ API keys](https://resend.com/docs/dashboard/api-keys/introduction)
2. เก็บ key ใน `backend/.env` บนเครื่องทดสอบ ห้ามใส่ใน `NEXT_PUBLIC_*`, source code, commit หรือแชต
3. ตั้งค่าสำหรับ **development เท่านั้น**:

```dotenv
ENVIRONMENT=development
EMAIL_PROVIDER=resend
RESEND_API_KEY=<key ที่สร้างใน Resend>
EMAIL_FROM=onboarding@resend.dev
FRONTEND_URL=http://localhost:3000
```

คงค่า DB/JWT/Gemini/CORS ของสภาพแวดล้อมทดสอบไว้ตามเดิม Restart backend แล้วใช้บัญชีทดสอบที่มีอีเมลตรงกับบัญชี Resend ลองสมัคร/ขอลิงก์ยืนยัน/ลืมรหัสผ่าน ตรวจอีเมลที่ได้รับรวมโฟลเดอร์สแปม และเปิดลิงก์ใน frontend ที่กำลังรันอยู่

ตัวแปร `ENVIRONMENT=development` ไม่ได้ปิด production guard บน Railway เพราะตรวจพบ Railway จาก environment ของ host ด้วย โค้ดจึงไม่ยอมเปิด production โดยใช้ sender ทดสอบ `@resend.dev` อย่าข้าม guard เพื่อเปิดรับผู้ใช้ทั่วไปด้วย sender นี้

## มีโดเมนแล้ว: เปิดส่งให้ผู้ใช้ทั่วไป

1. เข้า Resend → **Domains** → เพิ่มโดเมนหรือ subdomain ที่คุณควบคุม DNS ได้
2. เพิ่ม DNS records ตามที่ Resend แสดง และรอ **Verified** ดู [Verified Domains](https://resend.com/docs/dashboard/domains/introduction)
3. ใช้อีเมลผู้ส่งบนโดเมนที่ Verified เช่น `noreply@your-domain.example` ไม่ต้องให้ผู้ใช้ของเว็บมีโดเมน ผู้ใช้ยังรับผ่าน Gmail/Outlook ได้
4. ตั้งที่ **backend Railway → Variables**:

```dotenv
EMAIL_PROVIDER=resend
RESEND_API_KEY=<key จริงของคุณ>
EMAIL_FROM=noreply@your-domain.example
FRONTEND_URL=https://nutrilift-azure.vercel.app
```

เปลี่ยนอีเมลตัวอย่างเป็นโดเมนของคุณเอง ค่า `EMAIL_FROM` เป็นที่อยู่อีเมลอย่างเดียว แอปเติมชื่อ NutriLift ให้แล้ว เมื่อเลือก Resend ค่า `SMTP_*` จะไม่ใช้ในการส่ง ไม่จำเป็นต้องตั้ง SMTP host หรือ password เพิ่ม

โดเมนเว็บไซต์กับโดเมนผู้ส่งไม่จำเป็นต้องตรงกัน เว็บยังอยู่ที่ `nutrilift-azure.vercel.app` ได้ แต่ต้องใช้โดเมนที่คุณควบคุมเพื่อยืนยันอีเมลผู้ส่ง

Railway Free/Trial/Hobby ต้องส่งอีเมลผ่าน HTTPS API เนื่องจากไม่เปิด outbound SMTP ดู [Railway Outbound Networking](https://docs.railway.com/networking/outbound-networking)

ก่อน deploy ต้องผ่านขั้นตอน migration/บัญชีเดิมใน [เอกสาร rollout](account-security-rollout-2026-10-17.md) หลัง deploy ทดสอบกับอีเมลจริงและตรวจ Resend Logs/Emails เพื่อยืนยันการรับส่ง ควรปิด click/open tracking สำหรับอีเมลกู้บัญชีตามตัวอย่างการใช้งานในคู่มือโดเมนของ Resend

## การส่งและข้อจำกัดของ implementation

- ส่ง `POST https://api.resend.com/emails` ด้วย Bearer key, User-Agent และข้อความภาษาไทยแบบ plain text ตาม [Send Email API](https://resend.com/docs/api-reference/emails/send-email)
- ใส่ idempotency key ที่ได้จาก hash ของ action เดิม เพื่อให้การส่ง action เดิมซ้ำไม่สร้างเมลซ้ำภายในช่วงที่ Resend เก็บ key ไม่ใส่โทเคนหรืออีเมลตรง ๆ ใน header นี้
- กำหนด timeout 10 วินาที ไม่ตาม HTTP redirect และไม่สลับไป SMTP อัตโนมัติถ้า API ล้มเหลว
- รับผลสำเร็จเมื่อ provider ส่ง response สำเร็จพร้อม message ID เท่านั้น การตอบรับ API ยังไม่รับรองว่าเมลเข้ากล่องผู้รับ ต้องตรวจการส่งจริง
- เก็บ API key แบบ SecretStr ไม่พิมพ์ body, provider error, อีเมล หรือโทเคนใน error log
- `/auth/email-status` และ `/ready` ตรวจว่ามีค่าตั้งครบ ไม่ได้เรียก Resend เพื่อตรวจ key/โดเมนหรือ quota ทุกครั้ง
- ใช้ background task ภายใน process เช่นเดิม ยังไม่มี durable mail queue หากส่งล้มเหลวให้แก้ config/ตรวจ provider แล้วขอลิงก์ใหม่

เทสต์ใหม่ครอบคลุม payload ของทั้งสามลิงก์ การยืนยันตัวตนกับ API, idempotency, 3xx/401/403/429/503, timeout, response ที่ไม่มี message ID, key หาย และไม่เปิดเผย secret ใน log
