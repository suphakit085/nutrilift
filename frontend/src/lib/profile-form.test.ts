import assert from "node:assert/strict";
import { test } from "node:test";
import { ageFrom, createProfileDraft, profileFromDraft, toCE } from "./profile-form.ts";

const now = new Date("2026-10-06T00:00:00Z");
const profile = {
  sex: "male" as const, birth_year: 2000, birth_month: 2, height_cm: 175,
  weight_kg: 70, body_fat_pct: null, activity_level: "moderate" as const,
  training_days: 3, goal: "maintain" as const, restrictions: ["ไม่กินไข่"],
};

test("new profiles have no guessed personal values", () => {
  const draft = createProfileDraft();
  for (const key of ["sex", "birth_year", "birth_month", "height_cm", "weight_kg", "training_days", "activity_level", "goal"] as const) {
    assert.equal(draft[key], "");
  }
  assert.throws(() => profileFromDraft(draft, now));
});

test("saved profiles round-trip including zero training and nullable fat", () => {
  assert.deepEqual(profileFromDraft(createProfileDraft(profile), now), profile);
  const zero = { ...profile, training_days: 0 };
  assert.deepEqual(profileFromDraft(createProfileDraft(zero), now), zero);
});

test("Buddhist years normalize to Gregorian", () => {
  assert.equal(toCE(2543), 2000);
  assert.equal(profileFromDraft({ ...createProfileDraft(profile), birth_year: "2543" }, now).birth_year, 2000);
});

test("conservative age and UTC match the server at month boundaries", () => {
  assert.equal(ageFrom(2008, 10, now), 17);
  assert.equal(ageFrom(2008, 9, now), 18);
  assert.equal(ageFrom(2543, 2, now), 26);
  assert.equal(ageFrom(2000, 1, new Date("2026-01-01T00:30:00+07:00")), 25);
});

test("underage, over-age and missing month require correction", () => {
  for (const overrides of [{ birth_year: "2008", birth_month: "10" }, { birth_year: "1900" }, { birth_month: "" }]) {
    assert.throws(() => profileFromDraft({ ...createProfileDraft(profile), ...overrides }, now));
  }
  assert.equal(createProfileDraft({ ...profile, birth_month: null }).birth_month, "");
});

test("numeric bounds accept endpoints", () => {
  const result = profileFromDraft({ ...createProfileDraft(profile), height_cm: "120", weight_kg: "300", body_fat_pct: "60", training_days: "7" }, now);
  assert.equal(result.height_cm, 120);
  assert.equal(result.weight_kg, 300);
  assert.equal(result.body_fat_pct, 60);
});

for (const [field, value] of [
  ["height_cm", ""], ["height_cm", "119.9"], ["height_cm", "230.1"],
  ["weight_kg", ""], ["weight_kg", "29.9"], ["weight_kg", "300.1"],
  ["body_fat_pct", "2.9"], ["body_fat_pct", "60.1"],
  ["training_days", ""], ["training_days", "-1"], ["training_days", "8"], ["training_days", "1.5"],
  ["birth_year", "2000.5"], ["birth_year", "2300"], ["birth_month", "13"],
  ["weight_kg", "NaN"], ["weight_kg", "Infinity"],
  ["sex", ""], ["activity_level", ""], ["goal", ""],
]) {
  test(`rejects invalid ${field}=${value || "empty"}`, () => {
    assert.throws(() => profileFromDraft({ ...createProfileDraft(profile), [field]: value }, now));
  });
}
