# แหล่งอ้างอิงของฐานความรู้

บรรณานุกรมกลางของโปรเจก ใช้เป็นทั้ง (1) รายการเอกสารที่ต้องหามาอ่าน และ (2) รายการอ้างอิงในเล่ม

สถานะ: `[ ]` ยังไม่ได้อ่าน · `[~]` มีไฟล์แล้ว กำลังสรุป · `[x]` สรุปเป็นการ์ดแล้ว

**เครื่องหมายลิงก์**
✅ = เปิดตรวจแล้วว่าลิงก์ใช้งานได้จริงและเป็น open access
🔎 = ได้จากการค้นหา ยังไม่ได้เปิดตรวจเอง ให้ตรวจก่อนอ้างอิง

ดาวน์โหลดไฟล์ไว้ที่ `knowledge/sources/` (โฟลเดอร์นี้ถูก gitignore ไว้ ไม่ขึ้น GitHub)

**สถานะไฟล์ (31 ส.ค. 2569):** งานวิจัย open access ทั้ง 12 ฉบับดาวน์โหลดครบแล้ว
PMC บล็อกการโหลดอัตโนมัติ — ช่องทางที่ใช้ได้จริงคือ **Europe PMC**:
`https://europepmc.org/articles/<PMCID>?pdf=render` (ตรวจชื่อเรื่องกับต้นฉบับแล้วทุกไฟล์)

---

## 1. เอกสารอ้างอิงของไทย

- [~] **ปริมาณสารอาหารอ้างอิงที่ควรได้รับประจำวันสำหรับคนไทย พ.ศ. 2563 (Thai DRI)**
  สำนักโภชนาการ กรมอนามัย กระทรวงสาธารณสุข
  ✅ หน้าดาวน์โหลด: https://nutrition2.anamai.moph.go.th/th/dri/176096
  ✅ ไฟล์ `DRI2563.pdf` ~37 MB (มีผู้ดาวน์โหลดแล้วราว 2,869 ครั้ง)
  ✅ หน้ารวมเอกสาร DRI ทั้งหมด: https://nutrition2.anamai.moph.go.th/th/dri
  ใช้สำหรับ: ค่าอ้างอิงวิตามิน แร่ธาตุ ใยอาหาร โซเดียม สำหรับคนไทย
  ⚠️ หน้าเว็บไม่ได้ระบุเงื่อนไขการใช้ซ้ำไว้ชัดเจน — เป็นเอกสารราชการเผยแพร่สาธารณะ
  แต่ควรอ้างอิงให้ครบถ้วนและไม่คัดลอกตารางทั้งดุ้นลงเล่ม

