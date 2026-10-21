async(page)=>{
  const {origin,apiOrigin,artifactDir}=__AUTH_UAT_CONFIG__;
  const api='http://127.0.0.1:8026',email='methods@example.com',password='LocalMethods_123!';
  const checks=[],errors=[];
  const add=(id,passed)=>{checks.push({id,passed});if(!passed)throw new Error(id);};
  page.setDefaultTimeout(20000);
  page.on('pageerror',e=>errors.push(e.message));
  await page.route(apiOrigin+'/**',async route=>{
    const request=route.request(),url=new URL(request.url());
    const response=await page.request.fetch(api+url.pathname+url.search,{method:request.method(),headers:{...request.headers(),host:'127.0.0.1:8026'},data:request.postDataBuffer()??undefined});
    await route.fulfill({response});
  });
  await page.goto(origin+'/login');await page.locator('body').ariaSnapshot();
  await page.getByRole('button',{name:'สมัครสมาชิก',exact:true}).click();
  await page.locator('input[name=email]').fill(email);
  for(const box of await page.getByRole('checkbox').all())await box.check();
  await page.getByRole('button',{name:'ส่งรหัสยืนยัน',exact:true}).click();
  await page.getByRole('heading',{name:'กรอกรหัสยืนยันอีเมล',exact:true}).waitFor();
  let code;
  for(let i=0;i<50;i++){
    const mail=await(await page.request.get(api+'/__test/mail')).json();
    code=mail.findLast(m=>m.to===email&&m.code)?.code;
    if(code)break;await page.waitForTimeout(100);
  }
  if(!code)throw new Error('No local OTP');
  await page.locator('input[name=email-code]').fill(code);
  await page.getByRole('button',{name:'ยืนยันรหัส',exact:true}).click();
  await page.getByRole('heading',{name:'ตั้งรหัสผ่านของคุณ',exact:true}).waitFor();
  await page.locator('input[name=new-password]').fill(password);
  await page.locator('input[name=confirm-new-password]').fill(password);
  await page.getByRole('button',{name:'ตั้งรหัสผ่านและเริ่มใช้งาน',exact:true}).click();
  await page.waitForURL('**/profile');await page.locator('body').ariaSnapshot();
  await page.getByLabel('เพศ',{exact:true}).selectOption('male');
  await page.locator('input[name=birth-year]').fill('2000');
  await page.getByLabel('เดือนเกิด',{exact:true}).selectOption('1');
  await page.getByLabel('ส่วนสูง (ซม.)',{exact:true}).fill('175');
  await page.getByLabel('น้ำหนัก (กก.)',{exact:true}).fill('70');
  await page.getByLabel('เล่นเวทกี่วัน/สัปดาห์',{exact:true}).fill('3');
  await page.getByLabel('ระดับกิจกรรมโดยรวม',{exact:true}).selectOption('moderate');
  await page.getByLabel('เป้าหมาย',{exact:true}).selectOption('maintain');
  const save=()=>page.getByRole('button',{name:'บันทึกและคำนวณ',exact:true}).click();
  await save();await page.waitForURL('**/chat');add('signup-and-first-profile-save',true);
  await page.goto(origin+'/profile');await page.locator('body').ariaSnapshot();
  const methods=page.getByRole('region',{name:'สูตรที่ใช้คำนวณจริง',exact:true});
  await methods.waitFor();
  add('all-seven-methods-visible',await methods.locator('div.border-t').count()===7);
  add('mifflin-operands-and-protein-rate', (await methods.innerText()).includes('10 × 70')&&(await methods.innerText()).includes('70 × 1.8'));
  add('method-references-open-safely',await methods.locator('a[target="_blank"][rel="noopener noreferrer"]').count()===3);
  await page.screenshot({path:artifactDir+'/normal-methods.png',fullPage:true});
  const change=async(weight,height,goal)=>{
    await page.getByLabel('น้ำหนัก (กก.)',{exact:true}).fill(String(weight));
    await page.getByLabel('ส่วนสูง (ซม.)',{exact:true}).fill(String(height));
    await page.getByLabel('เป้าหมาย',{exact:true}).selectOption(goal);
    add('edited-'+weight+'-hides-stale-methods',!await methods.isVisible());
    await save();
  };
  await change(120,200,'bulk');await methods.waitFor();
  await page.screenshot({path:artifactDir+'/bmi30.png',fullPage:true});
  add('bmi30-bulk-surplus-suppressed',(await page.locator('body').innerText()).toLowerCase().includes('เพิ่มกล้ามเนื้อ (bulk) → รักษาน้ำหนัก (maintain)'));
  add('high-bmi-recommends-fat-loss-first',(await page.locator('body').innerText()).includes('ลดไขมันก่อน bulk'));
  await page.getByRole('button',{name:'เลือกเป้าหมายลดไขมัน',exact:true}).click();
  add('fat-loss-action-selects-draft-only',await page.getByLabel('เป้าหมาย',{exact:true}).inputValue()==='cut'&&!await methods.isVisible());
  await page.reload();await methods.waitFor();
  add('draft-does-not-silently-change-saved-goal',await page.getByLabel('เป้าหมาย',{exact:true}).inputValue()==='bulk');
  await page.getByRole('button',{name:'เลือกเป้าหมายลดไขมัน',exact:true}).click();
  await save();await methods.waitFor();
  add('user-can-save-recommended-cut',await page.getByLabel('เป้าหมาย',{exact:true}).inputValue()==='cut'&&await page.getByRole('button',{name:'เลือกเป้าหมายลดไขมัน',exact:true}).count()===0);
  for(const [weight,height] of [[200,230],[300,230],[50,180]]){
    await change(weight,height,'bulk');
    await page.getByRole('alert').filter({hasText:'นอกขอบเขต'}).waitFor();
    add('unsupported-'+weight+'-no-targets',!await methods.isVisible());
  }
  await page.screenshot({path:artifactDir+'/referral.png',fullPage:true});
  await change(50,175,'cut');await methods.waitFor();
  add('mild-underweight-deficit-suppressed',(await page.locator('body').innerText()).toLowerCase().includes('ลดไขมัน (cut) → รักษาน้ำหนัก (maintain)'));
  await change(70,175,'maintain');await methods.waitFor();
  const fat=page.getByLabel(/^เปอร์เซ็นต์ไขมัน/);
  if(await fat.count()){
    await fat.fill('20');await save();await methods.waitFor();
    add('body-fat-selects-katch',(await methods.innerText()).includes('370 + 21.6'));
  }else throw new Error('body fat control not found');
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:artifactDir+'/mobile-methods.png',fullPage:true});
  add('mobile-no-horizontal-overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  add('no-browser-runtime-errors',errors.length===0);
  return {mode:'Disposable local API, database, SMTP and production frontend build. No production deployment or external email.',checks,passed:checks.filter(c=>c.passed).length,failed:checks.filter(c=>!c.passed).length,errors};
}
