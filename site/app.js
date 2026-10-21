'use strict';
const $ = id => document.getElementById(id);
const COORDS = {Goa:[15.4909,73.8278],Manali:[32.2432,77.1892]};
const REQUIRED = ['booking_id','property_city','booking_date','checkin_date','checkout_date','customer_signup_date','num_rooms','booking_status'];
const STATE = {book:null,clean:[],eligible:[],enriched:[],audit:{version:1,imports:[],historical:[],current:[]},busy:false};
const nf = new Intl.NumberFormat('en-IN');
const rate = (n,d) => d ? (100*n/d).toFixed(2)+'%' : '—';
function message(id,text,error=false){$(id).textContent=text;$(id).classList.toggle('error',error);}
function dateOnly(value){
  if(value instanceof Date && !Number.isNaN(value.getTime())) return value.toISOString().slice(0,10);
  if(typeof value==='number' && window.XLSX){const d=XLSX.SSF.parse_date_code(value);return d?`${d.y}-${String(d.m).padStart(2,'0')}-${String(d.d).padStart(2,'0')}`:null;}
  const s=String(value??'').trim();const match=s.match(/^(\d{4})-(\d{2})-(\d{2})(?:$|[T ])/);if(!match)return null;
  const iso=match[1]+'-'+match[2]+'-'+match[3];const dt=new Date(iso+'T00:00:00Z');return !Number.isNaN(dt.getTime())&&dt.toISOString().slice(0,10)===iso?iso:null;
}
function num(v){return v===null||v===undefined||String(v).trim()===''?null:(Number.isFinite(Number(v))?Number(v):null);}
function cleanRows(rows){
  if(!rows.length)throw new Error('This worksheet has no records.');
  const missing=REQUIRED.filter(c=>!Object.hasOwn(rows[0],c));if(missing.length)throw new Error('Missing columns: '+missing.join(', '));
  const counts={invalid_required:0,invalid_stay:0,before_signup:0,negative_lead:0,zero_rooms:0,duplicate_id:0,unknown_status:0,price_mismatch:0,nights_mismatch:0};
  const seen=new Set();const clean=[];
  for(const row of rows){
    const id=String(row.booking_id??'').trim();const checkin=dateOnly(row.checkin_date),checkout=dateOnly(row.checkout_date),booking=dateOnly(row.booking_date),signup=dateOnly(row.customer_signup_date);const rooms=num(row.num_rooms);const status=String(row.booking_status??'').trim();let excluded=false;
    const flag=(name,condition)=>{if(condition){counts[name]++;excluded=true;}};
    flag('invalid_required',!id||!checkin||!checkout||!booking||!signup||rooms===null);
    flag('invalid_stay',!!(checkin&&checkout&&checkout<=checkin));flag('before_signup',!!(booking&&signup&&booking<signup));flag('negative_lead',!!(booking&&checkin&&booking>checkin));flag('zero_rooms',rooms!==null&&rooms<=0);flag('duplicate_id',!!id&&seen.has(id));flag('unknown_status',!['Completed','Cancelled','No-Show'].includes(status));if(id)seen.add(id);
    const adr=num(row.adr),nights=num(row.nights),discount=num(row.discount_amount),total=num(row.total_amount);
    if([adr,nights,rooms,discount,total].every(v=>v!==null)&&Math.abs(total-(adr*nights*rooms-discount))>.011)counts.price_mismatch++;
    if(checkin&&checkout&&nights!==null&&nights!==(Date.parse(checkout)-Date.parse(checkin))/86400000)counts.nights_mismatch++;
    if(!excluded)clean.push({booking_id:id,property_city:String(row.property_city??'').trim(),checkin_date:checkin,booking_status:status});
  }
  return {clean,raw:rows.length,excluded:rows.length-clean.length,flags:counts};
}
function setBusy(value){STATE.busy=value;$('file').disabled=value;$('sheet').disabled=value||!STATE.book;$('enrich').disabled=value||!STATE.eligible.length;$('export').disabled=value||!STATE.enriched.length;}
function importSheet(){
  try{
    const sheet=STATE.book.Sheets[$('sheet').value];const rows=XLSX.utils.sheet_to_json(sheet,{defval:null});const result=cleanRows(rows);
    STATE.clean=result.clean;STATE.eligible=result.clean.filter(r=>Object.hasOwn(COORDS,r.property_city)&&r.checkin_date.startsWith('2024-'));STATE.enriched=[];
    STATE.audit.imports.push({at:new Date().toISOString(),worksheet:$('sheet').value,raw:result.raw,valid:result.clean.length,excluded:result.excluded,eligible:STATE.eligible.length,flags:result.flags});
    $('raw').textContent=nf.format(result.raw);$('valid').textContent=nf.format(result.clean.length);$('eligible').textContent=nf.format(STATE.eligible.length);$('matched').textContent='—';
    message('import-status',`${nf.format(result.excluded)} rows excluded. Flag counts may overlap. ${nf.format(STATE.eligible.length)} valid Goa/Manali bookings in 2024 are eligible.`);
    message('weather-status','Ready to fetch. No previous weather data is applied to this import.');setBusy(false);render();
  }catch(e){STATE.clean=[];STATE.eligible=[];STATE.enriched=[];for(const id of ['raw','valid','eligible','matched'])$(id).textContent='—';setBusy(false);render();message('import-status',e.message,true);}
}
async function loadFile(event){
  const file=event.target.files[0];if(!file)return;
  if(!window.XLSX){message('import-status','Spreadsheet library did not load. Check your connection and reload the page.',true);return;}
  if(file.size>20*1024*1024){message('import-status','Please choose a file smaller than 20 MB.',true);return;}
  setBusy(true);message('import-status','Reading locally…');
  try{STATE.book=XLSX.read(await file.arrayBuffer(),{type:'array',cellDates:true});$('sheet').replaceChildren(...STATE.book.SheetNames.map(name=>{const o=document.createElement('option');o.value=name;o.textContent=name;return o;}));importSheet();}
  catch(e){message('import-status','Could not read this workbook: '+e.message,true);setBusy(false);}
}
async function requestJSON(url){
  let last;
  for(let attempt=0;attempt<3;attempt++){
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),45000);
    try{const response=await fetch(url,{signal:controller.signal,credentials:'omit',referrerPolicy:'no-referrer'});if(!response.ok)throw new Error('Weather service returned HTTP '+response.status);const data=await response.json();if(data.error)throw new Error(data.reason||'Weather service rejected the request.');return data;}
    catch(e){last=e;if(attempt<2)await new Promise(resolve=>setTimeout(resolve,1000*2**attempt));}finally{clearTimeout(timer);}
  }
  throw last;
}
function weatherMap(data,start,end){
  const daily=data.daily;const map=new Map();
  if(!daily||!Array.isArray(daily.time)||!Array.isArray(daily.precipitation_sum)||!Array.isArray(daily.temperature_2m_max)||daily.time.length!==daily.precipitation_sum.length||daily.time.length!==daily.temperature_2m_max.length)throw new Error('Historical response has invalid arrays.');
  if(data.daily_units?.precipitation_sum!=='mm'||data.daily_units?.temperature_2m_max!=='°C')throw new Error('Unexpected weather units.');
  daily.time.forEach((day,i)=>{if(dateOnly(day)!==day||day<start||day>end||map.has(day))throw new Error('Historical response contains invalid or duplicate dates.');let rain=num(daily.precipitation_sum[i]),max=num(daily.temperature_2m_max[i]);if(rain!==null&&rain<0)rain=null;map.set(day,{precipitation_sum:rain,temperature_2m_max:max});});return map;
}
function joinWeather(rows,maps){return rows.map(row=>{const w=maps[row.property_city]?.get(row.checkin_date);const available=!!w&&w.precipitation_sum!==null&&w.temperature_2m_max!==null;const rain=w?.precipitation_sum??null;const max=w?.temperature_2m_max??null;return {...row,precipitation_sum:rain,temperature_2m_max:max,weather_available:available,heavy_rain:rain===null?null:rain>=20,hot:max===null?null:max>=35,cold:max===null?null:max<=5,any_exposure:available?(rain>=20||max>=35||max<=5):null};});}
async function enrich(){
  if(STATE.busy||!STATE.eligible.length)return;setBusy(true);message('weather-status','Fetching historical weather…');$('weather-status').classList.add('loading');const maps={};const failed=[];
  for(const city of Object.keys(COORDS)){
    const rows=STATE.eligible.filter(r=>r.property_city===city);if(!rows.length)continue;const days=rows.map(r=>r.checkin_date).sort();const start=days[0],end=days.at(-1);const [latitude,longitude]=COORDS[city];
    const url=new URL('https://archive-api.open-meteo.com/v1/archive');url.search=new URLSearchParams({latitude,longitude,start_date:start,end_date:end,daily:'precipitation_sum,temperature_2m_max',timezone:'Asia/Kolkata',temperature_unit:'celsius',precipitation_unit:'mm'});
    const audit={city,start,end,url:url.href,requested_at:new Date().toISOString(),origin:'live'};
    try{const data=await requestJSON(url.href);maps[city]=weatherMap(data,start,end);Object.assign(audit,{status:'ok',days:maps[city].size,received_at:new Date().toISOString(),timezone:data.timezone,units:data.daily_units});}
    catch(e){audit.status='failed';audit.error=e.message;failed.push(city);}STATE.audit.historical.push(audit);
  }
  STATE.enriched=joinWeather(STATE.eligible,maps);const matched=STATE.enriched.filter(r=>r.weather_available).length;$('matched').textContent=nf.format(matched)+' / '+nf.format(STATE.eligible.length);$('weather-status').classList.remove('loading');
  message('weather-status',`${nf.format(matched)} of ${nf.format(STATE.eligible.length)} bookings matched to complete historical weather. ${failed.length?'Unavailable: '+failed.join(', ')+'. You can retry.':'Fetched from the live archive API; not a bundled snapshot.'}`,failed.length>0);setBusy(false);render();
}
function visibleRows(){return (STATE.enriched.length?STATE.enriched:STATE.eligible).filter(r=>($('city').value==='All'||r.property_city===$('city').value)&&($('exposure').value==='all'||($('exposure').value==='exposed'&&r.any_exposure===true)||($('exposure').value==='unexposed'&&r.any_exposure===false)||($('exposure').value==='missing'&&r.weather_available!==true)));}
function render(){
  const rows=visibleRows();$('groups').replaceChildren();
  for(const [label,value] of [['Any threshold met',true],['No thresholds met',false]]){
    const group=rows.filter(r=>r.weather_available&&r.any_exposure===value);const cancelled=group.filter(r=>r.booking_status==='Cancelled').length;const noShow=group.filter(r=>r.booking_status==='No-Show').length;
    const tr=document.createElement('tr');for(const text of [label,nf.format(group.length),`${cancelled} (${rate(cancelled,group.length)})`,`${noShow} (${rate(noShow,group.length)})`,`${cancelled+noShow} (${rate(cancelled+noShow,group.length)})`]){const td=document.createElement('td');td.textContent=text;tr.append(td);}$('groups').append(tr);
  }
  message('view-status',`${nf.format(rows.length)} bookings in view; ${nf.format(rows.filter(r=>r.weather_available!==true).length)} have unavailable or not-yet-fetched weather. Missing weather is excluded from both comparison groups.`);
}
function download(name,text,type){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function csvCell(v){let s=v===null||v===undefined?'':String(v);if(/^[\s]*[=+\-@]/.test(s)||/^[\t\r\n]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}
function exportCSV(){const columns=['booking_id','property_city','checkin_date','booking_status','precipitation_sum','temperature_2m_max','weather_available','heavy_rain','hot','cold','any_exposure'];const text=[columns,...visibleRows().map(r=>columns.map(c=>r[c]))].map(row=>row.map(csvCell).join(',')).join('\r\n');download('weather-enriched-bookings.csv','\ufeff'+text,'text/csv;charset=utf-8');}
async function current(){
  $('current').disabled=true;$('current-data').replaceChildren();
  for(const [city,coords] of Object.entries(COORDS)){
    const article=document.createElement('article');article.className='weather-card loading';const h=document.createElement('h3');h.textContent=city;const p=document.createElement('p');p.textContent='Retrieving current conditions…';article.append(h,p);$('current-data').append(article);
    const url=new URL('https://api.open-meteo.com/v1/forecast');url.search=new URLSearchParams({latitude:coords[0],longitude:coords[1],current:'temperature_2m,precipitation',timezone:'Asia/Kolkata',temperature_unit:'celsius',precipitation_unit:'mm',forecast_days:1});const audit={city,url:url.href,requested_at:new Date().toISOString()};
    try{const data=await requestJSON(url.href);const c=data.current;if(!c||num(c.temperature_2m)===null||num(c.precipitation)===null||!c.time)throw new Error('Incomplete current weather response.');p.textContent=`${c.temperature_2m} ${data.current_units.temperature_2m} · ${c.precipitation} ${data.current_units.precipitation} precipitation`;const meta=document.createElement('p');meta.className='muted';meta.textContent=`Model time: ${c.time} (${data.timezone}); precipitation interval: ${c.interval} seconds. Retrieved ${new Date().toLocaleString()}.`;article.append(meta);Object.assign(audit,{status:'ok',model_time:c.time,received_at:new Date().toISOString()});}
    catch(e){p.textContent='Unavailable: '+e.message+' Refresh to retry.';p.classList.add('error');Object.assign(audit,{status:'failed',error:e.message});}article.classList.remove('loading');STATE.audit.current.push(audit);
  }
  $('current').disabled=false;
}
$('file').addEventListener('change',loadFile);$('sheet').addEventListener('change',importSheet);$('enrich').addEventListener('click',enrich);$('city').addEventListener('change',render);$('exposure').addEventListener('change',render);$('export').addEventListener('click',exportCSV);$('audit').addEventListener('click',()=>download('weather-audit.json',JSON.stringify(STATE.audit,null,2),'application/json'));$('current').addEventListener('click',current);
document.documentElement.dataset.theme=matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';$('theme').addEventListener('click',()=>{document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark';});
