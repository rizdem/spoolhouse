// Spoolhouse - Printers: the printers list, a printer's slots, Will it fit? and collapsible sections.
// time left as "1 h 25 min" / "12 min"
const fmtLeft=s=>{const m=Math.round(s/60);return m>=60?`${Math.floor(m/60)} h ${m%60} min`:`${Math.max(1,m)} min`};
// ---------- printers
let printers=[], models=[], curPrinter=store.get("printer",null), pState=null, pLogLoaded=false, editingPrinter=null;
const ago=t=>{if(!t)return"";const s=Math.round(Date.now()/1000-t);return s<60?"just now":s<3600?`${Math.round(s/60)} min ago`:new Date(t*1000).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})};
const spoolLabel=s=>`${groupName(s)}${s.brand?" · "+s.brand:""} · ${fmtG(s.remaining_g)} g${s.serial?" · #"+s.serial:""}`;
const live=p=>p.state==="printing"||p.state==="paused";

async function loadPrinters(){
  try{const d=await call("/api/printers/list");printers=d.printers;models=d.models;renderPrinterList()}catch(e){}
}
function renderPrinterList(){
  const need=printers.reduce((a,p)=>a+p.unlinked,0); $("pbadge").hidden=!need; $("pbadge").textContent=need;
  const box=$("pCards"); box.replaceChildren();
  for(const p of printers){
    const c=el("div","pcard"), top=el("div","ptop"), ico=el("div","pico"); ico.innerHTML=PRINTER_ICON; top.appendChild(ico);
    const t=el("div"); t.style.minWidth="0"; t.appendChild(el("div","pname",p.name)); t.appendChild(el("div","pmeta",[p.model||"Creality printer",p.host].join(" · "))); top.appendChild(t);
    const stTxt=!p.at&&!p.error?"Checking…":p.error?"Offline":live(p)?(p.state==="paused"?"Paused":"Printing"):"Online";
    top.appendChild(el("span","pstate "+(!p.at&&!p.error?"checking":p.error?"offline":live(p)?"printing":"online"),stTxt)); c.appendChild(top);
    const dots=el("div","pdots"); p.loaded.forEach(l=>{const i=el("i",l.printing?"on":null);i.style.background="#"+l.color;dots.appendChild(i)});
    if(!p.loaded.length) dots.appendChild(el("span","mute",p.error?"Can't reach the printer":"No filament loaded")); c.appendChild(dots);
    const f=el("div","pfoot"); f.appendChild(el("span",null,live(p)?`${(p.used_mm/1000).toFixed(1)} m used this print`:p.at?`Checked ${ago(p.at)}`:""));
    f.appendChild(p.fit_short?el("span","warn",`⚠ Filament may run out`):p.humid.length?el("span","warn",`💧 ${p.humid.map(h=>`${Math.round(h.humidity)}%`).join(", ")} humidity`):p.unlinked?el("span","warn",`${p.unlinked} slot${p.unlinked>1?"s":""} not linked`):p.loaded.length?el("span","good","All slots linked"):el("span"));
    c.appendChild(f); c.onclick=()=>openPrinter(p.id); box.appendChild(c);
  }
  const add=el("div","pcard add"); add.textContent="+ Add printer"; add.onclick=()=>openPrinterEditor(null); box.appendChild(add);
}
function showPrinterList(){curPrinter=null;store.set("printer",null);$("pDetail").hidden=true;$("pList").hidden=false;loadPrinters()}
function openPrinter(id){
  fitChecked=null; fitFilesFor=null;
  curPrinter=id; store.set("printer",id); pState=null; pLogLoaded=false;
  $("pList").hidden=true; $("pDetail").hidden=false; $("pSlots").replaceChildren(); $("pUsageCard").hidden=true; $("pLogCard").hidden=true;
  const p=printers.find(x=>x.id===id); $("pdName").textContent=p?p.name:"Printer"; $("pdMeta").textContent=p?[p.model,p.host].filter(Boolean).join(" · "):"";
  $("pStatus").className="pstatus"; $("pStatus").textContent="Connecting…";
  loadPrinter(true,true);
}
function enterPrinters(){
  // the Printers tab remembers which printer you were looking at
  loadPrinters().then(()=>{ if(curPrinter&&printers.some(p=>p.id===curPrinter)) openPrinter(curPrinter); else showPrinterList() });
}
$("pBack").onclick=showPrinterList;

