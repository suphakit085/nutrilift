/**
 * Markdown -> block list, for the assistant's answers.
 *
 * Kept apart from the React component so it can be unit-tested: the test
 * runner strips types but not JSX, so anything importable from a `.tsx` file
 * is untestable here.
 *
 * This handles the subset the model actually emits rather than pulling in a
 * Markdown library: headings, bullets, tables, bold and inline code. Anything
 * it does not recognise falls through as a plain paragraph, so an unsupported
 * construct degrades to text rather than disappearing.
 *
 * Everything must also be safe while *streaming*, where the input is a prefix
 * of the real answer: a half-arrived table or an unclosed `**` must render as
 * text and become the real thing when the rest lands.
 */

export type Align = "left" | "right" | "center";

export type Block =
  | { kind: "heading"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "paragraph"; text: string }
  | { kind: "table"; header: string[]; rows: string[][]; align: Align[] }
  | { kind: "rule" };

const HEADING = /^\s{0,3}#{1,6}\s+(.*)$/;
const BULLET = /^\s{0,3}[-*•]\s+(.*)$/;
const RULE = /^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/;

/** A candidate table row: any line carrying an unescaped "|". Leading and
 *  trailing pipes are optional, as GitHub-flavoured Markdown allows. */
const TABLE_ROW = /^\s{0,3}[^\n]*(?<!\\)\|/;
/** The `| :--- | ---: |` line under the header. One dash is enough (`:-:` is
 *  legal), and the edge pipes are optional here too. */
const TABLE_DIVIDER = /^\s{0,3}\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$/;

/** GFM only calls it a table when the divider has as many cells as the header.
 *  That check is what keeps an ordinary sentence containing a pipe, followed by
 *  a `---` horizontal rule, from being swallowed as a one-column table. */
function isTableStart(header: string, divider: string): boolean {
  if (!TABLE_ROW.test(header) || !TABLE_DIVIDER.test(divider)) return false;
  return splitRow(header).length === splitRow(divider).length;
}

/** A Markdown table row is one line, so the only way to get several lines into
 *  a cell is an HTML break - which is what the model emits for a menu's list of
 *  items. Turning it into a real newline here keeps the renderer free of HTML:
 *  the cell is still plain text, and the cell element shows the newline. */
const HTML_BREAK = /<br\s*\/?>/gi;

export function breaksToNewlines(text: string): string {
  return text.replace(HTML_BREAK, "\n");
}

/** Split "| a | b |" into ["a", "b"], tolerating a missing edge pipe. An
 *  escaped \| stays inside its cell. */
function splitRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed
    .split(/(?<!\\)\|/)
    .map((cell) => breaksToNewlines(cell.trim().replace(/\\\|/g, "|")).trim());
}

function alignmentsOf(divider: string): Align[] {
  return splitRow(divider).map((cell) => {
    const left = cell.startsWith(":");
    const right = cell.endsWith(":");
    if (left && right) return "center";
    if (right) return "right";
    return "left";
  });
}

export function toBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", text: breaksToNewlines(paragraph.join("\n")) });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      blocks.push({ kind: "list", items: list });
      list = [];
    }
  };

  const lines = source.split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];

    // A table is only a table once its divider has arrived. While the model is
    // still streaming the header row there is no divider yet, so the row falls
    // through to the paragraph branch and shows as text - the same thing it did
    // before tables were supported - and re-renders as a table a moment later.
    if (i + 1 < lines.length && isTableStart(line, lines[i + 1])) {
      flushParagraph();
      flushList();
      const header = splitRow(line);
      const align = alignmentsOf(lines[i + 1]);
      const rows: string[][] = [];
      let j = i + 2;
      for (; j < lines.length && TABLE_ROW.test(lines[j]); j += 1) {
        const cells = splitRow(lines[j]);
        // Ragged rows happen mid-stream and in hand-written Markdown; pad or
        // trim to the header so the grid never collapses.
        while (cells.length < header.length) cells.push("");
        rows.push(cells.slice(0, header.length));
      }
      blocks.push({ kind: "table", header, rows, align });
      i = j - 1;
      continue;
    }

    const heading = line.match(HEADING);
    const bullet = line.match(BULLET);

    if (RULE.test(line)) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "rule" });
    } else if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "heading", text: heading[1] });
    } else if (bullet) {
      flushParagraph();
      list.push(bullet[1]);
    } else if (line.trim() === "") {
      flushParagraph();
      flushList();
    } else {
      flushList();
      paragraph.push(line);
    }
  }
  flushParagraph();
  flushList();
  return blocks;
}
