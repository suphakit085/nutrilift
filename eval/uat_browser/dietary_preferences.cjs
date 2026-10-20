async(page)=>{
  const {origin,apiOrigin,artifactDir}=__AUTH_UAT_CONFIG__;
  const api='http://127.0.0.1:8026',email='dietary-browser@example.com',password='DietaryBrowser_123!';
  try {
  const checks=[],errors=[];
  const add=(id,passed,actual={})=>{checks.push({id,passed,actual});if(!passed)throw Error('Failed: '+id);};
  page.setDefaultTimeout(20000);page.on('pageerror',error=>errors.push(error.message));
  await page.route(apiOrigin+'/**',async route=>{
    const req=route.request(),url=new URL(req.url());
    const response=await page.request.fetch(api+url.pathname+url.search,{
      method:req.method(),headers:{...req.headers(),host:'127.0.0.1:8026'},data:req.postDataBuffer()??undefined,
    });
    await route.fulfill({response});
  });
  // Real disposable API/SMTP ownership; the feature under test begins at profile.
  const started=await page.request.post(api+'/auth/registration/start',{data:{email,accepted_terms:true,is_adult:true}});
  add('local-registration-start',started.status()===200);
  const challenge=(await started.json()).challenge_id;let code;
  for(let i=0;i<40;i++){
    const mail=await(await page.request.get(api+'/__test/mail')).json();
    code=mail.findLast(row=>row.to===email&&row.code)?.code;if(code)break;await page.waitForTimeout(100);
  }
  if(!code)throw Error('No local SMTP ownership code');
  const proof=await page.request.post(api+'/auth/registration/verify',{data:{challenge_id:challenge,code}});
  const finish=await page.request.post(api+'/auth/registration/finish',{data:{challenge_id:challenge,setup_token:(await proof.json()).setup_token,password}});
  add('local-ownership-verified',finish.status()===200);
  await page.goto(origin+'/login');await page.locator('body').ariaSnapshot();
  await page.locator('input[name=email]').fill(email);await page.locator('input[name=password]').fill(password);
  await page.locator('button[type=submit]').click();await page.waitForURL('**/profile');
  const headers={Authorization:'Bearer '+(await finish.json()).access_token};
  const get=async path=>{const r=await page.request.get(api+path,{headers});return await r.json();};
  const profile={sex:'female',birth_year:1998,birth_month:2,height_cm:162,weight_kg:58,body_fat_pct:null,activity_level:'moderate',training_days:3,goal:'maintain',restrictions:['วีแกน','แพ้ถั่ว']};
  const seeded=await page.request.put(api+'/profile',{headers,data:profile});add('legacy-profile-seeded',seeded.status()===200);
  // Fault injection for a frontend-first rollout against an older API.
  const unavailable=async route=>route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({detail:'Not Found'})});
  await page.route(apiOrigin+'/dietary-options',unavailable);
  await page.goto(origin+'/profile');
  await page.getByRole('alert').filter({hasText:'โหลดโปรไฟล์ไม่สำเร็จ'}).waitFor();
  add('older-api-blocks-profile-settings-save',await page.getByRole('button',{name:'บันทึกและคำนวณ',exact:true}).isDisabled());
  await page.unroute(apiOrigin+'/dietary-options',unavailable);
  await page.goto(origin+'/profile');await page.getByRole('heading',{name:'โปรไฟล์ของฉัน',exact:true}).waitFor();
  const details=page.locator('details').filter({has:page.getByText('ข้อจำกัดอาหาร — แก้ไข',{exact:true})});
  add('profile-options-collapsed',(await details.getAttribute('open'))===null);
  await page.getByText('ข้อจำกัดอาหาร — แก้ไข',{exact:true}).click();
  add('legacy-broad-choice-retained',await page.getByRole('checkbox',{name:'แพ้ถั่ว — ยังไม่ระบุชนิด',exact:true}).isChecked());
  add('vegan-retained',await page.getByRole('checkbox',{name:'วีแกน',exact:true}).isChecked());
  for(const label of ['แพ้ถั่วลิสง','แพ้ถั่วเหลือง','แพ้งา'])add('specific-option-'+label,await page.getByRole('checkbox',{name:label,exact:true}).isVisible());
  await page.setViewportSize({width:390,height:844});
  add('expanded-profile-phone-fits',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:artifactDir+'/dietary-profile-phone.png',fullPage:true});
  const savingProfile=page.waitForResponse(r=>r.url().endsWith('/profile/settings')&&r.request().method()==='PUT');
  await page.getByRole('button',{name:'บันทึกและคำนวณ',exact:true}).click();
  add('profile-uses-versioned-capability-route',(await savingProfile).status()===200);
  await page.getByText('บันทึกแล้ว',{exact:true}).waitFor();
  add('saving-unrelated-profile-keeps-legacy',JSON.stringify((await get('/profile')).restrictions)===JSON.stringify(profile.restrictions));
  await page.goto(origin+'/chat');await page.getByPlaceholder('พิมพ์คำถามเรื่องอาหารและโภชนาการ…').waitFor();
  const send=async text=>{
    await page.locator('body').ariaSnapshot();
    await page.getByPlaceholder('พิมพ์คำถามเรื่องอาหารและโภชนาการ…').fill(text);
    const pending=page.waitForResponse(r=>r.url().endsWith('/chat')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'ส่ง',exact:true}).click();const r=await pending;
    await page.getByRole('button',{name:'ส่ง',exact:true}).waitFor();
    add('chat-response-'+checks.length,r.status()===200);
    return r.url().split('/conversations/')[1].split('/')[0];
  };
  const id=await send('ช่วยจัดมื้ออาหารทั้งหมด 3 มื้อให้ตรงกับเป้าหมายของผม');
  await page.getByRole('button',{name:'ระบุข้อจำกัดอาหาร',exact:true}).waitFor();
  add('ambiguous-allergy-asks-no-table',await page.getByText(/ก่อนจัดเมนู ขอทราบว่าคุณแพ้ถั่วชนิดใด/).isVisible()&&await page.getByRole('region',{name:'เมนูอาหารแบบรายมื้อ',exact:true}).count()===0);
  await page.getByRole('button',{name:'ระบุข้อจำกัดอาหาร',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'ข้อจำกัดอาหาร',exact:true});await dialog.waitFor();
  await dialog.getByRole('checkbox',{name:'แพ้ถั่วลิสง',exact:true}).check();
  await dialog.getByRole('checkbox',{name:'แพ้ถั่ว — ยังไม่ระบุชนิด',exact:true}).uncheck();
  add('allergy-removal-needs-explicit-confirmation',!(await dialog.locator('form').evaluate(form=>form.checkValidity())));
  const confirm=dialog.getByRole('checkbox',{name:'ฉันตรวจสอบแล้วว่าข้อแพ้ที่เลือกไว้ครบถ้วน และยืนยันการเปลี่ยนรายการเดิม',exact:true});
  await confirm.check();
  for(const width of [390,320]){
    await page.setViewportSize({width,height:844});
    add('settings-dialog-fits-'+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)&&await dialog.evaluate(d=>d.scrollWidth<=d.clientWidth));
  }
  await page.screenshot({path:artifactDir+'/dietary-confirmation-phone.png'});
  const beforeProfile=await get('/profile'),beforeRevisions=await get('/profile/history');
  const preferencePath=apiOrigin+'/conversations/'+id+'/dietary-preferences';
  const offline=async route=>route.abort('failed');
  await page.route(preferencePath,offline);
  await dialog.getByRole('button',{name:'ใช้เฉพาะห้องนี้',exact:true}).click();
  await dialog.getByRole('alert').waitFor();
  add('network-failure-keeps-editor-and-no-profile-change',await dialog.isVisible()&&JSON.stringify(await get('/profile'))===JSON.stringify(beforeProfile));
  await page.unroute(preferencePath,offline);
  await dialog.getByRole('button',{name:'ใช้เฉพาะห้องนี้',exact:true}).click();
  await dialog.waitFor({state:'hidden'});
  await page.getByText(/ใช้ข้อจำกัดอาหารเฉพาะห้องนี้แล้วครับ/).waitFor();
  add('room-choice-keeps-profile',JSON.stringify(await get('/profile'))===JSON.stringify(beforeProfile));
  add('room-choice-keeps-profile-history',JSON.stringify(await get('/profile/history'))===JSON.stringify(beforeRevisions));
  add('room-choice-persisted',JSON.stringify((await get('/conversations/'+id+'/dietary-preferences')).restrictions)===JSON.stringify(['วีแกน','แพ้ถั่วลิสง']));
  await send('ช่วยจัดเมนู 3 มื้อตามเป้าหมายและข้อจำกัดที่ยืนยัน');
  const menu=(await get('/conversations/'+id)).messages.findLast(m=>m.role==='assistant');
  add('vegan-peanut-menu-verified',menu.tool_calls?.some(t=>t.name==='suggest_day_menu'&&['success','partial'].includes(t.status)));
  const foodRows=menu.content.split('\n').filter(l=>l.startsWith('| มื้อ'));
  add('menu-no-peanut-or-animal-items',!foodRows.some(row=>/ถั่วลิสง|อกไก่|เนื้อวัว|ปลาแซลมอน|ไข่ไก่|เวย์/.test(row)));
  await page.getByRole('region',{name:'เมนูอาหารแบบรายมื้อ',exact:true}).last().waitFor();
  await page.screenshot({path:artifactDir+'/vegan-peanut-menu-phone.png'});
  await page.reload();await page.getByPlaceholder('พิมพ์คำถามเรื่องอาหารและโภชนาการ…').waitFor();
  // Restoring a room through the actual sidebar must retain its settings.
  await page.setViewportSize({width:1280,height:900});
  const detail=await get('/conversations/'+id);
  await page.getByRole('navigation').getByRole('button',{name:detail.title,exact:true}).click();
  await page.getByText('ช่วยจัดเมนู 3 มื้อตามเป้าหมายและข้อจำกัดที่ยืนยัน',{exact:true}).waitFor();
  await page.getByRole('button',{name:'ข้อจำกัดอาหาร',exact:true}).click();await dialog.waitFor();
  add('reload-settings-still-specific',await dialog.getByRole('checkbox',{name:'แพ้ถั่วลิสง',exact:true}).isChecked()&&!await dialog.getByRole('checkbox',{name:'แพ้ถั่ว — ยังไม่ระบุชนิด',exact:true}).isChecked());
  await dialog.getByRole('button',{name:'ปิด',exact:true}).click();
  await page.getByRole('button',{name:'+ แชตใหม่',exact:true}).click();
  const other=await send('ขอเมนูตามโปรไฟล์ 3 มื้อ');
  await page.getByRole('button',{name:'ระบุข้อจำกัดอาหาร',exact:true}).waitFor();
  add('new-room-uses-saved-legacy',other!==id&&(await get('/conversations/'+other+'/dietary-preferences')).restrictions.includes('แพ้ถั่ว'));
  await page.getByRole('button',{name:'ระบุข้อจำกัดอาหาร',exact:true}).click();await dialog.waitFor();
  await dialog.getByRole('checkbox',{name:'แพ้ถั่วเปลือกแข็ง เช่น อัลมอนด์ / มะม่วงหิมพานต์',exact:true}).check();
  await dialog.getByRole('checkbox',{name:'แพ้ถั่ว — ยังไม่ระบุชนิด',exact:true}).uncheck();await confirm.check();
  await dialog.getByRole('button',{name:'บันทึกในโปรไฟล์ด้วย',exact:true}).click();await dialog.waitFor({state:'hidden'});
  await page.getByText(/ใช้ข้อจำกัดอาหารห้องนี้และโปรไฟล์แล้วครับ/).waitFor();
  add('explicit-profile-save',JSON.stringify((await get('/profile')).restrictions)===JSON.stringify(['วีแกน','แพ้ถั่วเปลือกแข็ง']));
  add('explicit-profile-save-adds-revision',(await get('/profile/history')).length===beforeRevisions.length+1);
  await page.getByRole('button',{name:'+ แชตใหม่',exact:true}).click();
  const third=await send('ช่วยจัดเมนู 3 มื้อให้ตรงเป้าหมาย');
  const thirdContext=await get('/conversations/'+third+'/dietary-preferences');
  add('new-room-uses-saved-specific',JSON.stringify(thirdContext.restrictions)===JSON.stringify(['วีแกน','แพ้ถั่วเปลือกแข็ง']));
  const treeAnswer=(await get('/conversations/'+third)).messages.findLast(m=>m.role==='assistant');
  add('vegan-tree-nut-menu-verified',treeAnswer.tool_calls?.some(t=>t.name==='suggest_day_menu'&&['success','partial'].includes(t.status)));
  add('browser-runtime',errors.length===0,errors);
  add('delete-owned-local-account',(await page.request.delete(api+'/auth/account',{headers,data:{password}})).status()===204);
  add('deleted-local-token-denied',(await page.request.get(api+'/auth/me',{headers})).status()===401);
  const menus=[['vegan-peanut',menu],['vegan-tree',treeAnswer]].map(([id,reply])=>({
    id,answer:reply.content,tools:reply.tool_calls,
    menu_rows:reply.content.split('\n').filter(l=>l.startsWith('|')&&!l.startsWith('| ---')&&!l.includes('มื้ออาหาร |')).map(l=>l.trim().slice(1,-1).split('|').map(c=>c.trim())),
  }));
  return {checks,menus,passed:checks.filter(c=>c.passed).length,failed:checks.filter(c=>!c.passed).length};
  } catch(error) {
    await page.screenshot({path:artifactDir+'/failure.png',fullPage:true}).catch(()=>{});
    throw error;
  }
}
