"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, api, getToken, type Profile, type Targets } from "@/lib/api";

const ACTIVITY_OPTIONS = [
  { value: "sedentary", label: "แทบไม่ออกกำลังกาย (นั่งทำงานเป็นหลัก)" },
  { value: "light", label: "ออกกำลังกายเบา 1-3 วัน/สัปดาห์" },
  { value: "moderate", label: "ออกกำลังกายปานกลาง 3-5 วัน/สัปดาห์" },
  { value: "active", label: "ออกกำลังกายหนัก 6-7 วัน/สัปดาห์" },
  { value: "very_active", label: "ออกกำลังกายหนักมาก / ใช้แรงงานหนัก" },
] as const;

const GOAL_OPTIONS = [
  { value: "cut", label: "ลดไขมัน (cut)" },
  { value: "maintain", label: "รักษาน้ำหนัก" },
  { value: "bulk", label: "เพิ่มกล้ามเนื้อ (bulk)" },
] as const;

const RESTRICTION_OPTIONS = [
  "ฮาลาล",
  "มังสวิรัติ",
  "วีแกน",
  "แพ้นมวัว",
  "แพ้ถั่ว",
  "แพ้อาหารทะเล",
  "ไม่กินเนื้อวัว",
];

const EMPTY: Profile = {
  sex: "male",
  birth_year: new Date().getFullYear() - 25,
  height_cm: 170,
  weight_kg: 65,
  body_fat_pct: null,
  activity_level: "moderate",
  training_days: 3,
  goal: "maintain",
  restrictions: [],
};

export default function ProfilePage() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile>(EMPTY);
  const [targets, setTargets] = useState<Targets | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        setProfile(await api.getProfile());
        setTargets(await api.getTargets());
      } catch (err) {
        if (!(err instanceof ApiError && err.status === 404)) {
          setError((err as Error).message);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setStatus("กำลังบันทึก…");
    try {
      await api.saveProfile(profile);
      setTargets(await api.getTargets());
      setStatus("บันทึกแล้ว");
    } catch (err) {
      setStatus("");
      setError((err as Error).message);
    }
  }

  function toggleRestriction(item: string) {
    setProfile((p) => ({
      ...p,
      restrictions: p.restrictions.includes(item)
        ? p.restrictions.filter((r) => r !== item)
        : [...p.restrictions, item],
    }));
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-muted">กำลังโหลด…</p>
      </main>
    );
  }

  const inputClass =
    "mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 outline-none focus:border-accent";

  return (
    <main className="mx-auto max-w-3xl p-6">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold">โปรไฟล์ของฉัน</h1>
        <Link href="/chat" className="text-sm text-accent hover:underline">
          ไปหน้าแชต →
        </Link>
      </header>

      <form
        onSubmit={save}
        className="space-y-5 rounded-2xl border border-border bg-surface p-6"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm">เพศ</span>
            <select
              value={profile.sex}
              onChange={(e) =>
                setProfile({ ...profile, sex: e.target.value as Profile["sex"] })
              }
              className={inputClass}
            >
              <option value="male">ชาย</option>
              <option value="female">หญิง</option>
            </select>
          </label>

          <label className="block">
            <span className="text-sm">ปีเกิด (ค.ศ.)</span>
            <input
              type="number"
              required
              value={profile.birth_year}
              onChange={(e) =>
                setProfile({ ...profile, birth_year: Number(e.target.value) })
              }
              className={inputClass}
            />
          </label>

          <label className="block">
            <span className="text-sm">ส่วนสูง (ซม.)</span>
            <input
              type="number"
              step="0.1"
              required
              value={profile.height_cm}
              onChange={(e) =>
                setProfile({ ...profile, height_cm: Number(e.target.value) })
              }
              className={inputClass}
            />
          </label>

          <label className="block">
            <span className="text-sm">น้ำหนัก (กก.)</span>
            <input
              type="number"
              step="0.1"
              required
              value={profile.weight_kg}
              onChange={(e) =>
                setProfile({ ...profile, weight_kg: Number(e.target.value) })
              }
              className={inputClass}
            />
          </label>

          <label className="block">
            <span className="text-sm">
              เปอร์เซ็นต์ไขมัน (ถ้าทราบ){" "}
              <span className="text-muted">— ทำให้คำนวณแม่นขึ้น</span>
            </span>
            <input
              type="number"
              step="0.1"
              value={profile.body_fat_pct ?? ""}
              onChange={(e) =>
                setProfile({
                  ...profile,
                  body_fat_pct: e.target.value ? Number(e.target.value) : null,
                })
              }
              className={inputClass}
            />
          </label>

          <label className="block">
            <span className="text-sm">เล่นเวทกี่วัน/สัปดาห์</span>
            <input
              type="number"
              min={0}
              max={7}
              value={profile.training_days}
              onChange={(e) =>
                setProfile({ ...profile, training_days: Number(e.target.value) })
              }
              className={inputClass}
            />
          </label>
        </div>

        <label className="block">
          <span className="text-sm">ระดับกิจกรรมโดยรวม</span>
          <select
            value={profile.activity_level}
            onChange={(e) =>
              setProfile({
                ...profile,
                activity_level: e.target.value as Profile["activity_level"],
              })
            }
            className={inputClass}
          >
            {ACTIVITY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-sm">เป้าหมาย</span>
          <select
            value={profile.goal}
            onChange={(e) =>
              setProfile({ ...profile, goal: e.target.value as Profile["goal"] })
            }
            className={inputClass}
          >
            {GOAL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        <div>
          <span className="text-sm">ข้อจำกัดด้านอาหาร</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {RESTRICTION_OPTIONS.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => toggleRestriction(item)}
                className={`rounded-full border px-3 py-1 text-sm transition ${
                  profile.restrictions.includes(item)
                    ? "border-accent bg-accent-soft text-accent"
                    : "border-border text-muted hover:text-foreground"
                }`}
              >
                {item}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <p className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-500">
            {error}
          </p>
        )}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            className="rounded-lg bg-accent px-5 py-2.5 font-medium text-white transition hover:opacity-90"
          >
            บันทึกและคำนวณ
          </button>
          {status && <span className="text-sm text-muted">{status}</span>}
        </div>
      </form>

      {targets && <TargetsCard targets={targets} />}
    </main>
  );
}

