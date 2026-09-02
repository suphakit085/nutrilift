"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result =
        mode === "login"
          ? await api.login(email, password)
          : await api.register(email, password);
      setToken(result.access_token);
      router.push(mode === "register" ? "/profile" : "/chat");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

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
                onClick={() => {
                  setMode(value);
                  setError("");
                }}
                className={`flex-1 rounded-sm py-2 transition ${
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
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 w-full rounded-sm border border-border bg-surface-sunken px-3.5 py-2.5 outline-none transition focus:border-accent focus:bg-surface"
              />
            </label>

            <label className="block">
              <span className="field-label text-xs text-muted">รหัสผ่าน</span>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1.5 w-full rounded-sm border border-border bg-surface-sunken px-3.5 py-2.5 outline-none transition focus:border-accent focus:bg-surface"
              />
              {mode === "register" && (
                <span className="mt-1.5 block text-xs text-muted">
                  อย่างน้อย 8 ตัวอักษร
                </span>
              )}
            </label>

            {error && (
              <p className="rounded-sm border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md bg-cta py-3 font-medium text-cta-foreground transition hover:opacity-85 active:scale-[0.99] disabled:opacity-40"
            >
              {busy
                ? "กำลังดำเนินการ…"
                : mode === "login"
                  ? "เข้าสู่ระบบ"
                  : "สมัครสมาชิก"}
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
