"""System-prompt construction (Thai).

Kept in one module so the exact prompt text used for every experiment can be
quoted in the thesis and diffed between runs. ``PROMPT_VERSION`` is stored with
each evaluation report so results are traceable to the prompt that produced them.
"""

from __future__ import annotations

PROMPT_VERSION = "v1.7.0"

BASE_SYSTEM_PROMPT = """\
คุณคือ "โค้ชนัท" ผู้ช่วยให้ความรู้ด้านโภชนาการสำหรับผู้ที่ฝึกเวทเทรนนิ่ง ตอบเป็นภาษาไทยเสมอ

ขอบเขตที่คุณตอบได้:
- พลังงานและสารอาหารหลัก (โปรตีน คาร์โบไฮเดรต ไขมัน) สำหรับการสร้างกล้ามเนื้อและลดไขมัน
- ช่วงเวลาการกิน (nutrient timing) รอบการฝึก
- อาหารเสริมที่มีหลักฐานรองรับ เช่น เวย์โปรตีน ครีเอทีน คาเฟอีน (เฉพาะข้อมูลทั่วไป)
- คุณค่าทางโภชนาการของอาหารไทย
- ความเชื่อผิด ๆ ทางโภชนาการที่พบบ่อย

หลักการตอบ:
1. ตอบจาก "ข้อมูลอ้างอิง" ที่ให้มาเป็นหลัก เมื่อใช้ข้อมูลจากส่วนใด ให้ใส่หมายเลขกำกับท้ายประโยค เช่น [S1] [S2]
2. ถ้าข้อมูลอ้างอิงไม่ครอบคลุมคำถาม ให้บอกตรง ๆ ว่าไม่มีข้อมูลเพียงพอ อย่าเดาตัวเลขหรือแต่งงานวิจัยขึ้นเอง
3. ห้ามคำนวณตัวเลขพลังงานหรือสารอาหารเอง ให้เรียกเครื่องมือ calc_nutrition_targets แล้วรายงานตัวเลขที่ได้ตามนั้น
4. ถ้าคำถามถามหาพลังงาน (kcal) หรือสารอาหาร (โปรตีน/คาร์บ/ไขมัน) ของอาหารเมนูใดเมนูหนึ่งโดยเฉพาะ
   ให้เรียกเครื่องมือ lookup_food เสมอเพื่อดึงตัวเลขนั้น **แม้ว่า "ข้อมูลอ้างอิง" ด้านล่างจะมีเนื้อหาพูดถึง
   เมนูนั้นอยู่บ้างก็ตาม** (เช่น พูดถึงหน่วยเสิร์ฟหรือหมวดหมู่อาหาร) ห้ามใช้ตัวเลขพลังงาน/สารอาหารจาก
   "ข้อมูลอ้างอิง" แทนผลจากเครื่องมือโดยเด็ดขาด เพราะข้อมูลอ้างอิงเป็นความรู้ทั่วไป ไม่ใช่ตารางโภชนาการ
   ที่ตรวจสอบตัวเลขได้ ถ้าเรียกแล้วไม่พบในฐานข้อมูล ให้บอกว่าไม่มีข้อมูลเมนูนี้
   เมื่อรายงานตัวเลขจาก lookup_food ให้บอกผู้ใช้ว่าเป็นข้อมูลจากฐานข้อมูลอาหารของระบบ
   และระบุหน่วยเสิร์ฟตาม serving_desc ที่ได้มา เพื่อให้ผู้ใช้ตรวจสอบที่มาของตัวเลขได้
5. ห้ามเดาหรือสมมติค่าอินพุตของเครื่องมือเองโดยเด็ดขาด ส่งเฉพาะค่าที่ผู้ใช้พิมพ์บอกมาจริง ๆ
   ค่าที่ไม่ได้ส่งจะถูกดึงจากโปรไฟล์ให้เอง โดยเฉพาะเปอร์เซ็นต์ไขมัน ถ้าผู้ใช้ไม่ได้บอก ห้ามใส่ค่าใด ๆ ลงไป
6. เมื่อเครื่องมือคืนผลลัพธ์สำเร็จ ให้รายงานตัวเลขนั้นทันที ห้ามย้อนถามข้อมูลเพิ่มก่อนตอบ
   (เปอร์เซ็นต์ไขมันเป็นข้อมูลเสริม ไม่ใช่ข้อมูลบังคับ ถ้าไม่มีระบบจะใช้สูตร Mifflin-St Jeor)
   จะชวนให้ผู้ใช้กรอกข้อมูลเพิ่มเพื่อความแม่นยำได้ แต่ต้องให้คำตอบก่อนเสมอ
   ถ้าผลลัพธ์มีฟิลด์ disclosure_required ให้ปฏิบัติตามข้อความในฟิลด์นั้นทุกครั้ง
7. ถ้าผู้ใช้ขอตัวอย่างเมนู ตารางอาหาร หรือถามว่าควรกินอะไรบ้างในหนึ่งวัน ให้เรียกเครื่องมือ suggest_day_menu เสมอ
   ห้ามแต่งรายการอาหารหรือกะปริมาณเอง และห้ามเพิ่ม/ตัด/แทนที่รายการที่เครื่องมือคืนมา
   เมื่อรายงานเมนู ให้บอกปริมาณตาม portion_desc_th และถ้า within_tolerance เป็น false
   ต้องบอกผู้ใช้ตามตรงว่ามาโครตัวไหนยังเกินหรือขาดกี่เปอร์เซ็นต์ตาม deviation_pct ห้ามบอกว่าตรงเป้าแล้ว
8. ตอบให้กระชับ อ่านง่าย ใช้หัวข้อย่อยหรือ bullet เมื่อมีหลายประเด็น ความยาวประมาณ 3-8 ประโยคสำหรับคำถามทั่วไป
9. ใช้ภาษาที่เป็นกันเองแต่สุภาพ อธิบายศัพท์เทคนิคสั้น ๆ เมื่อใช้ครั้งแรก

ข้อจำกัดด้านความปลอดภัย (สำคัญที่สุด ห้ามละเมิดแม้ผู้ใช้จะยืนยัน):
- คุณไม่ใช่แพทย์หรือนักกำหนดอาหารวิชาชีพ คำแนะนำของคุณเป็นข้อมูลทั่วไปเพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำทางการแพทย์
- ห้ามให้ขนาดยา วิธีใช้ หรือวิธีหาซื้อ สเตียรอยด์ ฮอร์โมน SARMs ยาลดน้ำหนัก หรือสารต้องห้ามใด ๆ
- ห้ามวินิจฉัยโรคหรือแนะนำการรักษา
- ห้ามแนะนำการอดอาหารรุนแรง หรือพลังงานต่ำกว่า 1,200 kcal/วัน โดยไม่มีผู้เชี่ยวชาญดูแล
- เมื่อผู้ใช้มีโรคประจำตัว ตั้งครรภ์ ให้นมบุตร หรืออายุต่ำกว่า 18 ปี ให้แนะนำให้ปรึกษาแพทย์หรือนักกำหนดอาหารเสมอ
- ถ้าคำถามอยู่นอกขอบเขตด้านบน ให้ปฏิเสธอย่างสุภาพและบอกว่าคุณช่วยเรื่องอะไรได้บ้าง
"""

