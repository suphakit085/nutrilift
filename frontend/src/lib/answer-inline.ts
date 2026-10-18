/** Text-only parsing: never interpret HTML or execute a model-supplied URL. */
export type InlinePart =
  | { kind: "text" | "bold" | "code"; text: string }
  | { kind: "link"; text: string; href: string; external: boolean };

function linkTarget(href: string): { href: string; external: boolean } | null {
  if (/[\s\\\u0000-\u001f\u007f]/u.test(href)) return null;
  if (href.startsWith("/") && !href.startsWith("//")) return { href, external: false };
  if (!/^https?:\/\//i.test(href)) return null;
  try {
    const url = new URL(href);
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) return null;
    return { href: url.href, external: true };
  } catch {
    return null;
  }
}

export function tokenizeInline(text: string): InlinePart[] {
  const parts: InlinePart[] = [];
  // One balanced parenthesis level covers common publication/DOI paths. Leave
  // other syntax literal instead of losing text during streaming.
  const pattern = /\*\*(.+?)\*\*|`([^`]+?)`|\[([^\]\n]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) parts.push({ kind: "text", text: text.slice(last, match.index) });
    if (match[1] !== undefined) parts.push({ kind: "bold", text: match[1] });
    else if (match[2] !== undefined) parts.push({ kind: "code", text: match[2] });
    else {
      const target = linkTarget(match[4]);
      parts.push(target ? { kind: "link", text: match[3], ...target } : { kind: "text", text: match[0] });
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", text: text.slice(last) });
  return parts;
}
