import assert from "node:assert/strict";
import test from "node:test";

import { TOOL_LABELS, toolLabel } from "./tools.ts";

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
