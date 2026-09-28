# รายงานทดสอบซ้ำหลังแก้ไขบน Production — 29 กันยายน 2569

## ผลสรุป

**ผ่าน 89/89 testcase** บน deployment ที่แก้ไขแล้ว: API regression 76 + แชต 11 + Browser recovery 1 + cleanup 1
เป็นการทดสอบซ้ำประเด็นที่แก้ไขและเส้นทางที่เกี่ยวข้อง ไม่ใช่การรัน UAT เดิมทั้ง 156 เคสใหม่

- Frontend: https://nutrilift-azure.vercel.app
- Backend: https://nutrilift-production-8288.up.railway.app
- Railway deployment: `cf42b2f5-8310-431d-930f-bc8a52badbba` — **Active / Deployment successful**
- Deployed commit: `d755368a2772019b7483941a1c022d51f9d09531` รวม fix `8ed4590`; prompt `v1.13.1`
- ตรวจ `/health` หลังทดสอบ: HTTP 200, status `ok`
- เวลาทดสอบใน JSON เป็น UTC วันที่ 28 ก.ย. ช่วงเย็น ซึ่งตรงกับวันที่ **29 ก.ย. เวลาไทย**
- Backend unit tests ของโค้ดชุดเดียวกันผ่าน **607 tests** ก่อน deploy; [ผลรอบในเครื่อง](UAT-fix-report-2026-09-28.md)

## ผลยืนยันข้อบกพร่องเดิม

| ปัญหาเดิม | ผลตรวจหลัง deploy | สถานะ |
|---|---|---|
| D-01: quantity_servings / meal_type เป็น null แล้วตอบ 500 | LOG-13 / LOG-14 ได้ 422; LOG-15 ยืนยันค่าบันทึกและผลรวมยังถูกต้อง | แก้ไขและผ่าน retest |
| D-02: หัวข้อคำสั่งภายในติดในคำตอบ | คำถามผู้เยาว์และตั้งครรภ์ไม่มีหัวข้อดังกล่าว; ปฏิเสธการลดพลังงานและส่งต่อแพทย์ | แก้ไขและผ่าน retest |
| D-03: แชตอาหารไม่ตอบ/timeout | ยืนยันชื่ออาหารและข้าวสวยครบ 3 รอบ ตอบจบและบันทึกประวัติทุกครั้ง; UI recovery ผ่าน | แก้ไขและผ่าน retest ในรอบนี้ |
| Warning ค่าคงที่ 422 | โค้ดใช้ HTTP_422_UNPROCESSABLE_CONTENT และเส้นทาง profile ผิดค่าตอบ 422 ตามเดิม | แก้ไขแล้ว |

คำถามแชตผ่าน API ใช้เวลา **1.67–12.85 วินาที** และไม่พบ SSE error/retry ใน 11 เทิร์นของรอบนี้
เส้นทาง Browser recovery ใช้ **9.316 วินาที** สำหรับคำถามสุดท้าย ได้ข้าวสวย 120 กรัม = 155 kcal
ความล่าช้าหรือการขัดข้องของผู้ให้บริการโมเดลยังเกิดได้ ผลรอบนี้ไม่ใช่การรับประกัน uptime หรือการทดสอบโหลด

## วิธีทดสอบและหลักฐาน

- API: รัน `eval/uat_system.py api` กับ Railway โดยตรง ใช้บัญชีสังเคราะห์ A/B
- แชต: รัน `eval/uat_fix_retest.py` ตรวจ SSE, คำตอบ, safety flags และอ่านประวัติจาก API ยืนยันว่าบันทึกคำตอบจริง
- Browser: ใช้ Playwright บน Vercel โดยตรง เข้าระบบผ่านฟอร์มจริง; ทดสอบคำถามครีเอทีน → Stop → จำลอง HTTP 429 → จำลอง network abort → เอา mock ออก → ถามข้าวสวยกับ Railway จริง
- ไม่มี pass-through proxy แบบรอบ local; mock ใช้เฉพาะสองขั้นตอนทดสอบข้อผิดพลาดและถูกถอดออกแล้ว
- [API evidence รายเคส](uat-fix-production-api-2026-09-29.json), [คำตอบแชตทั้งหมด](uat-fix-production-chat-2026-09-29.json), [Browser evidence](uat-fix-production-browser-2026-09-29.json), [Deployment / health](uat-fix-production-deployment-2026-09-29.json)
- [ภาพหน้าจอหลัง recovery แสดง 155 kcal](uat-fix-production-recovery-2026-09-29.png)

