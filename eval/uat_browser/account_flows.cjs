async(page)=>{
  const {origin,apiOrigin,artifactDir}=__AUTH_UAT_CONFIG__;
  const api='http://127.0.0.1:8026',email='browser-owner@example.com';
  const checks=[],errors=[];
  const add=(id,passed,actual={})=>checks.push({id,passed,actual});
  page.setDefaultTimeout(15000);
  page.on('pageerror',e=>errors.push(e.message));
  // The built bundle uses the isolated CI origin. Forward requests to the
  // actual disposable API; do not synthesize account responses or tokens.
  await page.route(apiOrigin+'/**',async route=>{
    const req=route.request(),url=new URL(req.url());
    const response=await page.request.fetch(api+url.pathname+url.search,{
      method:req.method(),headers:{...req.headers(),host:'127.0.0.1:8026'},data:req.postDataBuffer()??undefined,
    });
    await route.fulfill({response});
  });
  const headers=()=>page.evaluate(()=>({Authorization:'Bearer '+localStorage.getItem('nutrition_token')}));
  const mail=async(subject,to=email)=>{
    for(let i=0;i<40;i++){
      const rows=await(await page.request.get(api+'/__test/mail')).json();
      const found=rows.findLast(row=>row.to===to&&row.subject.includes(subject));
      if(found?.links[0])return found.links[0];
      await page.waitForTimeout(100);
    }
    throw new Error('Expected local SMTP message was not captured');
  };
  const login=async(address,password,destination='/chat')=>{
    await page.goto(origin+'/login');
    await page.locator('body').ariaSnapshot();
    await page.locator('input[name=email]').fill(address);
    await page.locator('input[name=password]').fill(password);
    await page.locator('button[type=submit]').click();
    await page.waitForURL('**'+destination);
  };
  const passwordFields=async(password)=>{
    await page.locator('body').ariaSnapshot();
    await page.locator('input[name=new-password]').fill(password);
    await page.locator('input[name=confirm-new-password]').fill(password);
  };
  await page.goto(origin+'/login');
  await page.locator('body').ariaSnapshot();
  await page.getByRole('button',{name:'สมัครสมาชิก',exact:true}).click();
  await page.locator('input[name=email]').fill(email);
  await page.locator('input[name=password]').fill('BrowserOriginal_123!');
  await page.locator('input[name=confirm-password]').fill('BrowserOriginal_123!');
  add('signup-consent-required',!(await page.locator('form').evaluate(f=>f.checkValidity())));
  await page.getByRole('checkbox').nth(0).check();
  await page.getByRole('checkbox').nth(1).check();
  await page.locator('button[type=submit]').click();
  await page.waitForURL('**/verify-email');
  add('signup-verification-gate',await page.getByRole('heading',{name:'ยืนยันอีเมลของคุณ',exact:true}).isVisible());
  const pendingHeaders=await headers();
  add('unverified-profile-blocked',(await page.request.get(api+'/profile',{headers:pendingHeaders})).status()===403);
  add('unverified-conversations-blocked',(await page.request.get(api+'/conversations',{headers:pendingHeaders})).status()===403);
  const verifyLink=await mail('ยืนยันอีเมล');
  const rawVerify=new URLSearchParams(new URL(verifyLink).hash.slice(1)).get('token');
  await page.goto(verifyLink);
  await passwordFields('BrowserVerified_123!');
  await page.getByRole('button',{name:'ยืนยันอีเมลและตั้งรหัสผ่าน',exact:true}).click();
  await page.getByRole('link',{name:'ดำเนินการต่อ',exact:true}).waitFor();
  add('verification-clears-fragment',!page.url().includes('#'));
  add('verification-revokes-preregistration-session',(await page.request.get(api+'/auth/me',{headers:pendingHeaders})).status()===401);
  add('verification-link-single-use',(await page.request.post(api+'/auth/verify-email',{data:{token:rawVerify,new_password:'BrowserVerified_123!'}})).status()===400);
  add('preregistration-password-rejected',(await page.request.post(api+'/auth/login',{data:{email,password:'BrowserOriginal_123!'}})).status()===401);
  await login(email,'BrowserVerified_123!');
  await page.goto(origin+'/account');
  await page.getByText('ยืนยันอีเมลแล้ว',{exact:true}).waitFor();
  add('verified-account-visible',true);
  const beforeChange=await headers();
  await page.locator('input[name=current-password]').fill('BrowserVerified_123!');
  await passwordFields('BrowserChanged_456!');
  await page.getByRole('button',{name:'เปลี่ยนรหัสผ่าน',exact:true}).click();
  await page.getByRole('status').filter({hasText:'เปลี่ยนรหัสผ่านแล้ว'}).waitFor();
  add('password-change-revokes-old-session',(await page.request.get(api+'/auth/me',{headers:beforeChange})).status()===401);
  const active=await headers();
  add('password-change-issues-current-session',(await page.request.get(api+'/auth/me',{headers:active})).status()===200);
  await page.setViewportSize({width:390,height:844});
  add('account-phone-layout',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:artifactDir+'/account-phone.png',fullPage:true});
  await page.getByRole('button',{name:'ออกจากระบบเครื่องนี้',exact:true}).click();
  await page.waitForURL('**/login');
  add('logout-revokes-server-session',(await page.request.get(api+'/auth/me',{headers:active})).status()===401);
  await page.getByRole('link',{name:'ลืมรหัสผ่าน',exact:true}).click();
  await page.getByRole('heading',{name:'ลืมรหัสผ่าน',exact:true}).waitFor();
  await page.locator('body').ariaSnapshot();
  await page.getByLabel('อีเมล',{exact:true}).fill(email);
  await page.getByRole('button',{name:'ส่งลิงก์ตั้งรหัสผ่านใหม่',exact:true}).click();
  await page.getByRole('status').waitFor();
  const resetLink=await mail('ตั้งรหัสผ่าน');
  const rawReset=new URLSearchParams(new URL(resetLink).hash.slice(1)).get('token');
  await page.goto(resetLink);
  await passwordFields('BrowserReset_789!');
  await page.getByRole('button',{name:'บันทึกรหัสผ่านใหม่',exact:true}).click();
  await page.getByRole('status').waitFor();
  add('reset-clears-fragment',!page.url().includes('#'));
  add('reset-link-single-use',(await page.request.post(api+'/auth/reset-password',{data:{token:rawReset,new_password:'BrowserReset_789!'}})).status()===400);
  await login(email,'BrowserReset_789!');
  add('reset-password-login',true);
  await page.goto(origin+'/account');
  await page.getByText('ยืนยันอีเมลแล้ว',{exact:true}).waitFor();
  const ownerHeaders=await headers();
  // Open somebody else's verification link while this owner is logged in.
  const second='browser-second@example.com';
  await page.request.post(api+'/auth/register',{data:{email:second,password:'SecondOriginal_123!',accepted_terms:true,is_adult:true}});
  await page.goto(await mail('ยืนยันอีเมล',second));
  await passwordFields('SecondVerified_123!');
  await page.getByRole('button',{name:'ยืนยันอีเมลและตั้งรหัสผ่าน',exact:true}).click();
  await page.getByRole('link',{name:'ดำเนินการต่อ',exact:true}).waitFor();
  add('cross-account-link-keeps-owner-session',(await page.request.get(api+'/auth/me',{headers:ownerHeaders})).status()===200);
  add('cross-account-link-verifies-correct-owner',(await page.request.post(api+'/auth/login',{data:{email:second,password:'SecondVerified_123!'}})).status()===200);
  await login(email,'BrowserReset_789!');
  await page.goto(origin+'/account');
  await page.getByText('ยืนยันอีเมลแล้ว',{exact:true}).waitFor();
  await page.locator('body').ariaSnapshot();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'ดาวน์โหลดข้อมูลของฉัน',exact:true}).click();
  add('account-export',(await download).suggestedFilename()==='nutrilift-data.json');
  const beforeEmail=await headers();
  await page.locator('input[name=new-email]').fill('browser-renamed@example.com');
  await page.locator('input[name=email-current-password]').fill('BrowserReset_789!');
  await page.getByRole('button',{name:'ส่งลิงก์ยืนยันอีเมลใหม่',exact:true}).click();
  await page.getByRole('status').filter({hasText:'ส่งลิงก์ไปยังอีเมลใหม่แล้ว'}).waitFor();
  add('old-email-valid-until-confirmed',(await(await page.request.get(api+'/auth/me',{headers:beforeEmail})).json()).email===email);
  await page.goto(await mail('ยืนยันอีเมลใหม่','browser-renamed@example.com'));
  await page.locator('body').ariaSnapshot();
  await page.getByRole('button',{name:'ยืนยันเปลี่ยนอีเมล',exact:true}).click();
  await page.getByRole('link',{name:'ดำเนินการต่อ',exact:true}).waitFor();
  add('email-change-revokes-sessions',(await page.request.get(api+'/auth/me',{headers:beforeEmail})).status()===401);
  await login('browser-renamed@example.com','BrowserReset_789!');
  await page.goto(origin+'/account');
  await page.getByText('browser-renamed@example.com',{exact:true}).waitFor();
  await page.locator('body').ariaSnapshot();
  // CLI owns native modal dialogs. Accept this confirmation only for the
  // disposable account; backend password/ownership checks remain real.
  await page.evaluate(()=>{window.confirm=()=>true;});
  await page.locator('input[name=privacy-password]').fill('BrowserReset_789!');
  await page.getByRole('button',{name:'ถอนความยินยอมและออกจากระบบ',exact:true}).click();
  await page.waitForURL('**/login');
  await login('browser-renamed@example.com','BrowserReset_789!','/consent');
  await page.getByRole('checkbox').waitFor();
  add('withdrawal-requires-consent',await page.getByRole('checkbox').isVisible());
  await page.goto(origin+'/account');
  await page.getByText('browser-renamed@example.com',{exact:true}).waitFor();
  add('account-rights-after-withdrawal',await page.getByRole('button',{name:'ลบบัญชีและข้อมูลทั้งหมด',exact:true}).isVisible());
  const deleteHeaders=await headers();
  await page.locator('input[name=privacy-password]').fill('BrowserReset_789!');
  await page.locator('input[name=delete-confirmation]').fill('ลบบัญชี');
  await page.evaluate(()=>{window.confirm=()=>true;});
  await page.getByRole('button',{name:'ลบบัญชีและข้อมูลทั้งหมด',exact:true}).click();
  await page.waitForURL('**/login');
  add('delete-removes-account',(await page.request.get(api+'/auth/me',{headers:deleteHeaders})).status()===401);
  // Recorded old API contract: the new frontend can appear before Railway
  // finishes deploying. This is the only synthetic-response case in this run.
  await page.route(apiOrigin+'/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    const json=(status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body),headers:{'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Headers':'authorization,content-type','Access-Control-Allow-Methods':'GET,POST,OPTIONS'}});
    if(route.request().method()==='OPTIONS')return json(200,{});
    if(path==='/auth/login')return json(200,{access_token:'legacy-fixture-only',token_type:'bearer'});
    if(path==='/auth/me')return json(200,{id:'legacy',email:'legacy@example.com',needs_consent:false,consent_version:'2026-09-11'});
    if(path==='/conversations')return json(200,[]);
    return json(404,{detail:'Not Found'});
  });
  await page.setViewportSize({width:1280,height:900});
  await login('legacy@example.com','LegacyPassword_123!');
  await page.getByPlaceholder('พิมพ์คำถามเรื่องอาหารและโภชนาการ…').waitFor();
  await page.locator('body').ariaSnapshot();
  await page.getByRole('button',{name:'ออกจากระบบ',exact:true}).click();
  await page.waitForURL('**/login');
  add('frontend-first-rollout-old-api-login-and-logout',await page.evaluate(()=>localStorage.getItem('nutrition_token')===null));
  add('browser-runtime',errors.length===0,{errors});
  await page.evaluate(()=>localStorage.removeItem('nutrition_token'));
  return {mode:'Disposable API/SQLite with actual local SMTP capture; final legacy rollout case uses a recorded old-API contract fixture; no external emails or production data',checks,passed:checks.filter(c=>c.passed).length,failed:checks.filter(c=>!c.passed).length};
}
