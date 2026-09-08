"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, setToken } from "@/lib/api";
import ConsentNotice from "@/components/ConsentNotice";

/** The gate for accounts that owe consent.
 *
 *  Two ways in: signing in with an account created before consent was recorded,
 *  or any API call answering 403 with X-Consent-Required after the notice was
 *  reworded (api.ts redirects here). Either way the token is valid - what is
 *  missing is agreement to the text currently in force, so this does not sign
 *  anyone out; it collects the agreement and sends them back.
 *
 *  Declining is a real option, and it signs the user out rather than pretending
 *  the choice was not offered. Consent that cannot be refused is not consent. */
export default function ConsentPage() {
  const router = useRouter();
  const [accepted, setAccepted] = useState(false);
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const errorRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    // Someone who lands here with consent already on file has nothing to do -
    // send them on rather than asking twice.
    (async () => {
      try {
        const me = await api.me();
        if (!me.needs_consent) {
          router.replace("/chat");
          return;
        }
      } catch (err) {
        setError((err as Error).message);
      }
      setChecking(false);
    })();
  }, [router]);

  async function accept() {
    setError("");
    setBusy(true);
    try {
      await api.acceptConsent();
      router.replace("/chat");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  function decline() {
    setToken(null);
    router.replace("/login");
  }

  if (checking) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-muted">กำลังตรวจสอบ…</p>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-lg">
        <div className="rounded-lg border border-border bg-surface p-7">
          <h1 className="font-display text-xl font-bold tracking-tight">
            ขอความยินยอมก่อนใช้งานต่อ
          </h1>
          <p className="mt-2 text-sm leading-[1.8] text-muted">
            ระบบมีการเก็บและใช้ข้อมูลส่วนบุคคลของคุณ
            บัญชีนี้ยังไม่ได้บันทึกความยินยอมสำหรับข้อความฉบับปัจจุบัน
            กรุณาอ่านรายละเอียดด้านล่างแล้วเลือกว่าจะยินยอมหรือไม่
          </p>

          <div className="mt-5">
            <ConsentNotice />
          </div>

          <label className="mt-5 flex cursor-pointer items-start gap-2.5 text-sm leading-[1.7]">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--accent)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            />
            <span>ฉันได้อ่านและยินยอมให้เก็บและใช้ข้อมูลตามรายละเอียดข้างต้น</span>
          </label>

          {error && (
            <p
              ref={errorRef}
              role="alert"
              tabIndex={-1}
              className="mt-4 rounded-sm border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 outline-none"
            >
              {error}
            </p>
          )}

          <div className="mt-6 flex flex-col gap-3 border-t border-border pt-6 sm:flex-row sm:items-center">
            <button
              type="button"
              onClick={accept}
              disabled={!accepted || busy}
              className="rounded-md bg-cta px-7 py-3 font-medium text-cta-foreground transition hover:opacity-85 active:scale-[0.99] disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              {busy ? "กำลังบันทึก…" : "ยินยอมและใช้งานต่อ"}
            </button>
            <button
              type="button"
              onClick={decline}
              className="rounded-md border border-border px-7 py-3 text-sm transition hover:border-accent hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              ไม่ยินยอม และออกจากระบบ
            </button>
          </div>

          <p className="mt-4 text-xs leading-[1.7] text-muted">
            หากไม่ยินยอม จะยังใช้งานระบบต่อไม่ได้ ข้อมูลเดิมของคุณยังอยู่
            และขอให้ลบได้ตามช่องทางที่ระบุไว้ด้านบน
          </p>
        </div>
      </div>
    </main>
  );
}
