export function passwordProblem(password: string, confirm: string): string {
  if (password.length < 8) return "รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร";
  if (new TextEncoder().encode(password).length > 72) return "รหัสผ่านยาวเกิน 72 ไบต์ ภาษาไทยใช้ได้ประมาณ 24 ตัวอักษร";
  if (password !== confirm) return "รหัสผ่านทั้งสองช่องไม่ตรงกัน";
  return "";
}
