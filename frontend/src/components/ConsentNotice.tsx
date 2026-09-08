/** The PDPA notice, in one place.
 *
 *  Two screens ask for the same agreement - the register form and the consent
 *  gate for accounts that predate it - and the backend stores a single
 *  CONSENT_VERSION against whichever one the user saw. If the wording could
 *  differ between them, that stored version would be a lie, so both render this.
 *
 *  It is deliberately NOT inside a <details>. Collapsed, a user could tick
 *  "ยินยอม" without the text ever being on screen, which makes the record
 *  evidence of a click rather than of informed consent.
 *
 *  Keep CONSENT_VERSION in backend/app/api/schemas.py in step with edits here:
 *  changing this text without bumping it leaves existing users marked as having
 *  agreed to wording they never saw. */

/** PDPA: the data controller for this service. Change this to whichever address
 *  should receive access/erasure requests before real participants use it. */
export const CONTACT_EMAIL = "suphakit085@gmail.com";

export default function ConsentNotice() {
  return (
    <div className="space-y-2.5 rounded-sm border border-border bg-surface-sunken px-4 py-3.5 text-xs leading-[1.75] text-muted">
      <p className="font-display text-[11px] font-semibold tracking-[0.02em] text-foreground">
        ข้อมูลที่เก็บและวัตถุประสงค์ (PDPA)
      </p>
      <p>
        <strong className="font-semibold text-foreground">เก็บอะไร:</strong>{" "}
        อีเมล และรหัสผ่านที่เก็บแบบเข้ารหัสทางเดียว (กู้คืนเป็นข้อความเดิมไม่ได้) · เพศ
        ปีและเดือนเกิด ส่วนสูง น้ำหนัก เปอร์เซ็นต์ไขมัน ระดับกิจกรรม จำนวนวันเล่นเวท เป้าหมาย
        และข้อจำกัดด้านอาหาร · ข้อความที่สนทนากับระบบ และรายการอาหารที่คุณบันทึก
      </p>
      <p>
        <strong className="font-semibold text-foreground">ใช้ทำอะไร:</strong>{" "}
        คำนวณเป้าหมายพลังงานและสารอาหารเฉพาะบุคคล และประเมินผลระบบเพื่อจัดทำปริญญานิพนธ์
        ข้อมูลที่ใช้รายงานผลจะสรุปเป็นภาพรวม ไม่ระบุตัวบุคคล และไม่มีการส่งต่อหรือขายให้บุคคลที่สาม
      </p>
      <p>
        <strong className="font-semibold text-foreground">สิทธิของคุณ:</strong> ขอดู แก้ไข
        หรือลบข้อมูลของคุณได้ โดยติดต่อ{" "}
        <a
          href={`mailto:${CONTACT_EMAIL}`}
          className="underline underline-offset-2 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {CONTACT_EMAIL}
        </a>{" "}
        ขณะนี้ระบบยังไม่มีปุ่มลบบัญชีด้วยตนเอง และยังไม่มีระบบรีเซ็ตรหัสผ่าน
      </p>
      <p>
        <strong className="font-semibold text-foreground">ขอบเขต:</strong>{" "}
        ระบบนี้ให้ข้อมูลโภชนาการสำหรับผู้ฝึกเวทเทรนนิ่งเพื่อการศึกษาเท่านั้น
        ไม่ใช่คำแนะนำทางการแพทย์ และไม่ตอบเรื่องโรค อาการป่วย หรือยา
        หากมีโรคประจำตัวหรือกำลังตั้งครรภ์ ควรปรึกษาแพทย์หรือนักกำหนดอาหารก่อนปรับอาหาร
      </p>
    </div>
  );
}
