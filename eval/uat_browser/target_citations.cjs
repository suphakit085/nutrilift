async(page)=>{
  const {origin,apiOrigin,artifactDir}=__AUTH_UAT_CONFIG__;
  const api='http://127.0.0.1:8026',email='target-provenance@example.com',password='TargetBrowser_123!';
  const checks=[],answers=[],errors=[];
  const add=(id,passed,actual={})=>{checks.push({id,passed,actual});if(!passed)throw Error('Failed: '+id);};
  page.setDefaultTimeout(20000);page.on('pageerror',error=>errors.push(error.message));
  await page.route(apiOrigin+'/**',async route=>{
    const req=route.request(),url=new URL(req.url());
    const response=await page.request.fetch(api+url.pathname+url.search,{
      method:req.method(),headers:{...req.headers(),host:'127.0.0.1:8026'},data:req.postDataBuffer()??undefined,
    });
    await route.fulfill({response});
  });
  let headers;
  try{
    const start=await page.request.post(api+'/auth/registration/start',{data:{email,accepted_terms:true,is_adult:true}});
    add('registration-start',start.status()===200);
    const challenge=(await start.json()).challenge_id;
    let code;
    for(let i=0;i<50;i++){
      const mail=await(await page.request.get(api+'/__test/mail')).json();
      code=mail.findLast(row=>row.to===email&&row.code)?.code;
      if(code)break;await page.waitForTimeout(100);
    }
    if(!code)throw Error('No disposable SMTP code');
    const proof=await page.request.post(api+'/auth/registration/verify',{data:{challenge_id:challenge,code}});
    const finish=await page.request.post(api+'/auth/registration/finish',{data:{challenge_id:challenge,setup_token:(await proof.json()).setup_token,password}});
    add('ownership-verified',finish.status()===200);
    headers={Authorization:'Bearer '+(await finish.json()).access_token};
    const get=async path=>{const r=await page.request.get(api+path,{headers});if(!r.ok())throw Error('GET '+path+' '+r.status());return r.json();};
    await page.goto(origin+'/login');await page.locator('body').ariaSnapshot();
    await page.locator('input[name=email]').fill(email);await page.locator('input[name=password]').fill(password);
    await page.locator('button[type=submit]').click();await page.waitForURL('**/chat');
    const base={sex:'male',birth_year:2000,birth_month:1,height_cm:175,weight_kg:70,body_fat_pct:null,activity_level:'moderate',training_days:3,goal:'maintain',restrictions:[]};
    const send=async text=>{
      await page.locator('body').ariaSnapshot();
      await page.getByPlaceholder('พิมพ์คำถามเรื่องอาหารและโภชนาการ…').fill(text);
      const pending=page.waitForResponse(r=>r.url().endsWith('/chat')&&r.request().method()==='POST');
      await page.getByRole('button',{name:'ส่ง',exact:true}).click();const response=await pending;
      await page.getByRole('button',{name:'ส่ง',exact:true}).waitFor();
      if(response.status()!==200)throw Error('Chat status '+response.status());
      return response.url().split('/conversations/')[1].split('/')[0];
    };
    const scenarios=[
      {id:'original-maintain',profile:base,question:'จากโปรไฟล์ตอนนี้ ฉันควรกินพลังงานและโปรตีนวันละเท่าไร ใช้สูตรอะไร ขอแหล่งอ้างอิงด้วย'},
      {id:'female-cut',profile:{...base,sex:'female',weight_kg:62.5,height_cm:165.5,activity_level:'active',goal:'cut'},question:'ช่วยสรุปเป้าพลังงานตามโปรไฟล์ พร้อมสูตรและที่มา'},
      {id:'body-fat',profile:{...base,body_fat_pct:17.25},question:'โปรไฟล์นี้คำนวณพลังงานอย่างไร ขออ้างอิงด้วย'},
    ];
    for(const scenario of scenarios){
      const seeded=await page.request.put(api+'/profile/settings',{headers,data:scenario.profile});
      add(scenario.id+'-profile',seeded.status()===200);
      const before=await get('/profile'),revisions=await get('/profile/history');
      await page.goto(origin+'/chat');await page.getByPlaceholder('พิมพ์คำถามเรื่องอาหารและโภชนาการ…').waitFor();
      const id=await send(scenario.question);
      await page.getByRole('link',{name:'ISSN: Jäger และคณะ (2017)',exact:true}).waitFor();
      const detail=await get('/conversations/'+id),reply=detail.messages.findLast(m=>m.role==='assistant');
      const text=reply.content,targets=await get('/profile/targets');
      add(scenario.id+'-actual-numbers',text.includes(targets.energy_target_kcal+' กิโลแคลอรี/วัน')&&text.includes(targets.macros.protein_g+' กรัม/วัน'));
      add(scenario.id+'-protein-operands',text.includes(scenario.profile.weight_kg+' × '+(scenario.profile.goal==='cut'?'2':'1.8')));
      add(scenario.id+'-source-link',(await page.getByRole('link',{name:'ISSN: Jäger และคณะ (2017)',exact:true}).getAttribute('href'))==='https://link.springer.com/article/10.1186/s12970-017-0177-8');
      if(scenario.id==='body-fat'){
        add('body-fat-honest-source-gap',text.includes('ยังไม่มีลิงก์เอกสารต้นฉบับ')&&await page.getByRole('link',{name:'Mifflin และคณะ (1990)',exact:true}).count()===0);
      }else{
        add(scenario.id+'-formula-source',(await page.getByRole('link',{name:'Mifflin และคณะ (1990)',exact:true}).getAttribute('href'))==='https://pubmed.ncbi.nlm.nih.gov/2305711/');
      }
      add(scenario.id+'-policy-separated',text.includes('การเลือกของเครื่องคำนวณโครงการ')&&!text.includes('[S'));
      add(scenario.id+'-profile-unchanged',JSON.stringify(await get('/profile'))===JSON.stringify(before)&&JSON.stringify(await get('/profile/history'))===JSON.stringify(revisions));
      for(const width of [320,390,1280]){
        await page.setViewportSize({width,height:900});
        add(scenario.id+'-layout-'+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      }
      add(scenario.id+'-sidebar-source-hint',await page.getByText('อ่านแหล่งอ้างอิงได้จากลิงก์ในคำตอบ',{exact:true}).isVisible());
      await page.setViewportSize({width:390,height:844});
      await page.screenshot({path:artifactDir+'/'+scenario.id+'-phone.png',fullPage:true});
      await page.setViewportSize({width:1280,height:900});
      await page.reload();await page.getByPlaceholder('พิมพ์คำถามเรื่องอาหารและโภชนาการ…').waitFor();
      await page.getByRole('navigation').getByRole('button',{name:detail.title,exact:true}).click();
      await page.getByRole('link',{name:'ISSN: Jäger และคณะ (2017)',exact:true}).waitFor();
      add(scenario.id+'-history-links',JSON.stringify((await get('/conversations/'+id)).messages.findLast(m=>m.role==='assistant').content)===JSON.stringify(text));
      answers.push({id:scenario.id,question:scenario.question,answer:text,profile:scenario.profile,targets});
    }
    add('runtime-errors',errors.length===0,errors);
    add('delete-disposable-account',(await page.request.delete(api+'/auth/account',{headers,data:{password}})).status()===204);
    add('deleted-token-denied',(await page.request.get(api+'/auth/me',{headers})).status()===401);
    return {checks,answers,passed:checks.filter(c=>c.passed).length,failed:checks.filter(c=>!c.passed).length};
  }catch(error){
    await page.screenshot({path:artifactDir+'/failure.png',fullPage:true}).catch(()=>{});
    if(headers)await page.request.delete(api+'/auth/account',{headers,data:{password}}).catch(()=>{});
    throw error;
  }
}