async function loadPrinter(refresh=true,withLog=false){
  if(!curPrinter)return;
  const id=curPrinter;
  try{
    if(!spools.length) await loadInv();
    const d=await call("/api/printer/status",{id,refresh}); if(id!==curPrinter)return;
    pState=d; renderPrinter(); if(refresh) recheckFile();
    if(withLog&&!d.error) loadLog();
  }catch(e){$("pStatus").className="pstatus bad";$("pStatus").textContent=e.message}
}
function renderPrinter(){
  const st=pState||{};
  $("pdName").textContent=st.name||"Printer"; $("pdMeta").textContent=[st.model,st.host].filter(Boolean).join(" · ");
  const ps=$("pStatus"), job=st.job||{}, run=job.state==="printing"||job.state==="paused";
  if(st.error){ps.className="pstatus bad";ps.textContent=st.error}
  else{ps.className="pstatus";ps.textContent=[`Connected`,`synced ${ago(st.at)}`,
    run?`${job.state==="paused"?"Paused":"Printing"}${job.progress!=null?` ${Math.round(job.progress*100)}%`:""}${job.left_secs!=null?`, about ${fmtLeft(job.left_secs)} left`:""}: ${(job.used_mm/1000).toFixed(1)} m used so far, checked every ${st.fast_secs}s`:`Idle, checked every ${st.sync_secs}s while the app is open`,
    st.no_cfs&&"No CFS found: link the spool on the holder to track it"].filter(Boolean).join(" · ")}
  renderFit();
  const box=$("pSlots"); box.replaceChildren();
  // CFS units first, the external holder last
  const boxes=[...(st.boxes||[])].sort((x,y)=>(x.external-y.external)||(x.id-y.id));
  for(const bx of boxes){
    const mine=(st.slots||[]).filter(s=>s.local.split("-")[0]===String(bx.id));
    if(!mine.length||(!bx.external&&!bx.connected))continue;
    const grp=el("div","pgroup "+(bx.external?"ext":"cfs")), gh=el("div","ghead");
    gh.appendChild(el("h3",null,bx.external?(st.no_cfs?"Spool holder":"External spool holder"):bx.label));
    if(!bx.external&&bx.temp!=null){const hs=el("span",bx.humid_high?"humid":null,`${Math.round(bx.temp)}°C · ${Math.round(bx.humidity)}% humidity${bx.humid_high?" · too damp":""}`);
      if(bx.humid_high) hs.title=`Above your ${settings.humidity_max}% limit (Settings). Dry the filament or check the desiccant.`; gh.appendChild(hs)}
    grp.appendChild(gh);
    const grid=el("div","slots"+(bx.external?" one":""));
    mine.forEach(s=>grid.appendChild(slotCard(s,bx.external?"Spool":`Slot ${Number(s.local.split("-")[1])+1}`)));
    grp.appendChild(grid); box.appendChild(grp);
  }
  const usage=st.usage||[]; $("pUsageCard").hidden=!usage.length;
  $("pUsageSum").textContent=usage.length?`${usage.length} entr${usage.length===1?"y":"ies"} · last ${fmtWhen(usage[0].at)}`:"";
  const tb=$("pUsage"); tb.replaceChildren();
  if(usage.length){const h=el("tr");["When","Spool","Slot","Used"].forEach((x,i)=>h.appendChild(el("th",i===3?"num":null,x)));tb.appendChild(h)}
  for(const u of usage){
    const s=spools.find(x=>x.id===u.spool_id), slot=(st.slots||[]).find(x=>x.key===u.slot_key), tr=el("tr");
    tr.appendChild(el("td",null,new Date(u.at*1000).toLocaleString([], {day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"})));
    const sc=el("td"), nm=el("div","used"), line=el("span"); line.appendChild(swatch(u.color));
    line.appendChild(document.createTextNode(u.spool_id?(s?groupName(s):snapName(u.color,u.material)+" (deleted)"):`${snapName(u.color,u.material)}: not linked`)); nm.appendChild(line);
    if(!u.spool_id) nm.appendChild(assignSelect(u.id)); sc.appendChild(nm); tr.appendChild(sc);
    tr.appendChild(el("td",null,slot?slot.label:"—"));
    tr.appendChild(el("td","num",`${fmtG(u.grams)} g`)); tb.appendChild(tr);
  }
}
// ---------- will it fit?
makePicker($("fitFile"),{search:true,placeholder:"Search print files…"});
let fitFilesFor=null, fitChecked=null;
async function loadFitFiles(){
  if(fitFilesFor===curPrinter)return; fitFilesFor=curPrinter;
  const sel=$("fitFile"); sel.replaceChildren(new Option("Check a print file on the printer…",""));
  try{const {files}=await call("/api/printer/files",{id:curPrinter});
    files.forEach(f=>sel.appendChild(new Option(f.name.replace(/\.gcode$/i,"").replace(/_/g," "),f.name)))}
  catch(e){fitFilesFor=null}
  sel.value="";
}
function fitRow(it){
  const r=el("div","fitrow"), d=el("div","dot"); d.style.background="#"+(it.color||"888888"); r.appendChild(d);
  const t=el("div"); t.style.minWidth="0";
  t.appendChild(el("div","fn",it.name?`${it.name}`:`${it.type} · #${it.color}`));
  t.appendChild(el("div","fm",it.slot?`${it.slot} · print file colour #${it.color}`:(it.note||"")));
  if(it.stock){
    const s=it.stock, line=el("div","fstock");
    if(!s.found){line.classList.add("none");line.textContent=it.status==="short"?"No other spool of this in your inventory":"Not in your inventory"}
    else{
      const name=`${colorName(s.color)} ${matName(s.material).replace(/^Generic /,"")}${s.brand&&!matName(s.material).includes(s.brand)?" · "+s.brand:""}`;
      const many=s.spools>1?` (${s.spools} spools, ${fmtG(s.total_g)} g in all)`:"";
      line.classList.add(s.enough?"yes":"part");
      line.textContent=`${it.status==="short"?"Another spool in stock":"In stock"}: ${name} · ${fmtG(s.best_g)} g${many} · ${s.enough?"enough"+(it.status==="short"?" to swap in":""):`not enough (needs ${fmtG(s.need_g)} g)`}`;
    }
    t.appendChild(line);
  }
  r.appendChild(t);
  r.appendChild(el("div","fq",it.need_g!=null?`needs ${fmtG(it.need_g)} g · has ${it.have_g!=null?fmtG(it.have_g)+" g":"?"}${it.source==="CFS estimate"?" (CFS)":""}`:`needs ${fmtG(it.plan_g)} g`));
  const lab={ok:"Enough",tight:"Tight",short:`Short by ${fmtG(it.short_g||0)} g`,unknown:it.note?"Not loaded":"Unknown"}[it.status];
  r.appendChild(el("span","fpill "+it.status,lab)); return r;
}
function fitVerdict(check,after){
  const bad=check.items.filter(i=>i.status==="short"), unk=check.items.filter(i=>i.status==="unknown");
  const covered=list=>list.length&&list.every(i=>i.stock&&i.stock.found&&i.stock.enough);
  const n=x=>`${x.length} colour${x.length>1?"s":""}`;
  return bad.length?`Not enough filament for ${n(bad)}${after?" once the current print finishes":""}`+(covered(bad)?", but you have a spool in stock to swap in.":": swap or top up before printing.")
    :unk.length?(covered(unk)?`${unk.length>1?"Some colours aren't":"One colour isn't"} loaded yet, but you have enough in stock: load ${unk.length>1?"them":"it"} before printing.`
      :`${n(unk)} in this file ${unk.length>1?"aren't":"isn't"} loaded`+(unk.some(i=>!(i.stock&&i.stock.enough))?" and you don't have enough in stock.":".")):
    after?"Enough left for this after the current print finishes.":"Your loaded spools have enough for this print.";
}
function renderFit(){
  const st=pState||{}, fit=st.fit, card=$("pFit");
  loadFitFiles();
  const short=c=>!!(c&&(c.items||[]).some(i=>i.status==="short"));
  card.classList.toggle("fitbad",short(fit)||short(fitChecked));
  const fileName=f=>jobName({name:(f||"").replace(/\.gcode$/i,"")});
  if(fit){  // a print is running: its live check first
    $("fitTitle").textContent="This print: will it fit?";
    $("fitNote").textContent=fit.has_plan?fileName(fit.file)+" · amounts still needed from each spool":"This print file doesn't list how much filament it needs.";
    $("fitRows").replaceChildren(...(fit.items||[]).map(fitRow));
  }else{
    $("fitTitle").textContent="Will it fit?";
    $("fitNote").textContent=fitChecked?"":"Pick a file you've sent to the printer to check your loaded spools have enough of each colour before you start it.";
    $("fitRows").replaceChildren();
  }
  // the file you picked, shown alongside (while printing: what's left after the current print)
  const box=$("fitFileBox"); box.hidden=!fitChecked;
  if(!fitChecked)return;
  $("fitFileTitle").textContent=(fit?"Next print: ":"")+fileName(fitChecked.file);
  $("fitFileTitle").style.borderTop=fit?"":"0"; $("fitFileTitle").style.paddingTop=fit?"":"0"; $("fitFileTitle").style.marginTop=fit?"":"10px";
  $("fitFileNote").textContent=fitVerdict(fitChecked,fitChecked.after_current);
  $("fitFileRows").replaceChildren(...fitChecked.items.map(fitRow));
}
async function recheckFile(){
  // keep the picked file's check current as spools are used
  if(!fitChecked||!curPrinter)return;
  try{const r=await call("/api/printer/check_file",{id:curPrinter,file:fitChecked.file}); if(fitChecked&&r.file===fitChecked.file){fitChecked=r;renderFit()}}catch(e){}
}
$("fitFile").onchange=async()=>{
  const f=$("fitFile").value; if(!f){fitChecked=null;renderFit();return}
  $("fitFileBox").hidden=false; $("fitFileTitle").textContent=jobName({name:f.replace(/\.gcode$/i,"")}); $("fitFileNote").textContent="Checking…"; $("fitFileRows").replaceChildren();
  try{fitChecked=await call("/api/printer/check_file",{id:curPrinter,file:f})}catch(e){fitChecked=null;$("fitFileNote").textContent=e.message;return}
  renderFit();
};

function assignSelect(usageId){
  const sel=el("select","sm"); sel.style.maxWidth="240px";
  sel.appendChild(new Option("Assign to a spool…",""));
  spools.filter(x=>x.remaining_g>0).forEach(x=>sel.appendChild(new Option(spoolLabel(x),x.id)));
  sel.onclick=e=>e.stopPropagation();
  sel.onchange=async()=>{if(!sel.value)return;
    try{await call("/api/printer/assign",{usage_id:usageId,spool_id:+sel.value});await loadInv();await loadPrinter(false,false);loadLog()}
    catch(e){alert(e.message)}};
  return sel;
}
async function linkSlot(s,spoolId,usePrinterAmount){
  try{pState=await call("/api/printer/link",{printer_id:curPrinter,slot_key:s.key,spool_id:spoolId,use_printer_amount:usePrinterAmount});await loadInv();renderPrinter();loadPrinters()}
  catch(e){alert(e.message)}
}
function slotCard(s,title){
  const linked=s.spool_id?spools.find(x=>x.id===s.spool_id):null, holder=!s.material_code&&s.present&&pState&&pState.no_cfs;
  const card=el("div","slot"+(s.printing?" printing":"")+(s.present?"":" emptyslot")+(s.present&&!s.spool_id?" unlinked":""));
  const hd=el("div","shead"); hd.appendChild(el("span","ttl",title)); if(s.printing) hd.appendChild(el("span","pill","PRINTING")); card.appendChild(hd);
  const bd=el("div","sbody"), dot=el("div","dot"+(s.present&&!holder?"":" nodot")); if(s.present&&!holder) dot.style.background="#"+(s.color||"888888"); bd.appendChild(dot);
  const tx=el("div","stext"), nm=el("div","nm",holder?(linked?groupName(linked):"Spool holder"):s.present?(s.name||s.type):"Empty"); nm.title=nm.textContent; tx.appendChild(nm);
  tx.appendChild(el("div","sub2",holder?"No CFS: link the spool you load":s.present?[s.vendor,s.type].filter(Boolean).join(" · "):"No filament loaded")); bd.appendChild(tx); card.appendChild(bd);
  if(!s.present) return card;
  const am=el("div","samt"); am.appendChild(el("b",null,s.grams!=null?`${Math.round(s.grams)} g`:linked?`${fmtG(linked.remaining_g)} g`:"—"));
  if(s.remaining_mm!=null) am.appendChild(el("span",null,`left · ${(s.remaining_mm/1000).toFixed(1)} m`)); card.appendChild(am);
  const g=s.grams!=null?s.grams:linked?linked.remaining_g:0;
  const frac=Math.max(0,Math.min(1,g/((linked&&linked.total_g)||1000)));
  const bar=el("div","bar"+(frac<.1?" out":frac<.25?" low":"")), fill=el("i"); fill.style.width=Math.round(frac*100)+"%"; bar.appendChild(fill); card.appendChild(bar);
  const tag=s.tag, unknownTag=tag&&!s.spool_id&&s.tag_match==="none";
  // linked to a different spool than the tag in the slot says (e.g. picked by mistake)
  const tagSpool=typeof s.tag_match==="number"?spools.find(x=>x.id===s.tag_match):null;
  const against=tagSpool&&s.spool_id&&s.spool_id!==tagSpool.id;
  const stx=against?`The tag says ${groupName(tagSpool)} (#${tag.serial}), but this is linked to another spool`
    :unknownTag?`Not in your inventory (tag #${tag.serial}): scan it in`
    :s.swapped?"New spool loaded. Pick which one.":!s.spool_id?(tag&&s.tag_match==="several"?"Several spools match its tag: pick one":"Not linked"):linked?spoolLabel(linked):"Linked spool not found";
  const sl=el("div","sstate"+(s.swapped||!s.spool_id||against?" warn":""),stx); sl.title=stx; card.appendChild(sl);
  if(against){const back=el("button","btn sm","Switch back to the tagged spool"); back.onclick=()=>linkSlot(s,tagSpool.id,false); card.appendChild(back)}
  const ctl=el("div","sctl"), opt=el("label","opt"+(s.spool_id?" on":""));
  const cb=el("input"); cb.type="checkbox"; cb.checked=false;
  if(s.spool_id) opt.appendChild(document.createTextNode(tag&&String(s.tag_match)===String(s.spool_id)?"✓ Matched by its tag":"✓ Tracking usage"));
  else if(s.grams!=null){opt.appendChild(cb);opt.appendChild(el("span",null,`Use printer's estimate (${Math.round(s.grams)} g)`));opt.title="Sets the spool to the amount the CFS reported when it was loaded. Leave unticked to keep the spool's own figure."}
  const sel=el("select"); sel.appendChild(new Option("Not linked",""));
  const code=s.material_code, hex=(s.color||"").toUpperCase();
  const match=code?spools.filter(x=>x.material===code&&x.color.toUpperCase()===hex):[], sameMat=code?spools.filter(x=>x.material===code&&!match.includes(x)):[];
  const rest=spools.filter(x=>!match.includes(x)&&!sameMat.includes(x));
  for(const [label,list] of [["Matches this slot",match],["Same material",sameMat],[match.length||sameMat.length?"Other spools":"Your spools",rest]]){
    if(!list.length)continue; const og=document.createElement("optgroup"); og.label=label;
    list.forEach(x=>og.appendChild(new Option(spoolLabel(x),x.id))); sel.appendChild(og);
  }
  sel.value=s.spool_id||"";
  sel.onchange=async()=>{
    const chosen=sel.value?+sel.value:null;
    // the slot's tag already identifies its spool: changing that needs a deliberate yes
    if(tagSpool&&chosen!==tagSpool.id){
      const what=chosen?`link ${groupName(spools.find(x=>x.id===chosen))} instead`:"unlink it";
      if(!confirm(`The tag in ${title} says it's ${groupName(tagSpool)} (#${tag.serial}).\n\nDo you want to ${what}? Filament this slot uses will then ${chosen?"come off that spool":"not be charged automatically"}.`)){sel.value=s.spool_id||"";return}
    }
    linkSlot(s,chosen,cb.checked);
  };
  ctl.appendChild(opt); ctl.appendChild(sel); card.appendChild(ctl);
  return card;
}
// ---------- collapsible sections (closed by default; remembered)
document.querySelectorAll(".coll").forEach(c=>{
  const head=c.querySelector(".collhead"), key="coll_"+c.dataset.key;
  const set=open=>{c.classList.toggle("open",open);head.setAttribute("aria-expanded",open)};
  set(store.get(key,false));
  head.onclick=()=>{const open=!c.classList.contains("open");set(open);store.set(key,open)};
});

