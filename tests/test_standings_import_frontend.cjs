const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'static/index.html'),'utf8');
assert.ok(html.includes('<span>Importar datos</span>'));
assert.ok(html.includes('id="standings-import-form"'));
const script=fs.readFileSync(path.join(root,'static/app.js'),'utf8');
const block=script.slice(script.indexOf('let standingsPending='),script.indexOf("show(['team','player','upload']"));
const destination={category:'Mini masculí',competition:'Primera fase - Nivel C - 11',competition_date:'2026-10-01'};
const snapshot={title:'C.t. Mini Masculí',group:'Grupo 11',round:3,rows:[{position:1,team:'MVP CERVELLÓ',played:2,won:2,lost:0,not_played:0,points_for:125,points_against:83,points:4}]};
const elements=new Map(),calls=[];
const $=id=>{if(!elements.has(id))elements.set(id,{value:'',files:[],hidden:true,disabled:false,checked:false,events:{},replaceChildren(...children){this.children=children;this.value=children[0]?.value||'';},addEventListener(event,fn){this.events[event]=fn;}});return elements.get(id);};
let exists=true,fail=false,localLoads=0;
const context=vm.createContext({$,console,Option:class{constructor(text,value){this.text=text;this.value=value;}},date:s=>s,encoded:async file=>file.data,table:(e,headers,rows)=>{e.rows=rows;},loadStandings:async()=>{localLoads++;},api:async(url,options)=>{
 calls.push({url,payload:options?JSON.parse(options.body):null});
 if(url==='/api/standings/options')return {options:[destination]};
 assert.equal(url,'/api/standings/import');
 if(fail)throw Error('Error de prueba');
 return {destination,standings:snapshot,exists};
}});
vm.runInContext(block,context);
const run=code=>vm.runInContext(code,context);
const event={preventDefault(){}};
(async()=>{
 await run('loadStandingsImportOptions()');
 assert.equal(calls.length,1);
 $('standings-destination').value=JSON.stringify(destination);
 $('standings-file').files=[{name:'guardada.html',size:200,data:'html-base64'}];
 await $('standings-import-form').events.submit(event);
 assert.equal(calls.at(-1).payload.preview,true);
 assert.equal($('standings-import-preview').hidden,false);
 assert.equal($('standings-replace-label').hidden,false);
 assert.equal($('standings-import-table').rows[0][6],125);
 const before=calls.length;
 await $('standings-import-save').events.click();
 assert.equal(calls.length,before); // Replacement needs an explicit checkbox.
 $('standings-replace').checked=true;
 await $('standings-import-save').events.click();
 assert.equal(calls.at(-1).payload.replace,true);
 assert.equal(calls.at(-1).payload.category,destination.category);
 assert.equal($('standings-import-preview').hidden,true);
 assert.equal(localLoads,1); // Only reads the saved classification.
 $('standings-file').files=[{name:'otra.html',size:200,data:'other'}];
 exists=false;await $('standings-import-form').events.submit(event);
 assert.equal($('standings-replace-label').hidden,true);
 $('standings-destination').events.change();
 assert.equal($('standings-import-preview').hidden,true);
 const count=calls.length;await $('standings-import-save').events.click();
 assert.equal(calls.length,count); // Changing destination invalidates the review.
 fail=true;await $('standings-import-form').events.submit(event);
 assert.equal($('standings-import-status').textContent,'Error de prueba');
 assert.equal($('standings-preview-button').disabled,false);
 assert.equal($('standings-file').disabled,false);
 console.log('OK: manual classification review, explicit replacement, destination reset and error recovery');
})().catch(e=>{console.error(e);process.exitCode=1;});
