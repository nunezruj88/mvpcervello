'use strict';
const $=id=>document.getElementById(id);
let current='team', selected='', category=null, player='MNL', data=null, pending=null;
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
const fmt=n=>new Intl.NumberFormat('es-ES',{maximumFractionDigits:1}).format(n);
const date=s=>s.split('-').reverse().join('/');
function show(view){current=view;document.querySelectorAll('.view').forEach(e=>e.hidden=e.id!==view);document.querySelectorAll('nav button').forEach(e=>e.classList.toggle('active',e.dataset.view===view));location.hash=view;window.scrollTo({top:0});}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.view)));
function notice(message,error=false){$('notice').textContent=message;$('notice').className=error?'error':'';$('notice').hidden=false;if(error)$('notice').scrollIntoView({behavior:'smooth',block:'center'});}
async function api(url,options){const res=await fetch(url,options);let body;try{body=await res.json();}catch{throw Error('No se puede leer la respuesta del servidor.');}if(!res.ok)throw Error(body.error||'No se ha podido completar la petición.');return body;}
function table(container,headers,rows,focusIndex=-1){const t=el('table'), head=el('thead'),hr=el('tr');headers.forEach(v=>hr.append(el('th',v)));head.append(hr);const body=el('tbody');for(const row of rows){const tr=el('tr');if(focusIndex>=0&&row[focusIndex]===12)tr.className='focus-row';for(const v of row){const td=el('td');if(v instanceof Node)td.append(v);else td.textContent=v===null||v===undefined?'—':String(v);tr.append(td);}body.append(tr);}t.append(head,body);container.replaceChildren(rows.length?t:el('p','Todavía no hay acciones registradas.','muted'));}
function kpis(id,items){$(id).replaceChildren(...items.map(([label,value,sub])=>{const e=el('div',undefined,'kpi');e.append(el('span',label,'label'),el('strong',fmt(value)),el('p',sub));return e;}));}
function badge(complete){return el('span',complete?'Completo':'Parcial',complete?'badge done':'badge');}
function coverage(id,s){const e=$(id);e.classList.toggle('complete',s.matches>0&&!s.partial);e.textContent=!s.matches?'Sin partidos importados.':s.partial?`${s.partial} ${s.partial===1?'partido parcial':'partidos parciales'} en la selección. Las cifras corresponden únicamente a las acciones subidas.`:`${s.matches} ${s.matches===1?'partido marcado':'partidos marcados'} como completo${s.matches===1?'':'s'}. Estadísticas según las acciones registradas.`;}
function bar(label,sub,value,max,focus=false){const row=el('div',undefined,'bar-row'+(focus?' focus':'')),name=el('div',label,'bar-label');name.append(el('span',sub));const track=el('div',undefined,'bar-track'),fill=el('div',undefined,'bar-fill');fill.style.width=(max?value/max*100:0)+'%';track.append(fill);row.append(name,track,el('strong',fmt(value)));return row;}
function shotCell(p,n){return `${p['made'+n]}/${p['attempts'+n]}`;}
function selectionQuery(){
 const query=new URLSearchParams();if(category!==null)query.set('category',category);
 if(selected.startsWith('competition:')){const [start,name]=JSON.parse(selected.slice(12));query.set('competition',name);query.set('competition_date',start);}
 else if(selected)query.set('match',selected);
 return query;
}
function matchOptions(matches){
 const groups=new Map();
 for(const m of matches){
  const name=m.competition||'', start=m.competition_date||'';
  const key=JSON.stringify([start,name.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().trim()]);
  if(!groups.has(key))groups.set(key,{name,start,matches:[]});
  groups.get(key).matches.push(m);
 }
 return [...groups.values()].sort((a,b)=>a.start.localeCompare(b.start)||a.name.localeCompare(b.name,'es')).map(g=>{
  const group=el('optgroup');group.label=g.name?`${g.start?date(g.start):'Sin fecha'} - ${g.name}`:'Sin competición';
  group.append(new Option(g.name?`Toda la competición · ${group.label}`:'Todos los partidos sin competición','competition:'+JSON.stringify([g.start,g.name])));
  group.append(...g.matches.map(m=>new Option(`${date(m.date)} · ${m.home} – ${m.away}${m.complete?'':' (parcial)'}`,m.id)));
  return group;
 });
}
function renderFocus(){const s=data.summary, f=s.focus;coverage('player-coverage',s);kpis('player-kpis',[
 ['Puntos registrados',f.points,'De las acciones importadas'],['Canastas de 2',f.made2,`${f.missed2} fallos registrados`],['Faltas personales',f.fouls,'Una falta por acción'],['Acciones',f.events,'Del jugador en la selección']]);
 $('shooting').replaceChildren(...[1,2,3].map(n=>{const box=el('div',undefined,'shot'),text=el('div');text.append(el('h3',n===1?'Tiros libres':`Tiros de ${n}`),el('p',`${f['made'+n]} ${f['made'+n]===1?'acierto':'aciertos'} / ${f['attempts'+n]} ${f['attempts'+n]===1?'intento registrado':'intentos registrados'}`));box.append(text,el('strong',f['percent'+n]===null?'—':fmt(f['percent'+n])+' %'));const track=el('div',undefined,'bar-track'),fill=el('div',undefined,'bar-fill');fill.style.width=(f['percent'+n]||0)+'%';track.append(fill);box.append(track);return box;}));
 const max=Math.max(1,...s.trend.map(t=>t.focus_points));$('trend').replaceChildren(...s.trend.map(t=>bar(date(t.date),`${t.opponent} · ${t.complete?'Completo':'Parcial'}`,t.focus_points,max,true)));if(!s.trend.length)$('trend').append(el('p','Importa un partido para ver su evolución.','muted'));
 const term=$('action-search').value.trim().toLowerCase();const rows=s.focus_events.filter(e=>(e.action+' '+e.clock+' '+e.period+' '+e.opponent).toLowerCase().includes(term));
 table($('focus-table'),['Fecha','Rival','Período','Tiempo restante','Acción','Puntos'],rows.map(e=>[date(e.date),e.opponent,e.period,e.clock,e.action,e.points]));
}
function render(){const s=data.summary;
 $('category-select').replaceChildren(...data.categories.map(c=>new Option(c||'Sin categoría',c)));$('category-select').value=category;
 $('player-select').replaceChildren(...data.players.map(p=>new Option(p.name,p.id)));$('player-select').value=player;
 const focus=data.players.find(p=>p.id===player), stats=s.players.find(p=>p.id===player);
 $('focus-heading').textContent='Foco en '+focus.name;$('focus-name').textContent=focus.name;
 $('focus-team').textContent=data.selected_team+' · '+(category||'Sin categoría');
 $('focus-number').textContent=stats?.number??'—';$('focus-actions-title').textContent='Acciones de '+focus.name;
 for(const id of ['team-match','player-match']){const select=$(id);select.replaceChildren(new Option('Todos los partidos',''),...matchOptions(data.matches));select.value=selected;}
 coverage('team-coverage',s);$('team-empty').hidden=!!s.matches;$('team-content').hidden=!s.matches;
 const items=[['Faltas personales',s.team.fouls,'Registradas para el equipo']];
 if(!data.scoreboard)items.unshift(['Partidos importados',s.matches,`${s.partial} con grabación parcial`]);
 kpis('team-kpis',items);
 if(data.scoreboard){const score=data.scoreboard, card=el('div',undefined,'kpi');card.id='match-scoreboard';card.append(el('span',score.complete?'Marcador':'Marcador parcial','label'),el('strong',`${fmt(score.home_points)} – ${fmt(score.away_points)}`),el('p',`${score.home} – ${score.away}`),el('p','Puntos de las acciones importadas'));$('team-kpis').prepend(card);}
 const shots=el('div',undefined,'kpi');shots.id='team-shooting';shots.append(el('span','Tiros registrados','label'));
 for(const [n,label] of [[1,'Tiros libres'],[2,'Tiros de 2'],[3,'Triples']]){const row=el('p',label+': ');row.append(el('b',`${s.team['made'+n]}/${s.team['attempts'+n]}`));shots.append(row);}
 shots.append(el('p','Aciertos / intentos registrados'));$('team-kpis').append(shots);
 const max=Math.max(1,...s.players.map(p=>p.points));$('ranking').replaceChildren(...s.players.map(p=>bar(p.name,`Dorsal ${p.number??'—'}`,p.points,max,p.number===12)));
 const rival=data.scoreboard?(s.trend[0]?.opponent||'Rival'):'Rivales';
 $('period-legend').replaceChildren(el('span','MVP Cervelló','legend-team'),el('span',rival,'legend-opponent'));
 const pmax=Math.max(1,...s.periods.flatMap(p=>[p.team_points,p.opponent_points||0]));
 $('periods').replaceChildren(...s.periods.map(p=>{const group=el('div',undefined,'period-group'),bars=el('div',undefined,'period-bars');
  for(const [points,name,cls] of [[p.team_points,'MVP Cervelló',''],[p.opponent_points||0,rival,'opponent']]){const c=el('div',undefined,'column'),b=el('div',undefined,'col-bar '+cls);b.style.height=(points/pmax*150)+'px';c.title=`${p.period} · ${name}: ${points} puntos registrados`;c.append(el('strong',fmt(points)),b);bars.append(c);}
  group.append(bars,el('span',p.period));return group;
 }));
 table($('players-table'),['Jugador','Dorsal','PTS','TL','T2','T3','Faltas','Acciones'],s.players.map(p=>[p.name,p.number,p.points,shotCell(p,1),shotCell(p,2),shotCell(p,3),p.fouls,p.events]),1);
 $('export-team').href='/api/export?'+selectionQuery();
 table($('matches-table'),['Fecha','Partido','Cobertura','Acciones','Archivo',''],data.matches.map(m=>{const b=el('button','Ver estadísticas','primary');b.addEventListener('click',async()=>{selected=m.id;show('team');await refresh();});return [date(m.date),m.home+' – '+m.away,badge(m.complete),m.event_count,m.filename,b];}));
 renderFocus();
}
async function refresh(){try{const query=selectionQuery();query.set('player',player);data=await api('/api/data?'+query);category=data.selected_category;player=data.selected_player;render();}catch(e){notice(e.message,true);}}
$('category-select').addEventListener('change',async e=>{category=e.target.value;selected='';await refresh();});
$('player-select').addEventListener('change',async e=>{player=e.target.value;await refresh();});
for(const id of ['team-match','player-match'])$(id).addEventListener('change',async e=>{selected=e.target.value;await refresh();});
$('action-search').addEventListener('input',()=>{if(data)renderFocus();});
function resetPreview(){$('upload-notice').hidden=true;pending=null;$('preview').hidden=true;$('replace').checked=false;}
$('file').addEventListener('change',()=>{$('file-label').textContent=$('file').files[0]?.name||'Selecciona o arrastra tu archivo';resetPreview();});
$('complete').addEventListener('change',resetPreview);
const dz=$('dropzone');for(const event of ['dragenter','dragover'])dz.addEventListener(event,e=>{e.preventDefault();dz.classList.add('drag');});for(const event of ['dragleave','drop'])dz.addEventListener(event,e=>{e.preventDefault();dz.classList.remove('drag');});
dz.addEventListener('drop',e=>{if(e.dataTransfer.files.length){$('file').files=e.dataTransfer.files;$('file').dispatchEvent(new Event('change'));}});
function encoded(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('No se puede leer el archivo.'));reader.readAsDataURL(file);});}
$('upload-form').addEventListener('submit',async e=>{e.preventDefault();const file=$('file').files[0];if(!file)return;if(file.size>10*1024*1024){notice('El archivo supera 10 MB.',true);return;}resetPreview();$('preview-button').disabled=true;try{
 const payload={filename:file.name,data:await encoded(file),complete:$('complete').checked};const result=await api('/api/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,preview:true})});
 pending={payload,result};$('preview-title').textContent=result.match.home+' – '+result.match.away;
 $('preview-info').replaceChildren(el('p',`${date(result.match.date)} · ${result.match.event_count} registros · ${result.match.complete?'Completo':'Parcial'}`),...result.match.warnings.map(w=>el('p',w,'footnote')));
 if(result.match.competition)$('preview-info').prepend(el('p',`${date(result.match.competition_date)} - ${result.match.competition}`));
 if(result.exists)$('preview-info').append(el('p','Este partido ya está guardado. Reemplazarlo sustituye todas sus acciones.'));
 table($('preview-table'),['Período','Tiempo','Equipo','Categoría','Dorsal','Jugador','Acción','PTS'],result.events.map(e=>[e.period,e.clock,e.team,e.category||'Sin categoría',e.number,e.player,e.action,e.points]));
 if(result.match.event_count>100)$('preview-info').append(el('p','La vista previa muestra los primeros 100 registros. Se guardarán todos.','footnote'));
 $('replace-label').hidden=!result.exists;$('preview').hidden=false;$('notice').hidden=true;$('preview').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(error){notice(error.message,true);}finally{$('preview-button').disabled=false;}});
$('save').addEventListener('click',async()=>{if(!pending)return;if(pending.result.exists&&!$('replace').checked){notice('Marca reemplazar para actualizar este partido.',true);return;}$('save').disabled=true;try{
 const result=await api('/api/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...pending.payload,replace:$('replace').checked})});selected=result.match.id;category=result.match.category;resetPreview();$('upload-form').reset();$('file-label').textContent='Selecciona o arrastra tu archivo';await refresh();show('upload');$('upload-notice').textContent='Partido guardado. Las estadísticas ya están actualizadas.';$('upload-notice').hidden=false;window.scrollTo({top:0,behavior:'smooth'});
 }catch(error){notice(error.message,true);}finally{$('save').disabled=false;}});
show(['team','player','upload'].includes(location.hash.slice(1))?location.hash.slice(1):'team');refresh();

