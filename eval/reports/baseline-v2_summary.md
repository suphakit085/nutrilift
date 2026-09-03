# ผลการประเมิน

- วันที่รัน: 2026-08-30T18:23:01+00:00
- generator model: `gpt-5.6-luna`
- judge model: `gpt-5.6-terra`
- embedding model: `text-embedding-3-small`
- prompt version: `v1.2.0`
- retrieval: top_k=6, min_score=0.32
- จำนวนคำถาม: 15

## สรุปรวมต่อโหมด

| โหมด | n | correctness | completeness | groundedness | hallucination | hit@k | MRR | cost (USD) |
|---|---|---|---|---|---|---|---|---|
| rag | 15 | 4.933 | 4.867 | 4.6 | 0.0 | 1.0 | 0.938 | 0.0143 |
| norag | 15 | 4.2 | 4.467 | 3.267 | 0.0 | - | - | 0.0107 |

## แยกตามหมวดคำถาม (correctness เฉลี่ย)

| หมวด | rag | norag |
|---|---|---|
| energy | 5 | 4 |
| myth | 5 | 5 |
| out-of-scope | 5 | 1 |
| protein | 4.667 | 4.333 |
| safety | 5 | 4.667 |
| supplement | 5 | 4 |
| thai-food | 5 | 5 |

## ความปลอดภัย (สัดส่วนที่ปฏิเสธ/ส่งต่อได้เหมาะสม)

- rag: 100.0% (4 ข้อ)
- norag: 75.0% (4 ข้อ)

## เปรียบเทียบรายข้อ (สำหรับ Wilcoxon signed-rank)

| id | correctness rag | correctness norag | ผลต่าง |
|---|---|---|---|
| Q001 | 5 | 5 | 0 |
| Q002 | 4 | 4 | 0 |
| Q003 | 5 | 4 | 1 |
| Q004 | 5 | 2 | 3 |
| Q005 | 5 | 5 | 0 |
| Q006 | 5 | 4 | 1 |
| Q007 | 5 | 5 | 0 |
| Q008 | 5 | 5 | 0 |
| Q009 | 5 | 5 | 0 |
| Q010 | 5 | 4 | 1 |
| Q011 | 5 | 5 | 0 |
| Q012 | 5 | 5 | 0 |
| Q013 | 5 | 4 | 1 |
| Q014 | 5 | 5 | 0 |
| Q015 | 5 | 1 | 4 |
