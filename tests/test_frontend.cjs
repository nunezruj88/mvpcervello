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
function fixture(category, points, competition='', start='', matchDate='2026-10-03') {
  return Buffer.from('Fecha_partido;Local;Visitante;Periodo;Tiempo_restante;Equipo;Dorsal;Jugador;Accion_original;Puntos_accion;Categoria_equipo;Competicion;Fecha_competicion\n' +
    [['M.N.L.', points], ['E.L.N.', 1]].map(([name, score])=>
      `${matchDate};CB BEGUES;MVP CERVELLÓ;P1;05:00;MVP CERVELLÓ;12;${name};Cistella de ${score};${score};${category};${competition};${start}\n`).join(''));
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
    await page.locator('#team-match option').nth(2).getAttribute('value'));
  assert.equal(await page.locator('#player-select').inputValue(),'ELN');
  for(const [start,matchDate] of [['01/09/2026','2026-10-04'],['2026-09-01','2026-10-05'],['01/01/2027','2027-01-02']]) {
    const response=await fetch(base+'/api/import',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({filename:'league.csv',data:fixture('Cadet',3,'Liga escolar',start,matchDate).toString('base64')})});
    assert.equal(response.status,201);
  }
  await page.reload();
  await page.selectOption('#category-select','Cadet');
  await page.waitForFunction(()=>document.querySelectorAll('#team-match optgroup').length===3);
  for(const id of ['team-match','player-match']) {
    assert.deepEqual(await page.locator(`#${id} optgroup`).evaluateAll(groups=>groups.map(g=>[g.label,g.children.length])),
      [['Sin competición',2],['01/09/2026 - Liga escolar',3],['01/01/2027 - Liga escolar',2]]);
  }
  const groupedMatch=await page.locator('#team-match optgroup').nth(1).locator('option').nth(1).getAttribute('value');
  await page.locator('nav [data-view="team"]').click();
  await page.selectOption('#team-match',groupedMatch);
  await page.waitForFunction(()=>document.querySelector('#player-match').value===document.querySelector('#team-match').value && document.querySelector('#player-kpis strong').textContent==='3');
  assert.equal(await page.locator('#player-kpis strong').first().textContent(),'3');
  assert.equal(await page.locator('#match-scoreboard strong').textContent(),'0 – 4');
  assert.ok((await page.locator('#match-scoreboard').textContent()).includes('Marcador parcial'));
  assert.ok(!(await page.locator('#team-kpis').textContent()).includes('Partidos importados'));
  const competition=await page.locator('#team-match optgroup').nth(1).locator('option').first().getAttribute('value');
  await page.selectOption('#team-match',competition);
  await page.waitForFunction(()=>document.querySelector('#player-kpis strong').textContent==='6');
  assert.equal(await page.locator('#match-scoreboard').count(),0);
  assert.ok((await page.locator('#team-kpis').textContent()).includes('Partidos importados'));
  assert.ok((await page.locator('#export-team').getAttribute('href')).includes('competition_date=2026-09-01'));
  await page.selectOption('#player-select','ELN');
  await page.waitForFunction(()=>document.querySelector('#focus-name').textContent==='E.L.N.' && document.querySelector('#player-kpis strong').textContent==='2');
  assert.equal(await page.locator('#team-match').inputValue(),competition);
  assert.equal(await page.locator('#player-match').inputValue(),competition);
  await page.selectOption('#team-match','');
  await page.waitForFunction(()=>document.querySelector('#team-kpis strong').textContent==='4');
  assert.deepEqual(errors,[]);
  console.log('OK: selectors, filters, export, import, competition totals and scoreboard');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  server.kill();
  await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));
  fs.rmSync(temp,{recursive:true,force:true});
});
