async (page) => {
 const results=[];
 const add=(id,title,expected,actual,pass)=>results.push({id,title,expected,actual,status:pass?'PASS':'FAIL',method:'Browser UI'});
 await page.getByRole('button',{name:'+ เพิ่มเมนู',exact:true}).first().click();
 await page.getByRole('textbox',{name:'ค้นหาเมนู เช่น ข้าวมันไก่'}).fill('ข้าวสวย');
 await page.getByRole('button',{name:'ข้าวสวย 1 หน่วยบริโภค (120 ก.) · 155 kcal'}).click();
 await page.getByRole('button',{name:'เพิ่ม',exact:true}).click();
 await page.getByRole('button',{name:'แก้ไข',exact:true}).click();
 await page.getByRole('spinbutton',{name:'จำนวนหน่วยบริโภค'}).fill('2');
 await page.getByRole('button',{name:'บันทึก',exact:true}).click();
 await page.getByText('310 kcal',{exact:true}).first().waitFor();
 add('UI-18','Edit serving quantity updates diary','310 kcal',await page.getByText('310 kcal',{exact:true}).first().innerText(),true);
 await page.reload();
 await page.getByText('310 kcal',{exact:true}).first().waitFor();
 add('UI-19','Diary survives reload','310 kcal after reload',await page.getByText('310 kcal',{exact:true}).first().innerText(),true);
 await page.getByRole('button',{name:'วันก่อนหน้า'}).click();
 await page.getByRole('button',{name:'แก้ไข',exact:true}).waitFor({state:'hidden'});
 add('UI-20','Previous date shows different diary','no rice row',await page.getByText('ข้าวสวย',{exact:true}).count(),await page.getByText('ข้าวสวย',{exact:true}).count()===0);
 await page.getByRole('button',{name:'วันถัดไป'}).click();
 await page.getByText('310 kcal',{exact:true}).first().waitFor();
 add('UI-21','Return to today restores diary','rice row and next day disabled',{rice:await page.getByText('ข้าวสวย',{exact:true}).count(),nextDisabled:await page.getByRole('button',{name:'วันถัดไป'}).isDisabled()},await page.getByRole('button',{name:'วันถัดไป'}).isDisabled());
 for(const width of [390,768,1280]) {
   await page.setViewportSize({width,height:900});
   const size=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
   add('UI-DIARY-'+width,'Diary responsive '+width,'no horizontal overflow',size,size.document<=width);
 }
 await page.screenshot({path:'output/playwright/uat-system/diary.png',fullPage:true});
 page.once('dialog',dialog=>dialog.dismiss());
 await page.getByRole('button',{name:'ลบ',exact:true}).click();
 add('UI-22','Cancel diary deletion retains item','rice row still present',await page.getByText('ข้าวสวย',{exact:true}).count(),await page.getByText('ข้าวสวย',{exact:true}).count()===1);
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'ลบ',exact:true}).click();
 await page.getByText('ข้าวสวย',{exact:true}).waitFor({state:'hidden'});
 add('UI-23','Confirm diary deletion removes item','no rice row',await page.getByText('ข้าวสวย',{exact:true}).count(),await page.getByText('ข้าวสวย',{exact:true}).count()===0);
 await page.evaluate(rows=>sessionStorage.setItem('uat-diary-results',JSON.stringify(rows)),results);
 return results;
}
