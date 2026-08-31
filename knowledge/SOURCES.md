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

- [~] **ระบบสืบค้นคุณค่าทางโภชนาการ (NSS) — กรมอนามัย** ⭐ เจอใหม่ เป็นทางเลือกคู่กับ INMU
  ✅ https://thaifcd.anamai.moph.go.th/nss/index.php
  ✅ มีไฟล์ตารางรวมทั้งชุด: `DOH-nutrition-table-2018.pdf` (**148 หน้า, 86 MB**)
  https://thaifcd.anamai.moph.go.th/nss/pdf/ตารางคุณค่า%202018.pdf
  ⚠️ เป็นไฟล์สแกนทั้งเล่ม ไม่มี text layer — คัดค่าลง `foods.csv` ต้องอ่านด้วยตา
  ข้อดี: เป็นเอกสารราชการเผยแพร่สาธารณะไฟล์เดียวจบ ไม่ต้องกดค้นทีละเมนูแบบเว็บ INMU

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
- [ ] **Thomas DT, Erdman KA, Burke LM.** ACSM/AND/DC Joint Position Statement:
  Nutrition and Athletic Performance. *Med Sci Sports Exerc.* 2016;48(3):543-568.
  🔎 ค้นจาก PubMed: https://pubmed.ncbi.nlm.nih.gov/26891166/
  ⚠️ วารสารนี้ไม่ open access — ใช้สิทธิ์ห้องสมุด มข. หรือขอผ่านอาจารย์ที่ปรึกษา
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
| `energy` | สมดุลพลังงาน ✅, การปรับแคลอรี่เมื่อน้ำหนักนิ่ง, metabolic adaptation, refeed/diet break |
| `protein` | ปริมาณโปรตีน ✅, โปรตีนต่อมื้อ, โปรตีนพืชกับวีแกน, เวย์/เคซีน/โปรตีนถั่วเหลือง |
| `timing` | anabolic window, กินก่อน-หลังเล่น, ฝึกเช้าตอนท้องว่าง, IF กับการเล่นเวท |
| `supplement` | ครีเอทีน ✅, คาเฟอีน, เบต้าอะลานีน, BCAA/EAA, วิตามินดี, โอเมก้า-3, สิ่งที่ไม่คุ้มเงิน |
| `thai-food` | เมนูตามสั่งโปรตีนสูง, อาหารคลีนแบบไทย, การสั่งอาหารนอกบ้านช่วง cut, น้ำตาลแฝงในเครื่องดื่ม |
| `myth` | คาร์บตอนเย็นทำให้อ้วน, กินโปรตีนเกิน 30 g เสียเปล่า, spot reduction, เหงื่อออกมาก = เผาผลาญมาก |
| `safety` | สัญญาณอันตรายของการลดน้ำหนักเร็วเกินไป, ทำไมไม่แนะนำสารต้องห้าม, เมื่อไหร่ควรพบแพทย์ |
