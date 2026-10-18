"use client";

import groups from "@/lib/dietary-options.json";

export function dietaryLabel(value: string): string {
  return groups.flatMap((group) => group.options).find((item) => item.value === value)?.label ?? value;
}

export function DietaryRestrictionFields({ value, original, onChange }: {
  value: string[]; original: string[]; onChange: (next: string[]) => void;
}) {
  const known = new Set(groups.flatMap((group) => group.options.map((item) => item.value)));
  const extras = [...new Set([...original, ...value])].filter((item) => !known.has(item));
  const removed = original.filter((item) => /^(แพ้|ข้อจำกัดที่ยังไม่รองรับ:)/.test(item) && !value.includes(item));
  function toggle(item: string) {
    onChange(value.includes(item) ? value.filter((v) => v !== item) : [...value, item]);
  }
  const displayed = [...groups, ...(extras.length ? [{ label: "ข้อจำกัดอื่นที่เคยแจ้ง", options: extras.map((item) => ({value: item, label: item})) }] : [])];
  return <div className="space-y-4">
    <p className="text-sm text-muted">เลือกข้อแพ้ที่ทราบทั้งหมด หากยังไม่ทราบชนิดถั่ว ให้คงตัวเลือก “แพ้ถั่ว — ยังไม่ระบุชนิด” ไว้</p>
    {displayed.map((group) => <fieldset key={group.label} className="space-y-2">
      <legend className="mb-2 font-medium">{group.label}</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {group.options.map((item) => <label key={item.value} className="flex min-w-0 items-start gap-2 rounded-sm border border-border p-3 text-sm">
          <input type="checkbox" checked={value.includes(item.value)} onChange={() => toggle(item.value)} className="mt-1 shrink-0" />
          <span className="wrap-anywhere">{item.label}</span>
        </label>)}
      </div>
    </fieldset>)}
    {value.includes("แพ้ถั่ว") && <p className="rounded-sm bg-macro-carb-soft p-3 text-sm">
      ตัวเลือกแพ้ถั่วแบบเดิมครอบคลุมถั่วและโปรตีนพืชหลายชนิด เมื่อระบุชนิดได้แล้ว ให้ตรวจข้อแพ้ทั้งหมดก่อนนำตัวเลือกเดิมออก
    </p>}
    {removed.length > 0 && <div className="block rounded-sm border border-border p-3 text-sm">
      <span className="mb-2 block">กำลังนำข้อแพ้เดิมออก: {removed.map(dietaryLabel).join(" / ")}</span>
      <label className="flex items-start gap-2">
        <input key={JSON.stringify(removed)} name="confirm-allergy-changes" type="checkbox" required className="mt-1 shrink-0" />
        <span>ฉันตรวจสอบแล้วว่าข้อแพ้ที่เลือกไว้ครบถ้วน และยืนยันการเปลี่ยนรายการเดิม</span>
      </label>
    </div>}
    <p className="text-xs text-muted">ระบบกรองจากข้อมูลอาหารที่มี กรุณาตรวจฉลาก ส่วนผสม และการปนเปื้อนของอาหารจริงด้วย</p>
  </div>;
}
