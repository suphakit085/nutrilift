import type { Profile } from "./api";

type NumericField = "birth_year" | "birth_month" | "height_cm" | "weight_kg" | "body_fat_pct" | "training_days";
export type ProfileDraft = Omit<Profile, NumericField | "sex" | "activity_level" | "goal"> &
  Record<NumericField, string> & {
    sex: Profile["sex"] | "";
    activity_level: Profile["activity_level"] | "";
    goal: Profile["goal"] | "";
  };

export function toCE(year: number): number {
  return year >= 2400 ? year - 543 : year;
}

// The server uses UTC and rounds down throughout the birth month because the
// birth day is not collected. Keep the hint and the server age gate consistent.
export function ageFrom(year: number, month: number | null, now = new Date()): number {
  return now.getUTCFullYear() - toCE(year) - (month !== null && now.getUTCMonth() + 1 <= month ? 1 : 0);
}

export function createProfileDraft(profile?: Profile): ProfileDraft {
  return {
    sex: profile?.sex ?? "",
    birth_year: profile ? String(profile.birth_year) : "",
    birth_month: profile?.birth_month == null ? "" : String(profile.birth_month),
    height_cm: profile ? String(profile.height_cm) : "",
    weight_kg: profile ? String(profile.weight_kg) : "",
    body_fat_pct: profile?.body_fat_pct == null ? "" : String(profile.body_fat_pct),
    activity_level: profile?.activity_level ?? "",
    training_days: profile ? String(profile.training_days) : "",
    goal: profile?.goal ?? "",
    restrictions: [...(profile?.restrictions ?? [])],
  };
}

export function profileFromDraft(draft: ProfileDraft, now = new Date()): Profile {
  function number(field: NumericField, label: string, min: number, max: number, integer = false) {
    const raw = draft[field].trim();
    const value = Number(raw);
    if (!raw || !Number.isFinite(value) || value < min || value > max || (integer && !Number.isInteger(value))) {
      throw new Error(`${label}ต้องเป็น${integer ? "จำนวนเต็ม" : "ตัวเลข"}ระหว่าง ${min}–${max}`);
    }
    return value;
  }
  const birthYear = toCE(number("birth_year", "ปีเกิด", 1900, 2643, true));
  if (birthYear < 1900 || birthYear > 2100) throw new Error("ปีเกิดต้องอยู่ระหว่าง ค.ศ. 1900–2100 หรือ พ.ศ. 2443–2643");
  const birthMonth = number("birth_month", "เดือนเกิด", 1, 12, true);
  const age = ageFrom(birthYear, birthMonth, now);
  if (age < 18 || age > 100) throw new Error(`บริการนี้สำหรับผู้ที่อายุ 18–100 ปี (อายุประมาณ ${age} ปี)`);
  if (!draft.sex || !draft.activity_level || !draft.goal) throw new Error("กรุณาเลือกเพศ ระดับกิจกรรม และเป้าหมาย");
  return {
    sex: draft.sex, birth_year: birthYear, birth_month: birthMonth,
    height_cm: number("height_cm", "ส่วนสูง", 120, 230),
    weight_kg: number("weight_kg", "น้ำหนัก", 30, 300),
    body_fat_pct: draft.body_fat_pct.trim() ? number("body_fat_pct", "เปอร์เซ็นต์ไขมัน", 3, 60) : null,
    activity_level: draft.activity_level,
    training_days: number("training_days", "จำนวนวันเล่นเวท", 0, 7, true),
    goal: draft.goal, restrictions: [...draft.restrictions],
  };
}
