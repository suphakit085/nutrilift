import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const workspace=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const frontend=path.join(workspace,'frontend');
const npmCli=process.env.npm_execpath;
if(!npmCli)throw new Error('Run with npm run test:account-ui from frontend/.');
const origin='http://127.0.0.1:3026',api='http://127.0.0.1:8026';
const apiOrigin=(process.env.AUTH_UAT_API_BASE||'https://api.example.invalid').replace(/\/$/,'');
const artifactDir=path.resolve(process.env.AUTH_UAT_ARTIFACT_DIR||path.join(workspace,'output/playwright/account-regressions',new Date().toISOString().replaceAll(/[:.]/g,'-')));
mkdirSync(artifactDir,{recursive:true});
const session='account-flows-'+process.pid;
const servers=[];
let opened=false;
const cli=args=>{
  const result=spawnSync(process.execPath,[npmCli,'exec','--yes','--package=@playwright/cli@0.1.22','--','playwright-cli','--session',session,...args],
    {cwd:frontend,encoding:'utf8',timeout:240000,windowsHide:true,maxBuffer:12*1024*1024});
  if(result.error)throw result.error;
  if(result.status!==0||result.stdout.includes('### Error'))throw new Error((result.stdout+'\n'+result.stderr).slice(-8000));
  return result.stdout;
};
const free=port=>new Promise((resolve,reject)=>{
  const probe=createServer();probe.once('error',reject);probe.listen(port,'127.0.0.1',()=>probe.close(resolve));
});
const start=(name,command,args,cwd)=>{
  const child=spawn(command,args,{cwd,env:{...process.env,NEXT_TELEMETRY_DISABLED:'1'},windowsHide:true});
  const record={child,name,logs:''};servers.push(record);
  child.stdout.on('data',data=>{record.logs+=data;});child.stderr.on('data',data=>{record.logs+=data;});
  child.on('error',error=>{record.logs+=String(error);});return record;
};
const ready=async(url,record)=>{
  for(let i=0;i<100;i++){
    if(record&&record.child.exitCode!==null)throw new Error(record.name+' exited: '+record.logs);
    try{if((await fetch(url)).ok)return;}catch{/* startup */}
    await new Promise(resolve=>setTimeout(resolve,200));
  }
  throw new Error('Local account UAT service was not ready');
};
try{
  await free(3026);
  if(process.env.AUTH_UAT_MANAGED_API!=='1'){
    await free(8026);await free(1026);
    const python=process.env.AUTH_UAT_PYTHON||path.join(workspace,'backend/.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
    const backend=start('account-api',python,[path.join(workspace,'eval/uat_browser/local_accounts.py')],workspace);
    await ready(api+'/health',backend);
  }else await ready(api+'/health');
  const web=start('account-next',process.execPath,[path.join(frontend,'node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port','3026'],frontend);
  await ready(origin+'/login',web);
  const config={origin,apiOrigin,artifactDir};
  if(process.env.AUTH_UAT_RECIPIENT_FILE)Object.assign(config,JSON.parse(readFileSync(process.env.AUTH_UAT_RECIPIENT_FILE,'utf8')));
  const script=process.env.AUTH_UAT_SCRIPT||path.join(workspace,process.argv.includes('--methods')?'eval/uat_browser/presentation_methods.cjs':process.argv.includes('--onboarding')?'eval/uat_browser/profile_onboarding.cjs':'eval/uat_browser/account_flows.cjs');
  const snippet=path.join(artifactDir,'browser-check.cjs');
  writeFileSync(snippet,readFileSync(script,'utf8').replace('__AUTH_UAT_CONFIG__',JSON.stringify(config)));
  cli(['open',origin+'/login','--browser=chrome']);opened=true;
  const output=cli(['run-code','--filename',snippet]);
  writeFileSync(path.join(artifactDir,'browser-cli.txt'),output);
  const section=output.split('### Result\n')[1];
  if(!section)throw new Error('Account browser check returned no result');
  const report=JSON.parse(section.split('\n### ')[0].trim());
  writeFileSync(path.join(artifactDir,'results.json'),JSON.stringify(report,null,2)+'\n');
  for(const c of report.checks)console.log(`${c.passed?'PASS':'FAIL'} ${c.id}`);
  console.log(`Account browser checks: ${report.passed} passed, ${report.failed} failed. Evidence: ${artifactDir}`);
  if(report.failed)process.exitCode=1;
}finally{
  if(opened){try{cli(['close']);}catch{/* preserve failure */}}
  for(const record of servers.reverse()){
    if(record.name==='account-api'){
      try{await fetch(api+'/__test/shutdown',{method:'POST'});}catch{/* already stopped */}
      if(record.child.exitCode===null)await new Promise(resolve=>{record.child.once('exit',resolve);setTimeout(resolve,3000).unref();});
    }
    if(record.child.exitCode===null)record.child.kill();
    writeFileSync(path.join(artifactDir,record.name+'.txt'),record.logs);
  }
}
