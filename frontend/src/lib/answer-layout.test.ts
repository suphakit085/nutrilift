import assert from "node:assert/strict";
import test from "node:test";

import { foodWarningParts, isMealTable, prioritizeMenuWarnings, warningSection, withWarningSections } from "./answer-layout.ts";
import { toBlocks } from "./markdown.ts";

const menu = [
  "| มื้ออาหาร | รายการอาหารและปริมาณ | พลังงาน (kcal) | โปรตีน (g) | คาร์บ (g) | ไขมัน (g) |",
  "| --- | --- | ---: | ---: | ---: | ---: |",
  "| มื้อเช้า | ไข่ต้ม: 2 ฟอง<br>ข้าวสวย: 180 กรัม | 0.0 | 12.5 | 40.0 | 8.0 |",
  "| มื้อเสริมที่ 3 | นม: 1 กล่อง | 150.0 | 8.0 | 15.0 | 5.0 |",
  "| รวมทั้งวัน | | 2500.0 | 140.0 | 300.0 | 70.0 |",
].join("\n");

test("saved menu health warning moves before the menu without changing text or totals", () => {
  const warning = "BMI 15.4 ต่ำกว่าเกณฑ์ 18.5 ระบบไม่กำหนดพลังงานขาดดุลให้";
  const blocks = toBlocks(menu + "\n\nข้อจำกัดของเมนู\n- " + warning + "\n- โปรตีนขาด 20%");
  const before = JSON.stringify(blocks);
  const ordered = prioritizeMenuWarnings(blocks);
  assert.deepEqual(ordered[0], { kind: "heading", text: "ข้อควรทราบก่อนใช้เมนู" });
  assert.deepEqual(ordered[1], { kind: "list", items: [warning] });
  assert.deepEqual(ordered.find(b => b.kind === "table"), blocks.find(b => b.kind === "table"));
  assert.equal(JSON.stringify(ordered).split(warning).length - 1, 1);
  assert.ok(JSON.stringify(ordered).includes("โปรตีนขาด 20%"));
  assert.equal(JSON.stringify(blocks), before);
  assert.deepEqual(prioritizeMenuWarnings(ordered), ordered);
});

test("new health section is visible before the meal and never becomes a food disclosure", () => {
  const warning = "พลังงานเป้าหมายต่ำกว่า 1,200 kcal/วัน กรุณาปรึกษานักกำหนดอาหาร";
  const ordered = prioritizeMenuWarnings(toBlocks("### ข้อควรทราบก่อนใช้เมนู\n- " + warning + "\n\n" + menu));
  const health = withWarningSections(ordered).find(item => item.warning === "health" && item.block.kind === "list");
  assert.ok(health);
  assert.equal(foodWarningParts(warning), null);
  assert.deepEqual(ordered[1], { kind: "list", items: [warning] });
});

test("ordinary answers and meal source notes keep their existing order", () => {
  for (const text of ["งานวิจัยเรื่อง BMI [S1]", menu + "\n\nข้อจำกัดข้อมูลอาหาร\n- ข้อมูลใยอาหารยังไม่ครบ"]) {
    const blocks = toBlocks(text);
    assert.deepEqual(prioritizeMenuWarnings(blocks), blocks);
  }
});

test("meal recognition preserves all portions, supplemental rows, totals and zero values", () => {
  const table = toBlocks(menu)[0];
  assert.equal(table.kind, "table");
  if (table.kind !== "table") return;
  const before = JSON.stringify(table);
  assert.equal(isMealTable(table), true);
  assert.equal(JSON.stringify(table), before);
  assert.equal(table.rows[0][1], "ไข่ต้ม: 2 ฟอง\nข้าวสวย: 180 กรัม");
  assert.equal(table.rows[0][2], "0.0");
  assert.equal(table.rows[1][0], "มื้อเสริมที่ 3");
  assert.deepEqual(table.rows[2], ["รวมทั้งวัน", "", "2500.0", "140.0", "300.0", "70.0"]);
});

test("research comparison tables and streamed headers are not guessed to be meal cards", () => {
  for (const text of ["| อาหาร | โปรตีน |\n| --- | --- |\n| ไข่ | 12.5 |", menu.split("\n").slice(0, 2).join("\n")]) {
    const table = toBlocks(text)[0];
    if (table.kind !== "table") throw new Error("expected table");
    assert.equal(isMealTable(table), false);
  }
});

test("incomplete meal rows never become invented numeric zeroes", () => {
  const table = toBlocks(menu.split("\n").slice(0, 2).join("\n") + "\n| มื้อเช้า | ไข่")[0];
  if (table.kind !== "table") throw new Error("expected table");
  assert.equal(isMealTable(table), true);
  assert.equal(table.rows[0][2], "");
});

test("food warnings keep their full message and canonical names containing commas and parentheses", () => {
  const message = "คาร์โบไฮเดรตนี้รวมใยอาหารด้วย ไม่ใช่คาร์โบไฮเดรตที่ใช้ได้";
  const foods = "ปลาแซลมอนแอตแลนติก (เลี้ยง), อบ, ข้าวเจ้า, สุก";
  assert.deepEqual(foodWarningParts(`${message} (รายการ: ${foods})`), { message, foods });
  assert.equal(warningSection("**ข้อจำกัดข้อมูลอาหาร**"), "food");
  assert.equal(warningSection("ข้อจำกัดของเมนู"), "menu");
  assert.equal(warningSection("คำแนะนำเพิ่มเติม"), null);
});

test("partial or ordinary warnings stay fully visible without a disclosure", () => {
  for (const text of ["โปรตีนขาด 20%", "กรุณาตรวจส่วนผสมเมื่อแพ้อาหาร", "ยังไม่มีค่าใยอาหาร (รายการ: ข้าว", "คำเตือน (รายการ: )"]) {
    assert.equal(foodWarningParts(text), null);
  }
});

test("streamed menu and warning prefixes remain safe to render", () => {
  const full = menu + "\n\nข้อจำกัดข้อมูลอาหาร\n\n- ยังไม่มีค่าใยอาหาร (รายการ: แป้งปลูก)";
  for (let i = 1; i <= full.length; i++) {
    for (const block of toBlocks(full.slice(0, i))) {
      if (block.kind === "table") assert.doesNotThrow(() => isMealTable(block));
      if (block.kind === "list") for (const item of block.items) assert.doesNotThrow(() => foodWarningParts(item));
    }
  }
});

test("only food-data warning lists get compact food names; allergy and deficit warnings stay intact", () => {
  const blocks = toBlocks("ข้อจำกัดข้อมูลอาหาร\n\n- ยังไม่มีค่าใยอาหาร (รายการ: ข้าว)\n\nข้อจำกัดของเมนู\n- โปรตีนขาด 20%\n- กรุณาตรวจส่วนผสมเมื่อแพ้อาหาร\n\nคำแนะนำเพิ่มเติม\n- ข้อความธรรมดา (รายการ: ตัวอย่าง)");
  const before = JSON.stringify(blocks);
  const lists = withWarningSections(blocks).filter(({ block }) => block.kind === "list");
  assert.deepEqual(lists.map(({ warning }) => warning), ["food", "menu", null]);
  assert.equal(JSON.stringify(blocks), before);
});