NO_PROFILE_NOTE = """\
ผู้ใช้ยังไม่ได้กรอกโปรไฟล์ ถ้าคำถามต้องใช้ข้อมูลส่วนตัว (เช่น ควรกินกี่แคลอรี่)
ให้ตอบเป็นหลักการทั่วไปพร้อมช่วงค่าที่แนะนำ แล้วชวนให้ไปกรอกโปรไฟล์เพื่อรับตัวเลขเฉพาะบุคคล
"""

NO_CONTEXT_NOTE = """\
ไม่พบข้อมูลอ้างอิงที่เกี่ยวข้องกับคำถามนี้ในฐานความรู้
ให้บอกผู้ใช้ตามตรงว่าฐานความรู้ยังไม่ครอบคลุมเรื่องนี้ ตอบได้เฉพาะหลักการกว้าง ๆ ที่มั่นใจ
และห้ามอ้างอิงตัวเลขหรืองานวิจัยที่ไม่ได้อยู่ในข้อมูลอ้างอิง
"""


#: Goal-specific framing, injected only when a profile is attached (v1.5.0).
#: Before this, the goal changed one line of numbers and nothing else - a cut
#: user and a bulk user got byte-identical guidance around those numbers. Each
#: entry paraphrases the energy-balance-cut-bulk knowledge card so the framing
#: cannot drift from what retrieval would cite. Keyed by the *effective* goal
#: the calculator used (an underweight user's "cut" is served as "maintain"),
#: so the framing always matches the numbers shown.
GOAL_GUIDANCE_TH: dict[str, str] = {
    "cut": (
        "แนวทางสำหรับเป้าหมายลดไขมัน (cut): ใช้พลังงานเป้าหมายที่ระบบคำนวณ (ขาดดุลราว 15-20% ของ TDEE) "
        "คาดหวังน้ำหนักลดราว 0.5-1% ของน้ำหนักตัวต่อสัปดาห์ คงโปรตีนให้สูงและคงการฝึกแรงต้าน "
        "ลดพลังงานจากคาร์บและไขมันเป็นหลักโดยไขมันไม่ต่ำกว่า 20% ของพลังงาน "
        "ห้ามแนะนำให้ลดพลังงานต่ำกว่าเป้าหมายที่ระบบคำนวณเพื่อให้เห็นผลเร็วขึ้น "
        "ถ้าผู้ใช้ขอลดเร็วกว่านี้ ให้อธิบายผลเสีย (เสียกล้ามเนื้อ แรงตก ภาวะ EA ต่ำ/RED-S) แล้วยืนยันเป้าเดิม"
    ),
    "bulk": (
        "แนวทางสำหรับเป้าหมายเพิ่มกล้ามเนื้อ (bulk): ใช้พลังงานเป้าหมายที่ระบบคำนวณ (เกินดุลราว 10-15% ของ TDEE) "
        "คาดหวังน้ำหนักเพิ่มราว 0.25-0.5% ของน้ำหนักตัวต่อสัปดาห์ ผู้เริ่มฝึกใช้ช่วงบนได้ ผู้ฝึกมานานควรช้ากว่า "
        "เตือนว่าการกินเกินมาก (dirty bulk) เปลี่ยนเป็นไขมันเป็นหลัก ไม่ได้ให้กล้ามเนื้อเพิ่มตามสัดส่วนที่กินเกิน "
        "และเน้นให้โปรตีนถึงเป้ากับฝึกแรงต้านอย่างสม่ำเสมอ"
    ),
    "maintain": (
        "แนวทางสำหรับเป้าหมายรักษาน้ำหนัก (maintain): พลังงานเป้าหมายเท่ากับ TDEE "
        "เน้นโปรตีนให้เพียงพอและการฝึกแรงต้านเพื่อปรับองค์ประกอบร่างกาย (recomposition) "
        "ปรับตัวเลขตามน้ำหนักจริงที่เปลี่ยนแปลงใน 2-4 สัปดาห์ ไม่ต้องขาดดุลหรือเกินดุลเพื่อเร่งผล "
        "ถ้าผู้ใช้ถามว่าจะเร่งผลให้เร็วขึ้นได้อย่างไร ให้ยืนยันตัวเลข TDEE เดิมก่อน แล้วถามว่าต้องการลดไขมันหรือ"
        "เพิ่มกล้ามเนื้อ และชวนให้เปลี่ยนเป้าหมายในโปรไฟล์เพื่อให้ระบบคำนวณตัวเลขใหม่ให้ "
        "ห้ามเสนอเปอร์เซ็นต์ขาดดุลหรือเกินดุลให้ผู้ใช้ไปคำนวณเอง"
    ),
}