function TargetsCard({ targets }: { targets: Targets }) {
  const { macros } = targets;
  return (
    <section className="mt-6 rounded-2xl border border-border bg-surface p-6">
      <h2 className="text-lg font-semibold">เป้าหมายพลังงานและสารอาหาร</h2>
      <p className="mt-1 text-sm text-muted">
        {targets.inputs.goal_label_th} · {targets.inputs.activity_label_th}
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Stat label={`BMR (${targets.bmr_formula})`} value={`${targets.bmr_kcal} kcal`} />
        <Stat label="TDEE" value={`${targets.tdee_kcal} kcal`} />
        <Stat
          label="พลังงานเป้าหมาย"
          value={`${targets.energy_target_kcal} kcal`}
          hint={`ช่วง ${targets.energy_target_range_kcal[0]}–${targets.energy_target_range_kcal[1]}`}
          highlight
        />
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <Stat label="โปรตีน" value={`${macros.protein_g} g`} hint={`${macros.protein_kcal} kcal`} />
        <Stat label="คาร์โบไฮเดรต" value={`${macros.carb_g} g`} hint={`${macros.carb_kcal} kcal`} />
        <Stat label="ไขมัน" value={`${macros.fat_g} g`} hint={`${macros.fat_kcal} kcal`} />
      </div>

      {targets.warnings.length > 0 && (
        <ul className="mt-4 space-y-2">
          {targets.warnings.map((warning) => (
            <li
              key={warning}
              className="rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-600"
            >
              {warning}
            </li>
          ))}
        </ul>
      )}

      <details className="mt-4">
        <summary className="cursor-pointer text-sm text-muted">
          สูตรและแหล่งอ้างอิงที่ใช้คำนวณ
        </summary>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted">
          {targets.references.map((reference) => (
            <li key={reference}>{reference}</li>
          ))}
        </ul>
      </details>

      <p className="mt-4 text-xs text-muted">{targets.disclaimer}</p>
    </section>
  );
}

function Stat({
  label,
  value,
  hint,
  highlight,
}: {
  label: string;
  value: string;
  hint?: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        highlight ? "border-accent bg-accent-soft/40" : "border-border"
      }`}
    >
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
      {hint && <div className="text-xs text-muted">{hint}</div>}
    </div>
  );
}
