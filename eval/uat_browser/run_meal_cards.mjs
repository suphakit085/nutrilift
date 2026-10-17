import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const workspace = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const frontend = path.join(workspace, 'frontend');
const npmCli = process.env.npm_execpath;
if (!npmCli) throw new Error('Run this check with npm run test:meal-ui from frontend/.');
const port = Number(process.env.MEAL_UAT_PORT || 3041);
const remote = process.env.MEAL_UAT_ORIGIN;
if (remote && !process.env.MEAL_UAT_API_BASE) throw new Error('Remote checks require MEAL_UAT_API_BASE.');
const origin = (remote || `http://127.0.0.1:${port}`).replace(/\/$/, '');
const apiOrigin = (process.env.MEAL_UAT_API_BASE || 'https://api.example.invalid').replace(/\/$/, '');
for (const value of [origin, apiOrigin]) {
  const url = new URL(value);
  if (url.username || url.password || url.search || url.hash) throw new Error('UAT origins must not contain credentials or query strings.');
}
const artifactDir = path.resolve(process.env.MEAL_UAT_ARTIFACT_DIR ||
  path.join(workspace, 'output/playwright/meal-card-regressions', new Date().toISOString().replaceAll(/[:.]/g, '-')));
mkdirSync(artifactDir, { recursive: true });
const session = 'meal-cards-' + process.pid;
const cli = args => {
  const result = spawnSync(process.execPath, [npmCli, 'exec', '--yes', '--package=@playwright/cli@0.1.22', '--',
    'playwright-cli', '--session', session, ...args],
  { cwd: frontend, encoding: 'utf8', timeout: 240000, windowsHide: true, maxBuffer: 12 * 1024 * 1024 });
  if (result.error) throw result.error;
  if (result.status !== 0 || result.stdout.includes('### Error')) {
    throw new Error((result.stdout + '\n' + result.stderr).slice(-8000));
  }
  return result.stdout;
};
let server;
let serverLogs = '';
let opened = false;
try {
  if (!remote) {
    await new Promise((resolve, reject) => {
      const probe = createServer();
      probe.once('error', reject);
      probe.listen(port, '127.0.0.1', () => probe.close(resolve));
    });
    server = spawn(process.execPath, [path.join(frontend, 'node_modules/next/dist/bin/next'),
      'start', '--hostname', '127.0.0.1', '--port', String(port)],
    { cwd: frontend, env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1' }, windowsHide: true });
    server.stdout.on('data', data => { serverLogs += data; });
    server.stderr.on('data', data => { serverLogs += data; });
    let ready = false;
    for (let attempt = 0; attempt < 80; attempt++) {
      if (server.exitCode !== null) throw new Error('Next server exited: ' + serverLogs);
      try { const response = await fetch(origin + '/login'); if (response.ok) { ready = true; break; } } catch { /* startup */ }
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    if (!ready) throw new Error('Next server did not become ready: ' + serverLogs);
  }
  const source = readFileSync(path.join(workspace, 'eval/uat_browser/meal_cards.cjs'), 'utf8');
  const prepared = source.replace('__MEAL_UAT_CONFIG__', JSON.stringify({ origin, apiOrigin, artifactDir, fixtures: JSON.parse(readFileSync(path.join(workspace, 'eval/uat_browser/fixtures/meal-answers.json'), 'utf8')) }));
  const snippet = path.join(artifactDir, 'browser-check.cjs');
  writeFileSync(snippet, prepared);
  cli(['open', origin + '/login', '--browser=chrome']);
  opened = true;
  const output = cli(['run-code', '--filename', snippet]);
  writeFileSync(path.join(artifactDir, 'browser-cli.txt'), output);
  const section = output.split('### Result\n')[1];
  if (!section) throw new Error('The browser check did not return a result.');
  const report = JSON.parse(section.split('\n### ')[0].trim());
  writeFileSync(path.join(artifactDir, 'results.json'), JSON.stringify(report, null, 2) + '\n');
  for (const check of report.checks) console.log(`${check.passed ? 'PASS' : 'FAIL'} ${check.id}`);
  console.log(`Meal-card browser checks: ${report.passed} passed, ${report.failed} failed. Evidence: ${artifactDir}`);
  if (report.failed) process.exitCode = 1;
} finally {
  if (opened) { try { cli(['close']); } catch { /* preserve the original failure */ } }
  if (server) {
    server.kill();
    if (server.exitCode === null) await new Promise(resolve => {
      server.once('exit', resolve);
      setTimeout(resolve, 3000).unref();
    });
    writeFileSync(path.join(artifactDir, 'next-server.txt'), serverLogs);
  }
}
