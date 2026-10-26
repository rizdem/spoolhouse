// Spoolhouse - A printer's print log and the charge dialog.
// ---------- print log
let logMonth=null, logJobs=[], logTotal=0, logMode=store.get("logMode","all");
const fmtWhen=t=>t?new Date(t*1000).toLocaleString([], {day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"}):"";
const fmtDur=s=>{const d=Math.round(s/60);return d>=60?`${Math.floor(d/60)}h ${d%60}m`:`${d}m`};
const jobName=j=>j.name.replace(/_\d+h\d+m\d*s?$/,"").replace(/_/g," ");
function snapName(color,material){return `${color?colorName(color)+" ":""}${material?matName(material).replace(/^Generic /,""):"Filament"}`}
function swatch(color){const m=el("i","mini");m.style.background=color?"#"+color:"transparent";if(!color)m.style.borderStyle="dashed";return m}
async function loadLog(more=false){
  const tb=$("pLog"), id=curPrinter; $("pLogCard").hidden=false;
  if(!more){logJobs=[]; if(!tb.rows.length){tb.appendChild(el("tr")).appendChild(el("td","mute","Loading print history…"))}}
  try{
    const d=await call("/api/printer/history",{id,limit:50,start:more?logJobs.length:0}); if(id!==curPrinter)return;
    logJobs=more?logJobs.concat(d.jobs):d.jobs; logTotal=d.total; if(d.month) logMonth=d.month; renderLog();
  }catch(e){tb.replaceChildren();tb.appendChild(el("tr")).appendChild(el("td","bad",e.message))}
}
function renderLog(){
  const tb=$("pLog"); tb.replaceChildren();
  document.querySelectorAll("#logMode button").forEach(b=>b.classList.toggle("on",b.dataset.m===logMode));
  const needs=logJobs.filter(j=>j.needs).length; $("logNeeds").hidden=!needs; $("logNeeds").textContent=needs+(logJobs.length<logTotal?"+":"");
  const sum=$("pLogSum"); sum.replaceChildren(document.createTextNode(`${logTotal} print${logTotal===1?"":"s"}`));
  const m=logMonth, mon=new Date().toLocaleString([], {month:"long"});
  $("logMonth").textContent=m&&m.grams>0?`${mon}: ${fmtG(m.grams)} g used`+(m.cost?` · ${money(m.cost)}${m.unpriced_g>0?"+":""}`:"")+` across ${m.prints} print${m.prints===1?"":"s"}`:`${mon}: nothing charged yet`;
  if(m&&m.cost) sum.appendChild(el("span",null,`· ${money(m.cost)} this month`));
  if(needs) sum.appendChild(el("span","warn",`${needs}${logJobs.length<logTotal?"+":""} need${needs===1&&logJobs.length>=logTotal?"s":""} attention`));
  $("pLogMore").hidden=logJobs.length>=logTotal; $("pLogMore").textContent=`Load older prints (${logJobs.length} of ${logTotal})`;
  const rows=logMode==="needs"?logJobs.filter(j=>j.needs):logJobs;
  const h=el("tr");["Started","Print","Status","Time","Filament","Cost","From"].forEach((x,i)=>h.appendChild(el("th",i>=3&&i<=5?"num":null,x)));tb.appendChild(h);
  if(!rows.length){tb.appendChild(el("tr")).appendChild(el("td","mute",logMode==="needs"?"Nothing needs attention. Every print here is charged or skipped.":"No prints yet."));return}
  for(const j of rows){
    const tr=el("tr",j.needs?"needs":null);
    tr.appendChild(el("td",null,fmtWhen(j.start))); tr.appendChild(el("td",null,jobName(j)));
    const sc=el("td"); sc.appendChild(el("span","st "+j.status,j.status==="in_progress"?"Printing":j.status.replace(/_/g," "))); tr.appendChild(sc);
    tr.appendChild(el("td","num",fmtDur(j.duration)));
    tr.appendChild(el("td","num",`${(j.mm/1000).toFixed(1)} m · ${Math.round(j.grams)} g`));
    const ct=el("td","num",j.cost!=null?money(j.cost)+(j.cost_partial?"+":""):"—");
    if(j.cost_partial) ct.title="Some of the spools this print used have no price"; tr.appendChild(ct);
    const from=el("td"), u=el("div","used"), acts=el("div","acts");
    for(const x of j.spools){const s=spools.find(y=>y.id===x.spool_id), r=el("span"); r.appendChild(swatch(x.color));
      r.appendChild(document.createTextNode(`${s?groupName(s):snapName(x.color,x.material)+" (deleted)"} · ${fmtG(x.grams)} g`)); u.appendChild(r)}
    for(const x of j.unassigned){const r=el("span"); r.appendChild(swatch(x.color));
      r.appendChild(el("span","warn",`${fmtG(x.grams)} g unassigned${x.color||x.material?` · ${snapName(x.color,x.material)}`:""}${x.label?` · ${x.label}`:""}`)); u.appendChild(r)}
    if(j.status==="in_progress") u.appendChild(el("span","mute","Tracking live…"));
    else if(j.skipped){u.appendChild(el("span","mute","Skipped (already counted)"));
      const un=el("button","btn sm","Undo skip"); un.onclick=()=>skipJob(j,false); acts.appendChild(un)}
    else if(!j.spools.length&&!j.unassigned.length&&j.mm>0) u.appendChild(el("span","mute",j.tracked_era?"Not charged":"Not tracked (before this printer was added)"));
    if(j.status!=="in_progress"&&!j.skipped&&j.mm>0){
      const charged=j.spools.length>0;
      const b=el("button","btn sm"+(j.needs&&!charged?" pri":""),charged?"Edit":"Charge…"); b.onclick=()=>openCharge(j); acts.appendChild(b);
      if(!charged){const sk=el("button","btn sm","Skip"); sk.title="Your spool amounts already include this print"; sk.onclick=()=>skipJob(j,true); acts.appendChild(sk)}
    }
    from.appendChild(u); if(acts.children.length) from.appendChild(acts); tr.appendChild(from); tb.appendChild(tr);
  }
}
async function skipJob(j,skip){
  try{await call("/api/printer/skip_job",{id:curPrinter,job_id:j.id,skip});await loadLog()}catch(e){alert(e.message)}
}
document.querySelectorAll("#logMode button").forEach(b=>b.onclick=()=>{logMode=b.dataset.m;store.set("logMode",logMode);renderLog()});
$("pLogMore").onclick=()=>loadLog(true);

// ---------- charge dialog
let chargeJob=null;
const perMm=s=>({PLA:1.24,"PLA-Silk":1.24,"PLA-CF":1.29,PETG:1.27,"PETG-CF":1.30,ABS:1.04,ASA:1.07,TPU:1.21,PA:1.14,PC:1.20}[typeOf(s)]||1.24)*Math.PI*0.875*0.875/1000;
function suggestSpool(j){
  // the spool most likely to have fed this print: same filament as unassigned usage, else in this printer & same type
  const snap=j.unassigned.find(x=>x.material);
  if(snap){const m=spools.filter(s=>s.material===snap.material&&s.color.toUpperCase()===(snap.color||"").toUpperCase()&&s.remaining_g>0);
    if(m.length) return m.find(s=>inPrinter[s.id])||m[0]}
  const loaded=spools.filter(s=>inPrinter[s.id]&&inPrinter[s.id].slot.startsWith((printers.find(p=>p.id===curPrinter)||{}).name||"")&&s.remaining_g>0);
  const typed=list=>list.filter(s=>j.type_hint&&typeOf(s).toUpperCase().startsWith(j.type_hint));
  const same=typed(loaded); if(same.length) return same[0];
  const shelf=typed(spools.filter(s=>s.remaining_g>0));   // e.g. the only PETG you own, on the shelf
  if(shelf.length===1) return shelf[0];
  return loaded.length===1&&!j.type_hint?loaded[0]:null;
}
function chargeRow(spoolId,grams){
  const row=el("div","crow"), dot=el("div","dot"), sel=el("select"), g=el("input"), x=el("button","x","×");
  sel.appendChild(new Option("Choose a spool…",""));
  const inThis=spools.filter(s=>inPrinter[s.id]), rest=spools.filter(s=>!inPrinter[s.id]);
  for(const [label,list] of [["In a printer",inThis],["Other spools",rest]]){if(!list.length)continue;const og=document.createElement("optgroup");og.label=label;list.forEach(s=>og.appendChild(new Option(spoolLabel(s),s.id)));sel.appendChild(og)}
  sel.value=spoolId||""; g.type="number"; g.min="0"; g.step="0.1"; g.placeholder="grams"; g.value=grams!=null?(Math.round(grams*10)/10).toFixed(1):"";
  const paint=()=>{const s=spools.find(y=>y.id===+sel.value);dot.style.background=s?"#"+s.color:"transparent";dot.style.borderStyle=s?"solid":"dashed"};
  sel.onchange=()=>{
    paint(); const s=spools.find(y=>y.id===+sel.value);
    // one row: the whole print in this spool's material; extra rows: whatever is still unallocated
    if(s&&($("ceRows").children.length===1||!g.value)) g.value=(Math.max(0,remainingMm(row))*perMm(s)).toFixed(1);
    chargeSum()};
  g.oninput=chargeSum; x.onclick=()=>{row.remove();chargeSum()}; paint();
  row.append(dot,sel,g,el("span","mute","g"),x); return row;
}
function remainingMm(except){
  let mm=0; for(const r of $("ceRows").children){if(r===except)continue;const s=spools.find(y=>y.id===+r.querySelector("select").value), gr=+r.querySelector("input").value||0; if(s&&gr>0) mm+=gr/perMm(s)}
  return chargeJob.mm-mm;
}
function chargeSum(){
  // compare in metres so mixed materials add up correctly
  let mm=0; for(const r of $("ceRows").children){const s=spools.find(y=>y.id===+r.querySelector("select").value), gr=+r.querySelector("input").value||0; if(s&&gr>0) mm+=gr/perMm(s)}
  const tot=chargeJob.mm, out=$("ceSum"), pct=tot?mm/tot:0;
  const allocG=Math.round(pct*chargeJob.grams), totG=Math.round(chargeJob.grams);
  // within 3% counts as the whole print (the app rounds it to exactly 100% when saving)
  out.className="csum "+(pct>1.03?"over":pct>=0.97?"ok":"part");
  out.textContent=pct>1.03?`Over by about ${allocG-totG} g: that's more than the print used.`:pct>=0.97?`All ${totG} g allocated.`:`${allocG} of ${totG} g allocated. The rest stays unassigned.`;
  $("ceSave").disabled=pct>1.03;
}
function openCharge(j){
  chargeJob=j; $("ceTitle").textContent=jobName(j);
  $("ceMeta").textContent=[fmtWhen(j.start),fmtDur(j.duration),`${(j.mm/1000).toFixed(1)} m used (≈ ${Math.round(j.grams)} g)`].join(" · ");
  const rows=$("ceRows"); rows.replaceChildren();
  $("ceFrom").textContent="";
  if(j.spools.length) j.spools.filter(x=>spools.some(s=>s.id===x.spool_id)).forEach(x=>rows.appendChild(chargeRow(x.spool_id,x.grams)));
  if(!rows.children.length){const s=suggestSpool(j); rows.appendChild(chargeRow(s&&s.id,s?j.mm*perMm(s):null))}
  chargeSum(); $("cEditor").hidden=false;
  if(!j.spools.length&&j.file) prefillFromPlan(j);
}
async function prefillFromPlan(j){
  // the print file says how much of each colour it used: split the charge to match
  try{
    const {filaments}=await call("/api/printer/job_plan",{id:curPrinter,file:j.file});
    if(chargeJob!==j||!filaments.length)return;
    const rows=$("ceRows"); rows.replaceChildren();
    for(const f of filaments){const s=spools.find(x=>x.id===f.spool_id); rows.appendChild(chargeRow(s&&s.id,s?f.mm*perMm(s):f.g))}
    $("ceFrom").textContent="Pre-filled from the print file: "+filaments.map(f=>`${fmtG(f.g)} g ${f.type} #${f.color}`).join(", ")+". Check the spools match.";
    chargeSum();
  }catch(e){}
}
function closeCharge(){$("cEditor").hidden=true;chargeJob=null}
$("ceAdd").onclick=()=>{$("ceRows").appendChild(chargeRow(null,null));chargeSum()};
$("ceCancel").onclick=closeCharge;
$("cEditor").onclick=e=>{if(e.target===$("cEditor"))closeCharge()};
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("cEditor").hidden)closeCharge()});
$("ceSave").onclick=async()=>{
  const allocations=[...$("ceRows").children].map(r=>({spool_id:+r.querySelector("select").value,grams:+r.querySelector("input").value||0})).filter(a=>a.spool_id&&a.grams>0);
  try{await call("/api/printer/job_charges",{id:curPrinter,job_id:chargeJob.id,allocations});closeCharge();await loadInv();await loadLog();loadPrinter(false,false)}
  catch(e){$("ceSum").className="csum over";$("ceSum").textContent=e.message}
};
$("pRefresh").onclick=()=>loadPrinter(true,true);
$("pLogRefresh").onclick=()=>loadLog();

