// Run: node tests/test_frontend.cjs [python executable]. Requires Playwright Chromium.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'mvp-ui-'));
const server = spawn(process.argv[2] || 'python', ['app.py'], {
  cwd: root, env: {...process.env, MVP_DB: path.join(temp, 'test.sqlite3'), MVP_PORT: '18092'},
  stdio: ['ignore', 'pipe', 'pipe']
});
let browser;
const base = 'http://127.0.0.1:18092';
function fixture(category, points) {
  return Buffer.from('Fecha_partido;Local;Visitante;Periodo;Tiempo_restante;Equipo;Dorsal;Jugador;Accion_original;Puntos_accion;Categoria_equipo\n' +
    [['M.N.L.', points], ['E.L.N.', 1]].map(([name, score])=>
      `2026-10-03;CB BEGUES;MVP CERVELLÓ;P1;05:00;MVP CERVELLÓ;12;${name};Cistella de ${score};${score};${category}\n`).join(''));
}
(async()=>{
  for(let i=0;i<100;i++) {
    try {if((await fetch(base+'/health')).ok) break;} catch {}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  for(const [category,points] of [['Infantil',3],['Mini masculí',2]]) {
    const response=await fetch(base+'/api/import',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({filename:'fixture.csv',data:fixture(category,points).toString('base64')})});
    assert.equal(response.status,201);
  }
  browser=await chromium.launch({headless:true,...(process.env.MVP_BROWSER_CHANNEL?{channel:process.env.MVP_BROWSER_CHANNEL}:{})});
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);
  await page.waitForFunction(()=>document.querySelector('#category-select').options.length===2);
  assert.deepEqual(await page.locator('#category-select option').allTextContents(),['Infantil','Mini masculí']);
  assert.deepEqual(await page.locator('#player-select option').allTextContents(),['M.N.L.','E.L.N.']);
  await page.selectOption('#category-select','Mini masculí');
  await page.waitForFunction(()=>document.querySelector('#player-kpis strong').textContent==='2');
  assert.ok((await page.locator('#export-team').getAttribute('href')).includes('category=Mini+mascul'));
  await page.selectOption('#player-select','ELN');
  await page.waitForFunction(()=>document.querySelector('#focus-name').textContent==='E.L.N.');
  assert.equal(await page.locator('#player-kpis strong').first().textContent(),'1');
  await page.locator('nav [data-view="upload"]').click();
  await page.setInputFiles('#file',{name:'cadet.csv',mimeType:'text/csv',buffer:fixture('Cadet',2)});
  await page.click('#preview-button');
  await page.locator('#preview').waitFor({state:'visible'});
  assert.ok((await page.locator('#preview-table').textContent()).includes('Cadet'));
  await page.click('#save');
  await page.waitForFunction(()=>document.querySelector('#category-select').value==='Cadet');
  assert.equal(await page.locator('#team-match').inputValue(),
    await page.locator('#team-match option').nth(1).getAttribute('value'));
  assert.equal(await page.locator('#player-select').inputValue(),'ELN');
  assert.deepEqual(errors,[]);
  console.log('OK: selectors, category/player filtering, export and import refresh');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  server.kill();
  await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));
  fs.rmSync(temp,{recursive:true,force:true});
});
