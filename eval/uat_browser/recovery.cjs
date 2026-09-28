async (page) => {
 const results=[];
 const add=(id,title,expected,actual,pass,method='Browser UI with simulated response')=>results.push({id,title,expected,actual,status:pass?'PASS':'FAIL',method});
 const pattern='**/conversations/*/chat';
 const input=page.getByRole('textbox',{name:'พิมพ์คำถามเรื่องอาหารและโภชนาการ…'});
 const send=page.getByRole('button',{name:'ส่ง',exact:true});
 const error=page.locator('main p.text-red-600');
 try {
   await page.route(pattern,route=>route.fulfill({status:429,contentType:'application/json',body:JSON.stringify({detail:'UAT: กรุณารอสักครู่แล้วลองใหม่'})}));
   await input.fill('ทดสอบข้อผิดพลาดชั่วคราว');
   await send.click();
   await error.waitFor();
   add('UI-34','Rate limit response shows error and releases input','Thai error and input enabled',{error:await error.innerText(),enabled:await input.isEnabled()},(await error.innerText()).includes('กรุณารอ')&&await input.isEnabled());
 } finally {await page.unroute(pattern);}
 try {
   await page.route(pattern,route=>route.abort('failed'));
   await input.fill('ทดสอบเครือข่าย');
   await send.click();
   await error.waitFor();
   await send.waitFor();
   add('UI-35','Network failure does not leave streaming stuck','error and input enabled',{error:await error.innerText(),enabled:await input.isEnabled()},await input.isEnabled()&&!!(await error.innerText()));
 } finally {await page.unroute(pattern);}
 await input.fill('ข้าวสวย 120 กรัมมีพลังงานเท่าไร');
 const response=page.waitForResponse(r=>r.url().endsWith('/chat')&&r.request().method()==='POST');
 await send.click();
 const r=await response;
 await send.waitFor({timeout:120000});
 const body=await page.getByRole('main').innerText();
 add('UI-36','Real chat recovers after stop and network failures','HTTP 200 completed reply and no error',{http:r.status(),errorCount:await error.count(),hasRiceEnergy:body.includes('155')},r.status()===200&&await error.count()===0&&body.includes('155'),'Browser UI / live API');
 try {
   const payload='<img src=x onerror="window.__uatXss=1"> UAT-HTML';
   await page.route(pattern,route=>route.fulfill({status:200,contentType:'text/event-stream',body:'event: delta\ndata: '+JSON.stringify({text:payload})+'\n\nevent: done\ndata: '+JSON.stringify({text:payload,citations:[]})+'\n\n'}));
   await input.fill('ทดสอบการแสดงข้อความ HTML');
   await send.click();
   await page.getByText(/UAT-HTML/).waitFor();
   const injected=await page.evaluate(()=>({executed:!!window.__uatXss,images:document.querySelectorAll('main img').length}));
   add('UI-37','HTML in assistant answer does not execute','no script execution or injected image',injected,!injected.executed&&injected.images===0);
 } finally {await page.unroute(pattern);}
 const deletePattern='**/conversations/*';
 const remove=page.getByRole('button',{name:'ลบห้องแชต ครีเอทีนกินยังไง ต้องโหลดไหม',exact:true});
 try {
   await page.route(deletePattern,route=>route.request().method()==='DELETE'?route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({detail:'UAT simulated deletion failure'})}):route.continue());
   await remove.click();
   await page.getByText(/ลบห้องแชตไม่สำเร็จ/).waitFor();
   add('UI-38','Failed conversation deletion restores sidebar row','row restored with error',await remove.count(),await remove.count()===1);
 } finally {await page.unroute(deletePattern);}
 await remove.click();
 await remove.waitFor({state:'hidden'});
 await page.reload();
 await page.getByRole('button',{name:'+ แชตใหม่'}).waitFor();
 add('UI-39','Delete conversation remains deleted after reload','deleted row absent',await remove.count(),await remove.count()===0,'Browser UI / live API');
 await page.evaluate(()=>localStorage.setItem('nutrition_token','invalid-uat-token'));
 await page.goto('https://nutrilift-azure.vercel.app/profile');
 await page.waitForURL('**/login');
 const tokenPresent=await page.evaluate(()=>!!localStorage.getItem('nutrition_token'));
 add('UI-40','Invalid session returns to login and clears token','/login and no token',{url:page.url(),tokenPresent},!tokenPresent,'Browser UI / live API');
 return results;
}
