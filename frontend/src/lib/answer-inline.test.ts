import assert from "node:assert/strict";
import test from "node:test";

import { tokenizeInline } from "./answer-inline.ts";

test("calculator references render as named links with exact primary destinations", () => {
  const text = "ที่มา [Mifflin และคณะ (1990)](https://pubmed.ncbi.nlm.nih.gov/2305711/) และ "
    + "[ISSN: Jäger และคณะ (2017)](https://link.springer.com/article/10.1186/s12970-017-0177-8)";
  const links = tokenizeInline(text).filter(part => part.kind === "link");
  assert.deepEqual(links, [
    { kind: "link", text: "Mifflin และคณะ (1990)", href: "https://pubmed.ncbi.nlm.nih.gov/2305711/", external: true },
    { kind: "link", text: "ISSN: Jäger และคณะ (2017)", href: "https://link.springer.com/article/10.1186/s12970-017-0177-8", external: true },
  ]);
});

for (const href of ["javascript:alert(1)", "data:text/html,test", "file:///secret", "//evil.example",
  "https://user:password@example.com", "https://", "/\\evil.example", "java\tscript:alert(1)"]) {
  test("unsupported URL stays readable text: " + href, () => {
    const raw = `[source](${href})`;
    const parts = tokenizeInline(raw);
    assert.equal(parts.some(part => part.kind === "link"), false);
    assert.equal(parts.map(part => part.text).join(""), raw);
  });
}

test("existing bold, code, citation labels and profile instructions remain readable", () => {
  assert.deepEqual(tokenizeInline("**BMR** `70 × 1.8` [S1] [โปรไฟล์](/profile)"), [
    { kind: "bold", text: "BMR" }, { kind: "text", text: " " },
    { kind: "code", text: "70 × 1.8" }, { kind: "text", text: " [S1] " },
    { kind: "link", text: "โปรไฟล์", href: "/profile", external: false },
  ]);
});

test("publication URL parentheses do not truncate a source", () => {
  const parts = tokenizeInline("[article](https://example.com/doi/(1990)/241)");
  assert.deepEqual(parts, [{ kind: "link", text: "article", href: "https://example.com/doi/(1990)/241", external: true }]);
});

test("streaming prefixes and raw HTML never disappear or become executable HTML", () => {
  const raw = "[Mifflin และคณะ (1990)](https://pubmed.ncbi.nlm.nih.gov/2305711/)";
  for (let i = 0; i < raw.length; i++) {
    assert.equal(tokenizeInline(raw.slice(0, i)).map(part => part.text).join(""), raw.slice(0, i));
  }
  assert.deepEqual(tokenizeInline('<script>alert(1)</script>'), [{ kind: "text", text: '<script>alert(1)</script>' }]);
});
