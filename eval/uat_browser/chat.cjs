async (page) => {
 const results=[];
 const add=(id,title,expected,actual,pass)=>results.push({id,title,expected,actual,status:pass?'PASS':'FAIL',method:'Browser UI'});
 const input=page.getByRole('textbox',{name:'พิมพ์คำถามเรื่องอาหารและโภชนาการ…'});
 add('UI-24','Empty chat cannot send','disabled',await page.getByRole('button',{name:'ส่ง',exact:true}).isDisabled(),await page.getByRole('button',{name:'ส่ง',exact:true}).isDisabled());
 await input.fill('   ');
 add('UI-25','Whitespace-only chat cannot send','disabled',await page.getByRole('button',{name:'ส่ง',exact:true}).isDisabled(),await page.getByRole('button',{name:'ส่ง',exact:true}).isDisabled());
 add('UI-26','Composer has message length limit','4000',await input.getAttribute('maxlength'),await input.getAttribute('maxlength')==='4000');
 await input.fill('');
 await page.getByRole('button',{name:'ผมควรกินโปรตีนและพลังงานวันละเท่าไร',exact:true}).click();
 await page.getByRole('main').getByText(/1.6–2.2/).first().waitFor();
 add('UI-27','History opens saved answer','saved protein answer',true,true);
 await page.getByRole('button',{name:'+ แชตใหม่',exact:true}).click();
 await page.getByRole('heading',{name:'วันนี้อยากรู้เรื่องอะไร เกี่ยวกับโภชนาการ'}).waitFor();
 add('UI-28','New chat clears active conversation','starter suggestions',true,true);
 await page.getByRole('button',{name:'ครีเอทีนกินยังไง ต้องโหลดไหม →'}).click();
 await page.getByRole('button',{name:'ส่ง',exact:true}).waitFor({timeout:120000});
 const answer=await page.getByRole('main').innerText();
 add('UI-29','Suggested question streams cited answer','creatine answer with source markers',{hasSources:/\[S\d/.test(answer),hasAnswer:answer.length>250},/\[S\d/.test(answer)&&answer.length>250);
 await page.screenshot({path:'output/playwright/uat-system/chat-desktop.png',fullPage:true});
 await input.fill('ช่วยอธิบายโปรตีนสำหรับการฝึกเวทอย่างละเอียด');
 await page.getByRole('button',{name:'ส่ง',exact:true}).click();
 await page.getByRole('button',{name:'หยุด',exact:true}).click();
 await page.getByRole('button',{name:'ส่ง',exact:true}).waitFor();
 add('UI-30','Stop streaming releases composer','send button returns and input enabled',{inputEnabled:await input.isEnabled()},await input.isEnabled());
 for(const width of [390,768,1280]) {
   await page.setViewportSize({width,height:900});
   const size=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
   add('UI-CHAT-'+width,'Chat responsive '+width,'no horizontal overflow',size,size.document<=width);
 }
 await page.setViewportSize({width:390,height:844});
 return results;
}