- [ ] **Online Thai Food Composition Database (Thai FCD)** — สถาบันโภชนาการ ม.มหิดล (INMU)
  ✅ https://inmu.mahidol.ac.th/thaifcd/
  ✅ เวอร์ชันปัจจุบัน: **Version 3, สิงหาคม 2568** (รวมข้อมูลจาก Thai FCT ฉบับพิมพ์ปี 2015 และ 1999
  เข้ากับข้อมูลวิเคราะห์ใหม่จากห้องปฏิบัติการ INMU ช่วงปี 1997–2025)
  ✅ ค้นได้ 3 แบบ: ตามหมวดอาหาร / ตามชื่ออาหาร / ตามสารอาหาร
  ⚠️ **เป็นระบบค้นทีละรายการ ไม่มีปุ่มดาวน์โหลดทั้งฐาน** — ต้องคัดลอกทีละเมนูมาใส่ `foods.csv`
  ✅ **แต่ INMU เปิดให้โหลด "ดัชนีรายการอาหาร" เป็น PDF สาธารณะ** ซึ่งมีครบทั้ง 1,647 รายการ
  (Food ID + ชื่อไทย + ชื่ออังกฤษ + รหัสที่มาของข้อมูล) แต่ **ไม่มีค่าสารอาหาร**
  https://inmu.mahidol.ac.th/thaifcd/pdf/Food_Index.pdf
  แปลงเป็น CSV ด้วย `python tools/extract_thaifcd_index.py` → `knowledge/sources/thaifcd_index.csv`
  ใช้เลือกก่อนว่าจะเอาเมนูไหน แล้วค่อยเปิดเว็บดูค่าสารอาหารเฉพาะรายการที่เลือก
  PDF อื่นที่โหลดได้จากหน้า Terms: `Information_to_user.pdf` (วิธีเก็บตัวอย่าง/INFOODS Tagnames),
  `Source_of_data.pdf`, `Introduction_to_Thai_FCD.pdf`
  ✅ เงื่อนไข: ผู้ใช้ที่ไม่ใช่เชิงพาณิชย์ใช้ได้ฟรี **โดยต้องให้เครดิต INMU** ส่วนการใช้เชิงพาณิชย์
  หรือทำซ้ำเพื่อจำหน่ายต้องขออนุญาตและอาจมีค่าใช้จ่าย
  ✅ รูปแบบการอ้างอิงที่เจ้าของกำหนด:
  > Kunchit Judprasong, Prapasri Puwastien, et al. Institute of Nutrition, Mahidol University (2025).
  > Thai Food Composition Database, Online version 3, August 2025, Thailand.
  > https://inmu.mahidol.ac.th/thaifcd/home
  ✅ ติดต่อ: kunchit.jud@mahidol.ac.th · piyanut.sri@mahidol.ac.th
  ✅ โทร +66-2-800 2380 ต่อ 324, 423 · แฟกซ์ +66-2-441 9344
  ✅ ที่อยู่: สถาบันโภชนาการ ม.มหิดล 999 พุทธมณฑลสาย 4 ศาลายา พุทธมณฑล นครปฐม 73170

  **ถ้าส่งเมลแล้วไม่ได้รับการตอบกลับ** (สถานะปัจจุบัน: ส่งไปหลายวันแล้วยังเงียบ) ลองตามลำดับนี้
  1. โทรตามเบอร์ด้านบน — เร็วกว่าเมลมากในบริบทหน่วยงานไทย และมีสองเบอร์ต่อให้ลอง
  2. ส่งเมลถึง **piyanut.sri@mahidol.ac.th** ด้วย เผื่อคนแรกไม่ว่าง
  3. **ขอหนังสือราชการจากภาควิชา/คณะ** ให้อาจารย์ที่ปรึกษาลงนาม ระบุว่าเป็นปริญญานิพนธ์
     ไม่ใช่งานเชิงพาณิชย์ ระบุขอบเขตข้อมูลที่ขอ และจะอ้างอิงตามรูปแบบที่ INMU กำหนด
     — ช่องทางนี้ได้ผลกว่าเมลส่วนตัวมากในการติดต่อระหว่างสถาบัน
  4. ระหว่างรอ ใช้ดัชนีรายการอาหารด้านบนเลือกเมนูไปก่อน แล้วเปิดเว็บดูค่าทีละรายการ
     ซึ่ง**ทำได้เลยตามเงื่อนไขที่เขาประกาศไว้** ไม่ต้องรอการอนุมัติใด ๆ
  5. เผื่อไว้: หนังสือ **Thai Food Composition Tables 2015** ฉบับพิมพ์ อาจมีในห้องสมุด มข.
     ซึ่งเป็นแหล่งเดียวกันและอ้างอิงได้เหมือนกัน

- [x] **ระบบสืบค้นคุณค่าทางโภชนาการ (NSS) — กรมอนามัย**
  ✅ https://thaifcd.anamai.moph.go.th/nss/index.php
  ✅ มีไฟล์ตารางรวมทั้งชุด: `DOH-nutrition-table-2018.pdf` (**148 หน้า, 86 MB**)
  https://thaifcd.anamai.moph.go.th/nss/pdf/ตารางคุณค่า%202018.pdf
  ⚠️ เป็นไฟล์สแกนทั้งเล่ม ไม่มี text layer และใหญ่เกิน 20 MB ที่อ่านได้ครั้งเดียว — ตัดเป็น 15 ไฟล์
  ย่อยด้วย `pypdf` ก่อน (ไม่ใช้ `pdftoppm` เพราะไม่ได้ติดตั้งในเครื่องนี้) แล้วอ่านด้วยตาทีละไฟล์
  → แก้ 9 แถวใน `foods.csv` (31 ส.ค. 2569) ดูรายละเอียดการจับคู่/ปฏิเสธใน `knowledge/README.md`
  เช็คหมวดถั่วเมล็ดแห้งเพิ่มแล้ว (หน้า 17-22, ID 03001-03065+) — ไม่มีเต้าหู้ขาวแข็งหรือถั่วเหลือง
  ต้ม(เมล็ดแก่)โดยตรง มีแต่เต้าหู้อ่อน/ทอด/เหลือง/หมัก และถั่วแระต้ม (ถั่วเหลืองอ่อน/เขียว คนละ
  ผลิตภัณฑ์) จึงไม่ใช้ทั้งสองแถว ถือว่าตรวจสอบครบทุกหมวดที่เกี่ยวข้องในเอกสารนี้แล้ว

