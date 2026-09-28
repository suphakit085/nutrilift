async (page) => {
 const input=page.getByRole('textbox',{name:'พิมพ์คำถามเรื่องอาหารและโภชนาการ…'});
 const send=page.getByRole('button',{name:'ส่ง',exact:true});
 const error=page.locator('main p.text-red-600');
 const pattern='**/conversations/*/chat';
 await page.getByRole('button',{name:'ครีเอทีนกินยังไง ต้องโหลดไหม →'}).click();
 await send.waitFor({timeout:150000});
 const initialError=await error.count()?await error.innerText():null;
 await input.fill('ช่วยอธิบายโปรตีนสำหรับการฝึกเวทอย่างละเอียด');
 await send.click();
 await page.getByRole('button',{name:'หยุด',exact:true}).click();
 await send.waitFor();
 try {
   await page.route(pattern,route=>route.fulfill({status:429,contentType:'application/json',body:JSON.stringify({detail:'UAT: กรุณารอสักครู่แล้วลองใหม่'})}));
   await input.fill('ทดสอบข้อผิดพลาดชั่วคราว');await send.click();await error.waitFor();await send.waitFor();
 } finally {await page.unroute(pattern);}
 try {
   await page.route(pattern,route=>route.abort('failed'));
   await input.fill('ทดสอบเครือข่าย');await send.click();await error.waitFor();await send.waitFor();
 } finally {await page.unroute(pattern);}
 const start=Date.now();
 await input.fill('ข้าวสวย 120 กรัมมีพลังงานเท่าไร');
 await send.click();await send.waitFor({timeout:150000});
 const actual={initialError,seconds:(Date.now()-start)/1000,error:await error.count()?await error.innerText():null,mainText:await page.getByRole('main').innerText()};
 await page.screenshot({path:'output/playwright/uat-system/recovery-retest.png',fullPage:true});
 return [{id:'UI-36-R1',title:'Repeat stop, 429, network abort, then real food question',expected:'completed real reply with 155 kcal and no error',actual,status:!actual.error&&actual.mainText.includes('155')?'PASS':'FAIL',method:'Browser UI / live API after simulated errors'}];
}
