# Wilcoxon signed-rank: RAG vs no-RAG (baseline-v9)

H0: ไม่มีความต่างอย่างมีนัยสำคัญระหว่างคะแนน RAG กับ no-RAG แบบจับคู่รายข้อ (same generator/prompt, ต่างแค่มี context หรือไม่)

| ตัวชี้วัด | n คู่ | ค่าเฉลี่ย RAG | ค่าเฉลี่ย no-RAG | W statistic | p-value | นัยสำคัญที่ 0.05 |
|---|---|---|---|---|---|---|
| correctness | 150 | 4.887 | 4.693 | 86.00 | 0.0019 | ใช่ |
| completeness | 150 | 4.900 | 4.747 | 57.00 | 0.0114 | ใช่ |
| groundedness | 150 | 4.947 | 4.700 | 28.00 | 0.0002 | ใช่ |

หมายเหตุ: `zero_method="wilcox"` ตัดคู่ที่คะแนนเท่ากันทิ้งก่อนจัดอันดับ (พฤติกรรมมาตรฐานของ Wilcoxon signed-rank) `method="auto"` ให้ scipy เลือกวิธีคำนวณ p-value เอง (exact เมื่อ n เล็กและไม่มี tie, normal approximation เมื่อ n ใหญ่หรือมี tie) ตรงกับจำนวนคำถามที่คะแนนเท่ากันเยอะในชุดนี้
