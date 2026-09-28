async (page) => {
 const results=[];
 const add=(id,title,expected,actual,pass)=>results.push({id,title,expected,actual,status:pass?'PASS':'FAIL',method:'Browser UI'});
 await page.getByText('ดูหัวข้อและงานวิจัยที่อ้างอิง',{exact:true}).click();
 const refs=await page.getByRole('main').innerText();
 add('UI-31','Mobile citation details expand','research titles visible',refs.includes('Kreider'),refs.includes('Kreider'));
 await page.screenshot({path:'output/playwright/uat-system/chat-mobile.png',fullPage:true});
 await page.getByRole('button',{name:'เปิดเมนู'}).click();
 await page.getByRole('dialog',{name:'เมนู'}).waitFor();
 add('UI-32','Mobile menu opens','visible menu dialog',true,true);
 await page.keyboard.press('Escape');
 const closed=await page.getByRole('dialog',{name:'เมนู'}).count()===0;
 add('UI-33','Escape closes mobile menu','dialog removed',closed,closed);
 await page.setViewportSize({width:1280,height:900});
 return results;
}
