import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
process.env.AUTH_UAT_SCRIPT = path.join(here, "target_citations.cjs");
process.env.AUTH_UAT_ARTIFACT_DIR = process.env.TARGET_UAT_ARTIFACT_DIR || path.resolve(
  here, "../../output/playwright/target-citations", new Date().toISOString().replaceAll(/[:.]/g, "-"),
);
await import("./run_account_flows.mjs");
