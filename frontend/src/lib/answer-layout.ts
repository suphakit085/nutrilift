import type { Block } from "./markdown";

export type TableBlock = Extract<Block, { kind: "table" }>;

function plainLabel(text: string): string {
  return text.replace(/\*\*|`/g, "").trim();
}

/** Only known meal headers get cards; other comparison tables keep their grid. */
export function isMealTable(table: TableBlock): boolean {
  return table.rows.length > 0 && table.header.length >= 3
    && ["มื้อ", "มื้ออาหาร"].includes(plainLabel(table.header[0]))
    && ["รายการ", "รายการอาหาร", "รายการอาหารและปริมาณ"].includes(plainLabel(table.header[1]));
}

/** Collapse the long food-name suffix, never the warning itself.
 * Commas/parentheses can belong to a food's canonical name, so do not split it.
 * An incomplete suffix stays ordinary text during streaming.
 */
export function foodWarningParts(text: string): { message: string; foods: string } | null {
  const match = text.trim().match(/^([\s\S]+?)\s+\(รายการ:\s*([\s\S]+)\)$/);
  if (!match || !match[1].trim() || !match[2].trim()) return null;
  return { message: match[1].trim(), foods: match[2].trim() };
}

export function warningSection(text: string): "food" | "menu" | "health" | null {
  const label = plainLabel(text);
  if (label === "ข้อจำกัดข้อมูลอาหาร") return "food";
  if (label === "ข้อจำกัดของเมนู") return "menu";
  if (label === "ข้อควรทราบก่อนใช้เมนู") return "health";
  return null;
}

/** Derive context before React renders any callbacks; never mutate render state. */
export function withWarningSections(blocks: Block[]): { block: Block; warning: "food" | "menu" | "health" | null }[] {
  const result: { block: Block; warning: "food" | "menu" | "health" | null }[] = [];
  let warning: "food" | "menu" | "health" | null = null;
  for (const block of blocks) {
    if (block.kind === "paragraph" || block.kind === "heading") warning = warningSection(block.text);
    if (block.kind === "table" || block.kind === "rule") warning = null;
    result.push({ block, warning });
  }
  return result;
}

/** Also promote existing warnings in saved menus. Never rewrite stored text or
 * infer a diagnosis: only move calculator warning strings already displayed. */
export function prioritizeMenuWarnings(blocks: Block[]): Block[] {
  if (!blocks.some(block => block.kind === "table" && isMealTable(block))) return blocks;
  const warnings = new Set<string>();
  const remaining: Block[] = [];
  let section: ReturnType<typeof warningSection> = null;
  for (const block of blocks) {
    if (block.kind === "paragraph" || block.kind === "heading") section = warningSection(block.text);
    if (section === "health" && (block.kind === "heading" || block.kind === "paragraph")) continue;
    if (block.kind === "table" || block.kind === "rule") section = null;
    if (block.kind === "list" && (section === "health" || section === "menu")) {
      const items = block.items.filter(item => {
        const health = section === "health" || /BMI .*ต่ำกว่าเกณฑ์|พลังงานเป้าหมายต่ำกว่า|พลังงานเป้าหมายต่ำเกิน|คาร์โบไฮเดรตที่เหลือ.*ต่ำมาก/.test(item);
        if (health) warnings.add(item);
        return !health;
      });
      if (items.length) remaining.push({ ...block, items });
    } else remaining.push(block);
  }
  if (!warnings.size) return blocks;
  return [
    { kind: "heading", text: "ข้อควรทราบก่อนใช้เมนู" },
    { kind: "list", items: [...warnings] },
    ...remaining,
  ];
}
