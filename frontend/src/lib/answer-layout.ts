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

export function warningSection(text: string): "food" | "menu" | null {
  const label = plainLabel(text);
  if (label === "ข้อจำกัดข้อมูลอาหาร") return "food";
  if (label === "ข้อจำกัดของเมนู") return "menu";
  return null;
}

/** Derive context before React renders any callbacks; never mutate render state. */
export function withWarningSections(blocks: Block[]): { block: Block; warning: "food" | "menu" | null }[] {
  const result: { block: Block; warning: "food" | "menu" | null }[] = [];
  let warning: "food" | "menu" | null = null;
  for (const block of blocks) {
    if (block.kind === "paragraph" || block.kind === "heading") warning = warningSection(block.text);
    if (block.kind === "table" || block.kind === "rule") warning = null;
    result.push({ block, warning });
  }
  return result;
}
