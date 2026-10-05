"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, api, getToken, type Profile, type Targets } from "@/lib/api";
import { ageFrom, createProfileDraft, profileFromDraft, toCE, type ProfileDraft } from "@/lib/profile-form";

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
  "ไม่กินไก่",
  "ไม่กินไข่",
];

const BE_OFFSET = 543;

const MONTHS_TH = [
  "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
  "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
];

export default function ProfilePage() {
  const router = useRouter();
  const [profile, setProfile] = useState<ProfileDraft>(createProfileDraft);
  const [savedDraft, setSavedDraft] = useState<string | null>(null);
  const [targets, setTargets] = useState<Targets | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const draft = createProfileDraft(await api.getProfile());
        if (cancelled) return;
        setProfile(draft);
        setSavedDraft(JSON.stringify(draft));
      } catch (err) {
        if (cancelled) return;
        if (!(err instanceof ApiError && err.status === 404)) {
          setError((err as Error).message);
          setLoadFailed(true);
          setLoading(false);
          return;
        }
        setProfile(createProfileDraft());
        setSavedDraft(null);
        setTargets(null);
        setLoading(false);
        return;
      }
      try {
        const result = await api.getTargets();
        if (!cancelled) setTargets(result);
      } catch (err) {
        if (!cancelled) {
          setTargets(null);
          setError(`โหลดเป้าหมายไม่สำเร็จ: ${(err as Error).message}`);
        }
      } finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [router, retry]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (savingRef.current || loadFailed) return;
    let payload: Profile;
    try { payload = profileFromDraft(profile); }
    catch (err) { setError((err as Error).message); setStatus(""); return; }
    savingRef.current = true;
    setSaving(true);
    setError("");
    setStatus("กำลังบันทึก…");
    try {
      const saved = createProfileDraft(await api.saveProfile(payload));
      setProfile(saved);
      setSavedDraft(JSON.stringify(saved));
      setTargets(null);
      setStatus("บันทึกแล้ว");
      try { setTargets(await api.getTargets()); }
      catch (err) { setError(`บันทึกข้อมูลแล้ว แต่โหลดเป้าหมายไม่สำเร็จ: ${(err as Error).message}`); }
    } catch (err) {
      setStatus("");
      setError((err as Error).message);
    } finally {
      savingRef.current = false;
      setSaving(false);
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
    Number(profile.training_days) >= 5 && lowActivity
      ? `คุณเล่นเวท ${profile.training_days} วัน/สัปดาห์ แต่เลือกระดับกิจกรรมต่ำ ระบบคำนวณพลังงานจากระดับกิจกรรม` +
        " ไม่ใช่จำนวนวัน กรุณาทบทวนระดับที่เลือกโดยพิจารณาความหนัก ระยะเวลาฝึก และกิจกรรมระหว่างวันด้วย"
      : profile.training_days !== "" && Number(profile.training_days) <= 1 && highActivity
        ? "คุณเล่นเวทไม่เกิน 1 วัน/สัปดาห์ แต่เลือกระดับกิจกรรมสูง กรุณาทบทวนว่า" +
          "งานประจำหรือการออกกำลังอื่นสอดคล้องกับระดับที่เลือกหรือไม่"
        : "";

  const dirty = savedDraft !== JSON.stringify(profile);
  const birthYearCE = toCE(Number(profile.birth_year));
  const birthAge = ageFrom(birthYearCE, profile.birth_month ? Number(profile.birth_month) : null);
  const birthYearHint =
    !profile.birth_year || birthYearCE < 1900 || birthYearCE > 2100
      ? "กรอกได้ทั้ง ค.ศ. (เช่น 2004) และ พ.ศ. (เช่น 2547)"
      : Number(profile.birth_year) >= 2400
        ? `พ.ศ. ${profile.birth_year} = ค.ศ. ${birthYearCE}${profile.birth_month ? ` · อายุประมาณ ${birthAge} ปี` : ""}`
        : `ค.ศ. ${birthYearCE}${profile.birth_month ? ` · อายุประมาณ ${birthAge} ปี` : ""}`;

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
        {loadFailed && <div role="alert" className="rounded-sm border border-red-500/20 p-4 text-sm">
          โหลดโปรไฟล์ไม่สำเร็จ กรุณาลองใหม่ก่อนแก้ไขข้อมูล
          <button type="button" onClick={() => {
            setLoading(true);
            setError("");
            setLoadFailed(false);
            setRetry((value) => value + 1);
          }} className="ml-3 underline">ลองโหลดอีกครั้ง</button>
        </div>}
        <fieldset disabled={saving || loadFailed} className="space-y-6 disabled:opacity-60">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="field-label text-xs text-muted">เพศ</span>
            <select
              required
              aria-label="เพศ"
              value={profile.sex}
              onChange={(e) =>
                setProfile({ ...profile, sex: e.target.value as ProfileDraft["sex"] })
              }
              className={inputClass}
            >
              <option value="" disabled>เลือกเพศที่ใช้ในสูตรคำนวณ</option>
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
                setProfile({ ...profile, birth_year: e.target.value })
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
              aria-label="เดือนเกิด"
              value={profile.birth_month}
              onChange={(e) =>
                setProfile({
                  ...profile,
                  birth_month: e.target.value,
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
            <span className="mt-1.5 block text-xs text-muted">ใช้เดือนและปีเกิดประมาณอายุ โดยนับอายุลงตลอดเดือนเกิดเพราะไม่ได้เก็บวันเกิด</span>
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
                setProfile({ ...profile, height_cm: e.target.value })
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
                setProfile({ ...profile, weight_kg: e.target.value })
              }
              className={inputClass}
            />
          </label>

          <label className="block">
            <span className="field-label text-xs text-muted">
              เปอร์เซ็นต์ไขมัน (ถ้าทราบ){" "}
              <span className="normal-case tracking-normal text-muted/80">— เว้นว่างได้ ไม่ต้องคาดเดา</span>
            </span>
            <input
              type="number"
              step="0.1"
              min={3}
              max={60}
              value={profile.body_fat_pct}
              onChange={(e) =>
                setProfile({
                  ...profile,
                  body_fat_pct: e.target.value,
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
              required
              value={profile.training_days}
              onChange={(e) =>
                setProfile({ ...profile, training_days: e.target.value })
              }
              className={inputClass}
            />
          </label>
        </div>

        <label className="block">
          <span className="field-label text-xs text-muted">ระดับกิจกรรมโดยรวม</span>
          <select
            required
            aria-label="ระดับกิจกรรมโดยรวม"
            value={profile.activity_level}
            onChange={(e) =>
              setProfile({
                ...profile,
                activity_level: e.target.value as ProfileDraft["activity_level"],
              })
            }
            className={inputClass}
          >
            <option value="" disabled>เลือกระดับกิจกรรม</option>
            {ACTIVITY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <p className="mt-1.5 text-xs text-muted">พิจารณาทั้งงานประจำ การเดิน และการออกกำลัง ระดับนี้ใช้คำนวณพลังงาน ส่วนจำนวนวันเล่นเวทใช้เป็นบริบทคำตอบ</p>
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
            required
            aria-label="เป้าหมาย"
            value={profile.goal}
            onChange={(e) =>
              setProfile({ ...profile, goal: e.target.value as ProfileDraft["goal"] })
            }
            className={inputClass}
          >
            <option value="" disabled>เลือกเป้าหมาย</option>
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
            {Array.from(new Set([...RESTRICTION_OPTIONS, ...profile.restrictions])).map((item) => {
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
          <p role="alert" className="rounded-sm border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600">
            {error}
          </p>
        )}

        <div className="flex items-center gap-3 border-t border-border pt-6">
          <button
            type="submit"
            disabled={saving || loadFailed}
            className="rounded-md bg-cta px-7 py-3 font-medium text-cta-foreground transition hover:opacity-85 active:scale-[0.98]"
          >
            {saving ? "กำลังบันทึก…" : "บันทึกและคำนวณ"}
          </button>
          {status && (!dirty || saving) && <span role="status" className="text-sm text-muted">{status}</span>}
        </div>
        </fieldset>
      </form>

      {dirty && savedDraft !== null && <p role="status" className="mt-6 text-sm text-muted">ข้อมูลที่แก้ยังไม่ได้บันทึก กรุณาบันทึกและคำนวณเพื่ออัปเดตเป้าหมาย</p>}
      {targets && !dirty && !loadFailed && <TargetsCard targets={targets} />}
      <p className="mt-6 text-xs text-muted">สำหรับการจัดมื้อให้เข้ากับชีวิตประจำวัน แจ้งจำนวนมื้อ เวลาออกกำลัง งบประมาณ และอาหารที่ไม่ต้องการเพิ่มเติมในแชทได้</p>
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
