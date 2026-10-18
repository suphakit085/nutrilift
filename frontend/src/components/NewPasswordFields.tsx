import { accountInputClass } from "@/components/AccountShell";

export default function NewPasswordFields({ password, confirm, onPassword, onConfirm }: { password: string; confirm: string; onPassword: (value: string) => void; onConfirm: (value: string) => void }) {
  return <>
    <label className="block text-sm">รหัสผ่านใหม่
      <input name="new-password" type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={password} onChange={event => onPassword(event.target.value)} className={accountInputClass} aria-describedby="new-password-help" />
    </label>
    <p id="new-password-help" className="text-xs text-muted">อย่างน้อย 8 ตัวอักษร ไม่เกิน 72 ไบต์ (ภาษาไทยประมาณ 24 ตัวอักษร)</p>
    <label className="block text-sm">ยืนยันรหัสผ่านใหม่
      <input name="confirm-new-password" type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={confirm} onChange={event => onConfirm(event.target.value)} className={accountInputClass} />
    </label>
  </>;
}
