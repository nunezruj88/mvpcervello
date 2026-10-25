const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/app.js','utf8');
const nodes=new Map(), requests=[];
let allow=false, prompt='', refreshed=0, tableRows=[];
const match={id:'a'.repeat(24),revision:'b'.repeat(64),date:'2026-10-25',home:'MVP CERVELLÓ',away:'RIVAL',category:'',filename:'original.csv',event_count:2,players:['MNL']};
const node=()=>({children:[],append(...children){this.children.push(...children);},addEventListener(type,callback){this[type]=callback;}});
const ctx={URLSearchParams,selected:match.id,category:'Junior',player:'ELN',date:v=>v,
 $:id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},
 el:(tag,text)=>Object.assign(node(),{tag,text}),badge:()=>'',show:()=>{},resetPreview:()=>{},
 table:(container,headers,rows)=>{tableRows=rows;},window:{confirm:text=>{prompt=text;return allow;}},
 refresh:async()=>{refreshed++;},api:async(url,opts)=>{requests.push({url,opts});return url==='/api/matches'?{matches:[match]}:{deleted:match.id};}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('let deletingMatch='),source.indexOf('async function refresh()')),ctx);
(async()=>{
 await ctx.loadManagedMatches();assert.equal(tableRows[0][2],'Sin categoría');
 assert.equal(requests[0].url,'/api/matches');
 await ctx.deleteManagedMatch(match);assert.equal(requests.length,1);assert.equal(refreshed,0);
 assert.ok(prompt.includes('Sin categoría'));assert.ok(prompt.includes('RIVAL'));assert.ok(prompt.includes('2026-10-25'));
 allow=true;await ctx.deleteManagedMatch(match);
 const deletion=requests.find(r=>r.url==='/api/matches/delete');
 assert.deepEqual(JSON.parse(deletion.opts.body),{id:match.id,revision:match.revision,confirm:true});
 assert.equal(refreshed,1);assert.equal(ctx.selected,'');assert.equal(nodes.get('reload-matches').disabled,false);
 console.log('Lista global, confirmación, cancelación, borrado y actualización: correctos.');
})().catch(e=>{console.error(e);process.exitCode=1;});
