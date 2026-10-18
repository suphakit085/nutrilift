import path from "node:path";
import {fileURLToPath} from "node:url";
const here=path.dirname(fileURLToPath(import.meta.url));
process.env.DIETARY_UAT="1";
process.env.AUTH_UAT_SCRIPT=path.join(here,"chat_quality.cjs");
process.env.AUTH_UAT_ARTIFACT_DIR=process.env.QUALITY_UAT_ARTIFACT_DIR||path.resolve(here,"../../output/playwright/chat-quality",new Date().toISOString().replaceAll(/[:.]/g,"-"));
await import("./run_account_flows.mjs");
