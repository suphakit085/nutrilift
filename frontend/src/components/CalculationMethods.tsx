import type { Targets } from "@/lib/api";

export function CalculationMethods({ targets }: { targets: Targets }) {
  if (!targets.calculation_methods?.length) return <p className="text-sm text-muted">ผลเก่านี้ไม่มีรายละเอียดสูตรครบทุกค่า กรุณาคำนวณจากโปรไฟล์ปัจจุบันเพื่อดูสูตรที่ใช้งานจริง</p>;
  return <section aria-label="สูตรที่ใช้คำนวณจริง" className="space-y-4">
    <h3 className="text-base font-semibold">สูตรที่ใช้คำนวณจริง</h3>
    <p className="text-xs leading-relaxed text-muted">เลือกสมการจากข้อมูลโปรไฟล์ ใช้ค่าก่อนปัดคำนวณ และปัดเฉพาะผลที่แสดง สูตรเป็นการประมาณ ไม่ใช่ผลตรวจหรือการวินิจฉัยโรค</p>
    {targets.calculation_methods.map(method => <div key={method.key} className="border-t border-border pt-3">
      <p className="text-sm font-semibold">{method.name}</p>
      <p className="mt-1 break-words text-sm">{method.equation} ≈ {method.result.toLocaleString("th-TH")} {method.unit}</p>
      <p className="mt-1 text-xs leading-relaxed text-muted">{method.basis}</p>
      {method.source_url && <a className="mt-1 inline-block text-xs text-accent underline underline-offset-4" href={method.source_url} target="_blank" rel="noopener noreferrer">แหล่งอ้างอิงของวิธีนี้</a>}
    </div>)}
  </section>;
}
