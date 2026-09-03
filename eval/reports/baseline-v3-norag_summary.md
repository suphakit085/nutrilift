# ผลการประเมิน

- วันที่รัน: 2026-09-01T10:35:10+00:00
- generator model: `gemini-3.5-flash-lite`
- judge model: `gemini-3.1-flash-lite`
- embedding model: `gemini-embedding-001`
- prompt version: `v1.3.0`
- retrieval: top_k=6, min_score=0.63
- จำนวนคำถาม: 33

## สรุปรวมต่อโหมด

| โหมด | n | correctness | completeness | groundedness | hallucination | hit@k | MRR | cost (USD) |
|---|---|---|---|---|---|---|---|---|
| norag | 33 | 4.788 | 4.879 | 4.576 | 0.0 | - | - | 0.0 |

## แยกตามหมวดคำถาม (correctness เฉลี่ย)

| หมวด | norag |
|---|---|
| energy | 4.667 |
| myth | 5 |
| out-of-scope | 5 |
| protein | 4.667 |
| safety | 5 |
| supplement | 4.833 |
| thai-food | 5 |
| timing | 4.5 |

## ความปลอดภัย (สัดส่วนที่ปฏิเสธ/ส่งต่อได้เหมาะสม)

- norag: 100.0% (4 ข้อ)
