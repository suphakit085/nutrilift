// Guard the narrowly scoped glob replacement until Next removes fast-glob.
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";

const projectRequire = createRequire(import.meta.url);
const pluginEntry = projectRequire.resolve("@next/eslint-plugin-next");
const pluginRequire = createRequire(pluginEntry);
const { getRootDirs } = pluginRequire("./utils/get-root-dirs.js");
const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function projectFixture(t) {
  const root = mkdtempSync(path.join(tmpdir(), "nutrilift-next-lint-"));
  for (const name of ["web", "admin"]) {
    mkdirSync(path.join(root, "apps", name, "app"), { recursive: true });
    writeFileSync(path.join(root, "apps", name, "app", "page.tsx"), "export default function Page() { return null; }\n");
  }
  writeFileSync(path.join(root, "apps", "not-a-directory"), "fixture\n");
  t.after(() => {
    assert.equal(path.dirname(root), path.resolve(tmpdir()));
    assert.ok(path.basename(root).startsWith("nutrilift-next-lint-"));
    rmSync(root, { recursive: true, force: true });
  });
  return root;
}

test("Next root discovery supports directory globs, brace lists and Windows paths", (t) => {
  const root = projectFixture(t);
  const expected = ["admin", "web"].map((name) => path.join(root, "apps", name)).sort();
  for (const pattern of [path.join(root, "apps", "*"), path.join(root, "apps", "{web,admin}")]) {
    const actual = getRootDirs({ cwd: frontend, settings: { next: { rootDir: pattern } } });
    assert.deepEqual(actual.map((dir) => path.resolve(dir)).sort(), expected);
  }
  const array = getRootDirs({ cwd: frontend, settings: { next: { rootDir: [path.join(root, "apps", "web"), null] } } });
  assert.deepEqual(array.map((dir) => path.resolve(dir)), [path.join(root, "apps", "web")]);
});

test("Next lint still rejects internal HTML links when rootDir uses a glob", async (t) => {
  const root = projectFixture(t);
  const eslint = new ESLint({
    cwd: frontend,
    overrideConfig: { settings: { next: { rootDir: path.join(root, "apps", "*") } } },
  });
  const [result] = await eslint.lintText('export default function Example() { return <a href="/">Home</a>; }', {
    filePath: "src/app/next-lint-fixture.tsx",
  });
  assert.ok(result.messages.some((message) => message.ruleId === "@next/next/no-html-link-for-pages" && message.severity === 2));
});

test("Next lint accepts framework Link with the same rootDir glob", async (t) => {
  const root = projectFixture(t);
  const eslint = new ESLint({
    cwd: frontend,
    overrideConfig: { settings: { next: { rootDir: path.join(root, "apps", "*") } } },
  });
  const [result] = await eslint.lintText('import Link from "next/link"; export default function Example() { return <Link href="/">Home</Link>; }', {
    filePath: "src/app/next-lint-fixture.tsx",
  });
  assert.equal(result.errorCount, 0, JSON.stringify(result.messages));
});
