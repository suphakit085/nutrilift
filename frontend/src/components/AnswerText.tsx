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

import { toBlocks } from "@/lib/markdown";

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
    <div className="min-w-0 leading-relaxed wrap-anywhere">
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
        if (block.kind === "table") {
          // The day-menu answer is a four-row table of food names and grams; on
          // a phone it is wider than the bubble, so the table scrolls inside its
          // own box rather than pushing the whole message pane sideways.
          // `w-max` rather than `w-full`: a full-width table cannot overflow, so
          // the scroll box never scrolls and the columns squeeze instead - which
          // is what put "27.4" on two lines and split the หัวตาราง mid-word. The
          // wrap reset is the other half of it: the bubble sets wrap-anywhere so
          // long Thai prose breaks, and inside a cell that lands mid-number.
          return (
            <div key={i} className="my-3 -mx-1 overflow-x-auto">
              <table className="w-max min-w-full border-collapse text-left text-[0.95em] [overflow-wrap:normal] [word-break:normal]">
                <thead>
                  <tr className="border-b border-border">
                    {block.header.map((cell, c) => (
                      <th
                        key={c}
                        scope="col"
                        className="px-2 py-1.5 font-semibold whitespace-pre-line"
                        style={{ textAlign: block.align[c] ?? "left" }}
                      >
                        {inline(cell, `th${i}-${c}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, r) => (
                    <tr key={r} className="border-b border-border/50 last:border-0">
                      {row.map((cell, c) => (
                        <td
                          key={c}
                          className="px-2 py-1.5 align-top whitespace-pre-line"
                          style={{ textAlign: block.align[c] ?? "left" }}
                        >
                          {inline(cell, `td${i}-${r}-${c}`)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
