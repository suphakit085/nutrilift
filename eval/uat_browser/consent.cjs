async (page) => {
  const results=[];
  const add=(id,title,expected,actual,pass)=>results.push({id,title,expected,actual,status:pass?'PASS':'FAIL',method:'Browser UI'});
  add('UI-09','Account without current consent redirects','/consent',page.url(),page.url().endsWith('/consent'));
  const disabled=await page.getByRole('button',{name:'ยินยอมและใช้งานต่อ'}).isDisabled();
  add('UI-10','Consent acceptance requires explicit checkbox','disabled',disabled,disabled);
  await page.getByRole('button',{name:'ไม่ยินยอม และออกจากระบบ'}).click();
  await page.waitForURL('**/login');
  const tokenPresent=await page.evaluate(()=>!!localStorage.getItem('nutrition_token'));
  add('UI-11','Declining consent logs out','/login and no token',{url:page.url(),tokenPresent},!tokenPresent);
  return results;
}
