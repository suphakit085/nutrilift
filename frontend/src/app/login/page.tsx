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
          <span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-2xl">
            🥗
          </span>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight">NutriLift</h1>
          <p className="mt-1.5 text-sm text-muted">
            แชตบอทโภชนาการสำหรับผู้ฝึกเวทเทรนนิ่ง
          </p>
        </div>

        <div className="rounded-3xl border border-border bg-surface p-7">
          <div className="flex rounded-full bg-surface-sunken p-1 text-sm">
            {(["login", "register"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  setMode(value);
                  setError("");
                }}
                className={`flex-1 rounded-full py-2 transition ${
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
              <span className="text-sm">อีเมล</span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-border bg-surface-sunken px-3.5 py-2.5 outline-none transition focus:border-accent focus:bg-surface"
              />
            </label>

            <label className="block">
              <span className="text-sm">รหัสผ่าน</span>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-border bg-surface-sunken px-3.5 py-2.5 outline-none transition focus:border-accent focus:bg-surface"
              />
              {mode === "register" && (
                <span className="mt-1.5 block text-xs text-muted">
                  อย่างน้อย 8 ตัวอักษร
                </span>
              )}
            </label>

            {error && (
              <p className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-full bg-cta py-3 font-medium text-cta-foreground transition hover:opacity-85 active:scale-[0.99] disabled:opacity-40"
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
