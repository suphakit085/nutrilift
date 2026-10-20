"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";
import { passwordProblem } from "@/lib/account-validation";
import { accountInputClass, accountButtonClass } from "./AccountShell";
import ConsentNotice from "./ConsentNotice";
import NewPasswordFields from "./NewPasswordFields";

export default function RegistrationFlow({ initialEmail = "" }: { initialEmail?: string }) {
  const router = useRouter();
  const [step, setStep] = useState<"email" | "code" | "password" | "existing">("email");
  const [email, setEmail] = useState(initialEmail);
  const [adult, setAdult] = useState(false);
  const [consent, setConsent] = useState(false);
  const [challenge, setChallenge] = useState("");
  const [code, setCode] = useState("");
  const [grant, setGrant] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const alert = useRef<HTMLParagraphElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (error) alert.current?.focus(); }, [error]);
  useEffect(() => { heading.current?.focus(); }, [step]);
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown(value => Math.max(0, value - 1)), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await action(); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  async function send() {
    await perform(async () => {
      const result = await api.startRegistration(email, { accepted_terms: consent, is_adult: adult });
      setChallenge(result.challenge_id); setCode(""); setGrant("");
      setCooldown(result.resend_after); setNotice(result.message); setStep("code");
    });
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (step === "email") { await send(); return; }
    await perform(async () => {
      if (step === "code") {
        const result = await api.verifyRegistration(challenge, code);
        setCode(""); setNotice(result.message);
        if (result.already_registered) { setStep("existing"); return; }
        if (!result.setup_token) throw new Error("ยืนยันไม่สำเร็จ กรุณาขอรหัสใหม่");
        setGrant(result.setup_token); setNotice(""); setStep("password");
      } else {
        const problem = passwordProblem(password, confirm);
        if (problem) throw new Error(problem);
        const result = await api.finishRegistration(challenge, grant, password);
        setToken(result.access_token); setGrant(""); setPassword(""); setConfirm("");
        router.replace("/profile");
      }
    });
  }
  function restart() {
    setStep("email"); setChallenge(""); setGrant(""); setCode(""); setPassword(""); setConfirm(""); setError(""); setNotice("");
  }
  return <div>
    <p className="mt-6 text-xs text-muted">อีเมล → ยืนยันรหัส → ตั้งรหัสผ่าน</p>
    <h2 ref={heading} tabIndex={-1} className="mt-3 font-display text-lg font-semibold outline-none">{step === "email" ? "เริ่มสมัครด้วยอีเมล" : step === "code" ? "กรอกรหัสยืนยันอีเมล" : step === "password" ? "ตั้งรหัสผ่านของคุณ" : "อีเมลนี้มีบัญชีแล้ว"}</h2>
    {error && <p ref={alert} role="alert" tabIndex={-1} className="mt-4 text-sm text-red-600 outline-none">{error}</p>}
    {notice && <p role="status" className="mt-4 text-sm leading-relaxed">{notice}</p>}
    {step === "existing" ? <div className="mt-5 flex flex-wrap gap-4"><Link href="/login" className={accountButtonClass}>เข้าสู่ระบบ</Link><Link href="/forgot-password" className="text-sm underline">ลืมรหัสผ่าน</Link></div> : <form onSubmit={submit} className="mt-5"><fieldset disabled={busy} className="space-y-4">
      {step === "email" ? <>
        <label className="block text-sm">อีเมล<input name="email" type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} className={accountInputClass} /></label>
        <label className="flex items-start gap-2 text-xs leading-relaxed"><input type="checkbox" required checked={adult} onChange={event => setAdult(event.target.checked)} className="mt-0.5 h-4 w-4 shrink-0" />ฉันมีอายุ 18 ปีขึ้นไป</label>
        <label className="flex items-start gap-2 text-xs leading-relaxed"><input type="checkbox" required checked={consent} onChange={event => setConsent(event.target.checked)} className="mt-0.5 h-4 w-4 shrink-0" />ฉันยินยอมให้เก็บและใช้ข้อมูลตามรายละเอียดด้านล่าง</label>
        <ConsentNotice />
        <p className="text-xs leading-relaxed text-muted">เราจะส่งรหัส 6 หลักไปยังอีเมลนี้ คุณจะตั้งรหัสผ่านหลังยืนยันอีเมลแล้วเพียงครั้งเดียว</p>
      </> : step === "code" ? <>
        <p className="break-all text-sm text-muted">ส่งรหัสไปที่ {email} · รหัสหมดอายุใน 10 นาที</p>
        <label className="block text-sm">รหัสยืนยัน 6 หลัก<input name="email-code" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required value={code} onChange={event => setCode(event.target.value.replace(/[^0-9]/g, "").slice(0, 6))} className={accountInputClass} /></label>
        <p className="text-xs text-muted">หากไม่พบอีเมล กรุณาตรวจสอบโฟลเดอร์สแปม กรอกรหัสผิดได้ไม่เกิน 5 ครั้งต่อรหัส</p>
      </> : <>
        <p className="text-sm text-muted">ยืนยันอีเมลแล้ว ตั้งรหัสผ่านเพื่อใช้เข้าสู่ระบบครั้งต่อไป</p>
        <NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
      </>}
      <button type="submit" className={accountButtonClass}>{busy ? "กำลังดำเนินการ…" : step === "email" ? "ส่งรหัสยืนยัน" : step === "code" ? "ยืนยันรหัส" : "ตั้งรหัสผ่านและเริ่มใช้งาน"}</button>
      {step === "code" && <button type="button" disabled={busy || cooldown > 0} onClick={() => void send()} className="block text-sm underline disabled:opacity-40">{cooldown > 0 ? `ส่งรหัสใหม่ได้ใน ${cooldown} วินาที` : "ส่งรหัสใหม่"}</button>}
    </fieldset></form>}
    {step !== "email" && <button type="button" disabled={busy} onClick={restart} className="mt-5 block text-xs text-muted underline">เริ่มใหม่หรือแก้ไขอีเมล</button>}
  </div>;
}
