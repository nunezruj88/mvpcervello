// Run with Node; checks visibility and request behavior without a browser.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'static/index.html'),'utf8');
assert.ok(!html.match(/<article id="standings-panel"[^>]*\bhidden\b/));
const script=fs.readFileSync(path.join(root,'static/app.js'),'utf8');
const block=script.slice(script.indexOf('let standingsVersion='),script.indexOf('async function refresh(){'));
const elements=new Map(),calls=[];
const $=id=>{if(!elements.has(id))elements.set(id,{hidden:false,disabled:true,textContent:'',replaceChildren(){},addEventListener(event,fn){this[event]=fn;}});return elements.get(id);};
const context=vm.createContext({$,URLSearchParams,console,api:async(url,options)=>{calls.push([url,options?.method||'GET']);return {standings:null};}});
vm.runInContext("let selected='', category='Preinfantil';"+block,context);
async function run(code){return vm.runInContext(code,context);}
(async()=>{
 await run('loadStandings()');
 assert.equal($('standings-panel').hidden,false);
 assert.equal($('standings-refresh').disabled,true);
 assert.equal(calls.length,0);
 for(const name of ['Primera fase - Nivel C - 1','Primera Fase - Nivell C - 10','Primera fase - Nivel C - 01']){
  await run('selected='+JSON.stringify('competition:'+JSON.stringify(['2026-10-01',name]))+';loadStandings()');
  assert.equal($('standings-panel').hidden,false);
  assert.equal($('standings-refresh').disabled,false);
 }
 assert.ok(calls.every(([,method])=>method==='GET'));
 await $('standings-refresh').click();
 assert.equal(calls.filter(([,method])=>method==='POST').length,1);
 await run("selected='match-id';loadStandings()");
 assert.equal($('standings-panel').hidden,false);
 assert.equal($('standings-refresh').disabled,true);
 assert.equal(calls.filter(([,method])=>method==='POST').length,1);
 console.log('OK: refresh button stays visible; label variants enable it; only a click sends POST');
})().catch(error=>{console.error(error);process.exitCode=1;});
