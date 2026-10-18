"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, getToken, setToken, type AccountSession, type CurrentUser } from "@/lib/api";
import { passwordProblem } from "@/lib/account-validation";
import { accountButtonClass, accountInputClass } from "@/components/AccountShell";
import NewPasswordFields from "@/components/NewPasswordFields";

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [sessions, setSessions] = useState<AccountSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [privacyPassword, setPrivacyPassword] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!getToken()) { router.replace("/login"); return; }
    let active = true;
    (async () => {
      try {
        const [me, rows] = await Promise.all([api.me(), api.listSessions()]);
        if (active) { setUser(me); setSessions(rows); }
      } catch (err) { if (active) setError((err as Error).message); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [router, retry]);
  useEffect(() => { if (error) alertRef.current?.focus(); }, [error]);

  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await action(); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  function signedOut() { setToken(null); router.replace("/login"); }

  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    const problem = passwordProblem(newPassword, confirmPassword);
    if (problem) { setError(problem); return; }
    await perform(async () => {
      const result = await api.changePassword(password, newPassword);
      setToken(result.access_token);
      setPassword(""); setNewPassword(""); setConfirmPassword("");
      setSessions(await api.listSessions());
      setNotice("เปลี่ยนรหัสผ่านแล้ว และยกเลิกการเข้าสู่ระบบเดิมทุกเครื่อง เครื่องนี้ใช้การเข้าสู่ระบบใหม่แล้ว");
    });
  }

  async function changeEmail(event: React.FormEvent) {
    event.preventDefault();
    await perform(async () => {
      setNotice((await api.changeEmail(newEmail, emailPassword)).message);
      setEmailPassword("");
    });
  }

  async function exportData() {
    await perform(async () => {
      const data = await api.exportAccount();
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = "nutrilift-data.json"; link.click();
      URL.revokeObjectURL(url);
      setNotice("ดาวน์โหลดข้อมูลของคุณแล้ว");
    });
  }

  async function withdraw() {
    if (!privacyPassword) { setError("กรุณากรอกรหัสผ่านปัจจุบันเพื่อยืนยัน"); return; }
    if (!window.confirm("ถอนความยินยอมและออกจากระบบทุกเครื่อง? ข้อมูลจะยังเก็บอยู่ หากต้องการลบให้ใช้การลบบัญชี")) return;
    await perform(async () => { await api.withdrawConsent(privacyPassword); signedOut(); });
  }

  async function removeAccount(event: React.FormEvent) {
    event.preventDefault();
    if (deleteConfirm !== "ลบบัญชี") { setError("กรุณาพิมพ์ ลบบัญชี เพื่อยืนยัน"); return; }
    if (!window.confirm("ยืนยันลบบัญชี โปรไฟล์ ประวัติแชต และบันทึกอาหารทั้งหมด? การลบย้อนกลับไม่ได้")) return;
    await perform(async () => { await api.deleteAccount(privacyPassword); signedOut(); });
  }

  const panel = "rounded-lg border border-border bg-surface p-6";
  const secondary = "rounded-md border border-border px-4 py-2 text-sm transition hover:border-accent disabled:opacity-40";
  if (loading) return <main className="flex min-h-screen items-center justify-center"><p role="status" className="text-muted">กำลังโหลดบัญชี…</p></main>;

  return <main className="mx-auto max-w-2xl px-6 py-10">
    <header className="mb-7 flex flex-wrap items-center justify-between gap-3">
      <h1 className="font-display text-2xl font-bold">บัญชีและความปลอดภัย</h1>
      <Link href="/chat" className={secondary}>ไปหน้าแชต</Link>
    </header>
    {error && <div role="alert" ref={alertRef} tabIndex={-1} className="mb-5 rounded-sm border border-red-500/20 p-4 text-sm text-red-600 outline-none">{error}</div>}
    {notice && <p role="status" className="mb-5 rounded-sm border border-border p-4 text-sm">{notice}</p>}
    {!user ? <button className={secondary} onClick={() => { setLoading(true); setError(""); setRetry(value => value + 1); }}>ลองโหลดอีกครั้ง</button> : <div className="space-y-6">
      <section className={panel}>
        <h2 className="font-display font-semibold">อีเมลบัญชี</h2>
        <p className="mt-2 break-all text-sm">{user.email}</p>
        <p className="mt-1 text-xs text-muted">{user.email_verified ? "ยืนยันอีเมลแล้ว" : "ยังไม่ได้ยืนยันอีเมล"}</p>
        {!user.email_verified && <Link href="/verify-email" className="mt-3 inline-block text-sm underline">ยืนยันอีเมลเพื่อเริ่มใช้งาน</Link>}
        {user.needs_consent && user.email_verified && <Link href="/consent" className="mt-3 block text-sm underline">อ่านและให้ความยินยอมก่อนใช้งานต่อ</Link>}
        <button disabled={busy} onClick={() => perform(async () => { await api.logout(); signedOut(); })} className={`${secondary} mt-4 block`}>ออกจากระบบเครื่องนี้</button>
      </section>
      <section className={panel}>
        <h2 className="mb-4 font-display font-semibold">เปลี่ยนรหัสผ่าน</h2>
        <form onSubmit={changePassword}><fieldset disabled={busy} className="space-y-4">
          <label className="block text-sm">รหัสผ่านปัจจุบัน<input name="current-password" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} className={accountInputClass} /></label>
          <NewPasswordFields password={newPassword} confirm={confirmPassword} onPassword={setNewPassword} onConfirm={setConfirmPassword} />
          <button className={accountButtonClass}>เปลี่ยนรหัสผ่าน</button>
        </fieldset></form>
      </section>
      <section className={panel}>
        <h2 className="font-display font-semibold">เปลี่ยนอีเมล</h2>
        <p className="mt-2 mb-4 text-xs leading-relaxed text-muted">อีเมลเดิมยังใช้ได้จนกว่าจะยืนยันลิงก์ที่ส่งไปอีเมลใหม่ หลังยืนยันจะออกจากระบบทุกเครื่อง</p>
        <form onSubmit={changeEmail}><fieldset disabled={busy || !user.email_verified} className="space-y-4 disabled:opacity-50">
          <label className="block text-sm">อีเมลใหม่<input name="new-email" type="email" autoComplete="email" required value={newEmail} onChange={event => setNewEmail(event.target.value)} className={accountInputClass} /></label>
          <label className="block text-sm">รหัสผ่านปัจจุบัน<input name="email-current-password" type="password" autoComplete="current-password" required value={emailPassword} onChange={event => setEmailPassword(event.target.value)} className={accountInputClass} /></label>
          <button className={accountButtonClass}>ส่งลิงก์ยืนยันอีเมลใหม่</button>
        </fieldset></form>
      </section>
      <section className={panel}>
        <h2 className="font-display font-semibold">การเข้าสู่ระบบที่ยังใช้งานได้</h2>
        <ul className="mt-4 divide-y divide-border">{sessions.map(session => <li key={session.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
          <div><span>{session.is_current ? "การเข้าสู่ระบบนี้" : "การเข้าสู่ระบบอื่น"}</span><p className="mt-1 text-xs text-muted">เริ่ม {new Date(session.created_at).toLocaleString("th-TH")} · หมดอายุ {new Date(session.expires_at).toLocaleString("th-TH")}</p></div>
          {!session.is_current && <button disabled={busy} className={secondary} onClick={() => perform(async () => { await api.revokeSession(session.id); setSessions(await api.listSessions()); setNotice("ยกเลิกการเข้าสู่ระบบที่เลือกแล้ว"); })}>ยกเลิก</button>}
        </li>)}</ul>
        <button disabled={busy} className={`${secondary} mt-4`} onClick={() => perform(async () => { await api.logoutAll(); signedOut(); })}>ออกจากระบบทุกเครื่อง</button>
      </section>
      <section className={panel}>
        <h2 className="font-display font-semibold">ข้อมูลของคุณ</h2>
        <p className="mt-2 text-xs leading-relaxed text-muted">ดาวน์โหลดข้อมูลบัญชี โปรไฟล์ ประวัติแชต และบันทึกอาหารเป็นไฟล์ JSON</p>
        <button disabled={busy || !user.email_verified} className={`${secondary} mt-4`} onClick={exportData}>ดาวน์โหลดข้อมูลของฉัน</button>
      </section>
      <section className={`${panel} border-red-500/30`}>
        <h2 className="font-display font-semibold">ความยินยอมและการลบบัญชี</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">ถอนความยินยอมจะหยุดการใช้งานและออกจากระบบทุกเครื่อง ข้อมูลยังคงอยู่ หากต้องการลบข้อมูลทั้งหมดให้เลือกลบบัญชี</p>
        <form onSubmit={removeAccount}><fieldset disabled={busy} className="mt-4 space-y-4">
          <label className="block text-sm">รหัสผ่านปัจจุบันเพื่อยืนยัน<input name="privacy-password" type="password" autoComplete="current-password" required value={privacyPassword} onChange={event => setPrivacyPassword(event.target.value)} className={accountInputClass} /></label>
          <button type="button" className={secondary} onClick={withdraw}>ถอนความยินยอมและออกจากระบบ</button>
          <label className="block text-sm">พิมพ์ ลบบัญชี เพื่อยืนยันการลบถาวร<input name="delete-confirmation" autoComplete="off" value={deleteConfirm} onChange={event => setDeleteConfirm(event.target.value)} className={accountInputClass} /></label>
          <p className="text-xs text-muted">ลบบัญชีแล้ว โปรไฟล์ ประวัติแชต และบันทึกอาหารจะถูกลบและกู้คืนผ่านแอปไม่ได้</p>
          <button disabled={deleteConfirm !== "ลบบัญชี"} className="rounded-md border border-red-500/40 px-5 py-2.5 text-sm text-red-600 disabled:opacity-40">ลบบัญชีและข้อมูลทั้งหมด</button>
        </fieldset></form>
      </section>
    </div>}
  </main>;
}
