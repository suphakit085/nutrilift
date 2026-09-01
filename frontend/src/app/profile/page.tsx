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
    "mt-1.5 w-full rounded-xl border border-border bg-surface-sunken px-3.5 py-2.5 outline-none transition focus:border-accent focus:bg-surface";

  return (
    <main className="mx-auto max-w-3xl p-6 pb-16">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">โปรไฟล์ของฉัน</h1>
          <p className="mt-1 text-sm text-muted">
            ใช้คำนวณพลังงานและสารอาหารเฉพาะบุคคล
          </p>
        </div>
        <Link
          href="/chat"
          className="rounded-full border border-border px-4 py-2 text-sm transition hover:border-accent hover:text-accent"
        >
          ไปหน้าแชต →
        </Link>
      </header>

      <form
        onSubmit={save}
        className="space-y-6 rounded-3xl border border-border bg-surface p-7"
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
          <p className="mt-0.5 text-xs text-muted">เลือกได้มากกว่า 1 ข้อ</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {RESTRICTION_OPTIONS.map((item) => {
              const selected = profile.restrictions.includes(item);
              return (
                <button
                  key={item}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => toggleRestriction(item)}
                  className={`rounded-full border px-4 py-2 text-sm transition ${
                    selected
                      ? "border-accent bg-accent-soft font-medium text-accent"
                      : "border-border bg-surface-sunken text-muted hover:border-accent/40 hover:text-foreground"
                  }`}
                >
                  {item}
                </button>
              );
            })}
          </div>
        </div>

        {error && (
          <p className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600">
            {error}
          </p>
        )}

        <div className="flex items-center gap-3 border-t border-border pt-6">
          <button
            type="submit"
            className="rounded-full bg-cta px-7 py-3 font-medium text-cta-foreground transition hover:opacity-85 active:scale-[0.98]"
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
  const total = targets.energy_target_kcal || 1;

  return (
    <section className="mt-6 space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-2xl font-semibold tracking-tight">
          เป้าหมายต่อวันของคุณ
        </h2>
        <span className="rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent">
          {targets.inputs.goal_label_th}
        </span>
      </div>

      {/* Energy row. The target is the number that actually drives decisions,
          so it gets the filled treatment and the other two stay quiet. */}
      <div className="grid gap-3 sm:grid-cols-3">
        <EnergyStat label={`BMR · ${targets.bmr_formula}`} value={targets.bmr_kcal} />
        <EnergyStat label="TDEE" value={targets.tdee_kcal} />
        <EnergyStat
          label="พลังงานเป้าหมาย"
          value={targets.energy_target_kcal}
          hint={`ช่วง ${targets.energy_target_range_kcal[0]}–${targets.energy_target_range_kcal[1]}`}
          filled
        />
      </div>

      {/* Macro row. Each bar is that macro's share of the calorie target, so
          the bars carry real information rather than being decoration. */}
      <div className="grid gap-3 sm:grid-cols-3">
        <MacroStat
          label="โปรตีน"
          grams={macros.protein_g}
          kcal={macros.protein_kcal}
          share={macros.protein_kcal / total}
          bar="bg-macro-protein"
          track="bg-macro-protein-soft"
        />
        <MacroStat
          label="คาร์โบไฮเดรต"
          grams={macros.carb_g}
          kcal={macros.carb_kcal}
          share={macros.carb_kcal / total}
          bar="bg-macro-carb"
          track="bg-macro-carb-soft"
        />
        <MacroStat
          label="ไขมัน"
          grams={macros.fat_g}
          kcal={macros.fat_kcal}
          share={macros.fat_kcal / total}
          bar="bg-macro-fat"
          track="bg-macro-fat-soft"
        />
      </div>

      {targets.warnings.length > 0 && (
        <ul className="space-y-2">
          {targets.warnings.map((warning) => (
            <li
              key={warning}
              className="rounded-2xl border border-macro-carb/30 bg-macro-carb-soft px-4 py-3 text-sm"
            >
              {warning}
            </li>
          ))}
        </ul>
      )}

      <div className="rounded-2xl border border-border bg-surface p-5">
        <details>
          <summary className="cursor-pointer text-sm font-medium">
            สูตรและแหล่งอ้างอิงที่ใช้คำนวณ
          </summary>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted">
            {targets.references.map((reference) => (
              <li key={reference}>{reference}</li>
            ))}
          </ul>
        </details>
        <p className="mt-4 border-t border-border pt-4 text-xs text-muted">
          {targets.disclaimer}
        </p>
      </div>
    </section>
  );
}

function EnergyStat({
  label,
  value,
  hint,
  filled,
}: {
  label: string;
  value: number;
  hint?: string;
  filled?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl p-5 transition ${
        filled
          ? "bg-cta text-cta-foreground"
          : "border border-border bg-surface"
      }`}
    >
      <div className={`text-xs ${filled ? "opacity-70" : "text-muted"}`}>
        {label}
      </div>
      <div className="mt-3 flex items-baseline gap-1.5">
        <span className="text-3xl font-semibold tracking-tight tabular-nums">
          {value.toLocaleString()}
        </span>
        <span className={`text-sm ${filled ? "opacity-70" : "text-muted"}`}>
          kcal
        </span>
      </div>
      {hint && (
        <div className={`mt-1 text-xs ${filled ? "opacity-70" : "text-muted"}`}>
          {hint}
        </div>
      )}
    </div>
  );
}

function MacroStat({
  label,
  grams,
  kcal,
  share,
  bar,
  track,
}: {
  label: string;
  grams: number;
  kcal: number;
  share: number;
  bar: string;
  track: string;
}) {
  const percent = Math.round(share * 100);
  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-3 flex items-baseline gap-1.5">
        <span className="text-3xl font-semibold tracking-tight tabular-nums">
          {grams}
        </span>
        <span className="text-sm text-muted">g</span>
      </div>
      <div className={`mt-4 h-1.5 w-full overflow-hidden rounded-full ${track}`}>
        <div
          className={`h-full rounded-full ${bar}`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
      <div className="mt-2 text-xs text-muted tabular-nums">
        {kcal.toLocaleString()} kcal · {percent}% ของพลังงาน
      </div>
    </div>
  );
}