- [x] **คู่มือธงโภชนาการ** — กองโภชนาการ กรมอนามัย (ISBN 974-7889-85-4)
  ✅ https://nutrition2.anamai.moph.go.th/th/book/201525 → `ThongPhochanakan-manual.pdf` (14 หน้า)
  ⚠️ ไฟล์สแกน ไม่มี text layer (อ่านด้วยการแปลงภาพเป็นข้อความตรง ไม่ใช่ OCR อัตโนมัติ)
  หมายเหตุ: ไฟล์ไม่มีปีพิมพ์ที่อ่านได้ชัดเจน ใช้ ISBN อ้างอิงแทน — ปี 2564 ที่เคยเขียนไว้ตรงนี้
  ไม่ได้ยืนยันจากไฟล์จริง จึงตัดออก
  → การ์ด `thai-food-guide` (สัดส่วน 5 หมู่, ตาราง 3 ระดับพลังงาน 1600/2000/2400 kcal,
  หน่วยตวงครัวเรือน)

- [ ] **ASEAN Food Composition Database** (สำรอง ถ้าเมนูไหนไม่มีใน Thai FCD)
  🔎 https://inmu.mahidol.ac.th/aseanfoods/doc/OnlineASEAN_FCD_V1_2014.pdf

- [x] **ธงโภชนาการ / ข้อปฏิบัติการกินอาหารเพื่อสุขภาพที่ดีของคนไทย** — กรมอนามัย
  ซ้ำกับรายการด้านบน (`คู่มือธงโภชนาการ`) — เป็นเอกสารเดียวกัน ("ข้อปฏิบัติการกินอาหารเพื่อสุขภาพ
  ที่ดีของคนไทย" คือชื่อทางการของโภชนบัญญัติ 9 ประการที่คู่มือธงโภชนาการอิงตาม) ครอบคลุมแล้วใน
  การ์ด `thai-food-guide`

## 2. Position stands (โครงหลักของคำแนะนำเชิงกีฬา)

ทั้งหมดเป็น open access ผ่าน PubMed Central (PMC)

- [x] **Jäger R, et al.** ISSN Position Stand: Protein and Exercise. *JISSN.* 2017;14:20.
  ✅ https://pmc.ncbi.nlm.nih.gov/articles/PMC5477153/ (CC BY 4.0)
  → `cards/protein-requirement.md`
  ตัวเลขที่ตรวจกับต้นฉบับแล้ว: โปรตีนรวม **1.4–2.0 g/kg/วัน** · ต่อมื้อ **0.25 g/kg หรือ 20–40 g**
- [x] **Kreider RB, et al.** ISSN position stand: safety and efficacy of creatine supplementation.
  *JISSN.* 2017;14:18. 🔎 https://pmc.ncbi.nlm.nih.gov/articles/PMC5469049/
  → `cards/creatine.md`
- [x] **Aragon AA, et al.** ISSN position stand: diets and body composition. *JISSN.* 2017;14:16.
  🔎 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5470183/
  → `cards/energy-balance-cut-bulk.md`
- [~] **Kerksick CM, et al.** ISSN position stand: nutrient timing. *JISSN.* 2017;14:33.
  🔎 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5596471/ · DOI 10.1186/s12970-017-0189-4
  → การ์ด `nutrient-timing`
- [~] **Guest NS, et al.** ISSN position stand: caffeine and exercise performance. *JISSN.* 2021;18:1.
  🔎 https://pmc.ncbi.nlm.nih.gov/articles/PMC7777221 · DOI 10.1186/s12970-020-00383-4
  → การ์ด `caffeine` (คาเฟอีน 3–6 mg/kg ก่อนออกกำลังกายราว 60 นาที)
- [x] **Thomas DT, Erdman KA, Burke LM.** ACSM/AND/DC Joint Position Statement:
  Nutrition and Athletic Performance. *Med Sci Sports Exerc.* 2016;48(3):543-568.
  ✅ ได้ผ่านสิทธิ์ห้องสมุด มข. (Ovid — Khon Kaen University Journals@Ovid) 31 ส.ค. 2569
  → ขยายการ์ด `energy-balance-cut-bulk` ด้วยแนวคิด Energy Availability (EA) และ RED-S
  ⚠️ เอกสาร 26 หน้าส่วนใหญ่เป็นโภชนาการกีฬาแบบทั่วไป/กีฬาความอดทน (carb loading, hydration
  ระหว่างแข่งนาน, altitude, ความร้อน/เย็น) ซึ่งอยู่นอกขอบเขตเวทเทรนนิ่งของโปรเจกนี้ จึงดึงมาเฉพาะ
  ส่วน EA/RED-S ที่เกี่ยวกับความปลอดภัยตอน cut เท่านั้น
- [x] **Kerksick CM, et al.** ISSN exercise & sports nutrition review update. *JISSN.* 2018;15:38.
  🔎 ค้นจาก PMC — เป็นหนึ่งในเอกสารที่งานวิจัยประเมินแชตบอทใช้เป็นเกณฑ์ตัดสิน (ดู `docs/related-work.md`)
  → การ์ด `hmb`, `beta-alanine`, `unproven-muscle-supplements` (31 ส.ค. 2569 — เอกสาร 57 หน้า
  ครอบคลุมหลายหัวข้อ ดึงมาเฉพาะส่วนที่ยังไม่มีการ์ดคุมอยู่ก่อนแล้ว ส่วนที่เหลือ เช่น พลังงาน/คาร์บ/
  ไขมันสำหรับนักกีฬาทั่วไป ไม่ตรงขอบเขตเวทเทรนนิ่งเฉพาะทางของโปรเจกนี้ จึงยังไม่แยกเป็นการ์ด)

## 3. งานวิจัยเฉพาะเรื่อง

- [x] **Morton RW, et al.** Meta-analysis: protein supplementation and resistance training.
  *Br J Sports Med.* 2018;52(6):376-384. 🔎 https://pubmed.ncbi.nlm.nih.gov/28698222/
  (49 การทดลอง, 1,863 คน; จุดอิ่มตัวราว **1.62 g/kg/วัน**)
- [x] **Helms ER, Aragon AA, Fitschen PJ.** Natural bodybuilding contest preparation: nutrition.
  *JISSN.* 2014;11:20. ✅ https://pmc.ncbi.nlm.nih.gov/articles/PMC4033492/
  (ลดน้ำหนัก 0.5–1%/สัปดาห์ · โปรตีน 2.3–3.1 g/kg **มวลกายไร้ไขมัน** · ไขมัน 15–30% ของพลังงาน)
- [x] **Iraki J, et al.** Nutrition Recommendations for Bodybuilders in the Off-Season.
  *Sports (Basel).* 2019;7(7):154. 🔎 https://pmc.ncbi.nlm.nih.gov/articles/PMC6680710/
  (เกินดุลพลังงาน ~10–20% · เพิ่มน้ำหนัก ~0.25–0.5%/สัปดาห์)
- [x] **Mifflin MD, St Jeor ST, et al.** A new predictive equation for resting energy expenditure.
  *Am J Clin Nutr.* 1990;51(2):241-247. 🔎 https://pubmed.ncbi.nlm.nih.gov/2305711/
- [~] **Schoenfeld BJ, Aragon AA.** How much protein can the body use in a single meal?
  *JISSN.* 2018;15:10. 🔎 ค้นจาก PMC → การ์ด `protein-per-meal-myth`
  ⚠️ **สำคัญ** — เป็นที่มาของตัวเลข 0.4 g/kg ต่อมื้อ ซึ่งเดิมการ์ดโปรตีนอ้างผิดว่ามาจาก ISSN
- [x] **Antonio J, et al.** Common questions and misconceptions about creatine supplementation.
  *JISSN.* 2021;18:13. 🔎 ค้นจาก PMC → การ์ด `creatine`, `creatine-myths`
- [x] **Trexler ET, Smith-Ryan AE, Norton LE.** Metabolic adaptation to weight loss.
  *JISSN.* 2014;11:7. 🔎 ค้นจาก PMC → การ์ด `metabolic-adaptation`
- [x] **Aragon AA, Schoenfeld BJ.** Nutrient timing revisited: is there a post-exercise anabolic
  window? *JISSN.* 2013;10:5. ✅ https://pmc.ncbi.nlm.nih.gov/articles/PMC3577439/
  → การ์ด `nutrient-timing` (31 ส.ค. 2569: ขยายหัวข้อ "หน้าต่างอนาโบลิก" ด้วยกรอบปฏิบัติ
  3-4 ชม. ระหว่างมื้อก่อน/หลังฝึก, ปริมาณ 0.4-0.5 g/kg LBM ต่อมื้อ, และผลของอายุ/ประสบการณ์ฝึก)

## 3b. เอกสารใหม่ที่หาเพิ่ม (1-2 ก.ย. 2569) — ครบทุกฉบับแล้ว ทุกใบเขียนเป็นการ์ดแล้ว

เอกสารเดิมที่มีไฟล์อยู่แล้วใช้ครบหมดแล้ว (ดู TASKS.md) จึงค้นหาเอกสารใหม่เพื่อเติมหัวข้อที่ยังไม่มี
การ์ดคุมตามตาราง "รายการการ์ดที่วางแผนไว้" ด้านล่าง — ตรวจ open access จริงทุกฉบับแล้ว (fetch หน้า
บทความตรง ไม่ใช่แค่เดาจากผลค้นหา)

- [x] **Ferrando AA, Wolfe RR, et al.** ISSN position stand: essential amino acid supplementation
  on skeletal muscle and performance. *JISSN.* 2023;20(1):2263409.
  ✅ https://pmc.ncbi.nlm.nih.gov/articles/PMC10561576/ · DOI 10.1080/15502783.2023.2263409 (CC BY 4.0)
  → การ์ด `eaa` (1 ก.ย. 2569 — EAA vs BCAA, ปริมาณ 1.5-18g, ก่อน/หลังฝึก, ช่วง cut ต้องการ EAA
  เพิ่ม 3 เท่า, ผู้สูงอายุ/anabolic resistance, ความปลอดภัย) ingest แล้ว ทดสอบ retrieval ภาษาไทย
  3 คำถามผ่านหมด (score 0.72-0.81 เทียบ threshold 0.63)
- [x] **Mendes B, Correia J, Santos I, Schoenfeld B, Swinton P, Mendonca G.** Effects of plant- vs
  animal-based proteins on muscle protein synthesis: a systematic review with meta-analysis.
  SportRxiv preprint, 2025. ✅ https://sportrxiv.org/index.php/server/preprint/view/526
  DOI 10.51224/SRXIV.526 (preprint, เปิดอ่าน/ดาวน์โหลดฟรี ไม่มี paywall)
  → การ์ด `plant-protein` (1 ก.ย. 2569) และแก้ประโยคที่ไม่มีแหล่งอ้างอิงกำกับใน
  `protein-requirement.md` ให้มีที่มาแล้ว ingest + ทดสอบ retrieval ผ่าน
- [x] **Zare R, Devrim-Lanpir A, et al.** Effect of soy protein supplementation on muscle
  adaptations, metabolic and antioxidant status, hormonal response, and exercise performance:
  a systematic review of RCTs. *Sports Medicine.* 2023;53(12):2417-2446.
  ✅ https://pmc.ncbi.nlm.nih.gov/articles/PMC10687132/ · DOI 10.1007/s40279-023-01899-w (CC BY 4.0)
  → การ์ด `soy-protein` (1 ก.ย. 2569) ingest + ทดสอบ retrieval ผ่าน
- [x] **Cornish SM, Cordingley DM, et al.** Effects of omega-3 supplementation alone and combined
  with resistance exercise on skeletal muscle in older adults: a systematic review and
  meta-analysis. *Nutrients.* 2022;14(11):2221.
  ✅ https://pmc.ncbi.nlm.nih.gov/articles/PMC9182791/ · DOI 10.3390/nu14112221 (CC BY 4.0)
  → การ์ด `omega-3` (1 ก.ย. 2569) — เขียนให้ตรงขอบเขตประชากรจริง (ศึกษาเฉพาะผู้สูงอายุ ≥55 ปี
  ระบุไว้ชัดตั้งแต่หัวข้อแรกของการ์ด ไม่กล่าวอ้างเกินหลักฐานว่าช่วยสร้างกล้ามในคนทั่วไป)
  ingest + ทดสอบ retrieval ผ่าน (เคยเจอเอกสารที่ตรงหัวข้อกว่านี้ — Therdyothin et al. 2025,
  *Nutrition Reviews* 83(2):e131-e143 — แต่ติด paywall จึงไม่ใช้)

**รอบที่ 2 (2 ก.ย. 2569)** — หาเพิ่มอีก 5 ฉบับเพื่อให้ครบทุกหัวข้อในตาราง "รายการการ์ดที่วางแผนไว้"
ตรวจ open access จริงทุกฉบับเช่นเดิม

- [x] **Ramirez-Campillo R, Andrade DC, Clemente FM, Afonso J, Perez-Castilla A, Gentil P.** A
  proposed model to test the hypothesis of exercise-induced localized fat reduction (spot
  reduction), including a systematic review with meta-analysis. *Hum Mov.* 2022;23(3):1-14.
  ✅ https://hummov.awf.wroc.pl/A-proposed-model-to-test-the-hypothesis-of-exercise-induced-localized-fat-reduction,143162,0,2.html
  DOI 10.5114/hm.2022.110373 (open access, เว็บทางการของวารสาร)
  → การ์ด `fat-loss-myths` ส่วน spot reduction — 13 การศึกษา 1,158 คน ไม่พบความต่างมีนัยสำคัญ
  (pooled ES -0.03, 95%CI -0.10 ถึง 0.05)
- [x] **Liu HY, Eso AA, Cook N, O'Neill HM, Albarqouni L.** Meal timing and anthropometric and
  metabolic outcomes: a systematic review and meta-analysis. *JAMA Netw Open.* 2024;7(11):e2442163.
  ✅ https://pmc.ncbi.nlm.nih.gov/articles/PMC11530941/ · DOI 10.1001/jamanetworkopen.2024.42163
  (CC BY) → การ์ด `fat-loss-myths` ส่วนคาร์บตอนกลางคืน — 29 RCT 2,485 คน พบกินแคลอรี่ช่วงเช้า
  มากกว่าลดน้ำหนักได้มากกว่าจริง (1.75 กก.) แต่หลักฐานความเชื่อมั่นต่ำ ไม่ได้แยกดูเฉพาะคาร์บ
- [x] **Trabelsi K, Stannard SR, Ghlissi Z, et al.** Effect of fed- versus fasted state resistance
  training during Ramadan on body composition and selected metabolic parameters in bodybuilders.
  *J Int Soc Sports Nutr.* 2013;10:23. ✅ https://pmc.ncbi.nlm.nih.gov/articles/PMC3639860/
  DOI 10.1186/1550-2783-10-23 (CC BY) → การ์ด `fasted-training`
- [x] **Schoenfeld BJ, Aragon AA, Wilborn CD, Krieger JW, Sonmez GT.** Body composition changes
  associated with fasted versus non-fasted aerobic exercise. *J Int Soc Sports Nutr.* 2014;11:54.
  ✅ https://pmc.ncbi.nlm.nih.gov/articles/PMC4242477/ (open access)
  → การ์ด `fasted-training` (คู่กับ Trabelsi ด้านบน — คนละโหมดออกกำลังกาย เวท vs แอโรบิก)
- [x] **Han Q, Xiang M, An N, Tan Q, Shao J, Wang Q.** Effects of vitamin D3 supplementation on
  strength of lower and upper extremities in athletes: an updated systematic review and
  meta-analysis of RCTs. *Front Nutr.* 2024;11:1381301.
  ✅ https://pmc.ncbi.nlm.nih.gov/articles/PMC11163122/ · DOI 10.3389/fnut.2024.1381301 (CC BY)
  → การ์ด `vitamin-d-athletes` — 10 RCT นักกีฬา 354 คน ไม่พบว่าเพิ่มความแข็งแรงโดยรวมชัดเจน
  (มีนัยสำคัญเฉพาะแรงหดตัวต้นขา) แม้จะแก้ระดับวิตามินดีในเลือดได้จริง
- [x] **กรมอนามัย กระทรวงสาธารณสุข.** นโยบาย "หวานปกติ เท่ากับ หวาน 50%" 11 ก.พ. 2569 (รายงาน
  ผ่าน ThaiPR.NET, สสส., และ South China Morning Post ที่อ้างผลสำรวจของสำนักโภชนาการ)
  ✅ https://www.thaipr.net/health/3692342 · https://www.scmp.com/news/asia/southeast-asia/article/3343216/thailand-cuts-back-sugar-coffee-and-tea-tackle-health-crisis
  → การ์ด `thai-drinks-sugar` — ตัวเลขน้ำตาลจริงจากผลสำรวจ (กาแฟเย็น 650ml ~9 ช้อนชา,
  ชานมไข่มุก 300ml ~12 ช้อนชา) เป็นแหล่งข่าวที่รายงานผลสำรวจหน่วยงานรัฐ ไม่ใช่เอกสารวิชาการต้นฉบับ
  โดยตรง — ระบุไว้ชัดในการ์ดว่าเป็นค่าเฉลี่ยจากการสำรวจ

**การ์ด `thai-food-eating-out`** ไม่ได้ใช้เอกสารภายนอกใหม่ — ใช้ตัวเลขจริงจากฐานข้อมูล
`foods.csv` ของระบบเอง (ซึ่งมีที่มาสืบย้อนได้ทีละแถวอยู่แล้วตาม `knowledge/README.md`)

## 4. งานวิจัยเกี่ยวกับแชตบอทโภชนาการ (สำหรับบทที่ 2)

รายละเอียดและการวิเคราะห์อยู่ใน [`docs/related-work.md`](../docs/related-work.md)

- [~] **PLOS One (2025)** — ประเมินความรู้ด้านโภชนาการการกีฬาของแชตบอท LLM
  ✅ https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0325982
- [ ] **Luangaphirom T, et al.** ThaiNutriChat. *Multimedia Systems.* 2024;30(5):298.
  🔎 https://link.springer.com/article/10.1007/s00530-024-01495-6 (ต้องใช้สิทธิ์ห้องสมุด)
- [ ] **DietGlance** (arXiv 2502.01317) ✅ https://arxiv.org/html/2502.01317v1
- [ ] **HealthGenie** (arXiv 2504.14594) 🔎 https://arxiv.org/pdf/2504.14594

---

## รายการการ์ดที่วางแผนไว้ (เป้าหมาย 60+ ใบ)

| หมวด (`topic`) | การ์ดที่ตั้งใจเขียน |
|---|---|
| `energy` | สมดุลพลังงาน ✅, การปรับแคลอรี่เมื่อน้ำหนักนิ่ง ✅, metabolic adaptation ✅, refeed/diet break ✅ (ทั้งหมดอยู่ใน `energy-balance-cut-bulk` + `metabolic-adaptation`) |
| `protein` | ปริมาณโปรตีน ✅, โปรตีนต่อมื้อ ✅, โปรตีนพืชกับวีแกน ✅, เวย์เทียบถั่วเหลือง ✅ |
| `timing` | anabolic window ✅ (`nutrient-timing`), กินก่อน-หลังเล่น ✅, ฝึกเช้าตอนท้องว่าง ✅ (`fasted-training`), IF กับการเล่นเวท ✅ (`intermittent-fasting`) |
| `supplement` | ครีเอทีน ✅, คาเฟอีน ✅, เบต้าอะลานีน ✅, BCAA/EAA ✅, วิตามินดี ✅ (DRI ทั่วไปใน `calcium-iron-vitd` + มุมนักกีฬาใน `vitamin-d-athletes`), โอเมก้า-3 ✅, สิ่งที่ไม่คุ้มเงิน ✅ |
| `thai-food` | ธงโภชนาการ ✅ (`thai-food-guide`), เมนูตามสั่งโปรตีนสูง/การสั่งอาหารนอกบ้านช่วง cut ✅ (`thai-food-eating-out` — รวม "อาหารคลีนแบบไทย" ไว้ในนี้ด้วยแทนที่จะแยกการ์ด), น้ำตาลแฝงในเครื่องดื่ม ✅ (`thai-drinks-sugar`) |
| `myth` | คาร์บตอนเย็นทำให้อ้วน ✅, กินโปรตีนเกิน 30 g เสียเปล่า ✅ (`protein-per-meal-myth`), spot reduction ✅, เหงื่อออกมาก = เผาผลาญมาก ✅ (3 อย่างแรกรวมในการ์ดเดียว `fat-loss-myths`) |
| `safety` | สัญญาณอันตรายของการลดน้ำหนักเร็วเกินไป, ทำไมไม่แนะนำสารต้องห้าม, เมื่อไหร่ควรพบแพทย์ — จัดการผ่าน guardrails แบบ rule-based ในโค้ดแทน ไม่ใช่ RAG card (ดู `app/services/guardrails.py`) จึงไม่ใช่คอขวดของฐานความรู้ |
