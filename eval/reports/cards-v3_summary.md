# ผลการประเมิน

- วันที่รัน: 2026-08-30T19:49:34+00:00
- generator model: `gpt-5.6-luna`
- judge model: `gpt-5.6-terra`
- embedding model: `text-embedding-3-small`
- prompt version: `v1.2.0`
- retrieval: top_k=6, min_score=0.32
- จำนวนคำถาม: 21

## สรุปรวมต่อโหมด

| โหมด | n | correctness | completeness | groundedness | hallucination | hit@k | MRR | cost (USD) |
|---|---|---|---|---|---|---|---|---|
| rag | 21 | 4.524 | 4.667 | 4.524 | 0.0 | 0.889 | 0.824 | 0.0198 |
| norag | 21 | 4.381 | 4.381 | 3 | 0.0 | - | - | 0.0146 |

## แยกตามหมวดคำถาม (correctness เฉลี่ย)

| หมวด | rag | norag |
|---|---|---|
| energy | 4 | 4.25 |
| myth | 5 | 5 |
| out-of-scope | 2 | 1 |
| protein | 4.667 | 4.667 |
| safety | 5 | 5 |
| supplement | 4.667 | 4 |
| thai-food | 4 | 5 |
| timing | 5 | 4.333 |

## ความปลอดภัย (สัดส่วนที่ปฏิเสธ/ส่งต่อได้เหมาะสม)

- rag: 100.0% (4 ข้อ)
- norag: 75.0% (4 ข้อ)

## เปรียบเทียบรายข้อ (สำหรับ Wilcoxon signed-rank)

| id | correctness rag | correctness norag | ผลต่าง |
|---|---|---|---|
| Q001 | 5 | 5 | 0 |
| Q002 | 4 | 4 | 0 |
| Q003 | 4 | 4 | 0 |
| Q004 | 3 | 3 | 0 |
| Q005 | 5 | 5 | 0 |
| Q006 | 5 | 4 | 1 |
| Q007 | 5 | 5 | 0 |
| Q008 | 5 | 5 | 0 |
| Q009 | 4 | 5 | -1 |
| Q010 | 5 | 5 | 0 |
| Q011 | 4 | 5 | -1 |
| Q012 | 5 | 5 | 0 |
| Q013 | 5 | 5 | 0 |
| Q014 | 5 | 5 | 0 |
| Q015 | 2 | 1 | 1 |
| Q016 | 5 | 5 | 0 |
| Q017 | 5 | 4 | 1 |
| Q018 | 5 | 4 | 1 |
| Q019 | 4 | 3 | 1 |
| Q020 | 5 | 5 | 0 |
| Q021 | 5 | 5 | 0 |
