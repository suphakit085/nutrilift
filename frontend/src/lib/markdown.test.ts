import assert from "node:assert/strict";
import test from "node:test";

import { toBlocks } from "./markdown.ts";

// The day-menu answer the meal-plan tool produces. Reported on 4 ก.ย. 2569 as
// "ตารางดูเพี้ยน": the renderer had no table support, so the reader saw the
// pipes and the `:---` divider as literal text.
const MENU_TABLE = [
  "| มื้ออาหาร | รายการอาหารและปริมาณ | โปรตีน |",
  "| :--- | :--- | ---: |",
  "| มื้อเช้า | ปลากะพง (200 กรัม), มันสำปะหลัง (325 กรัม) | 42 g |",
  "| มื้อกลางวัน | เนื้อวัวไม่ติดมัน (75 กรัม), ข้าวสวย (8 ทัพพี) | 42.5 g |",
].join("\n");

test("a pipe table becomes a table block", () => {
  const blocks = toBlocks(MENU_TABLE);
  assert.equal(blocks.length, 1);
  const table = blocks[0];
  assert.equal(table.kind, "table");
  if (table.kind !== "table") return;
  assert.deepEqual(table.header, ["มื้ออาหาร", "รายการอาหารและปริมาณ", "โปรตีน"]);
  assert.equal(table.rows.length, 2);
  assert.equal(table.rows[0][0], "มื้อเช้า");
  assert.equal(table.rows[1][2], "42.5 g");
});

test("divider colons set column alignment", () => {
  const table = toBlocks(MENU_TABLE)[0];
  if (table.kind !== "table") throw new Error("expected a table");
  assert.deepEqual(table.align, ["left", "left", "right"]);
  const centred = toBlocks("| a | b |\n| :-: | --- |\n| 1 | 2 |")[0];
  if (centred.kind !== "table") throw new Error("expected a table");
  assert.equal(centred.align[0], "center");
});

test("a table without an edge pipe still parses", () => {
  const table = toBlocks("a | b\n--- | ---\n1 | 2")[0];
  assert.equal(table.kind, "table");
});

test("prose before and after a table is kept", () => {
  const blocks = toBlocks(`นี่คือเมนูครับ\n\n${MENU_TABLE}\n\nปรับวิธีปรุงได้`);
  assert.deepEqual(
    blocks.map((b) => b.kind),
    ["paragraph", "table", "paragraph"],
  );
});

test("a header row with no divider yet stays text while streaming", () => {
  // Mid-stream the divider has not arrived. It must not vanish or throw; it
  // shows as text and becomes a table once the next line lands.
  const blocks = toBlocks("| มื้ออาหาร | โปรตีน |");
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].kind, "paragraph");
});

test("every prefix of a table answer parses without throwing", () => {
  const full = `สรุปเมนูครับ\n\n${MENU_TABLE}\n\nรวม 2,684 kcal`;
  for (let i = 1; i <= full.length; i += 1) {
    assert.doesNotThrow(() => toBlocks(full.slice(0, i)), `prefix length ${i}`);
  }
});

test("a short row is padded to the header width", () => {
  const table = toBlocks("| a | b | c |\n| --- | --- | --- |\n| 1 |")[0];
  if (table.kind !== "table") throw new Error("expected a table");
  assert.deepEqual(table.rows[0], ["1", "", ""]);
});

test("an escaped pipe stays inside its cell", () => {
  const table = toBlocks("| a | b |\n| --- | --- |\n| x \\| y | z |")[0];
  if (table.kind !== "table") throw new Error("expected a table");
  assert.equal(table.rows[0][0], "x | y");
});

test("a horizontal rule is not mistaken for a table divider", () => {
  const blocks = toBlocks("ก่อนหน้า\n\n---\n\nหลังจาก");
  assert.deepEqual(
    blocks.map((b) => b.kind),
    ["paragraph", "rule", "paragraph"],
  );
});

test("an HTML break inside a cell becomes a real newline", () => {
  // A table row is one line, so <br> is the only way the model can put a menu's
  // several items in one cell. Reported on 7 ก.ย. 2569: the reader saw the tag.
  const table = toBlocks(
    "| มื้อ | รายการ |\n| --- | --- |\n| เช้า | - ปลากะพง: 1.25 × 100 กรัม<br>- มันสำปะหลัง: 3.25 × 100 กรัม |",
  )[0];
  if (table.kind !== "table") throw new Error("expected a table");
  assert.equal(
    table.rows[0][1],
    "- ปลากะพง: 1.25 × 100 กรัม\n- มันสำปะหลัง: 3.25 × 100 กรัม",
  );
});

test("every spelling of the break tag is handled", () => {
  const table = toBlocks("| a | b |\n| --- | --- |\n| x<br>y<BR/>z<br />w | 1 |")[0];
  if (table.kind !== "table") throw new Error("expected a table");
  assert.equal(table.rows[0][0], "x\ny\nz\nw");
});

test("a break in ordinary prose is a newline too", () => {
  const blocks = toBlocks("บรรทัดแรก<br>บรรทัดสอง");
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].kind, "paragraph");
  if (blocks[0].kind !== "paragraph") return;
  assert.equal(blocks[0].text, "บรรทัดแรก\nบรรทัดสอง");
});

test("no other HTML is touched", () => {
  // Only <br> is understood. Anything else stays literal text rather than
  // becoming markup - the renderer never interprets HTML from the model.
  const blocks = toBlocks("<b>ตัวหนา</b> กับ <script>alert(1)</script>");
  if (blocks[0].kind !== "paragraph") throw new Error("expected a paragraph");
  assert.equal(blocks[0].text, "<b>ตัวหนา</b> กับ <script>alert(1)</script>");
});

test("headings, bullets and paragraphs still work", () => {
  const blocks = toBlocks("### มื้อเช้า\n\n- ข้าวสวย 2 ทัพพี\n- ไข่ต้ม 2 ฟอง\n\nกินให้ครบนะครับ");
  assert.deepEqual(
    blocks.map((b) => b.kind),
    ["heading", "list", "paragraph"],
  );
});