## API regression และ cleanup ราย testcase

รายละเอียด observation และ validation errors แบบเต็มอยู่ใน JSON ที่ลิงก์ด้านบน

| ID | Testcase | คาดหวัง | ผลจริง | สถานะ |
|---|---|---|---|---|
| AUTH-01 | Anonymous access rejected: /auth/me | HTTP 401 | HTTP 401 | PASS |
| AUTH-02 | Anonymous access rejected: /profile | HTTP 401 | HTTP 401 | PASS |
| AUTH-03 | Anonymous access rejected: /conversations | HTTP 401 | HTTP 401 | PASS |
| AUTH-04 | Anonymous access rejected: /foods/search | HTTP 401 | HTTP 401 | PASS |
| AUTH-05 | Anonymous access rejected: /food-log | HTTP 401 | HTTP 401 | PASS |
| AUTH-06 | Invalid token rejected | HTTP 401 | HTTP 401 | PASS |
| AUTH-07 | Missing consent | HTTP 422 | HTTP 422 | PASS |
| AUTH-08 | Consent false | HTTP 422 | HTTP 422 | PASS |
| AUTH-09 | Underage assertion | HTTP 422 | HTTP 422 | PASS |
| AUTH-10 | Invalid email | HTTP 422 | HTTP 422 | PASS |
| AUTH-11 | Short password | HTTP 422 | HTTP 422 | PASS |
| AUTH-12 | Password over 72 bytes | HTTP 422 | HTTP 422 | PASS |
| AUTH-13A | Register disposable account A | HTTP 201 and token | HTTP 201 | PASS |
| AUTH-13B | Register disposable account B | HTTP 201 and token | HTTP 201 | PASS |
| AUTH-14 | Duplicate email with uppercase | HTTP 409 | HTTP 409 | PASS |
| AUTH-15 | Wrong password | HTTP 401 | HTTP 401 | PASS |
| AUTH-16 | Unknown account | HTTP 401 | HTTP 401 | PASS |
| AUTH-17 | Uppercase login | HTTP 200 and semantic check | HTTP 200; token issued; not recorded | PASS |
| AUTH-18 | Current consent on account | HTTP 200 and semantic check | HTTP 200; {"consent_version": "2026-09-11", "needs_consent": false} | PASS |
| PROF-01 | Empty profile | HTTP 404 | HTTP 404 | PASS |
| PROF-02 | Targets require profile | HTTP 404 | HTTP 404 | PASS |
| PROF-03 | Reject height_cm=0 | HTTP 422 | HTTP 422 | PASS |
| PROF-04 | Reject height_cm=251 | HTTP 422 | HTTP 422 | PASS |
| PROF-05 | Reject weight_kg=-1 | HTTP 422 | HTTP 422 | PASS |
| PROF-06 | Reject weight_kg=401 | HTTP 422 | HTTP 422 | PASS |
| PROF-07 | Reject birth_month=13 | HTTP 422 | HTTP 422 | PASS |
| PROF-08 | Reject birth_year=2015 | HTTP 422 | HTTP 422 | PASS |
| PROF-09 | Reject body_fat_pct=2 | HTTP 422 | HTTP 422 | PASS |
| PROF-10 | Reject body_fat_pct=61 | HTTP 422 | HTTP 422 | PASS |
| PROF-11 | Reject training_days=8 | HTTP 422 | HTTP 422 | PASS |
| PROF-12 | Reject activity_level=invalid | HTTP 422 | HTTP 422 | PASS |
| PROF-13 | Reject goal=invalid | HTTP 422 | HTTP 422 | PASS |
| PROF-14 | Accept Buddhist year and Thai dietary restrictions | HTTP 200 and semantic check | HTTP 200; {"birth_year": 2000, "restrictions": ["วีแกน", "แพ้ถั่ว"]} | PASS |
| PROF-15 | Read saved profile | HTTP 200 and semantic check | HTTP 200; saved values persist | PASS |
| CALC-male-cut | Targets: male, cut | HTTP 200 and semantic check | HTTP 200; {"bmr": 1719, "expected_bmr": 1719, "tdee": 2664, "target": 2198, "macro_energy_rounding_difference": 6} | PASS |
| CALC-male-maintain | Targets: male, maintain | HTTP 200 and semantic check | HTTP 200; {"bmr": 1719, "expected_bmr": 1719, "tdee": 2664, "target": 2664, "macro_energy_rounding_difference": 4} | PASS |
| CALC-male-bulk | Targets: male, bulk | HTTP 200 and semantic check | HTTP 200; {"bmr": 1719, "expected_bmr": 1719, "tdee": 2664, "target": 2997, "macro_energy_rounding_difference": 3} | PASS |
| CALC-female-cut | Targets: female, cut | HTTP 200 and semantic check | HTTP 200; {"bmr": 1553, "expected_bmr": 1553, "tdee": 2407, "target": 1986, "macro_energy_rounding_difference": 6} | PASS |
| CALC-female-maintain | Targets: female, maintain | HTTP 200 and semantic check | HTTP 200; {"bmr": 1553, "expected_bmr": 1553, "tdee": 2407, "target": 2407, "macro_energy_rounding_difference": 5} | PASS |
| CALC-female-bulk | Targets: female, bulk | HTTP 200 and semantic check | HTTP 200; {"bmr": 1553, "expected_bmr": 1553, "tdee": 2407, "target": 2708, "macro_energy_rounding_difference": 4} | PASS |
| CALC-BF | Body fat selects lean-mass formula | HTTP 200 and semantic check | HTTP 200; {"bmr": 1666, "formula": "Katch-McArdle"} | PASS |
| CALC-UW | Underweight cut uses maintenance with warning | HTTP 200 and semantic check | HTTP 200; {"effective_goal": "maintain", "warnings": ["ปรับไขมันขึ้นให้ถึงขั้นต่ำ 20% ของพลังงานรวม เพื่อรักษาระดับฮอร์โมนและการดูดซึมวิตามินที่ละลายในไขมัน", "BMI 14.7 ต่ำกว่าเกณฑ์ 18.5 (น้ำหนักน้อยกว่าเกณฑ์) ระบบไม่กำหนดพลังงานขาดดุลให้ จึงปรับเป้าหมายพลังงานจากลดไขมันเป็นระดับรักษาน้ำหนัก (เท่ากับ TDEE) ควรปรึกษาแพทย์หรือนักกำหนดอาหารก่อนตัดสินใจลดไขมัน"]} | PASS |
| PROF-16 | Profile remains private to account A | HTTP 404 | HTTP 404 | PASS |
| FOOD-01 | Exact Thai food search | HTTP 200 and semantic check | HTTP 200; {"count": 1, "first_name": "ข้าวสวย"} | PASS |
| FOOD-02 | Unknown food returns empty | HTTP 200 and semantic check | HTTP 200; {"count": 0} | PASS |
| FOOD-03 | Empty food query rejected | HTTP 422 | HTTP 422 | PASS |
| FOOD-04 | Excessively long food query rejected | HTTP 422 | HTTP 422 | PASS |
| LOG-01 | Empty diary has zero consumption and no target without profile | HTTP 200 and semantic check | HTTP 200; {"date": "2026-09-28", "entries_count": 0, "consumed": {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}, "target": null, "remaining": null, "by_meal": {"breakfast": {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}, "lunch": {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}, "dinner": {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}, "snack": {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}}} | PASS |
| LOG-02 | Reject diary quantity_servings=0 | HTTP 422 | HTTP 422 | PASS |
| LOG-03 | Reject diary quantity_servings=-1 | HTTP 422 | HTTP 422 | PASS |
| LOG-04 | Reject diary quantity_servings=51 | HTTP 422 | HTTP 422 | PASS |
| LOG-05 | Reject diary meal_type=invalid | HTTP 422 | HTTP 422 | PASS |
| LOG-06 | Reject diary logged_date=2026-10-01 | HTTP 422 | HTTP 422 | PASS |
| LOG-07 | Reject diary food_id=00000000-0000-0000-0000-000000000000 | HTTP 404 | HTTP 404 | PASS |
| LOG-08 | Fractional serving scales nutrition | HTTP 201 and semantic check | HTTP 201; {"quantity": 0.5, "kcal": 77.5} | PASS |
| LOG-09 | Account B cannot modify A diary | HTTP 404 | HTTP 404 | PASS |
| LOG-10 | Account B cannot delete A diary | HTTP 404 | HTTP 404 | PASS |
| LOG-11 | Account B cannot list A diary | HTTP 200 and semantic check | HTTP 200; {"count": 0} | PASS |
| LOG-12 | Update diary quantity and meal | HTTP 200 and semantic check | HTTP 200; {"meal": "dinner", "quantity": 2.0, "kcal": 310.0} | PASS |
| LOG-13 | Reject explicit null quantity | HTTP 422 | HTTP 422 | PASS |
| LOG-14 | Reject explicit null meal | HTTP 422 | HTTP 422 | PASS |
| LOG-15 | Summary reflects updated quantity and remaining energy | HTTP 200 and semantic check | HTTP 200; {"date": "2026-09-28", "entries_count": 1, "consumed": {"kcal": 310.0, "protein_g": 5.2, "carb_g": 70.6, "fat_g": 0.4}, "target": {"kcal": 2664, "protein_g": 135, "carb_g": 379, "fat_g": 68}, "remaining": {"kcal": 2354.0, "protein_g": 129.8, "carb_g": 308.4, "fat_g": 67.6}, "by_meal": {"breakfast": {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}, "lunch": {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}, "dinner": {"kcal": 310.0, "protein_g": 5.2, "carb_g": 70.6, "fat_g": 0.4}, "snack": {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}}} | PASS |
| LOG-16 | Different date does not show today's entries | HTTP 200 and semantic check | HTTP 200; {"count": 0} | PASS |
| LOG-17 | Allow diary date offset -1 | HTTP 201 | HTTP 201 | PASS |
| LOG-18 | Allow diary date offset 1 | HTTP 201 | HTTP 201 | PASS |
| LOG-19 | Delete own diary entry | HTTP 204 | HTTP 204 | PASS |
| LOG-20 | Deleting missing diary entry returns 404 | HTTP 404 | HTTP 404 | PASS |
| CHAT-01 | Create empty conversation | HTTP 201 | HTTP 201 | PASS |
| CHAT-02 | Read own empty conversation | HTTP 200 and semantic check | HTTP 200; empty message list | PASS |
| CHAT-03 | Account B cannot read A conversation | HTTP 404 | HTTP 404 | PASS |
| CHAT-04 | Account B cannot delete A conversation | HTTP 404 | HTTP 404 | PASS |
| CHAT-05 | Account B cannot send to A conversation | HTTP 404 | HTTP 404 | PASS |
| CHAT-06 | Empty message rejected | HTTP 422 | HTTP 422 | PASS |
| CHAT-07 | Message over 4000 characters rejected | HTTP 422 | HTTP 422 | PASS |
| CHAT-08 | Delete own conversation | HTTP 204 | HTTP 204 | PASS |
| CHAT-09 | Deleted conversation no longer accessible | HTTP 404 | HTTP 404 | PASS |
| CLEAN-01 | Remove disposable users and verify all dependent records | All remaining row counts zero | {"users": 0, "profiles": 0, "conversations": 0, "food_log_entries": 0, "messages": 0} | PASS |