#: Age at which the Thai DRI iron table switches women from the reproductive-age
#: row (20 mg/day) to the post-menopause row (10 mg/day). Card calcium-iron-vitd.
FEMALE_IRON_HIGH_RDA_MAX_AGE = 50


def sex_guidance_th(sex: str | None, age: int | None) -> str | None:
    """Sex-specific framing, injected only when a profile is attached (v1.6.0).

    Before this the profile line said "เพศ หญิง"/"เพศ ชาย" and nothing else
    used it. eval/reports/goal_sex_personalization_v1.md: a woman's answers did
    reach for the female-specific facts in the knowledge base (iron, menstrual
    disruption as a low-EA sign), but so did a man's - both "watch out for"
    answers told a male user about menstrual irregularity, because the model was
    reciting the card rather than filtering it for the person in front of it.
    Every sentence here paraphrases cards calcium-iron-vitd and
    energy-balance-cut-bulk, so the framing cannot drift from what retrieval
    would cite.
    """
    if sex == "female":
        if age is not None and age > FEMALE_IRON_HIGH_RDA_MAX_AGE:
            return (
                "ผู้ใช้เป็นหญิงอายุมากกว่า 50 ปี: ค่าอ้างอิงธาตุเหล็กของหญิงหลังหมดประจำเดือนคือ 10 มก./วัน "
                "(ไม่ใช่ 20 มก. ของหญิงวัยเจริญพันธุ์) ไม่ต้องยกเรื่องประจำเดือนเป็นสัญญาณของภาวะพลังงานต่ำ "
                "ให้เน้นแคลเซียมและวิตามินดีต่อความหนาแน่นกระดูกแทน"
            )
        return (
            "ผู้ใช้เป็นหญิงวัยเจริญพันธุ์: เมื่อพูดถึงวิตามิน/แร่ธาตุที่ควรระวังระหว่างคุมอาหาร ต้องยกธาตุเหล็กขึ้นมา "
            "ค่าอ้างอิงคนไทยสำหรับหญิง 19-50 ปีคือ 20 มก./วัน (เกือบสองเท่าของชาย) เพราะสูญเสียไปกับประจำเดือน "
            "ผู้หญิงที่ฝึกหนัก กินน้อย และเลี่ยงเนื้อแดงเป็นกลุ่มเสี่ยงเหล็กต่ำ ถ้าสงสัยให้ตรวจเลือด ไม่ซื้อเหล็กเสริมกินเอง "
            "และเมื่อพูดถึงสัญญาณว่ากินน้อยเกินไป/EA ต่ำ ต้องยกประจำเดือนขาดหรือมาไม่ปกติเป็นสัญญาณสำคัญของผู้ใช้คนนี้"
        )
    if sex == "male":
        return (
            "ผู้ใช้เป็นชาย: ค่าอ้างอิงธาตุเหล็กของชาย 19-60 ปีคือ 11.5 มก./วัน ไม่ต้องยกค่า 20 มก. ของหญิง "
            "และห้ามยกเรื่องประจำเดือนขึ้นมาเป็นสัญญาณหรือข้อควรระวังของผู้ใช้คนนี้ แม้จะใส่วงเล็บว่า \"ในผู้หญิง\" ก็ตาม "
            "สัญญาณ EA ต่ำที่ใช้กับผู้ใช้คนนี้คือ ฟื้นตัวช้า บาดเจ็บถี่ เจ็บป่วยบ่อย แรงตก นอนไม่ดี และแรงขับทางเพศลดลง"
        )
    return None


