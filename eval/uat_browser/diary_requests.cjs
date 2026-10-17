async (page) => {
  const { origin, apiOrigin, artifactDir } = __DIARY_UAT_CONFIG__;
  page.setDefaultTimeout(8000);
  const checks = [];
  const pageErrors = [];
  const unexpected = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  const deferred = () => {
    let release;
    const promise = new Promise(resolve => { release = resolve; });
    return { promise, release };
  };
  let gates = [];
  let dateGate = null;
  let searchGate = null;
  let writeGate = null;
  let dateFailure = null;
  let searchFailure = null;
  let abortSearch = null;
  const macros = { kcal: 100, protein_g: 10, carb_g: 10, fat_g: 2 };
  const empty = { kcal: 0, protein_g: 0, carb_g: 0, fat_g: 0 };
  const food = query => ({
    id: '22222222-2222-4222-8222-222222222222', name_th: 'UAT_SEARCH_' + query,
    serving_desc: '100 g', serving_g: 100, ...macros, fiber_g: 1,
    match: 'exact', estimated: false, warnings: [],
  });
  const entry = date => ({
    id: '11111111-1111-4111-8111-111111111111', food_id: null,
    food_name_th: 'UAT_DAY_' + date, serving_desc: '100 g', serving_g: 100,
    serving_kcal: 100, serving_protein_g: 10, serving_carb_g: 10, serving_fat_g: 2,
    quantity_servings: 1, meal_type: 'breakfast', logged_date: date,
    total_kcal: 100, total_protein_g: 10, total_carb_g: 10, total_fat_g: 2,
    created_at: date + 'T00:00:00Z',
  });
  const json = (route, status, data) => route.fulfill({
    status, contentType: 'application/json', body: JSON.stringify(data),
    headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Headers': 'authorization,content-type', 'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS' },
  });
  const handler = async route => {
    const request = route.request();
    if (request.method() === 'OPTIONS') return json(route, 200, {});
    const url = new URL(request.url());
    const date = url.searchParams.get('date');
    if (request.method() === 'GET' && ['/food-log', '/food-log/summary'].includes(url.pathname)) {
      if (dateGate?.date === date) {
        const gate = dateGate;
        gate.seen.release();
        await gate.wait.promise;
        if (gate.failure) return json(route, 503, { detail: 'UAT_OLD_DAY_FAILURE' });
      }
      if (dateFailure === date) return json(route, 503, { detail: 'UAT_DAY_FAILURE' });
      if (url.pathname === '/food-log') return json(route, 200, [entry(date)]);
      return json(route, 200, { date, entries_count: 1, consumed: macros, target: null, remaining: null,
        by_meal: { breakfast: macros, lunch: empty, dinner: empty, snack: empty } });
    }
    if (url.pathname === '/foods/search' && request.method() === 'GET') {
      const query = url.searchParams.get('q');
      if (searchGate?.query === query) {
        const gate = searchGate;
        gate.seen.release();
        await gate.wait.promise;
        if (gate.failure) return json(route, 503, { detail: 'UAT_OLD_SEARCH_FAILURE' });
      }
      if (abortSearch === query) return route.abort('failed');
      if (searchFailure === query) return json(route, 503, { detail: 'UAT_SEARCH_FAILURE' });
      return json(route, 200, query === 'UAT_EMPTY' ? [] : [food(query)]);
    }
    if (url.pathname === '/food-log' && request.method() === 'POST' && writeGate) {
      const gate = writeGate;
      gate.seen.release();
      await gate.wait.promise;
      if (gate.failure) return json(route, 503, { detail: 'UAT_OLD_WRITE_FAILURE' });
      return json(route, 201, entry(request.postDataJSON().logged_date));
    }
    unexpected.push({ path: url.pathname, method: request.method() });
    return json(route, 401, { detail: 'Unexpected request in isolated browser fixture' });
  };
  const releaseAll = () => { for (const gate of gates) gate.wait.release(); gates = []; };
  const gate = properties => {
    const value = { ...properties, seen: deferred(), wait: deferred() };
    gates.push(value); return value;
  };
  const result = (id, passed, actual) => checks.push({ id, passed, actual });
  const visible = locator => locator.isVisible().catch(() => false);
  const staleVisible = async text => {
    const locator = page.getByText(text, { exact: true });
    await locator.waitFor({ state: 'visible', timeout: 700 }).catch(() => {});
    return visible(locator);
  };
  const reset = async () => {
    releaseAll(); dateGate = searchGate = writeGate = null;
    dateFailure = searchFailure = abortSearch = null;
    await page.goto(origin + '/log');
    await page.getByRole('heading', { name: 'บันทึกอาหารประจำวัน', exact: true }).waitFor();
    await page.getByText('UAT_DAY_', { exact: false }).waitFor();
    await page.locator('body').ariaSnapshot();
  };
  const run = async (id, work) => {
    try { await reset(); await work(); }
    catch (error) { result(id, false, { error: error.message.slice(0, 1600) }); }
    finally { releaseAll(); }
  };
  const choose = async date => page.locator('input[type=date]').fill(date);
  const openSearch = async () => {
    await page.locator('body').ariaSnapshot();
    await page.getByRole('button', { name: '+ เพิ่มเมนู', exact: true }).first().click();
    await page.locator('body').ariaSnapshot();
    return page.getByPlaceholder('ค้นหาเมนู เช่น ข้าวมันไก่');
  };
  const waitForGate = value => Promise.race([
    value.seen.promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error('Fixture request did not start')), 7000)),
  ]);
  await page.route(apiOrigin + '/**', handler);
  try {
    await page.goto(origin + '/login');
    await page.evaluate(() => localStorage.setItem('nutrition_token', 'browser-only-diary-uat-placeholder'));
    await reset();
    const today = await page.locator('input[type=date]').inputValue();
    const shift = days => {
      const d = new Date(today + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + days);
      return d.toISOString().slice(0, 10);
    };
    const a = shift(-3), b = shift(-2), c = shift(-1);
    await run('date-late-success', async () => {
      await choose(a); await page.getByText('UAT_DAY_' + a, { exact: true }).waitFor();
      dateGate = gate({ date: b });
      await choose(b); await waitForGate(dateGate);
      result('date-loading-clears-previous-data', !(await visible(page.getByText('UAT_DAY_' + a, { exact: true }))), { selectedDate: b });
      result('date-loading-disables-food-actions', await page.getByRole('button', { name: '+ เพิ่มเมนู', exact: true }).first().isDisabled(), {});
      await choose(c); await page.getByText('UAT_DAY_' + c, { exact: true }).waitFor();
      dateGate.wait.release();
      const stale = await staleVisible('UAT_DAY_' + b);
      result('date-late-success', !stale && await visible(page.getByText('UAT_DAY_' + c, { exact: true })), { selectedDate: await page.locator('input[type=date]').inputValue(), stale });
      await page.screenshot({ path: artifactDir + '/date-late-success.png', fullPage: true });
    });
    await run('date-late-error', async () => {
      dateGate = gate({ date: b, failure: true });
      await choose(b); await waitForGate(dateGate);
      await choose(c); await page.getByText('UAT_DAY_' + c, { exact: true }).waitFor();
      dateGate.wait.release();
      const stale = await staleVisible('UAT_OLD_DAY_FAILURE');
      result('date-late-error', !stale && !(await visible(page.getByText('UAT_OLD_DAY_FAILURE', { exact: false }))), { stale });
    });
    await run('date-error-retry', async () => {
      dateFailure = b; await choose(b);
      await page.getByRole('alert').filter({ hasText: 'UAT_DAY_FAILURE' }).waitFor();
      dateFailure = null;
      await page.getByRole('button', { name: 'ลองโหลดอีกครั้ง', exact: true }).click();
      await page.getByText('UAT_DAY_' + b, { exact: true }).waitFor();
      result('date-error-retry', !(await visible(page.getByText('UAT_DAY_FAILURE', { exact: false }))), { recovered: true });
    });
    for (const failure of [false, true]) await run('old-day-write-' + (failure ? 'error' : 'success'), async () => {
      await choose(a); await page.getByText('UAT_DAY_' + a, { exact: true }).waitFor();
      const search = await openSearch(); await search.fill('write-food');
      await page.getByRole('button', { name: /UAT_SEARCH_write-food/ }).click();
      writeGate = gate({ failure });
      await page.getByRole('button', { name: 'เพิ่ม', exact: true }).click();
      await waitForGate(writeGate);
      await choose(c); await page.getByText('UAT_DAY_' + c, { exact: true }).waitFor();
      result('date-change-closes-picker-' + failure, !(await visible(search)), {});
      writeGate.wait.release();
      const staleError = await staleVisible('เพิ่มรายการไม่สำเร็จ: UAT_OLD_WRITE_FAILURE');
      result('old-day-write-' + (failure ? 'error' : 'success'), !staleError && await visible(page.getByText('UAT_DAY_' + c, { exact: true })), { staleError, selectedDate: c });
    });
    for (const failure of [false, true]) await run('search-late-' + (failure ? 'error' : 'success'), async () => {
      const search = await openSearch(); searchGate = gate({ query: 'ไก่', failure });
      await search.fill('ไก่'); await waitForGate(searchGate);
      await search.fill('ปลา'); await page.getByText('UAT_SEARCH_ปลา', { exact: true }).waitFor();
      searchGate.wait.release();
      const stale = await staleVisible('UAT_SEARCH_ไก่');
      const error = await visible(page.getByText('ค้นหาไม่สำเร็จ: UAT_OLD_SEARCH_FAILURE', { exact: true }));
      result('search-late-' + (failure ? 'error' : 'success'), !stale && !error && await visible(page.getByText('UAT_SEARCH_ปลา', { exact: true })), { query: await search.inputValue(), stale, error });
    });
    await run('search-cleared-before-response', async () => {
      const search = await openSearch(); searchGate = gate({ query: 'ข้าว' });
      await search.fill('ข้าว'); await waitForGate(searchGate); await search.fill('');
      searchGate.wait.release(); const stale = await staleVisible('UAT_SEARCH_ข้าว');
      result('search-cleared-before-response', !stale && await search.inputValue() === '', { stale });
    });
    await run('search-picker-remounted', async () => {
      let search = await openSearch(); searchGate = gate({ query: 'ไก่' });
      await search.fill('ไก่'); await waitForGate(searchGate);
      await page.getByRole('button', { name: 'ปิด', exact: true }).click();
      search = await openSearch(); await search.fill('ปลา');
      await page.getByText('UAT_SEARCH_ปลา', { exact: true }).waitFor();
      searchGate.wait.release(); const stale = await staleVisible('UAT_SEARCH_ไก่');
      result('search-picker-remounted', !stale && await visible(page.getByText('UAT_SEARCH_ปลา', { exact: true })), { stale });
    });
    for (const network of [false, true]) await run(network ? 'search-network-retry' : 'search-503-retry', async () => {
      const search = await openSearch();
      if (network) abortSearch = 'ปลา'; else searchFailure = 'ปลา';
      await search.fill('ปลา');
      await page.getByRole('alert').filter({ hasText: 'ค้นหาไม่สำเร็จ' }).waitFor();
      const emptyVisible = await visible(page.getByText('ไม่พบเมนูนี้ในฐานข้อมูลอาหาร', { exact: false }));
      result(network ? 'search-network-shows-error' : 'search-503-shows-error', !emptyVisible, { emptyVisible });
      if (!network) await page.screenshot({ path: artifactDir + '/search-error.png', fullPage: true });
      abortSearch = searchFailure = null;
      await page.getByRole('button', { name: 'ลองค้นหาอีกครั้ง', exact: true }).click();
      await page.getByText('UAT_SEARCH_ปลา', { exact: true }).waitFor();
      result(network ? 'search-network-retry' : 'search-503-retry', !(await visible(page.getByRole('alert').filter({ hasText: 'ค้นหาไม่สำเร็จ' }))), { recovered: true });
    });
    await run('search-real-empty-response', async () => {
      const search = await openSearch(); await search.fill('UAT_EMPTY');
      await page.getByText('ไม่พบเมนูนี้ในฐานข้อมูลอาหาร', { exact: false }).waitFor();
      result('search-real-empty-response', !(await visible(page.getByRole('alert').filter({ hasText: 'ค้นหาไม่สำเร็จ' }))), { httpStatus: 200, results: 0 });
    });
    await run('diary-layout', async () => {
      for (const width of [390, 768, 1280]) {
        await page.setViewportSize({ width, height: 900 });
        const size = await page.evaluate(() => ({ viewport: innerWidth, width: document.documentElement.scrollWidth }));
        result('diary-layout-' + width, size.width <= size.viewport, size);
      }
      await page.screenshot({ path: artifactDir + '/diary-layout.png', fullPage: true });
    });
    result('no-javascript-exceptions', pageErrors.length === 0, { pageErrors });
    result('all-api-requests-isolated', unexpected.length === 0, { unexpected });
  } finally {
    releaseAll();
    await page.evaluate(() => localStorage.removeItem('nutrition_token')).catch(() => {});
    await page.unroute(apiOrigin + '/**', handler);
  }
  return { origin, mode: 'Browser-only fixture; no real account, database writes or email', checks,
    passed: checks.filter(check => check.passed).length, failed: checks.filter(check => !check.passed).length };
}
