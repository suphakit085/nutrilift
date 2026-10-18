"use client";

import { useState } from "react";
import Link from "next/link";
import AccountShell, { accountButtonClass } from "@/components/AccountShell";
import NewPasswordFields from "@/components/NewPasswordFields";
import { api, setToken } from "@/lib/api";
import { clearEmailLinkToken, useEmailLinkToken } from "@/lib/email-link";
import { passwordProblem } from "@/lib/account-validation";

export default function ResetPasswordPage() {
  const token = useEmailLinkToken();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const problem = passwordProblem(password, confirm);
    if (problem) { setError(problem); return; }
    setBusy(true); setError("");
    try {
      const result = await api.resetPassword(token, password);
      setToken(null); setPassword(""); setConfirm(""); clearEmailLinkToken(); setNotice(result.message);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <AccountShell title="ตั้งรหัสผ่านใหม่" description="หลังตั้งรหัสผ่านใหม่ การเข้าสู่ระบบเดิมทุกเครื่องจะถูกยกเลิก">
    {error && <p role="alert" className="mb-4 text-sm text-red-600">{error}</p>}
    {notice ? <p role="status" className="text-sm">{notice}</p> : token ? <form onSubmit={submit}>
      <fieldset disabled={busy} className="space-y-4">
        <NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
        <button className={accountButtonClass}>{busy ? "กำลังบันทึก…" : "บันทึกรหัสผ่านใหม่"}</button>
      </fieldset>
    </form> : <p className="text-sm text-muted">กรุณาเปิดหน้านี้จากลิงก์รีเซ็ตรหัสผ่านในอีเมล</p>}
    <Link href="/forgot-password" className="mt-5 inline-block text-sm text-muted underline">ขอลิงก์ตั้งรหัสผ่านใหม่</Link>
  </AccountShell>;
}