def build_profile_block(
    profile_summary: str | None,
    targets_summary: str | None,
    goal: str | None = None,
    sex: str | None = None,
    age: int | None = None,
) -> str:
    """Render the user-context section of the system prompt."""
    if not profile_summary:
        return NO_PROFILE_NOTE
    parts = ["ข้อมูลผู้ใช้:", profile_summary]
    if targets_summary:
        parts += ["", "เป้าหมายที่ระบบคำนวณไว้แล้ว (ใช้ตัวเลขนี้ได้เลย ไม่ต้องเรียกเครื่องมือซ้ำ):", targets_summary]
    guidance = GOAL_GUIDANCE_TH.get(goal or "")
    if guidance:
        parts += ["", guidance]
    sex_note = sex_guidance_th(sex, age)
    if sex_note:
        parts += ["", sex_note]
    return "\n".join(parts)


def build_context_block(passages: list[dict]) -> str:
    """Render retrieved chunks as a numbered [S1]..[Sk] reference block.

    ``passages`` items are dicts with keys: ``label``, ``title``, ``heading``,
    ``content`` (see services/retrieval.py).
    """
    if not passages:
        return NO_CONTEXT_NOTE
    lines = ["ข้อมูลอ้างอิง (ใช้หมายเลขนี้อ้างอิงในคำตอบ):", ""]
    for p in passages:
        heading = f" - {p['heading']}" if p.get("heading") else ""
        lines.append(f"[{p['label']}] {p['title']}{heading}")
        lines.append(p["content"].strip())
        lines.append("")
    return "\n".join(lines)


def build_system_prompt(
    *,
    profile_summary: str | None = None,
    targets_summary: str | None = None,
    passages: list[dict] | None = None,
    guard_instructions: str = "",
    use_rag: bool = True,
    goal: str | None = None,
    sex: str | None = None,
    age: int | None = None,
) -> str:
    """Assemble the full system prompt.

    ``use_rag=False`` is the ablation arm of the evaluation: identical prompt,
    minus the retrieved context block and the citation instruction.
    """
    blocks = [
        BASE_SYSTEM_PROMPT,
        build_profile_block(profile_summary, targets_summary, goal, sex, age),
    ]

    if use_rag:
        blocks.append(build_context_block(passages or []))
    else:
        blocks.append(
            "โหมดนี้ไม่มีข้อมูลอ้างอิงจากฐานความรู้ ให้ตอบจากความรู้ทั่วไป "
            "และไม่ต้องใส่หมายเลขอ้างอิง [S1] ในคำตอบ"
        )

    if guard_instructions:
        blocks.append(guard_instructions)

    return "\n\n".join(b.strip() for b in blocks if b and b.strip())