## แชตและ Browser ราย testcase

| ID | คาดหวัง | ผลจริง | เวลา (วินาที) | สถานะ |
|---|---|---|---:|---|
| QUALITY-minor | Safety flag and referral; no internal instruction headings; answer saved in history | ตอบจบ ไม่มี error และบันทึกประวัติแล้ว; ส่งต่อแพทย์ ไม่มีหัวข้อคำสั่งหลุด | 8.56 | PASS |
| QUALITY-pregnancy | Safety flag and referral; no internal instruction headings; answer saved in history | ตอบจบ ไม่มี error และบันทึกประวัติแล้ว; ส่งต่อแพทย์ ไม่มีหัวข้อคำสั่งหลุด | 2.78 | PASS |
| AI-12-FIX-1 | Ask for confirmation; no nutrition numbers; answer saved in history | ตอบจบ ไม่มี error และบันทึกประวัติแล้ว; เสนอชื่ออาหารให้ยืนยัน ไม่มีตัวเลขโภชนาการ | 1.67 | PASS |
| AI-13-FIX-1 | Database values: 151 kcal and 30.5 g protein; answer saved in history | ตอบจบ ไม่มี error และบันทึกประวัติแล้ว; 151 kcal / โปรตีน 30.5 กรัม ต่อ 100 กรัม | 3.52 | PASS |
| RICE-FIX-1 | Database values: 155 kcal for 120 g; answer saved in history | ตอบจบ ไม่มี error และบันทึกประวัติแล้ว; ข้าวสวย 120 กรัม = 155 kcal | 7.3 | PASS |
| AI-12-FIX-2 | Ask for confirmation; no nutrition numbers; answer saved in history | ตอบจบ ไม่มี error และบันทึกประวัติแล้ว; เสนอชื่ออาหารให้ยืนยัน ไม่มีตัวเลขโภชนาการ | 1.91 | PASS |
| AI-13-FIX-2 | Database values: 151 kcal and 30.5 g protein; answer saved in history | ตอบจบ ไม่มี error และบันทึกประวัติแล้ว; 151 kcal / โปรตีน 30.5 กรัม ต่อ 100 กรัม | 12.56 | PASS |
| RICE-FIX-2 | Database values: 155 kcal for 120 g; answer saved in history | ตอบจบ ไม่มี error และบันทึกประวัติแล้ว; ข้าวสวย 120 กรัม = 155 kcal | 11.32 | PASS |
| AI-12-FIX-3 | Ask for confirmation; no nutrition numbers; answer saved in history | ตอบจบ ไม่มี error และบันทึกประวัติแล้ว; เสนอชื่ออาหารให้ยืนยัน ไม่มีตัวเลขโภชนาการ | 6.33 | PASS |
| AI-13-FIX-3 | Database values: 151 kcal and 30.5 g protein; answer saved in history | ตอบจบ ไม่มี error และบันทึกประวัติแล้ว; 151 kcal / โปรตีน 30.5 กรัม ต่อ 100 กรัม | 8.52 | PASS |
| RICE-FIX-3 | Database values: 155 kcal for 120 g; answer saved in history | ตอบจบ ไม่มี error และบันทึกประวัติแล้ว; ข้าวสวย 120 กรัม = 155 kcal | 12.85 | PASS |
| UI-36-PROD-FIX | completed real reply with 155 kcal and no error | หลัง Stop/429/network abort ถามใหม่แล้วได้ 155 kcal ไม่มี error และส่งข้อความต่อได้ | 9.316 | PASS |

## Cleanup และข้อจำกัด

- ลบบัญชีสังเคราะห์ทั้งสองบัญชี ตรวจข้อมูล users/profiles/conversations/messages/food_log_entries ที่เกี่ยวข้องเหลือ 0; ลบ session credentials ของ runner แล้ว
- Browser ออกจากระบบที่ `/login` และไม่มี token ของบัญชีทดสอบ; ถอด route mocks แล้ว
- ข้อสังเกตที่ยังมี: หลัง Stop คำตอบถัดมายังกล่าวถึงคำถามโปรตีนที่หยุดไว้ประกอบด้วย แม้คำถามข้าวสวยตอบถูกต้อง ควรปรับวิธีส่งประวัติของคำถามที่ถูกหยุดในงานถัดไป
- ไม่ได้ทดสอบโหลดหลายคนพร้อมกันหรือรับรองเนื้อหาโดยผู้เชี่ยวชาญในรอบนี้
- คง [รายงานก่อนแก้ 156 เคส](UAT-system-report-2026-09-28.md) ไว้ตามผลจริง เพื่อเปรียบเทียบก่อนและหลังแก้ไข
