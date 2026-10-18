"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AccountShell, { accountButtonClass, accountInputClass } from "@/components/AccountShell";
import { api, getToken, setToken } from "@/lib/api";
import { clearEmailLinkToken, useEmailLinkToken } from "@/lib/email-link";
import NewPasswordFields from "@/components/NewPasswordFields";
import { passwordProblem } from "@/lib/account-validation";

export default function EmailActionPage({ purpose }: { purpose: "verify" | "change" }) {
  const token = useEmailLinkToken();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [cooldown, setCooldown] = useState(false);
  const [mailAvailable, setMailAvailable] = useState<boolean | null>(null);
  const [continueHref, setContinueHref] = useState("/login");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const changing = purpose === "change";

  useEffect(() => {
    let active = true;
    api.emailStatus().then(value => { if (active) setMailAvailable(value.available); }).catch(() => { if (active) setMailAvailable(false); });
    if (!changing && !token && getToken()) api.me().then(user => {
      if (!active) return;
      setEmail(user.email);
      if (user.email_verified) { setDone(true); setNotice("อีเมลนี้ยืนยันแล้ว"); setContinueHref(user.needs_consent ? "/consent" : "/chat"); }
    }).catch(() => {});
    return () => { active = false; };
  }, [changing, token]);

  useEffect(() => {
    if (!cooldown) return;
    const timer = setTimeout(() => setCooldown(false), 60_000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function confirmLink() {
    if (!changing) {
      const problem = passwordProblem(password, confirm);
      if (problem) { setError(problem); return; }
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const result = changing ? await api.confirmEmail(token) : await api.verifyEmail(token, password);
      clearEmailLinkToken();
      setToken(null); setPassword(""); setConfirm(""); setContinueHref("/login");
      setDone(true); setNotice(result.message);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function resend(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try { setNotice((await api.resendVerification(email)).message); setCooldown(true); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return <AccountShell title={changing ? "ยืนยันอีเมลใหม่" : "ยืนยันอีเมลของคุณ"} description={changing ? "กดยืนยันเพื่อเปลี่ยนอีเมลบัญชี หลังสำเร็จจะออกจากระบบทุกเครื่อง" : "ยืนยันว่าคุณเป็นเจ้าของอีเมลก่อนใช้โปรไฟล์ แชต และบันทึกอาหาร บัญชีเดิมต้องยืนยันอีเมลก่อนใช้งานต่อ"}>
    {error && <p role="alert" className="mb-4 rounded-sm border border-red-500/20 p-3 text-sm text-red-600">{error}</p>}
    {notice && <p role="status" className="mb-4 text-sm leading-relaxed">{notice}</p>}
    {done ? <Link href={changing ? "/login" : continueHref} className={accountButtonClass}>ดำเนินการต่อ</Link> : token ? <form onSubmit={event => { event.preventDefault(); void confirmLink(); }}><fieldset disabled={busy} className="space-y-4">
      {!changing && <><p className="text-sm text-muted">ตั้งรหัสผ่านเพื่อยืนยันสิทธิ์บัญชี รหัสผ่านนี้จะแทนรหัสที่กรอกตอนสมัคร และออกจากระบบเดิมทุกเครื่อง</p><NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} /></>}
      <button className={accountButtonClass}>{busy ? "กำลังยืนยัน…" : changing ? "ยืนยันเปลี่ยนอีเมล" : "ยืนยันอีเมลและตั้งรหัสผ่าน"}</button>
    </fieldset></form> : changing ? <p className="text-sm text-muted">กรุณาเปิดหน้านี้จากลิงก์ในอีเมลใหม่ หากลิงก์หมดอายุ ให้ขอใหม่ในหน้าบัญชี</p> : <>
      <p className="mb-5 text-sm leading-relaxed text-muted">เปิดลิงก์ในอีเมลที่ได้รับ หากไม่พบให้ตรวจสอบโฟลเดอร์สแปมหรือขอลิงก์ใหม่ด้านล่าง</p>
      {mailAvailable === false && <p role="alert" className="mb-4 text-sm text-red-600">บริการส่งอีเมลยังไม่พร้อม กรุณาติดต่อผู้ดูแลระบบ</p>}
      <form onSubmit={resend} className="space-y-4">
        <label className="block text-sm">อีเมล<input name="email" type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} className={accountInputClass} /></label>
        <button disabled={busy || cooldown || mailAvailable !== true} className={accountButtonClass}>{busy ? "กำลังส่ง…" : cooldown ? "ขอใหม่ได้ในประมาณ 1 นาที" : "ส่งลิงก์ยืนยันอีกครั้ง"}</button>
      </form>
      <Link href="/account" className="mt-5 inline-block text-xs text-muted underline">จัดการบัญชีหรือออกจากระบบ</Link>
    </>}
    {token && !done && (changing ? <Link href="/account" className="mt-5 block text-sm underline">ขอลิงก์ใหม่ในหน้าบัญชี</Link> : <button type="button" onClick={clearEmailLinkToken} className="mt-5 block text-sm underline">ขอลิงก์ยืนยันใหม่</button>)}
  </AccountShell>;
}
