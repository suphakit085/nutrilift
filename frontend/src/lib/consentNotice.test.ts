import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// ConsentNotice is a .tsx component and this runner strips types but not JSX,
// so the notice is checked as text - the same reason tools.ts and markdown.ts
// live apart from their components. Whitespace is collapsed the way a browser
// collapses the JSX line wraps, so a phrase split across source lines still
// matches.
const notice = readFileSync(new URL("../components/ConsentNotice.tsx", import.meta.url), "utf8")
  .replace(/\s+/g, " ");

test("the notice says the chat goes to Google Gemini", () => {
  // chat.py sends the conversation and a profile summary to Gemini on every
  // turn. A notice that leaves this out collects consent to something other
  // than what the system does.
  assert.ok(notice.includes("Google Gemini"), "the notice never names Google Gemini");
  assert.ok(notice.includes("ข้อมูลที่ส่งออกนอกระบบ"), "the paragraph on data leaving the system is gone");
});

test("the notice does not claim nothing is shared with third parties", () => {
  // The first version said exactly this while every chat turn went to Google.
  assert.ok(
    !notice.includes("ไม่มีการส่งต่อหรือขายให้บุคคลที่สาม"),
    "the false 'not shared with third parties' claim is back",
  );
});

test("the notice warns against typing identifying details into the chat", () => {
  // Gemini's unpaid terms say not to submit personal information; the notice
  // is the only place a user learns to keep it out of what they type.
  assert.ok(notice.includes("ไม่ควรพิมพ์ชื่อ-นามสกุล"), "the warning about identifying details is gone");
});
