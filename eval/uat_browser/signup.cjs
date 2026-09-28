async (page) => {
  const results = [];
  const add = (id, title, expected, actual, pass) => results.push({id,title,expected,actual,status:pass?'PASS':'FAIL',method:'Browser UI'});
  const valid = () => page.locator('form').evaluate(f => f.checkValidity());
  await page.getByRole('textbox',{name:'อีเมล',exact:true}).fill('');
  await page.getByRole('textbox',{name:'รหัสผ่าน แสดง',exact:true}).fill('');
  await page.getByRole('textbox',{name:'ยืนยันรหัสผ่าน',exact:true}).fill('');
  await page.getByRole('checkbox',{name:'ฉันมีอายุ 18 ปีขึ้นไป'}).uncheck();
  await page.getByRole('checkbox',{name:'ฉันยินยอมให้เก็บและใช้ข้อมูลตามรายละเอียดด้านล่าง'}).uncheck();
  add('UI-01','Anonymous profile redirects to login','/login',page.url(),page.url().endsWith('/login'));
  add('UI-02','Empty signup form rejected','invalid',await valid(),!(await valid()));
  await page.getByRole('textbox',{name:'อีเมล',exact:true}).fill('invalid-email');
  add('UI-03','Malformed email rejected','typeMismatch',await page.getByRole('textbox',{name:'อีเมล',exact:true}).evaluate(e=>e.validity.typeMismatch),await page.getByRole('textbox',{name:'อีเมล',exact:true}).evaluate(e=>e.validity.typeMismatch));
  await page.getByRole('textbox',{name:'อีเมล',exact:true}).fill('uat-ui-validation@example.com');
  const password = page.getByRole('textbox',{name:'รหัสผ่าน แสดง',exact:true});
  await password.fill('Temporary-validation-only');
  await page.getByRole('textbox',{name:'ยืนยันรหัสผ่าน',exact:true}).fill('different');
  const mismatch = await page.locator('#confirm-error').innerText();
  add('UI-04','Password confirmation mismatch warning','visible mismatch warning',mismatch,mismatch.length>0);
  await page.getByRole('button',{name:'แสดง',exact:true}).click();
  const shown = await page.locator('input[name=password]').getAttribute('type');
  await page.getByRole('button',{name:'ซ่อน',exact:true}).click();
  const hidden = await page.locator('input[name=password]').getAttribute('type');
  add('UI-05','Show and hide password','text then password',{shown,hidden},shown==='text'&&hidden==='password');
  await page.getByRole('textbox',{name:'ยืนยันรหัสผ่าน',exact:true}).fill('Temporary-validation-only');
  await page.getByRole('checkbox',{name:'ฉันมีอายุ 18 ปีขึ้นไป'}).check();
  add('UI-06','Consent remains required after age check','invalid',await valid(),!(await valid()));
  await page.getByRole('checkbox',{name:'ฉันยินยอมให้เก็บและใช้ข้อมูลตามรายละเอียดด้านล่าง'}).check();
  add('UI-07','Complete signup form can submit','valid',await valid(),await valid());
  for (const width of [390,768,1280]) {
    await page.setViewportSize({width,height:900});
    const size = await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
    add('UI-SIGNUP-'+width,'Signup responsive '+width,'no horizontal overflow',size,size.document<=width);
  }
  return results;
}
