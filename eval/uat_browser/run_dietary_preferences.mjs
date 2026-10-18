import path from "node:path";
import {fileURLToPath} from "node:url";
const here=path.dirname(fileURLToPath(import.meta.url));
process.env.DIETARY_UAT="1";
process.env.AUTH_UAT_SCRIPT=path.join(here,"dietary_preferences.cjs");
process.env.AUTH_UAT_ARTIFACT_DIR=process.env.DIETARY_UAT_ARTIFACT_DIR||path.resolve(here,"../../output/playwright/dietary-regressions",new Date().toISOString().replaceAll(/[:.]/g,"-"));
await import("./run_account_flows.mjs");
