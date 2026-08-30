# แหล่งอ้างอิงของฐานความรู้

รายการนี้คือบรรณานุกรมกลางของโปรเจก ใช้เป็นทั้ง (1) รายการเอกสารที่ต้องหามาอ่าน
และ (2) รายการอ้างอิงในเล่มปริญญานิพนธ์

สถานะ: `[ ]` ยังไม่ได้อ่าน/ยังไม่มีไฟล์ · `[~]` มีไฟล์แล้ว กำลังสรุป · `[x]` สรุปเป็นการ์ดแล้ว

---

## 1. เอกสารอ้างอิงของไทย (ใช้เป็นฐานของค่าที่แนะนำสำหรับคนไทย)

- [ ] **ปริมาณสารอาหารอ้างอิงที่ควรได้รับประจำวันสำหรับคนไทย พ.ศ. 2563 (Thai DRI 2020)**
  — สำนักโภชนาการ กรมอนามัย กระทรวงสาธารณสุข
  ใช้สำหรับ: ค่าอ้างอิงวิตามิน แร่ธาตุ ใยอาหาร โซเดียม สำหรับคนไทย
- [ ] **ตารางแสดงคุณค่าทางโภชนาการของอาหารไทย (Nutritive Values of Thai Foods)**
  — กองโภชนาการ กรมอนามัย
  ใช้สำหรับ: สร้าง `knowledge/foods.csv`
- [ ] **ฐานข้อมูลคุณค่าทางโภชนาการอาหารไทย INMU** — สถาบันโภชนาการ มหาวิทยาลัยมหิดล
  ใช้สำหรับ: ตรวจสอบ/เติมเมนูใน `foods.csv`
- [ ] **ธงโภชนาการ / ข้อปฏิบัติการกินอาหารเพื่อสุขภาพที่ดีของคนไทย**
  ใช้สำหรับ: การ์ดเรื่องการกินให้ครบหมู่และสัดส่วนอาหาร

## 2. Position stands (โครงหลักของคำแนะนำเชิงกีฬา)

- [x] **Jager R, et al.** ISSN Position Stand: Protein and Exercise.
  *J Int Soc Sports Nutr.* 2017;14:20. → `cards/protein-requirement.md`
- [x] **Kreider RB, et al.** ISSN position stand: safety and efficacy of creatine supplementation.
  *J Int Soc Sports Nutr.* 2017;14:18. → `cards/creatine.md`
- [x] **Aragon AA, et al.** ISSN position stand: diets and body composition.
  *J Int Soc Sports Nutr.* 2017;14:16. → `cards/energy-balance-cut-bulk.md`
- [ ] **Kerksick CM, et al.** ISSN position stand: nutrient timing.
  *J Int Soc Sports Nutr.* 2017;14:33. → การ์ด `nutrient-timing`
- [ ] **Guest NS, et al.** ISSN position stand: caffeine and exercise performance.
  *J Int Soc Sports Nutr.* 2021;18:1. → การ์ด `caffeine`
- [ ] **Thomas DT, Erdman KA, Burke LM.** ACSM/AND/DC Joint Position Statement:
  Nutrition and Athletic Performance. *Med Sci Sports Exerc.* 2016;48(3):543-568.
- [ ] **Kerksick CM, et al.** ISSN exercise & sports nutrition review update:
  research & recommendations. *J Int Soc Sports Nutr.* 2018;15:38.

## 3. งานวิจัยเฉพาะเรื่อง

- [x] **Morton RW, et al.** Meta-analysis: protein supplementation and resistance training.
  *Br J Sports Med.* 2018;52(6):376-384.
- [x] **Helms ER, Aragon AA, Fitschen PJ.** Natural bodybuilding contest preparation: nutrition.
  *J Int Soc Sports Nutr.* 2014;11:20.
- [x] **Iraki J, et al.** Nutrition Recommendations for Bodybuilders in the Off-Season.
  *Sports (Basel).* 2019;7(7):154.
- [x] **Mifflin MD, St Jeor ST, et al.** A new predictive equation for resting energy expenditure.
  *Am J Clin Nutr.* 1990;51(2):241-247.
- [ ] **Schoenfeld BJ, Aragon AA.** How much protein can the body use in a single meal?
  *J Int Soc Sports Nutr.* 2018;15:10. → การ์ด `protein-per-meal-myth`
- [ ] **Antonio J, et al.** Common questions and misconceptions about creatine supplementation.
  *J Int Soc Sports Nutr.* 2021;18:13.
- [ ] **Trexler ET, Smith-Ryan AE, Norton LE.** Metabolic adaptation to weight loss.
  *J Int Soc Sports Nutr.* 2014;11:7. → การ์ด `metabolic-adaptation`

---

## รายการการ์ดที่วางแผนไว้ (เป้าหมาย 60+ ใบ)

| หมวด (`topic`) | การ์ดที่ตั้งใจเขียน |
|---|---|
| `energy` | สมดุลพลังงาน ✅, การปรับแคลอรี่เมื่อน้ำหนักนิ่ง, metabolic adaptation, refeed/diet break |
| `protein` | ปริมาณโปรตีน ✅, โปรตีนต่อมื้อ, โปรตีนพืชกับวีแกน, เวย์/เคซีน/โปรตีนถั่วเหลือง |
| `timing` | anabolic window, กินก่อน-หลังเล่น, การกินตอนฝึกเช้าตอนท้องว่าง, IF กับการเล่นเวท |
| `supplement` | ครีเอทีน ✅, คาเฟอีน, เบต้าอะลานีน, BCAA/EAA, วิตามินดี, โอเมก้า-3, สิ่งที่ไม่คุ้มเงิน |
| `thai-food` | เมนูตามสั่งที่โปรตีนสูง, อาหารคลีนแบบไทย, การสั่งอาหารนอกบ้านช่วง cut, เครื่องดื่มและน้ำตาลแฝง |
| `myth` | คาร์บตอนเย็นทำให้อ้วน, กินโปรตีนเกิน 30 g เสียเปล่า, ทำ spot reduction ได้, เหงื่อออกมาก = เผาผลาญมาก |
| `safety` | สัญญาณอันตรายของการลดน้ำหนักเร็วเกินไป, ทำไมไม่แนะนำสารต้องห้าม, เมื่อไหร่ควรพบแพทย์ |
