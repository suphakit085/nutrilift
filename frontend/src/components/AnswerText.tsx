/**
 * Render the assistant's answer.
 *
 * The answers arrive as Markdown - the system prompt asks for headings and
 * bullets when there are several points, and the model obliges. Until now the
 * bubble rendered `{content}` inside `whitespace-pre-wrap`, so a user reading a
 * day's menu saw the source: `### **มื้อเช้า**` and `* **ข้าวสวย:** 7 × 1 ทัพพี`.
 * Found by driving the real UI on 4 ก.ย. 2569.
 *
 * This handles the subset the model actually emits rather than pulling in a
 * Markdown library: headings, bullets, bold, and inline code. Anything it does
 * not recognise falls through as plain text, which is the same thing the old
 * code did - so an unsupported construct degrades to what we had before rather
 * than disappearing.
 *
 * It also has to be safe while *streaming*: half of a `**bold**` arrives before
 * the other half, so the inline splitter must leave an unclosed marker alone
 * instead of swallowing the rest of the answer.
 */

type Block =
  | { kind: "heading"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "paragraph"; text: string }
  | { kind: "rule" };

const HEADING = /^\s{0,3}#{1,6}\s+(.*)$/;
const BULLET = /^\s{0,3}[-*•]\s+(.*)$/;
const RULE = /^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/;

function toBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      blocks.push({ kind: "list", items: list });
      list = [];
    }
  };

  for (const line of source.split("\n")) {
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

/** `**bold**` and `` `code` ``. An unclosed marker is left as literal text so a
 *  half-streamed token does not eat the rest of the line. */
function inline(text: string, keyPrefix: string) {
  const parts: React.ReactNode[] = [];
  const pattern = /\*\*(.+?)\*\*|`([^`]+?)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    if (match[1] !== undefined) {
      parts.push(
        <strong key={`${keyPrefix}-b${index}`} className="font-semibold">
          {match[1]}
        </strong>,
      );
    } else {
      parts.push(
        <code key={`${keyPrefix}-c${index}`} className="stat-figure text-[0.95em]">
          {match[2]}
        </code>,
      );
    }
    last = pattern.lastIndex;
    index += 1;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function AnswerText({ content }: { content: string }) {
  const blocks = toBlocks(content);
  return (
    <div className="leading-relaxed">
      {blocks.map((block, i) => {
        if (block.kind === "rule") {
          return <hr key={i} className="my-3 border-border" />;
        }
        if (block.kind === "heading") {
          return (
            <h3 key={i} className="mt-4 mb-1.5 font-display text-base font-bold first:mt-0">
              {inline(block.text, `h${i}`)}
            </h3>
          );
        }
        if (block.kind === "list") {
          return (
            <ul key={i} className="my-2 list-disc space-y-1 pl-5">
              {block.items.map((item, j) => (
                <li key={j}>{inline(item, `l${i}-${j}`)}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i} className="my-2 whitespace-pre-wrap first:mt-0 last:mb-0">
            {inline(block.text, `p${i}`)}
          </p>
        );
      })}
    </div>
  );
}
