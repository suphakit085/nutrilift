async(page)=>{
  const config=__MEAL_UAT_CONFIG__;
  const {origin,apiOrigin,artifactDir}=config;
  page.setDefaultTimeout(15000);
  const checks=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const add=(id,passed,actual={})=>{checks.push({id,passed,actual});};
  const fixtures=[...config.fixtures,
    {id:'research-table',answer:'| งานวิจัย | กลุ่มตัวอย่าง | ผล |\n| --- | --- | --- |\n| ตัวอย่าง | ผู้ใหญ่ | ยังสรุปไม่ได้ |'},
    {id:'partial-header',answer:'| มื้ออาหาร | รายการอาหารและปริมาณ | พลังงาน (kcal) |'},
    {id:'literal-html',answer:'| มื้ออาหาร | รายการอาหารและปริมาณ | โปรตีน (g) |\n| --- | --- | --- |\n| มื้อเช้า | <img src=x onerror="window.__mealUnsafe=true"> | 0.0 |'},
  ];
  let active=fixtures[0];
  const conversation={id:'meal-card-fixture',title:'ตัวอย่างทดสอบการแสดงผล',created_at:'2026-10-18T00:00:00Z',updated_at:'2026-10-18T00:00:00Z'};
  const handler=async route=>{
    const request=route.request(),url=new URL(request.url());
    const json=(status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body),headers:{'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Headers':'authorization,content-type','Access-Control-Allow-Methods':'GET,POST,PATCH,DELETE,OPTIONS'}});
    if(request.method()==='OPTIONS')return json(200,{});
    if(url.pathname==='/conversations'&&request.method()==='GET')return json(200,[conversation]);
    if(url.pathname==='/conversations/'+conversation.id)return json(200,{...conversation,messages:[
      {id:'fixture-user',role:'user',content:'ขอแสดงตัวอย่างเมนู',created_at:conversation.created_at},
      {id:'fixture-answer',role:'assistant',content:active.answer,citations:[],tool_calls:active.outcome?[{name:'suggest_day_menu',status:active.outcome}]:[],created_at:conversation.created_at},
    ]});
    return json(401,{detail:'Unexpected request in presentation fixture'});
  };
  await page.route(apiOrigin+'/**',handler);
  await page.goto(origin+'/login');
  await page.evaluate(()=>localStorage.setItem('nutrition_token','meal-ui-fixture-only'));
  const show=async fixture=>{
    active=fixture;
    await page.setViewportSize({width:1280,height:900});
    await page.goto(origin+'/chat');
    await page.locator('body').ariaSnapshot();
    await page.getByRole('navigation').getByRole('button',{name:conversation.title,exact:true}).click();
    await page.locator('main .flex.justify-start').last().waitFor();
  };
  const rowsOf=answer=>answer.split('\n').filter(line=>/^\|/.test(line)).slice(2)
    .map(line=>line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(cell=>cell.trim().replace(/<br\s*\/?>/gi,'\n')));
  try{
    for(const fixture of config.fixtures){
      await show(fixture);
      const rows=rowsOf(fixture.answer);
      const bubble=page.locator('main .flex.justify-start').last();
      for(const width of [320,390,430,767,768,1280]){
        await page.setViewportSize({width,height:900});
        const cards=bubble.getByRole('region',{name:'เมนูอาหารแบบรายมื้อ',exact:true});
        const table=bubble.getByRole('table');
        const size=await page.evaluate(()=>({viewport:innerWidth,pageWidth:document.documentElement.scrollWidth}));
        let preserved=true;
        if(width<768){
          preserved=await cards.isVisible()&&!(await table.isVisible())&&(await cards.getByRole('article').count())===rows.length;
          for(const row of rows){
            const card=cards.getByRole('article',{name:row[0],exact:true});
            const values=await card.locator('dd').allTextContents();
            preserved=preserved&&values.join('|')===row.slice(2).join('|');
            if(row[1]){
              const foods=await card.getByRole('list',{name:'รายการอาหาร '+row[0],exact:true}).getByRole('listitem').allTextContents();
              preserved=preserved&&foods.join('\n')===row[1];
            }
            const box=await card.evaluate(el=>({client:el.clientWidth,scroll:el.scrollWidth}));
            preserved=preserved&&box.scroll<=box.client;
          }
        }else{
          preserved=await table.isVisible()&&!(await cards.isVisible());
          const actual=await table.locator('tbody tr').evaluateAll(nodes=>nodes.map(n=>Array.from(n.querySelectorAll('td'),td=>td.textContent)));
          preserved=preserved&&JSON.stringify(actual)===JSON.stringify(rows);
        }
        add(fixture.id+'-'+width,preserved&&size.pageWidth<=width,{size,rows:rows.length,allPortionsAndMacrosPreserved:preserved});
        if(width===390||width===1280){
          const first=width===390?cards.getByRole('article').first():table;
          await first.scrollIntoViewIfNeeded();
          await page.screenshot({path:artifactDir+'/'+fixture.id+'-'+width+'.png',fullPage:true});
        }
      }
      const details=bubble.locator('details').filter({has:page.getByText('ดูรายชื่ออาหารที่เกี่ยวข้อง',{exact:true})});
      if(await details.count()){
        const first=details.first();
        const warning=await first.evaluate(el=>({text:el.parentElement.firstChild.textContent.trim(),visible:el.parentElement.getClientRects().length>0}));
        add(fixture.id+'-warning-visible',warning.visible&&Boolean(warning.text)&&!(await first.locator('p').isVisible()),warning);
        await first.locator('summary').focus();
        await page.keyboard.press('Enter');
        add(fixture.id+'-warning-keyboard-open',await first.locator('p').isVisible()&&(await first.getAttribute('open'))!==null);
        await page.keyboard.press('Space');
        add(fixture.id+'-warning-keyboard-close',!(await first.locator('p').isVisible()));
      }
      for(const line of fixture.answer.split('\n').filter(l=>l.startsWith('- ')&&!l.includes('(รายการ:'))){
        const message=line.slice(2);
        add(fixture.id+'-important-'+checks.length,await bubble.getByText(message,{exact:false}).last().isVisible(),{message});
      }
      await page.setViewportSize({width:390,height:900});
      await page.emulateMedia({media:'print'});
      add(fixture.id+'-print-table',await bubble.getByRole('table').isVisible()&&!(await bubble.getByRole('region',{name:'เมนูอาหารแบบรายมื้อ'}).isVisible()));
      await page.emulateMedia({media:'screen'});
    }
    for(const fixture of fixtures.slice(config.fixtures.length)){
      await show(fixture);
      await page.setViewportSize({width:390,height:900});
      const bubble=page.locator('main .flex.justify-start').last();
      if(fixture.id==='research-table')add('research-table-fallback',await bubble.getByRole('table').isVisible()&&await bubble.getByRole('article').count()===0);
      if(fixture.id==='partial-header')add('incomplete-header-visible',await bubble.innerText().then(t=>t.includes('รายการอาหารและปริมาณ'))&&await bubble.getByRole('article').count()===0);
      if(fixture.id==='literal-html')add('literal-html-never-executes',await bubble.locator('img').count()===0&&!(await page.evaluate(()=>window.__mealUnsafe))&&await bubble.innerText().then(t=>t.includes('<img')));
    }
    add('browser-runtime',errors.length===0,{errors});
  }finally{
    await page.evaluate(()=>localStorage.removeItem('nutrition_token'));
    await page.unroute(apiOrigin+'/**',handler);
  }
  return {mode:'Recorded-answer browser fixture; no real accounts, database writes or email',checks,passed:checks.filter(c=>c.passed).length,failed:checks.filter(c=>!c.passed).length};
}
