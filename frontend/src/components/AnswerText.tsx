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
import { foodWarningParts, isMealTable, withWarningSections, type TableBlock } from "@/lib/answer-layout";

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

function MealCards({ table }: { table: TableBlock }) {
  return (
    <section aria-label="เมนูอาหารแบบรายมื้อ" className="my-3 space-y-3 md:hidden print:hidden">
      {table.rows.map((row, r) => (
        <article key={r} aria-label={row[0] || "มื้ออาหาร"} className="min-w-0 rounded-md border border-border bg-surface-sunken/40 p-3">
          <h4 className="font-display font-semibold">{inline(row[0], `meal-${r}`)}</h4>
          {row[1] && (
            <ul aria-label={`รายการอาหาร ${row[0]}`} className="mt-2 space-y-1.5 text-sm">
              {row[1].split("\n").filter((item) => item.trim()).map((item, j) => (
                <li key={j}>{inline(item, `food-${r}-${j}`)}</li>
              ))}
            </ul>
          )}
          <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 border-t border-border pt-2 text-sm">
            {table.header.slice(2).map((label, c) => (
              <div key={c} className="min-w-0">
                <dt className="text-xs text-muted">{inline(label, `metric-${r}-${c}`)}</dt>
                <dd className="stat-figure font-medium">{inline(row[c + 2] || "—", `value-${r}-${c}`)}</dd>
              </div>
            ))}
          </dl>
        </article>
      ))}
    </section>
  );
}

export function AnswerText({ content }: { content: string }) {
  const blocks = withWarningSections(toBlocks(content));
  return (
    <div className="min-w-0 leading-relaxed wrap-anywhere">
      {blocks.map(({ block, warning }, i) => {
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
              {block.items.map((item, j) => {
                const parts = warning === "food" ? foodWarningParts(item) : null;
                return (
                  <li key={j}>
                    {inline(parts?.message ?? item, `l${i}-${j}`)}
                    {parts && (
                      <details className="mt-1 text-sm">
                        <summary className="cursor-pointer text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
                          ดูรายชื่ออาหารที่เกี่ยวข้อง
                        </summary>
                        <p className="mt-1 text-muted">{inline(parts.foods, `names${i}-${j}`)}</p>
                      </details>
                    )}
                  </li>
                );
              })}
            </ul>
          );
        }
        if (block.kind === "table") {
          const cards = isMealTable(block);
          // Meal cards fit a phone. Other tables retain a scrollable grid;
          // desktop grids avoid breaking a nutrient value across lines.
          return (
            <div key={i}>
              {cards && <MealCards table={block} />}
              <div className={`my-3 -mx-1 overflow-x-auto ${cards ? "hidden md:block print:block" : ""}`}>
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
