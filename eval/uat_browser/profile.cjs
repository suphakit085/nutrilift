async (page) => {
  const results=[];
  const add=(id,title,expected,actual,pass)=>results.push({id,title,expected,actual,status:pass?'PASS':'FAIL',method:'Browser UI'});
  const height=page.getByRole('spinbutton',{name:'ส่วนสูง (ซม.)',exact:true});
  await height.fill('0');
  const heightInvalid=await height.evaluate(e=>!e.checkValidity());
  add('UI-13','Profile rejects zero height','invalid',heightInvalid,heightInvalid);
  await height.fill('165');
  await page.getByRole('combobox',{name:'เพศ',exact:true}).selectOption('female');
  await page.getByRole('spinbutton',{name:/ปีเกิด/}).fill('2543');
  await page.getByRole('combobox',{name:'เดือนเกิด',exact:true}).selectOption('1');
  await page.getByRole('spinbutton',{name:'น้ำหนัก (กก.)',exact:true}).fill('60');
  await page.getByRole('spinbutton',{name:/เปอร์เซ็นต์ไขมัน/}).fill('22');
  await page.getByRole('combobox',{name:'เป้าหมาย',exact:true}).selectOption('bulk');
  await page.getByRole('button',{name:'วีแกน',exact:true}).click();
  await page.getByRole('button',{name:'แพ้ถั่ว',exact:true}).click();
  await page.getByRole('button',{name:'บันทึกและคำนวณ'}).click();
  await page.getByText('บันทึกแล้ว',{exact:true}).waitFor();
  add('UI-14','Save female profile with body fat and restrictions','saved confirmation',await page.getByText('บันทึกแล้ว',{exact:true}).innerText(),true);
  await page.reload();
  await page.getByRole('button',{name:'วีแกน',exact:true,pressed:true}).waitFor();
  const values={sex:await page.getByRole('combobox',{name:'เพศ',exact:true}).inputValue(),year:await page.getByRole('spinbutton',{name:/ปีเกิด/}).inputValue(),weight:await page.getByRole('spinbutton',{name:'น้ำหนัก (กก.)',exact:true}).inputValue(),bodyfat:await page.getByRole('spinbutton',{name:/เปอร์เซ็นต์ไขมัน/}).inputValue(),nuts:await page.getByRole('button',{name:'แพ้ถั่ว',exact:true}).getAttribute('aria-pressed')};
  add('UI-15','Reload retains profile and multiple restrictions','female / 2000 / 60 / 22 / selected',values,values.sex==='female'&&values.year==='2000'&&values.weight==='60'&&values.bodyfat==='22'&&values.nuts==='true');
  for(const width of [390,768,1280]) {
    await page.setViewportSize({width,height:900});
    const size=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
    add('UI-PROFILE-'+width,'Profile responsive '+width,'no horizontal overflow',size,size.document<=width);
  }
  return results;
}
