/**
 * Names for the backend's tool calls, as the reader should see them.
 *
 * Kept out of the page component so it can be unit-tested: the test runner
 * strips types but not JSX, so anything importable from a `.tsx` file is
 * untestable here - the same reason `markdown.ts` lives apart from AnswerText.
 *
 * Two things were wrong with the single-string version this replaces. Every
 * label was the "กำลัง…" form, so a finished answer went on claiming to be
 * searching - and went on pulsing - for the life of the transcript. And
 * `suggest_day_menu` had no entry at all, so the fallback printed the raw
 * function name at the reader, which is the same leak of internal names the
 * system prompt's rule 10 forbids the model itself. Both found by driving the
 * web UI on 7 ก.ย. 2569.
 */

export type ToolLabel = { running: string; done: string };

export const TOOL_LABELS: Record<string, ToolLabel> = {
  calc_nutrition_targets: {
    running: "กำลังคำนวณพลังงานและสารอาหาร…",
    done: "คำนวณพลังงานและสารอาหารจากโปรไฟล์แล้ว",
  },
  lookup_food: {
    running: "กำลังค้นฐานข้อมูลอาหาร…",
    done: "ค้นจากฐานข้อมูลอาหารแล้ว",
  },
  suggest_day_menu: {
    running: "กำลังจัดเมนูให้ตรงเป้าหมาย…",
    done: "จัดเมนูจากฐานข้อมูลอาหารแล้ว",
  },
};

/** A tool this file has no label for still must not show its function name.
 *  A new backend tool should get an entry above; until it does, the reader
 *  sees something true and harmless rather than `suggest_day_menu`. */
export const UNKNOWN_TOOL: ToolLabel = {
  running: "กำลังใช้เครื่องมือของระบบ…",
  done: "ใช้เครื่องมือของระบบแล้ว",
};

export function toolLabel(tool: string, running: boolean): string {
  const labels = TOOL_LABELS[tool] ?? UNKNOWN_TOOL;
  return running ? labels.running : labels.done;
}
