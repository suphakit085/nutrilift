"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";
import ConsentNotice from "@/components/ConsentNotice";

/** Mirrors PASSWORD_MAX_BYTES in backend/app/api/schemas.py. bcrypt hashes at
 *  most 72 bytes, and Thai is 3 bytes per character - so a Thai passphrase runs
 *  out at ~24 characters, well inside what anyone would consider a short
 *  password. The server rejects it either way; showing the limit here means a
 *  Thai user is not told "too long" only after pressing สมัครสมาชิก. */
const PASSWORD_MAX_BYTES = 72;

function byteLength(value: string) {
  return new TextEncoder().encode(value).length;
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [isAdult, setIsAdult] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const errorRef = useRef<HTMLParagraphElement>(null);

  const registering = mode === "register";
  const bytes = byteLength(password);
  const tooLong = bytes > PASSWORD_MAX_BYTES;
  const mismatch = registering && confirm.length > 0 && password !== confirm;

  // Moving focus to the message is what makes it reachable: a screen reader
  // announces the alert, and a keyboard user is not left at the bottom of the
  // form wondering why nothing happened.
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  function switchMode(value: "login" | "register") {
    setMode(value);
    setError("");
    setConfirm("");
    setAcceptedTerms(false);
    setIsAdult(false);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (registering) {
      if (tooLong) {
        setError(
          `รหัสผ่านยาวเกินไป (${bytes}/${PASSWORD_MAX_BYTES} ไบต์) ภาษาไทยใช้ได้ประมาณ 24 ตัวอักษร`,
        );
        return;
      }
      if (password !== confirm) {
        setError("รหัสผ่านทั้งสองช่องไม่ตรงกัน");
        return;
      }
    }
    setError("");
    setBusy(true);
    try {
      const result = registering
        ? await api.register(email, password, {
            accepted_terms: acceptedTerms,
            is_adult: isAdult,
          })
        : await api.login(email, password);
      setToken(result.access_token);
      if (registering) {
        router.push("/profile");
        return;
      }
      // An account created before consent was recorded, or one that predates a
      // reworded notice, has to agree before it can reach any data route -
      // asking here is friendlier than letting /chat bounce off a 403.
      const me = await api.me();
      router.push(me.needs_consent ? "/consent" : "/chat");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const inputClass =
    "w-full rounded-sm border border-border bg-surface-sunken px-3.5 py-2.5 outline-none transition focus:border-accent focus:bg-surface";

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-7 text-center">
          <span className="inline-flex h-12 w-12 items-center justify-center rounded-md bg-cta text-cta-foreground">
            <LeafIcon className="h-6 w-6" />
          </span>
          <h1 className="mt-4 font-display text-2xl font-bold uppercase tracking-tight">NutriLift</h1>
          <p className="mt-1.5 text-sm text-muted">
            แชตบอทโภชนาการสำหรับผู้ฝึกเวทเทรนนิ่ง
          </p>
        </div>

        <div className="rounded-lg border border-border bg-surface p-7">
          <div className="flex border border-border p-1 text-sm">
            {(["login", "register"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => switchMode(value)}
                aria-pressed={mode === value}
                className={`flex-1 rounded-sm py-2 transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                  mode === value
                    ? "bg-cta font-medium text-cta-foreground"
                    : "text-muted hover:text-foreground"
                }`}
              >
                {value === "login" ? "เข้าสู่ระบบ" : "สมัครสมาชิก"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <label className="block">
              <span className="field-label text-xs text-muted">อีเมล</span>
              <input
                type="email"
                name="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={`mt-1.5 ${inputClass}`}
              />
            </label>

            <div>
              <label className="block">
                <span className="field-label text-xs text-muted">รหัสผ่าน</span>
                <div className="relative mt-1.5">
                  <input
                    type={showPassword ? "text" : "password"}
                    name="password"
                    // A password manager needs to be told which of the two this
                    // is, or it offers the saved password on a signup form and
                    // saves nothing on a real one.
                    autoComplete={registering ? "new-password" : "current-password"}
                    required
                    // Only a new password owes the minimum; enforcing it at sign-in
                    // would lock out any account whose password predates the rule.
                    minLength={registering ? 8 : undefined}
                    aria-describedby={registering ? "password-hint" : undefined}
                    aria-invalid={registering && tooLong ? true : undefined}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className={`${inputClass} pr-16`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-pressed={showPassword}
                    className="absolute inset-y-0 right-0 px-3 text-xs text-muted transition hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  >
                    {showPassword ? "ซ่อน" : "แสดง"}
                  </button>
                </div>
              </label>
              {registering && (
                <span
                  id="password-hint"
                  className={`mt-1.5 block text-xs ${tooLong ? "text-red-600" : "text-muted"}`}
                >
                  {tooLong
                    ? `ยาวเกินไป ${bytes}/${PASSWORD_MAX_BYTES} ไบต์ — ภาษาไทยใช้ได้ประมาณ 24 ตัวอักษร`
                    : "อย่างน้อย 8 ตัวอักษร · ภาษาไทยใช้ได้ประมาณ 24 ตัวอักษร"}
                </span>
              )}
            </div>

            {registering && (
              <div>
                <label className="block">
                  <span className="field-label text-xs text-muted">ยืนยันรหัสผ่าน</span>
                  {/* There is no password-reset flow, so a typo here is an
                      account nobody can ever get back into. */}
                  <input
                    type={showPassword ? "text" : "password"}
                    name="confirm-password"
                    autoComplete="new-password"
                    required
                    aria-invalid={mismatch ? true : undefined}
                    aria-describedby={mismatch ? "confirm-error" : undefined}
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className={`mt-1.5 ${inputClass}`}
                  />
                </label>
                {mismatch && (
                  <span id="confirm-error" className="mt-1.5 block text-xs text-red-600">
                    รหัสผ่านทั้งสองช่องไม่ตรงกัน
                  </span>
                )}
              </div>
            )}

            {registering && (
              <div className="space-y-3 border-t border-border pt-4">
                <Check
                  checked={isAdult}
                  onChange={setIsAdult}
                  invalidMessage="บริการนี้สำหรับผู้ที่มีอายุ 18 ปีขึ้นไป"
                >
                  ฉันมีอายุ <strong className="font-semibold">18 ปีขึ้นไป</strong>
                </Check>

                <Check
                  checked={acceptedTerms}
                  onChange={setAcceptedTerms}
                  invalidMessage="ต้องยอมรับการเก็บและใช้ข้อมูลก่อนจึงจะสมัครได้"
                >
                  ฉันยินยอมให้เก็บและใช้ข้อมูลตามรายละเอียดด้านล่าง
                </Check>

                <ConsentNotice />
              </div>
            )}

            {error && (
              <p
                ref={errorRef}
                role="alert"
                tabIndex={-1}
                className="rounded-sm border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 outline-none"
              >
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy || (registering && (tooLong || mismatch))}
              className="w-full rounded-md bg-cta py-3 font-medium text-cta-foreground transition hover:opacity-85 active:scale-[0.99] disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              {busy ? "กำลังดำเนินการ…" : registering ? "สมัครสมาชิก" : "เข้าสู่ระบบ"}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-muted">
          ระบบนี้ให้ข้อมูลเพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำทางการแพทย์
        </p>
      </div>
    </main>
  );
}

/** A required checkbox whose failure message is Thai. Without setCustomValidity
 *  Chrome shows "Please check this box if you want to proceed." in English no
 *  matter the page language - the same reason the profile form overrides it. */
function Check({
  checked,
  onChange,
  invalidMessage,
  children,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  invalidMessage: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 text-xs leading-[1.7]">
      <input
        type="checkbox"
        required
        checked={checked}
        onChange={(e) => {
          e.currentTarget.setCustomValidity("");
          onChange(e.target.checked);
        }}
        onInvalid={(e) => e.currentTarget.setCustomValidity(invalidMessage)}
        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--accent)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      />
      <span>{children}</span>
    </label>
  );
}

function LeafIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" />
      <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" />
    </svg>
  );
}
