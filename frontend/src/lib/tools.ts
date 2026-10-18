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
export type ToolStatus = "success" | "partial" | "error" | "not_found" | "confirmation_required";
export type ToolCall = { name: string; status?: ToolStatus };

export function readToolStatus(value: unknown): ToolStatus | undefined {
  return typeof value === "string"
    && ["success", "partial", "error", "not_found", "confirmation_required"].includes(value)
    ? value as ToolStatus : undefined;
}

export const TOOL_LABELS: Record<string, ToolLabel> = {
  set_dietary_preferences: { running: "กำลังยืนยันข้อจำกัดอาหาร…", done: "ยืนยันข้อจำกัดอาหารแล้ว" },
  clarify_dietary_restrictions: { running: "กำลังตรวจข้อจำกัดอาหาร…", done: "ตรวจข้อจำกัดอาหารแล้ว" },
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

export function toolLabel(tool: string, running: boolean, status?: ToolStatus): string {
  const labels = TOOL_LABELS[tool] ?? UNKNOWN_TOOL;
  if (status === "success") return labels.done;
  if (status === "partial") return tool === "suggest_day_menu"
    ? "จัดตัวอย่างเมนูแล้ว ยังไม่ครบเงื่อนไขที่ขอ" : "ได้ผลลัพธ์บางส่วน";
  if (status === "error") return tool === "suggest_day_menu"
    ? "ยังจัดเมนูตามคำขอไม่ได้" : "ยังดำเนินการตามคำขอไม่ได้";
  if (status === "confirmation_required") return tool === "clarify_dietary_restrictions" || tool === "suggest_day_menu"
    ? "รอระบุชนิดอาหารที่แพ้" : "รอคุณยืนยันชื่ออาหาร";
  if (status === "not_found") return "ไม่พบรายการอาหารในฐานข้อมูล";
  if (running) return labels.running;
  // Old history has only a tool name: completion is not evidence of success.
  return "ประมวลผลคำขอแล้ว";
}

export function toolPresentation(tool: ToolCall, pending = false) {
  const status = readToolStatus(tool.status);
  const running = pending && !status;
  return {
    label: toolLabel(tool.name, running, status), running,
    icon: running ? "⚙" : status === "success" ? "✓"
      : status === "error" || status === "partial" ? "!"
      : status === "confirmation_required" ? "?" : "•",
    tone: status === "error" ? "error" : status === "partial" ? "warning"
      : status === "success" ? "success" : "neutral",
  };
}
