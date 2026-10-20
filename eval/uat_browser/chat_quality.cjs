async(page)=>{
  const {origin,apiOrigin,artifactDir}=__AUTH_UAT_CONFIG__;
  const api='http://127.0.0.1:8026',email='quality-browser@example.com',password='QualityBrowser_123!';
  const checks=[],answers=[],errors=[];
  const add=(id,passed,actual={})=>{checks.push({id,passed,actual});if(!passed)throw Error('Failed: '+id);};
  page.setDefaultTimeout(30000);page.on('pageerror',error=>errors.push(error.message));
  // Forward the compiled test origin to the actual local API, without mocking responses.
  await page.route(apiOrigin+'/**',async route=>{
    const req=route.request(),url=new URL(req.url());
    const response=await page.request.fetch(api+url.pathname+url.search,{
      method:req.method(),headers:{...req.headers(),host:'127.0.0.1:8026'},data:req.postDataBuffer()??undefined,
    });await route.fulfill({response});
  });
  let headers;
  try{
    const start=await page.request.post(api+'/auth/registration/start',{data:{email,accepted_terms:true,is_adult:true}});
    add('registration-start',start.status()===200);
    const challenge=(await start.json()).challenge_id;let code;
    for(let i=0;i<50;i++){
      const mail=await(await page.request.get(api+'/__test/mail')).json();
      code=mail.findLast(row=>row.to===email&&row.code)?.code;if(code)break;await page.waitForTimeout(100);
    }
    if(!code)throw Error('No disposable SMTP code');
    const proof=await page.request.post(api+'/auth/registration/verify',{data:{challenge_id:challenge,code}});
    const finish=await page.request.post(api+'/auth/registration/finish',{data:{challenge_id:challenge,setup_token:(await proof.json()).setup_token,password}});
    add('ownership-verified',finish.status()===200);
    headers={Authorization:'Bearer '+(await finish.json()).access_token};
    const get=async path=>{const r=await page.request.get(api+path,{headers});if(!r.ok())throw Error('GET '+path+' '+r.status());return r.json();};
    await page.goto(origin+'/login');await page.locator('body').ariaSnapshot();
    await page.locator('input[name=email]').fill(email);await page.locator('input[name=password]').fill(password);
    await page.locator('button[type=submit]').click();await page.waitForURL('**/profile');
    const base={sex:'male',birth_year:2000,birth_month:1,height_cm:175,weight_kg:70,body_fat_pct:null,activity_level:'moderate',training_days:3,goal:'maintain',restrictions:[]};
    const cases=[
      {id:'underweight',profile:{...base,weight_kg:50,height_cm:180,goal:'cut',activity_level:'light'},question:'จากโปรไฟล์ผมอยากลดไขมัน ช่วยกำหนดแคลอรี่และจัดเมนู 3 มื้อ',count:3},
      {id:'six-meals',profile:{...base,weight_kg:82,height_cm:178,birth_year:2005,activity_level:'active',goal:'bulk',restrictions:['ไม่ใช้อาหารเสริม']},question:'ช่วยจัดเมนูทั้งหมด 6 มื้อ เพิ่มมื้อเสริมได้ ไม่ใช้อาหารเสริม',count:6},
      {id:'budget',profile:base,question:'จัดเมนู 3 มื้อ งบ 120 บาทต่อวัน',count:3},
      {id:'vegan-peanut',profile:{...base,sex:'female',weight_kg:58,height_cm:162,restrictions:['วีแกน','แพ้ถั่วลิสง']},question:'ช่วยจัดเมนู 3 มื้อจากโปรไฟล์',count:3},
      {id:'unsupported-allergy',profile:{...base,restrictions:['แพ้เห็ด']},question:'ช่วยจัดเมนู 3 มื้อ',count:0},
    ];
    for(const item of cases){
      add(item.id+'-profile',(await page.request.put(api+'/profile/settings',{headers,data:item.profile})).status()===200);
      const before=await get('/profile'),revisions=await get('/profile/history');
      await page.goto(origin+'/chat');await page.getByPlaceholder('พิมพ์คำถามเรื่องอาหารและโภชนาการ…').waitFor();
      await page.locator('body').ariaSnapshot();
      await page.getByPlaceholder('พิมพ์คำถามเรื่องอาหารและโภชนาการ…').fill(item.question);
      const pending=page.waitForResponse(r=>r.url().endsWith('/chat')&&r.request().method()==='POST');
      await page.getByRole('button',{name:'ส่ง',exact:true}).click();const response=await pending;
      await page.getByRole('button',{name:'ส่ง',exact:true}).waitFor();
      add(item.id+'-http',response.status()===200);
      const id=response.url().split('/conversations/')[1].split('/')[0];
      const detail=await get('/conversations/'+id),reply=detail.messages.findLast(m=>m.role==='assistant'),text=reply.content;
      const rows=text.split('\n').filter(line=>line.startsWith('| มื้อ')&&!line.includes('มื้ออาหาร |'));
      add(item.id+'-count',rows.length===item.count);
      add(item.id+'-profile-unchanged',JSON.stringify(await get('/profile'))===JSON.stringify(before)&&JSON.stringify(await get('/profile/history'))===JSON.stringify(revisions));
      if(item.id==='underweight'){
        add('health-warning-before-target',text.indexOf('BMI 15.4')>=0&&text.indexOf('BMI 15.4')<text.indexOf('เป้าหมาย: พลังงาน')&&text.split('BMI 15.4').length===2);
        add('health-maintenance-unchanged',text.includes('2062 kcal')&&text.includes('ไม่กำหนดพลังงานขาดดุล'));
        const note=page.getByRole('note',{name:'ข้อควรทราบก่อนใช้เมนู',exact:true});await note.waitFor();
        add('health-notice-before-table-in-dom',await note.evaluate(node=>!!(node.compareDocumentPosition(document.querySelector('table'))&Node.DOCUMENT_POSITION_FOLLOWING)));
      }
      if(item.id==='six-meals'){
        add('supplemental-no-fresh-noodles-or-raw-potatoes',rows.filter(line=>line.startsWith('| มื้อเสริม')).every(line=>!line.includes('เส้นใหญ่, สด')&&!line.includes('มันฝรั่ง:')));
        add('recorded-state-visible',rows.some(line=>line.includes('น้ำหนักสุกตามรายการ'))&&rows.some(line=>line.includes('น้ำหนักดิบตามรายการ')));
        add('no-supplement-powders',rows.every(line=>!line.includes('เวย์')&&!line.includes('ไอโซเลท')));
      }
      if(item.id==='budget'){
        add('budget-before-menu',text.indexOf('ยังไม่ได้คำนวณราคา')>=0&&text.indexOf('ยังไม่ได้คำนวณราคา')<text.indexOf('| มื้ออาหาร'));
        add('budget-not-success',reply.tool_calls?.[0]?.status==='partial');
        await page.getByText(/จัดตัวอย่างเมนูแล้ว ยังไม่ครบเงื่อนไขที่ขอ/).waitFor();
      }
      if(item.id==='unsupported-allergy'){
        add('unsupported-specific-and-kept',text.includes('เห็ด')&&text.includes('ยังไม่มีตัวกรอง')&&!text.includes('ระบุข้อจำกัดให้ชัดเจน')&&reply.tool_calls?.[0]?.status==='error');
      }
      if(item.id==='vegan-peanut')add('vegan-allergy-kept',rows.every(line=>!/(ถั่วลิสง|อกไก่|เนื้อวัว|ปลาแซลมอน|ไข่ไก่|เวย์)/.test(line)));
      for(const width of [320,390,1280]){
        await page.setViewportSize({width,height:900});add(item.id+'-layout-'+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      }
      if(item.count){
        const tableRegion=page.getByRole('region',{name:'ตารางเมนูอาหาร เลื่อนแนวนอนได้',exact:true});
        add(item.id+'-keyboard-table-scroll',await tableRegion.getAttribute('tabindex')==='0');
        await tableRegion.focus();add(item.id+'-table-focus',await tableRegion.evaluate(node=>node===document.activeElement));
      }
      await page.setViewportSize({width:390,height:844});
      if(item.id==='underweight')await page.getByRole('note',{name:'ข้อควรทราบก่อนใช้เมนู',exact:true}).scrollIntoViewIfNeeded();
      await page.screenshot({path:artifactDir+'/'+item.id+'-phone.png',fullPage:true});
      await page.setViewportSize({width:1280,height:900});await page.reload();
      await page.getByPlaceholder('พิมพ์คำถามเรื่องอาหารและโภชนาการ…').waitFor();
      await page.getByRole('navigation').getByRole('button',{name:detail.title,exact:true}).click();
      await page.getByText(item.question,{exact:true}).waitFor();
      if(item.id==='underweight')await page.getByRole('note',{name:'ข้อควรทราบก่อนใช้เมนู',exact:true}).waitFor();
      add(item.id+'-history-restored',(await get('/conversations/'+id)).messages.findLast(m=>m.role==='assistant').content===text);
      answers.push({id:item.id,question:item.question,answer:text,tools:reply.tool_calls,profile:item.profile});
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
