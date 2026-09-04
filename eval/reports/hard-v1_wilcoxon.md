# Wilcoxon signed-rank: RAG vs no-RAG (hard-v1)

H0: ไม่มีความต่างอย่างมีนัยสำคัญระหว่างคะแนน RAG กับ no-RAG แบบจับคู่รายข้อ (same generator/prompt, ต่างแค่มี context หรือไม่)

| ตัวชี้วัด | n คู่ | ค่าเฉลี่ย RAG | ค่าเฉลี่ย no-RAG | W statistic | p-value | นัยสำคัญที่ 0.05 |
|---|---|---|---|---|---|---|
| correctness | 50 | 4.980 | 4.700 | 5.50 | 0.0032 | ใช่ |
| completeness | 50 | 5.000 | 4.760 | 0.00 | 0.0057 | ใช่ |
| groundedness | 50 | 4.960 | 4.660 | 6.00 | 0.0171 | ใช่ |

หมายเหตุ: `zero_method="wilcox"` ตัดคู่ที่คะแนนเท่ากันทิ้งก่อนจัดอันดับ (พฤติกรรมมาตรฐานของ Wilcoxon signed-rank) `method="auto"` ให้ scipy เลือกวิธีคำนวณ p-value เอง (exact เมื่อ n เล็กและไม่มี tie, normal approximation เมื่อ n ใหญ่หรือมี tie) ตรงกับจำนวนคำถามที่คะแนนเท่ากันเยอะในชุดนี้
