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

/** Mirrors ProfileIn._birth_year_ce in backend/app/api/schemas.py. The server
 *  already accepts พ.ศ. and converts it, but the form used to cap the input at
 *  `ปีนี้ - 18` in ค.ศ., so 2547 was rejected before it could ever reach that
 *  conversion - the support existed and was unreachable. The raw value is still
 *  what gets sent; this only decides what to show the user and whether to
 *  pre-check the age gate. The two constants must stay in step with the server:
 *  if they disagree, the form and the API disagree about which era a year is. */
const BE_THRESHOLD = 2400;
const BE_OFFSET = 543;

function toCE(year: number) {
  return year >= BE_THRESHOLD ? year - BE_OFFSET : year;
}

/** Mirrors ProfileInput.age() in backend/app/services/nutrition.py, including
 *  its month rule, so the hint under the field cannot claim an age the server
 *  would then reject. */
function ageFrom(yearCE: number, month: number | null) {
  const now = new Date();
  let years = now.getFullYear() - yearCE;
  if (month !== null && now.getMonth() + 1 <= month) years -= 1;
  return years;
}

const MONTHS_TH = [
  "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
  "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
];

const EMPTY: Profile = {
  sex: "male",
  birth_year: new Date().getFullYear() - 25,
  birth_month: null,
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
    if (birthYearCE < 1900 || birthYearCE > 2100) {
      setError("ปีเกิดต้องอยู่ระหว่าง ค.ศ. 1900-2100 (หรือ พ.ศ. 2443-2643)");
      return;
    }
    if (birthAge < 18) {
      setError(`บริการนี้สำหรับผู้ที่มีอายุ 18 ปีขึ้นไป (ปีเกิดที่กรอกได้อายุ ${birthAge} ปี)`);
      return;
    }
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
    "mt-1.5 w-full rounded-sm border border-border bg-surface-sunken px-3.5 py-2.5 outline-none transition focus:border-accent focus:bg-surface";

  const lowActivity = profile.activity_level === "sedentary" || profile.activity_level === "light";
  const highActivity = profile.activity_level === "active" || profile.activity_level === "very_active";
  const activityMismatch =
    profile.training_days >= 5 && lowActivity
      ? `คุณเล่นเวท ${profile.training_days} วัน/สัปดาห์ แต่เลือกระดับกิจกรรมต่ำ ระบบคำนวณพลังงานจากระดับกิจกรรม` +
        " ไม่ใช่จำนวนวัน ถ้าฝึกจริงตามนี้ควรเลือก “ปานกลาง” ขึ้นไป ไม่งั้นพลังงานที่คำนวณได้จะต่ำกว่าที่ใช้จริง"
      : profile.training_days <= 1 && highActivity
        ? "คุณเล่นเวทไม่เกิน 1 วัน/สัปดาห์ แต่เลือกระดับกิจกรรมสูง ถ้างานประจำไม่ได้ใช้แรงมาก" +
          " ควรลดระดับลง ไม่งั้นพลังงานที่คำนวณได้จะสูงกว่าที่ใช้จริง"
        : "";

  const birthYearCE = toCE(profile.birth_year);
  const birthAge = ageFrom(birthYearCE, profile.birth_month);
  const birthYearHint =
    !profile.birth_year || birthYearCE < 1900 || birthYearCE > 2100
      ? "กรอกได้ทั้ง ค.ศ. (เช่น 2004) และ พ.ศ. (เช่น 2547)"
      : profile.birth_year >= BE_THRESHOLD
        ? `พ.ศ. ${profile.birth_year} = ค.ศ. ${birthYearCE} · อายุ ${birthAge} ปี`
        : `ค.ศ. ${birthYearCE} · อายุ ${birthAge} ปี`;

  return (
    <main className="mx-auto max-w-3xl p-6 pb-16">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">โปรไฟล์ของฉัน</h1>
          <p className="mt-1 text-sm text-muted">
            ใช้คำนวณพลังงานและสารอาหารเฉพาะบุคคล
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/log"
            className="rounded-md border border-border px-4 py-2 text-sm transition hover:border-accent hover:text-accent"
          >
            บันทึกอาหาร
          </Link>
          <Link
            href="/chat"
            className="rounded-md border border-border px-4 py-2 text-sm transition hover:border-accent hover:text-accent"
          >
            ไปหน้าแชต →
          </Link>
        </div>
      </header>

      <form
        onSubmit={save}
        className="space-y-6 rounded-lg border border-border bg-surface p-7"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="field-label text-xs text-muted">เพศ</span>
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
            <span className="field-label text-xs text-muted">ปีเกิด (ค.ศ. หรือ พ.ศ.) · 18 ปีขึ้นไป</span>
            {/* min/max span both eras, because a single number input cannot
                express two disjoint ranges and capping at ค.ศ. is what made
                พ.ศ. impossible to enter. The age rule is checked in save()
                against the converted year instead, and the server remains the
                real gate (calc_nutrition_targets raises -> 422). */}
            <input
              type="number"
              required
              name="birth-year"
              min={1900}
              max={new Date().getFullYear() + BE_OFFSET}
              aria-describedby="birth-year-hint"
              value={profile.birth_year}
              onChange={(e) =>
                setProfile({ ...profile, birth_year: Number(e.target.value) })
              }
              className={inputClass}
            />
            {/* Reading the year back is the whole point: someone who types 2547
                sees "พ.ศ. 2547 = ค.ศ. 2004" and knows it was understood, and
                someone who typed it by mistake sees an age that is obviously
                wrong before they submit. */}
            <span id="birth-year-hint" className="mt-1.5 block text-xs text-muted">
              {birthYearHint}
            </span>
          </label>

          <label className="block">
            <span className="field-label text-xs text-muted">เดือนเกิด</span>
            {/* The year alone let a December-born 17-year-old through from
                1 January; the month lets the server round the age down. */}
            <select
              required
              value={profile.birth_month ?? ""}
              onChange={(e) =>
                setProfile({
                  ...profile,
                  birth_month: e.target.value ? Number(e.target.value) : null,
                })
              }
              className={inputClass}
            >
              <option value="" disabled>
                เลือกเดือน
              </option>
              {MONTHS_TH.map((name, index) => (
                <option key={name} value={index + 1}>
                  {name}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="field-label text-xs text-muted">ส่วนสูง (ซม.)</span>
            {/* Same limits as nutrition._validate, so the browser stops a bad
                value before the request instead of after it. */}
            <input
              type="number"
              step="0.1"
              required
              min={120}
              max={230}
              value={profile.height_cm}
              onChange={(e) =>
                setProfile({ ...profile, height_cm: Number(e.target.value) })
              }
              className={inputClass}
            />
          </label>

          <label className="block">
            <span className="field-label text-xs text-muted">น้ำหนัก (กก.)</span>
            <input
              type="number"
              step="0.1"
              required
              min={30}
              max={300}
              value={profile.weight_kg}
              onChange={(e) =>
                setProfile({ ...profile, weight_kg: Number(e.target.value) })
              }
              className={inputClass}
            />
          </label>

          <label className="block">
            <span className="field-label text-xs text-muted">
              เปอร์เซ็นต์ไขมัน (ถ้าทราบ){" "}
              <span className="normal-case tracking-normal text-muted/80">— ทำให้คำนวณแม่นขึ้น</span>
            </span>
            <input
              type="number"
              step="0.1"
              min={3}
              max={60}
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
            <span className="field-label text-xs text-muted">เล่นเวทกี่วัน/สัปดาห์</span>
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
          <span className="field-label text-xs text-muted">ระดับกิจกรรมโดยรวม</span>
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
          {/* The energy formula uses this level only; training days do not
              enter it. "เล่นเวท 6 วัน" with "แทบไม่ออกกำลังกาย" used to save
              silently and give a TDEE far too low
              (production_review_2026-09-24.md B10). */}
          {activityMismatch && (
            <span className="mt-1.5 block rounded-sm bg-macro-carb-soft px-3 py-2 text-xs">
              {activityMismatch}
            </span>
          )}
        </label>

        <label className="block">
          <span className="field-label text-xs text-muted">เป้าหมาย</span>
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
          <span className="field-label text-xs text-muted">ข้อจำกัดด้านอาหาร</span>
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
                  className={`rounded-sm border px-4 py-2 text-sm transition ${
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
          <p className="rounded-sm border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600">
            {error}
          </p>
        )}

        <div className="flex items-center gap-3 border-t border-border pt-6">
          <button
            type="submit"
            className="rounded-md bg-cta px-7 py-3 font-medium text-cta-foreground transition hover:opacity-85 active:scale-[0.98]"
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
        <h2 className="font-display text-2xl font-bold tracking-tight">
          เป้าหมายต่อวันของคุณ
        </h2>
        {/* When the calculator refused to build a deficit (underweight),
            say so in the badge instead of showing "cut" over maintenance numbers.
            The matching warning below explains why. */}
        <span className="field-label border border-accent px-3 py-1.5 text-[11px] text-accent">
          {targets.effective_goal && targets.effective_goal !== targets.inputs.goal
            ? `${targets.inputs.goal_label_th} → ${targets.effective_goal_label_th}`
            : targets.inputs.goal_label_th}
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
              className="rounded-sm border border-macro-carb/30 bg-macro-carb-soft px-4 py-3 text-sm"
            >
              {warning}
            </li>
          ))}
        </ul>
      )}

      <div className="rounded-lg border border-border bg-surface p-5">
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
      className={`rounded-lg p-5 transition ${
        filled
          ? "bg-cta text-cta-foreground"
          : "border border-border bg-surface"
      }`}
    >
      <div className={`field-label text-[11px] ${filled ? "opacity-60" : "text-muted"}`}>
        {label}
      </div>
      <div className="mt-3 flex items-baseline gap-1.5">
        <span className="stat-figure text-3xl font-semibold">
          {value.toLocaleString()}
        </span>
        <span className={`text-sm ${filled ? "opacity-60" : "text-muted"}`}>
          kcal
        </span>
      </div>
      {hint && (
        <div className={`mt-1 text-xs ${filled ? "opacity-60" : "text-muted"}`}>
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
    <div className="rounded-lg border border-border bg-surface p-5">
      <div className="field-label text-[11px] text-muted">{label}</div>
      <div className="mt-3 flex items-baseline gap-1.5">
        <span className="stat-figure text-3xl font-semibold">
          {grams}
        </span>
        <span className="text-sm text-muted">g</span>
      </div>
      <div className={`mt-4 h-1.5 w-full overflow-hidden rounded-sm ${track}`}>
        <div
          className={`h-full ${bar}`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
      <div className="mt-2 text-xs text-muted">
        <span className="stat-figure">{kcal.toLocaleString()} kcal</span> ·{" "}
        <span className="stat-figure">{percent}%</span> ของพลังงาน
      </div>
    </div>
  );
}
