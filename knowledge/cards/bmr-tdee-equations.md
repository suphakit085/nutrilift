---
slug: bmr-tdee-equations
title: ที่มาของสูตร BMR และ TDEE — Harris-Benedict, Mifflin-St Jeor, Katch-McArdle และตัวคูณกิจกรรม
topic: energy
lang: th
review_status: ai_reviewed_pending_independent_review
content_fix_version: v1
baseline_id: '2026-10-27'
sources:
  - "Harris JA, Benedict FG. A Biometric Study of Human Basal Metabolism. Proc Natl Acad Sci U S A. 1918;4(12):370-373. [ตรวจข้อมูลบรรณานุกรม]"
  - "Mifflin MD, St Jeor ST, Hill LA, Scott BJ, Daugherty SA, Koh YO. A new predictive equation for resting energy expenditure in healthy individuals. Am J Clin Nutr. 1990;51(2):241-247. [ตรวจจาก abstract]"
  - "O'Neill JER, Corish CA, Horner K. Accuracy of Resting Metabolic Rate Prediction Equations in Athletes: A Systematic Review with Meta-analysis. Sports Med. 2023;53(12):2373-2398. doi:10.1007/s40279-023-01896-z"
  - "Tang M, Wang J, Xiang Y, Xu R. Metabolic adaptation fluctuates with different prediction equations: a secondary analysis based on a weight-loss clinical trial. Front Nutr. 2025;12:1543263. doi:10.3389/fnut.2025.1543263"
  - "FAO/WHO/UNU. Human energy requirements: Report of a Joint FAO/WHO/UNU Expert Consultation, Rome, 17-24 October 2001. FAO Food and Nutrition Technical Report Series 1. Rome: FAO; 2004. บทที่ 5."
---

# ใครคิดค้นสูตร BMR: Harris-Benedict และ Mifflin-St Jeor

BMR หรือ RMR/REE คือพลังงานที่ร่างกายใช้ขณะพัก สมการทุกสมการเป็นการประมาณจากข้อมูลของกลุ่มคนที่ใช้สร้างสมการ ไม่ใช่การวัดจากตัวเราจริง งานของ Mifflin และคณะวัดค่าจริงด้วยการวัดก๊าซจากการหายใจ (indirect calorimetry) แล้วนำมาสร้างสมการ

- **Harris-Benedict:** มาจาก Harris JA และ Benedict FG ซึ่งตีพิมพ์บทความ "A Biometric Study of Human Basal Metabolism" ในวารสาร PNAS ปี 1918 (แหล่งข้อมูลระบุชื่อด้วยอักษรย่อชื่อต้นเท่านั้น) Mifflin และคณะ (1990) อ้างถึงสมการนี้ว่าได้มาในปี 1919 สมการใช้อายุ น้ำหนัก และส่วนสูง ในงานของ Mifflin สมการนี้ประมาณค่าสูงกว่าค่าที่วัดได้ประมาณ 5%
- **Mifflin-St Jeor:** ตีพิมพ์ปี 1990 ในวารสาร American Journal of Clinical Nutrition โดย Mifflin MD, St Jeor ST, Hill LA, Scott BJ, Daugherty SA และ Koh YO ศึกษาผู้ใหญ่สุขภาพดี 498 คน (หญิง 247 ชาย 251) อายุ 19-78 ปี มีทั้งน้ำหนักปกติ 264 คนและอ้วน 234 คน สมการชาย = 10 × น้ำหนัก (กก.) + 6.25 × ส่วนสูง (ซม.) − 5 × อายุ (ปี) + 5 สมการหญิงใช้ − 161 แทน + 5 งานเดียวกันให้สมการจากมวลไร้ไขมัน 19.7 × FFM + 413 (ตรวจจาก abstract)
- **Katch-McArdle:** ใช้มวลไร้ไขมันแทนน้ำหนัก รูปที่พบบ่อยคือ RMR = 370 + 21.6 × LBM (กก.) ตามที่ Tang และคณะ (2025) ใช้ ซึ่งไม่ใช่เอกสารต้นกำเนิดของสมการ สมการ Cunningham (1980) ก็ใช้ LBM เช่นกัน ถ้าเปอร์เซ็นต์ไขมันที่ใช้คลาดเคลื่อน ผลก็คลาดเคลื่อนตาม

# สูตรไหนแม่นที่สุด และ TDEE กับตัวคูณกิจกรรมมาจากไหน

ไม่มีสูตรใดแม่นที่สุดสำหรับทุกคน O'Neill และคณะ (2023) ทบทวนอย่างเป็นระบบในนักกีฬา 29 งาน 1,430 คน พบว่าค่าเฉลี่ยของ Cunningham (1980), Harris-Benedict (1918), Cunningham (1991), De Lorenzo และ Ten-Haaf ไม่ต่างจากค่าวัดจริงอย่างมีนัยสำคัญ ส่วน Mifflin-St Jeor, Owen, FAO/WHO/UNU, Nelson และ Koehler ประมาณต่ำหรือสูงเกินอย่างมีนัยสำคัญ ด้านรายบุคคล Ten-Haaf ประมาณได้ภายใน ±10% ใน 80.2% ของผู้เข้าร่วม สมการอื่นทำได้ 40.7-63.7% ผู้วิจัยสรุปว่าไม่มีสมการใดรับประกันว่าดีที่สุด ควรเลือกสมการที่สร้างจากคนที่มีลักษณะใกล้เคียงกับผู้ใช้ ผลนี้เป็นของนักกีฬา คนทั่วไปอาจได้ผลต่างออกไป

TDEE (พลังงานทั้งวัน) ประมาณจาก BMR × ตัวคูณกิจกรรม รายงาน FAO/WHO/UNU (2004) เรียกตัวคูณนี้ว่า PAL และแบ่งวิถีชีวิตเป็นนั่งทำงานหรือกิจกรรมเบา PAL 1.40-1.69 กระฉับกระเฉงหรือปานกลาง 1.70-1.99 และกิจกรรมหนัก 2.00-2.40 (ค่าเกิน 2.40 รักษาไว้นานได้ยาก) เครื่องคำนวณต่าง ๆ ใช้ชุดตัวคูณต่างกัน TDEE ที่ได้จึงเป็นจุดเริ่มต้น ไม่ใช่ค่าที่วัดจริง ควรติดตามแนวโน้มน้ำหนักจริงแล้วปรับพลังงานตามผล (ดูการ์ดสมดุลพลังงาน)
