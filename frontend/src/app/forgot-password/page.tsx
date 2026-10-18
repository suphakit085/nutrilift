"use client";

import { useEffect, useState } from "react";
import AccountShell, { accountButtonClass, accountInputClass } from "@/components/AccountShell";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [available, setAvailable] = useState<boolean | null>(null);
  const [cooldown, setCooldown] = useState(false);
  useEffect(() => {
    let active = true;
    api.emailStatus().then(value => { if (active) setAvailable(value.available); }).catch(() => { if (active) setAvailable(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!cooldown) return;
    const timer = setTimeout(() => setCooldown(false), 60_000);
    return () => clearTimeout(timer);
  }, [cooldown]);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try { setNotice((await api.forgotPassword(email)).message); setCooldown(true); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <AccountShell title="ลืมรหัสผ่าน" description="กรอกอีเมลที่ใช้สมัคร เราจะส่งลิงก์ตั้งรหัสผ่านใหม่ให้เมื่อมีบัญชีที่ตรงกัน">
    {available === false && <p role="alert" className="mb-4 text-sm text-red-600">บริการส่งอีเมลยังไม่พร้อม กรุณาติดต่อผู้ดูแลระบบ</p>}
    {error && <p role="alert" className="mb-4 text-sm text-red-600">{error}</p>}
    {notice && <p role="status" className="mb-4 text-sm leading-relaxed">{notice}</p>}
    <form onSubmit={submit} className="space-y-4">
      <label className="block text-sm">อีเมล<input name="email" type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} className={accountInputClass} /></label>
      <button disabled={busy || cooldown || available !== true} className={accountButtonClass}>{busy ? "กำลังส่ง…" : cooldown ? "ขอใหม่ได้ในประมาณ 1 นาที" : "ส่งลิงก์ตั้งรหัสผ่านใหม่"}</button>
    </form>
  </AccountShell>;
}
