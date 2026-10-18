import assert from "node:assert/strict";
import test from "node:test";

import { TOOL_LABELS, toolLabel, toolPresentation, readToolStatus } from "./tools.ts";

// The three tools chat.py declares. If the backend gains a fourth, the last
// test here is the one that should start failing.
const BACKEND_TOOLS = ["calc_nutrition_targets", "lookup_food", "suggest_day_menu"];

test("a finished tool call no longer claims to be running", () => {
  for (const tool of BACKEND_TOOLS) {
    const done = toolLabel(tool, false);
    assert.ok(!done.startsWith("กำลัง"), `${tool} still says "กำลัง" when finished: ${done}`);
    assert.ok(!done.includes("…"), `${tool} keeps its ellipsis when finished: ${done}`);
  }
});

test("a running tool call says so", () => {
  for (const tool of BACKEND_TOOLS) {
    assert.ok(toolLabel(tool, true).startsWith("กำลัง"));
  }
});

test("no label ever shows a function name", () => {
  // What the reader saw before: the chip above a day's menu read
  // "suggest_day_menu". Rule 10 of the system prompt forbids the model from
  // printing internal names; the UI must hold to the same line.
  for (const tool of [...BACKEND_TOOLS, "some_future_tool"]) {
    for (const running of [true, false]) {
      const label = toolLabel(tool, running);
      assert.ok(!label.includes("_"), `${tool} leaked an identifier: ${label}`);
      assert.ok(!/[a-z]+_[a-z]+/.test(label), `${tool} leaked an identifier: ${label}`);
    }
  }
});

test("an unknown tool falls back instead of printing its name", () => {
  assert.ok(!toolLabel("brand_new_tool", true).includes("brand"));
  assert.ok(toolLabel("brand_new_tool", true).startsWith("กำลัง"));
  assert.ok(!toolLabel("brand_new_tool", false).startsWith("กำลัง"));
});

test("every tool the backend declares has its own label", () => {
  for (const tool of BACKEND_TOOLS) {
    assert.ok(tool in TOOL_LABELS, `${tool} has no label and would use the generic fallback`);
  }
});

test("only an explicit successful outcome earns a checkmark, including during streaming", () => {
  for (const pending of [false, true]) {
    assert.equal(toolPresentation({ name: "suggest_day_menu", status: "success" }, pending).icon, "✓");
    for (const status of ["partial", "error", "not_found", "confirmation_required", undefined] as const) {
      const shown = toolPresentation({ name: "suggest_day_menu", status }, pending);
      assert.notEqual(shown.icon, "✓", String(status));
      if (status) assert.equal(shown.running, false);
    }
  }
});

test("old history stays neutral and failures and partial menus explain the outcome", () => {
  assert.equal(toolPresentation({ name: "suggest_day_menu" }).tone, "neutral");
  assert.ok(!toolPresentation({ name: "suggest_day_menu" }).label.includes("จัดเมนู"));
  assert.match(toolPresentation({ name: "suggest_day_menu", status: "partial" }).label, /ยังไม่ครบเงื่อนไขที่ขอ/);
  assert.match(toolPresentation({ name: "suggest_day_menu", status: "error" }).label, /ไม่ได้/);
  assert.match(toolPresentation({ name: "lookup_food", status: "confirmation_required" }).label, /รอคุณยืนยัน/);
});

test("unrecognized or malformed outcomes never become success", () => {
  for (const value of [null, "done", true, {}, ["success"], 1]) assert.equal(readToolStatus(value), undefined);
  assert.equal(readToolStatus("success"), "success");
});
