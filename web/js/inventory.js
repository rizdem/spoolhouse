// Spoolhouse - Inventory: the spool list, totals, filters, selection, Recently deleted, shopping list and spool form.
// ---------- inventory
let spools=[], settings={low_g:250,tare_g:200};
let inPrinter={};
const PRINTER_ICON='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="9" rx="2"/><path d="M7 18v3h10v-3"/></svg>';
function printerChip(text,live){const c=el("span","inp"+(live?" live":""));c.innerHTML=PRINTER_ICON;c.appendChild(document.createTextNode(text));return c}
async function loadInv(){
  try{
    const [l,s]=await Promise.all([call("/api/inv/list"),call("/api/inv/settings")]);
    spools=l.spools; settings=s.settings; inPrinter=l.in_printer||{}; renderInv(); loadShop(); loadTrash();
  }catch(e){status(e.message,"bad","istatus")}
}
const RECENT_OUT=60*86400; // a finished filament keeps alerting for 60 days, then drops off
function lowGroups(){
  const groups={};
  for(const s of spools){const k=s.material+"|"+s.color;(groups[k]=groups[k]||{material:s.material,color:s.color,left:0,spools:[]}).left+=s.remaining_g;groups[k].spools.push(s)}
  const now=Date.now()/1000;
  return Object.values(groups).filter(gr=>gr.left<settings.low_g&&(gr.left>0||gr.spools.some(s=>now-s.updated<RECENT_OUT))).sort((a,b)=>a.left-b.left);
}
function renderAlerts(){
  const low=lowGroups();
  $("badge").hidden=!low.length; $("badge").textContent=low.length;
  $("alerts").hidden=!spools.length; $("alerts").classList.toggle("warn",low.length>0);
  if(document.activeElement!==$("lowG")) $("lowG").value=settings.low_g;
  $("alTitle").textContent=low.length?`Running low (${low.length})`:"Stock levels look fine";
  const list=$("alertList");list.replaceChildren();
  for(const gr of low){
    const a=el("div","alert");const dot=el("div","dot");dot.style.background="#"+(gr.color||"888888");a.appendChild(dot);
    a.appendChild(el("div","what",`${spoolColor(gr.spools.find(s=>s.color_name)||gr)} ${matName(gr.material).replace(/^Generic /,"")}`));
    const n=gr.spools.filter(s=>s.remaining_g>0).length;
    a.appendChild(el("div","qty"+(gr.left?"":" out"),gr.left?`${gr.left} g left${n>1?` across ${n} spools`:""}`:"Out of stock"));
    const pick=gr.spools.filter(s=>s.remaining_g>0).sort((x,y)=>x.remaining_g-y.remaining_g)[0]||gr.spools[0];
    a.onclick=()=>openEditor(pick);
    list.appendChild(a);
  }
}
$("lowG").onchange=async()=>{try{settings=(await call("/api/inv/settings",{low_g:$("lowG").value})).settings;renderInv()}catch(e){status(e.message,"bad","istatus")}};
const equiv=s=>s.total_g?s.remaining_g/s.total_g:0;
const fmtSpools=n=>{const r=Math.round(n*10)/10;return (Number.isInteger(r)?r:r.toFixed(1))+" spool"+(r===1?"":"s")};
const groupKey=s=>s.material+"|"+s.color;
const groupName=s=>`${spoolColor(s)} ${matName(s.material).replace(/^Generic /,"")}`;
let mode=store.get("invMode","spools"), groupFilter=null;
// ---------- filters
// base plastic for Creality's own product lines (Generic ones are named after their type)
const CREALITY_TYPE={"01001":"PLA","01601":"PLA","02001":"PLA-CF","03001":"ABS","04001":"PLA","05001":"PLA-Silk","06001":"PETG","06002":"PETG",
  "07001":"ABS","07002":"PC","08001":"PLA","09001":"PLA","09002":"PLA","10001":"TPU","11001":"PA","12002":"PPA-CF","12003":"PAHT-CF",
  "13001":"PLA-CF","14001":"PLA","15001":"PLA","16001":"TPU","17001":"PLA","18001":"PLA","19001":"ASA"};
const isCreality=id=>(MATERIALS[id]||"").startsWith("Creality ");
const typeOf=s=>CREALITY_TYPE[s.material]||matName(s.material).replace(/^(Generic|Creality) /,"");
const brandOf=s=>s.brand||(isCreality(s.material)?"Creality":"No brand");
function familyOf(hex){
  // name the colour family from hue/saturation/lightness so every shade of blue files under Blue
  const h6=(hex||"888888").padEnd(6,"0"),r=parseInt(h6.slice(0,2),16)/255,g=parseInt(h6.slice(2,4),16)/255,b=parseInt(h6.slice(4,6),16)/255;
  const mx=Math.max(r,g,b),mn=Math.min(r,g,b),l=(mx+mn)/2,d=mx-mn,sat=d?d/(1-Math.abs(2*l-1)):0;
  let hue=0; if(d){hue=mx===r?((g-b)/d)%6:mx===g?(b-r)/d+2:(r-g)/d+4; hue=(hue*60+360)%360}
  if(l<.13)return"Black"; if(l>.92||l>.82&&sat<.2)return"White"; if(sat<.15)return"Grey";
  if(hue>=15&&hue<45&&l<.45)return"Brown"; if(hue>=25&&hue<65&&l>.78)return"Beige";
  if(hue<15||hue>=345)return"Red"; if(hue<45)return"Orange"; if(hue<70)return"Yellow"; if(hue<160)return"Green";
  if(hue<195)return"Teal"; if(hue<255)return"Blue"; if(hue<320)return"Purple"; return"Pink";
}
const FAMILY_SWATCH={Black:"111111",White:"F5F5F5",Grey:"8E8E93",Red:"E0281E",Orange:"FF7A1A",Brown:"8B4513",Beige:"E8D5B0",Yellow:"FFD60A",Green:"34A853",Teal:"20B2AA",Blue:"1E6FE0",Purple:"8E44AD",Pink:"FF5FA2"};
const FACETS=[["type","Type",typeOf],["brand","Brand",brandOf],["colour","Colour",s=>familyOf(s.color)],["shop","Shop",s=>s.source||"Unknown"],
  ["where","Location",s=>inPrinter[s.id]?"In printer":"On shelf"]];
const filters=Object.fromEntries(FACETS.map(([k])=>[k,new Set(store.get("f_"+k,[]))]));
let openFacet=null;
const anyFilter=()=>FACETS.some(([k])=>filters[k].size);
function passes(s,skip){return FACETS.every(([k,,fn])=>k===skip||!filters[k].size||filters[k].has(fn(s)))}
function renderFilters(base){
  // base = spools after search/hide-empty; counts for a facet ignore that facet's own selection
  const box=$("filters"); box.replaceChildren();
  for(const [k,label,fn] of FACETS){
    const wrap=el("div","fbtn"), sel=filters[k];
    const btn=el("button",sel.size?"on":"",sel.size===1?`${label}: ${[...sel][0]}`:sel.size?`${label} (${sel.size})`:label);
    btn.onclick=e=>{e.stopPropagation();openFacet=openFacet===k?null:k;renderInv()};
    wrap.appendChild(btn);
    if(openFacet===k){
      const pop=el("div","pop");pop.onclick=e=>e.stopPropagation();
      const counts={}; base.filter(s=>passes(s,k)).forEach(s=>{const v=fn(s);counts[v]=(counts[v]||0)+1});
      sel.forEach(v=>{if(!(v in counts))counts[v]=0});
      const opts=Object.entries(counts).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));
      if(!opts.length)pop.appendChild(el("div","empty","Nothing to filter yet."));
      for(const [v,n] of opts){
        const row=el("label"),cb=el("input");cb.type="checkbox";cb.checked=sel.has(v);
        cb.onchange=()=>{cb.checked?sel.add(v):sel.delete(v);store.set("f_"+k,[...sel]);renderInv()};
        row.appendChild(cb);
        if(k==="colour"){const sw=el("span","sw2");sw.style.background="#"+FAMILY_SWATCH[v];row.appendChild(sw)}
        row.appendChild(el("span",null,v));row.appendChild(el("span","cnt",n));pop.appendChild(row);
      }
      wrap.appendChild(pop);
    }
    box.appendChild(wrap);
  }
  if(anyFilter()){const c=el("button","fclear","Clear filters");c.onclick=()=>{FACETS.forEach(([k])=>{filters[k].clear();store.set("f_"+k,[])});openFacet=null;renderInv()};box.appendChild(c)}
  return box;
}
document.addEventListener("click",()=>{if(openFacet){openFacet=null;renderInv()}});
document.addEventListener("keydown",e=>{
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="f"&&!$("view-inventory").hidden){e.preventDefault();$("q").focus();$("q").select()}
  if(e.key==="Escape"&&openFacet){openFacet=null;renderInv()}
});

let selecting=false; const picked=new Set(); let visibleIds=[];
const CHECK='<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
function addCheck(it,ids){
  // selection mode: a tick in front of the row; clicking the row toggles all its spools
  visibleIds.push(...ids);
  if(!selecting)return false;
  const c=el("div","check");c.innerHTML=CHECK;it.prepend(c);
  it.classList.toggle("picked",ids.length>0&&ids.every(i=>picked.has(i)));
  it.onclick=()=>{const all=ids.every(i=>picked.has(i));ids.forEach(i=>all?picked.delete(i):picked.add(i));renderInv()};
  return true;
}
function setSelecting(on){
  selecting=on;picked.clear();$("selectBtn").classList.toggle("on",on);$("selectBtn").textContent=on?"Cancel":"Select";
  // pop the ticks in once on entering, not on every re-render
  $("list").classList.toggle("entering",on); if(on)setTimeout(()=>$("list").classList.remove("entering"),250);
  renderInv();
}
function renderSelbar(){
  const bar=$("selbar"); bar.hidden=!selecting; if(!selecting)return;
  [...picked].forEach(i=>{if(!spools.some(s=>s.id===i))picked.delete(i)});
  const n=picked.size, vis=[...new Set(visibleIds)];
  $("selCount").textContent=`${n} selected`;
  $("selDelete").disabled=!n; $("selDelete").textContent=n?`Delete ${n}`:"Delete";
  $("selAll").textContent=vis.length&&vis.every(i=>picked.has(i))?"Select none":"Select all";
}
$("selectBtn").onclick=()=>setSelecting(!selecting);
$("selDone").onclick=()=>setSelecting(false);
$("selAll").onclick=()=>{const vis=[...new Set(visibleIds)],all=vis.every(i=>picked.has(i));vis.forEach(i=>all?picked.delete(i):picked.add(i));renderInv()};
$("selDelete").onclick=async()=>{
  const ids=[...picked]; if(!ids.length)return;
  try{const {deleted}=await call("/api/inv/delete_many",{ids});setSelecting(false);
    toast(`Deleted ${deleted} spool${deleted===1?"":"s"}`,"var(--bad)",{label:"Undo",fn:()=>undoDelete(ids)});await loadInv()}
  catch(e){alert(e.message)}
};
function renderInv(){
  renderAlerts(); visibleIds=[];
  const q=$("q").value.trim().toLowerCase(), hide=$("hideEmpty").checked;
  // what the current search/filters/filament pick select, before hiding empties
  const inView=s=>(!groupFilter||groupKey(s)===groupFilter)
    &&(!q||[groupName(s),matName(s.material),typeOf(s),brandOf(s),familyOf(s.color),s.color,s.source,s.notes,s.serial].join(" ").toLowerCase().includes(q));
  const filtered=!!(q||groupFilter||anyFilter());
  const statSet=spools.filter(s=>inView(s)&&passes(s));
  $("stats").classList.toggle("filtered",filtered); $("statsNote").hidden=!filtered;
  $("statsNoteText").textContent=`Totals for the ${statSet.length} matching spool${statSet.length===1?"":"s"} (including empty ones)`;
  const inStock=statSet.filter(s=>s.remaining_g>0);
  const eq=inStock.reduce((a,s)=>a+equiv(s),0), r=Math.round(eq*10)/10;
  $("stCount").textContent=Number.isInteger(r)?r:r.toFixed(1);
  $("stCountSub").textContent=`${inStock.length} spool${inStock.length===1?"":"s"} on hand`;
  const kg=g=>g<1000?`${fmtG(g)} g`:`${(g/1000).toFixed(2)} kg`, pc=(a,b)=>b?Math.round(a/b*100):0;
  const bought=statSet.reduce((a,s)=>a+(s.total_g||0),0), left=inStock.reduce((a,s)=>a+s.remaining_g,0);
  const used=statSet.reduce((a,s)=>a+Math.max(0,(s.total_g||0)-s.remaining_g),0);   // includes finished spools
  $("stLeft").textContent=kg(left); $("stLeftSub").textContent=bought?`${pc(left,bought)}% of ${kg(bought)} bought`:"";
  $("stUsed").textContent=kg(used); $("stUsedSub").textContent=bought?`${pc(used,bought)}% of ${kg(bought)} bought`:"";
  const priced=statSet.filter(s=>s.cost!=null);
  const spent=priced.reduce((a,s)=>a+s.cost,0), value=priced.reduce((a,s)=>a+(s.total_g?s.cost*s.remaining_g/s.total_g:0),0);
  const usedCost=spent-value;
  $("stSpent").textContent=priced.length?money(spent):"—";
  $("stSpentSub").textContent=priced.length?`${priced.length} spool${priced.length===1?"":"s"} with a price`:"Add prices to see costs";
  $("stValue").textContent=priced.length?money(value):"—"; $("stValueSub").textContent=priced.length?`${pc(value,spent)}% of spend`:"";
  $("stUsedCost").textContent=priced.length?money(usedCost):"—"; $("stUsedCostSub").textContent=priced.length?`${pc(usedCost,spent)}% of spend`:"";
  document.querySelectorAll("#mode button").forEach(b=>b.classList.toggle("on",b.dataset.m===mode));
  const base=spools.filter(s=>(!hide||s.remaining_g>0)&&inView(s));
  const rows=base.filter(s=>passes(s));
  const fbox=renderFilters(base);
  if(q||anyFilter()) fbox.appendChild(el("span","fcount",`Showing ${rows.length} of ${spools.filter(s=>!hide||s.remaining_g>0).length} spools`));
  const chip=$("groupChip"), showGroups=mode==="groups"&&!groupFilter;
  $("chipRow").hidden=!groupFilter;
  if(groupFilter){const s=spools.find(x=>groupKey(x)===groupFilter);chip.textContent=`Showing ${s?groupName(s):"filament"}  ×`}
  const list=$("list");list.replaceChildren(); list.classList.toggle("selecting",selecting);
  try{ renderRows(rows,list,showGroups) } finally { renderSelbar() }
}
function renderRows(rows,list,showGroups){
  if(!rows.length){list.appendChild(el("div","none",spools.length?"No spools match.":"No spools yet. Scan a spool's tag to add it."));return}
  if(showGroups) return renderGroups(rows,list);
  for(const s of rows){
    const pct=s.total_g?s.remaining_g/s.total_g:0;
    const it=el("div","item"+(s.remaining_g<=0?" empty":""));
    const dot=el("div","dot");dot.style.background="#"+(s.color||"888888");it.appendChild(dot);
    const mid=el("div"), nm=el("div","name",matName(s.material).replace(/^Generic /,""));
    const ip=inPrinter[s.id]; if(ip) nm.appendChild(printerChip(ip.printing?`Printing · ${ip.slot}`:`In printer · ${ip.slot}`,ip.printing));
    mid.appendChild(nm);
    mid.appendChild(el("div","meta",[brandOf(s)!=="No brand"&&brandOf(s),spoolColor(s),s.source,s.purchased,s.serial&&"serial "+s.serial].filter(Boolean).join(" · ")));it.appendChild(mid);
    const lv=el("div");const bar=el("div","bar"+(pct<=0?" out":pct<.2?" low":""));const fill=el("i");fill.style.width=Math.round(pct*100)+"%";bar.appendChild(fill);
    lv.appendChild(bar);lv.appendChild(el("div","left",`${fmtG(s.remaining_g)} / ${fmtG(s.total_g)} g`));it.appendChild(lv);
    it.appendChild(el("div","price",money(s.cost)));
    if(!addCheck(it,[s.id])) it.onclick=()=>openEditor(s);
    list.appendChild(it);
  }
}
function renderGroups(rows,list){
  const groups={};
  for(const s of rows)(groups[groupKey(s)]=groups[groupKey(s)]||[]).push(s);
  const sorted=Object.entries(groups).sort((a,b)=>b[1].reduce((t,s)=>t+equiv(s),0)-a[1].reduce((t,s)=>t+equiv(s),0));
  for(const [key,ss] of sorted){
    const left=ss.reduce((a,s)=>a+s.remaining_g,0), cap=ss.reduce((a,s)=>a+s.total_g,0), eq=ss.reduce((a,s)=>a+equiv(s),0);
    const full=ss.filter(s=>s.total_g&&s.remaining_g>=s.total_g).length, open=ss.filter(s=>s.remaining_g>0&&s.remaining_g<s.total_g).length;
    const value=ss.filter(s=>s.cost!=null).reduce((a,s)=>a+s.cost*equiv(s),0);
    const it=el("div","item grp"+(left<=0?" empty":""));
    const dot=el("div","dot");dot.style.background="#"+(ss[0].color||"888888");it.appendChild(dot);
    const mid=el("div"), gn=el("div","name",groupName(ss[0])), nIn=ss.filter(x=>inPrinter[x.id]).length;
    if(nIn) gn.appendChild(printerChip(`${nIn} in printer`,ss.some(x=>inPrinter[x.id]&&inPrinter[x.id].printing)));
    mid.appendChild(gn);
    mid.appendChild(el("div","meta",[`${ss.length} spool${ss.length===1?"":"s"}`,full&&`${full} full`,open&&`${open} open`].filter(Boolean).join(" · ")));it.appendChild(mid);
    const lv=el("div");const pct=cap?left/cap:0;const bar=el("div","bar"+(left<=0?" out":left<settings.low_g?" low":""));const fill=el("i");fill.style.width=Math.round(pct*100)+"%";bar.appendChild(fill);
    lv.appendChild(bar);lv.appendChild(el("div","left",`${fmtSpools(eq)} · ${(left/1000).toFixed(2)} kg`));it.appendChild(lv);
    it.appendChild(el("div","price",ss.some(s=>s.cost!=null)?money(value):"—"));
    if(!addCheck(it,ss.map(s=>s.id))) it.onclick=()=>{groupFilter=key;renderInv()};
    list.appendChild(it);
  }
}
function stockNote(){
  const note=$("eStockNote"); if(!editing||editing.id){note.textContent="";return}
  const key=$("eMat").value+"|"+$("eHex").value.toUpperCase(), have=spools.filter(s=>groupKey(s)===key);
  const now=have.reduce((a,s)=>a+equiv(s),0), n=1;
  const total=+$("eTotal").value||0, each=total?Math.min(+$("eLeft").value||0,total)/total:0;
  const name=`${colorName($("eHex").value.toUpperCase())} ${matName($("eMat").value).replace(/^Generic /,"")}`;
  note.textContent=have.length?`You have ${fmtSpools(now)} of ${name} → ${fmtSpools(now+n*each)} with this one.`
    :`New filament: ${name}.`;
}
["eMat","eHex","ePicker","eTotal","eLeft","eRange","eGross","eTare"].forEach(id=>$(id).addEventListener("input",stockNote));
$("eMat").addEventListener("change",stockNote);
$("eMat").addEventListener("change",()=>{if(!$("eBrand").value&&isCreality($("eMat").value))$("eBrand").value="Creality"});
document.querySelectorAll("#editor [data-f], #eSizes button").forEach(b=>b.addEventListener("click",stockNote));
document.querySelectorAll("#mode button").forEach(b=>b.onclick=()=>{mode=b.dataset.m;groupFilter=null;store.set("invMode",mode);renderInv()});
$("groupChip").onclick=()=>{groupFilter=null;renderInv()};
$("q").oninput=renderInv;
$("statsClear").onclick=()=>{$("q").value="";groupFilter=null;FACETS.forEach(([k])=>{filters[k].clear();store.set("f_"+k,[])});openFacet=null;renderInv()};
$("hideEmpty").onchange=()=>{store.set("hideEmpty",$("hideEmpty").checked);renderInv()};
$("hideEmpty").checked=store.get("hideEmpty",true);

$("scan").onclick=async()=>{
  busy(true);status("Place the spool's tag on the reader…","mute","istatus");
  try{
    const r=await call("/api/inv/scan"),d=r.data;
    if(!r.spool&&r.deleted_spool){
      const s=r.deleted_spool;
      if(confirm(`This tag belongs to ${groupName(s)}, which is in Recently deleted.\n\nRestore it?`)){
        await call("/api/inv/restore",{ids:[s.id]}); await loadInv();
        status(`Restored ${groupName(s)}, ${fmtG(s.remaining_g)} g left.`,"ok","istatus"); openEditor(spools.find(x=>x.id===s.id)||s);
      }else status("Left in Recently deleted.","mute","istatus");
    }
    else if(r.spool){
      const s=r.spool; if(!s.uids.split(" ").includes(r.uid)) s.uids=(s.uids+" "+r.uid).trim();
      status(`Found: ${groupName(s)}, ${fmtG(s.remaining_g)} g left. Update it below.`,"ok","istatus");
      openEditor(s);
    }else{
      const g=GRAMS[d.weight]||1000;
      status(`New spool: ${d.material_name} ${d.color}. Add its details and save.`,"ok","istatus");
      openEditor(null,{serial:d.serial,material:d.material,color:d.color.replace("#",""),total_g:g,remaining_g:g,uids:r.uid,purchased:today()});
    }
  }catch(e){fail(e,"istatus")}
  busy(false);
};

// ---------- recently deleted
let trash=[];
async function loadTrash(){
  try{const d=await call("/api/inv/trash"); trash=d.spools;
    $("trashLink").hidden=!trash.length; $("trashLink").textContent=`Recently deleted (${trash.length})`;
    if(!$("trashSheet").hidden) renderTrash();
  }catch(e){}
}
function renderTrash(){
  const box=$("trRows"); box.replaceChildren();
  if(!trash.length) box.appendChild(el("div","shempty","Nothing here."));
  for(const s of trash){
    const r=el("div","shrow"), d=el("div","dot"); d.style.background="#"+(s.color||"888888"); r.appendChild(d);
    const t=el("div"); t.style.minWidth="0"; t.appendChild(el("div","sn",groupName(s)+(s.brand?` · ${s.brand}`:"")));
    const ago=Math.floor((Date.now()/1000-s.deleted_at)/86400);
    t.appendChild(el("div","sm",`${fmtG(s.remaining_g)} of ${fmtG(s.total_g)} g · deleted ${ago<1?"today":ago===1?"yesterday":ago+" days ago"} · ${s.days_left} day${s.days_left===1?"":"s"} left`)); r.appendChild(t);
    const rb=el("button","btn sm","Restore"); rb.onclick=async()=>{await call("/api/inv/restore",{ids:[s.id]});await loadInv();loadTrash()}; r.appendChild(rb);
    const x=el("button","x","×"); x.title="Delete for good"; x.onclick=async()=>{
      if(!confirm(`Delete ${groupName(s)} for good? This can't be undone. Its print history is kept.`))return;
      await call("/api/inv/purge",{ids:[s.id]}); loadTrash()}; r.appendChild(x);
    box.appendChild(r);
  }
  $("trEmpty").disabled=$("trRestoreAll").disabled=!trash.length;
}
$("trashLink").onclick=()=>{$("trashSheet").hidden=false;renderTrash();loadTrash()};
$("trClose").onclick=()=>{$("trashSheet").hidden=true};
$("trashSheet").onclick=e=>{if(e.target===$("trashSheet"))$("trashSheet").hidden=true};
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("trashSheet").hidden)$("trashSheet").hidden=true});
$("trRestoreAll").onclick=async()=>{const ids=trash.map(s=>s.id);await call("/api/inv/restore",{ids});toast(`Restored ${ids.length} spool${ids.length===1?"":"s"}`,"var(--ok)");await loadInv();loadTrash()};
$("trEmpty").onclick=async()=>{
  if(!confirm(`Delete all ${trash.length} spool${trash.length===1?"":"s"} in Recently deleted for good? This can't be undone.`))return;
  await call("/api/inv/purge",{all:true}); loadTrash()};

// ---------- shopping list
let shopItems=[], shopShowHidden=false;
const shopKey=i=>i.key;
makePicker($("shAdd"),{search:true,placeholder:"Search your filaments…"});
async function loadShop(action){
  try{
    const d=await call("/api/shopping",action||{}); shopItems=d.items;
    const visible=shopItems.filter(i=>!i.hidden).length; $("shopCount").hidden=!visible; $("shopCount").textContent=visible;
    // filaments not already on the list can be added
    const sel=$("shAdd"), on=new Set(shopItems.filter(i=>!i.hidden).map(shopKey));
    sel.replaceChildren(new Option("Add another filament…",""));
    d.filaments.filter(f=>!on.has(f.key)).sort((a,b)=>a.name.localeCompare(b.name))
      .forEach(f=>sel.appendChild(new Option(`${f.name.replace(/^Generic /,"")} · ${f.color_name||colorName(f.color)}`,f.key)));
    sel.value="";
    if(!$("shopSheet").hidden) renderShop();
  }catch(e){}
}
function shopLine(i){
  const what=`${i.name.replace(/^Generic /,"")}, ${i.color_name||colorName(i.color)}`+(i.brand&&!i.name.includes(i.brand)?` (${i.brand})`:"");
  const size=i.size_g>=1000?`${i.size_g/1000} kg`:`${i.size_g} g`;
  const last=[i.price!=null&&`last ${money(i.price)}`,i.shop&&`at ${i.shop}`].filter(Boolean).join(" ");
  return `- ${i.qty} x ${what}, ${size}`+(last?` - ${last}`:"");
}
function shopText(){
  const items=shopItems.filter(i=>!i.hidden);
  const lines=[`Filament shopping list (${new Date().toLocaleDateString([], {day:"numeric",month:"short",year:"numeric"})})`,"",...items.map(shopLine)];
  const priced=items.filter(i=>i.price!=null); if(priced.length) lines.push("",`Estimated total: ${money(priced.reduce((a,i)=>a+i.price*i.qty,0))}`);
  return lines.join("\n");
}
function renderShop(){
  const box=$("shRows"); box.replaceChildren();
  const rows=shopItems.filter(i=>shopShowHidden||!i.hidden), nHidden=shopItems.filter(i=>i.hidden).length;
  if(!rows.length) box.appendChild(el("div","shempty","Nothing to buy. Filaments appear here when they run low."));
  for(const i of rows){
    const r=el("div","shrow"+(i.hidden?" hid":"")), d=el("div","dot"); d.style.background="#"+i.color; r.appendChild(d);
    const t=el("div"); t.style.minWidth="0";
    t.appendChild(el("div","sn",`${i.name.replace(/^Generic /,"")} · ${i.color_name||colorName(i.color)}`+(i.brand&&!i.name.includes(i.brand)?` · ${i.brand}`:"")));
    const m=el("div","sm"); m.appendChild(el("span",i.reason==="out"?"out":i.reason==="low"?"low":null,i.reason==="out"?"Out of stock":i.reason==="low"?`${fmtG(i.remaining_g)} g left`:"Added by you"));
    m.appendChild(document.createTextNode([i.price!=null&&` · last ${money(i.price)}`,i.shop&&` at ${i.shop}`,i.bought&&` (${i.bought})`].filter(Boolean).join("")));
    t.appendChild(m); r.appendChild(t);
    if(i.hidden){const u=el("button","btn sm","Show"); u.onclick=()=>loadShop({action:"unhide",key:i.key}); r.appendChild(u); r.appendChild(el("span"))}
    else{
      const q=el("div","qtyctl"), minus=el("button",null,"−"), n=el("span",null,i.qty), plus=el("button",null,"+");
      minus.onclick=()=>loadShop({action:"qty",key:i.key,qty:i.qty-1}); plus.onclick=()=>loadShop({action:"qty",key:i.key,qty:i.qty+1});
      q.append(minus,n,plus); r.appendChild(q);
      const x=el("button","x","×"); x.title=i.reason==="added"?"Take off the list":"Not needed (hidden until it runs low again)"; x.onclick=()=>loadShop({action:"hide",key:i.key}); r.appendChild(x);
    }
    box.appendChild(r);
  }
  $("shShowHidden").hidden=!nHidden; $("shShowHidden").textContent=shopShowHidden?"Hide items you don't need":`Show ${nHidden} hidden item${nHidden>1?"s":""}`;
  const items=shopItems.filter(i=>!i.hidden), priced=items.filter(i=>i.price!=null);
  const n=items.reduce((a,i)=>a+i.qty,0);
  $("shTotal").textContent=items.length?`${n} spool${n===1?"":"s"}`+(priced.length?` · estimated ${money(priced.reduce((a,i)=>a+i.price*i.qty,0))}`+(priced.length<items.length?" (some have no price)":""):""):"";
  ["shCopy","shEmail"].forEach(id=>$(id).disabled=!items.length);
}
$("shopBtn").onclick=()=>{shopShowHidden=false;$("shopSheet").hidden=false;renderShop();loadShop()};
$("shClose").onclick=()=>{$("shopSheet").hidden=true};
$("shopSheet").onclick=e=>{if(e.target===$("shopSheet"))$("shopSheet").hidden=true};
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("shopSheet").hidden)$("shopSheet").hidden=true});
$("shShowHidden").onclick=()=>{shopShowHidden=!shopShowHidden;renderShop()};
$("shAdd").onchange=()=>{const k=$("shAdd").value;if(k)loadShop({action:"add",key:k})};
$("shCopy").onclick=async()=>{
  const text=shopText();
  try{await navigator.clipboard.writeText(text)}
  catch(e){const ta=el("textarea");ta.value=text;document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove()}
  toast("Shopping list copied","var(--ok)");
};
$("shEmail").onclick=async()=>{try{await call("/api/shopping/email",{text:shopText()})}catch(e){alert(e.message)}};

// ---------- editor
let editing=null;
const GRAMS_LIST=Object.entries(GRAMS);
GRAMS_LIST.forEach(([w,g])=>{const b=document.createElement("button");b.textContent=w.replace(/(\d)(k?g)$/,"$1 $2");b.onclick=()=>{const full=+$("eLeft").value===+$("eTotal").value;$("eTotal").value=g;if(full)$("eLeft").value=g;syncRange()};$("eSizes").appendChild(b)});
function syncRange(){const t=Math.max(0,+$("eTotal").value||0);$("eRange").max=t||1000;$("eRange").value=Math.min(+$("eLeft").value||0,t)}
$("eTotal").oninput=syncRange;
$("eLeft").oninput=syncRange;
$("eRange").oninput=e=>{$("eLeft").value=e.target.value};
document.querySelectorAll("#editor [data-f]").forEach(b=>b.onclick=()=>{$("eLeft").value=Math.round((+$("eTotal").value||0)*+b.dataset.f);syncRange()});
function applyWeigh(){
  const out=$("eWeighOut"), gross=$("eGross").value;
  if(gross===""){out.textContent="Put the spool on a scale and type the reading. Remaining = reading − empty spool.";return}
  const tare=+$("eTare").value||0, total=+$("eTotal").value||0, raw=Math.round(+gross-tare);
  const left=Math.max(0,total?Math.min(raw,total):raw);
  $("eLeft").value=left; syncRange();
  out.textContent=`${+gross} − ${tare} = ${left} g left`+(raw<0?" (reading is below the empty-spool weight)":raw>total&&total?" (capped at the spool size)":"");
}
$("eGross").oninput=applyWeigh;
$("eTare").oninput=applyWeigh;
$("eTareDefault").onclick=async()=>{
  try{settings=(await call("/api/inv/settings",{tare_g:$("eTare").value})).settings;$("eWeighOut").textContent=`New spools will assume an empty spool weighs ${settings.tare_g} g.`}
  catch(e){alert(e.message)}
};
function eColor(h){h=(h||"").replace("#","").toUpperCase();if(!/^[0-9A-F]{6}$/.test(h))return;$("eHex").value=h;$("ePicker").value="#"+h}
$("ePicker").oninput=e=>eColor(e.target.value);
$("eHex").oninput=e=>eColor(e.target.value);

function openEditor(existing,fresh){
  const s=existing||fresh; editing={id:existing?existing.id:null,serial:s.serial||"",uids:s.uids||""};
  $("edTitle").textContent=existing?matName(s.material):"Add stock";
  edSub();
  $("eMat").value=MATERIALS[s.material]?s.material:"00001";
  eColor(s.color||"FFFFFF");
  $("eTotal").value=s.total_g??1000; $("eLeft").value=s.remaining_g??s.total_g??1000; syncRange();
  $("eGross").value=""; $("eTare").value=s.tare_g??settings.tare_g; applyWeigh();
  $("eCost").value=s.cost??""; $("eDate").value=s.purchased||""; $("eSource").value=s.source||""; $("eNotes").value=s.notes||"";
  $("eBrand").value=s.brand||(isCreality($("eMat").value)?"Creality":"");
  $("eCName").value=s.color_name||""; $("eNozzle").value=s.nozzle_temp||""; $("eBed").value=s.bed_temp||"";
  $("eSpeed").value=s.print_speed||""; $("eFlow").value=s.flow||""; $("eFillMsg").textContent=""; eFillOffer();
  const bl=$("brands");bl.replaceChildren();[...new Set(["Creality",...spools.map(x=>x.brand).filter(Boolean)])].forEach(v=>{const o=document.createElement("option");o.value=v;bl.appendChild(o)});
  $("eDelete").hidden=!existing;
  // spools added before scanning was required can be linked to their tag here
  $("eScanWrap").hidden=!(existing&&!s.serial&&!s.uids); eScanning=false; $("eScan").textContent="Scan tag to link";
  $("eScanMsg").className="warn"; $("eScanMsg").textContent="This spool isn't linked to a tag. Scan its tag so it's tracked accurately.";
  const dl=$("sources");dl.replaceChildren();[...new Set(spools.map(x=>x.source).filter(Boolean))].forEach(v=>{const o=document.createElement("option");o.value=v;dl.appendChild(o)});
  stockNote();
  $("editor").hidden=false; setTimeout(()=>$(existing?"eLeft":"eCost").focus(),0);
}
function closeEditor(){if(eScanning)call("/api/cancel").catch(()=>{});$("editor").hidden=true;editing=null}
let eScanning=false;
function edSub(){
  const ip=editing.id&&inPrinter[editing.id];
  $("edSub").textContent=[ip&&`In printer · ${ip.slot}`,editing.serial&&"Serial "+editing.serial,editing.uids&&"Tags "+editing.uids.split(" ").join(", ")].filter(Boolean).join(" · ")||"Not linked to a tag";
}
$("eScan").onclick=async()=>{
  const msg=$("eScanMsg");
  if(eScanning){call("/api/cancel").catch(()=>{});return}
  eScanning=true; $("eScan").textContent="Cancel scan"; msg.className="mute"; msg.textContent="Place one of the spool's tags on the reader…";
  try{
    const r=await call("/api/inv/scan"),d=r.data; if(!editing)return;
    if(r.spool&&r.spool.id!==editing.id) throw new Error(`That tag already belongs to another spool (${groupName(r.spool)}). Scan this spool's own tag.`);
    // the tag is the source of truth for what the filament is
    const changed=$("eMat").value!==d.material||$("eHex").value.toUpperCase()!==d.color.replace("#","").toUpperCase();
    if(MATERIALS[d.material]) $("eMat").value=d.material; eColor(d.color);
    editing.serial=d.serial; editing.uids=r.uid; edSub(); stockNote();
    msg.className="ok"; msg.textContent=`Linked to tag ${r.uid} (${d.material_name} ${d.color})${changed?". Type and colour updated from the tag":""}. Save to keep it.`;
  }catch(e){msg.className=e.message==="Cancelled."?"mute":"bad";msg.textContent=e.message==="Cancelled."?"Scan cancelled.":e.message}
  eScanning=false; $("eScan").textContent="Scan tag to link";
};
$("eClose").onclick=closeEditor;
// "Fill in from <brand>": the brand's filament nearest this spool's type and colour
async function eFillOffer(){
  const brand=$("eBrand").value.trim(), db=await filamentDb();
  const known=db.brands.some(b=>b.name.toLowerCase()===brand.toLowerCase());
  $("eFill").hidden=!known; if(known)$("eFill").textContent=`Fill in from ${brand}'s details`;
}
$("eBrand").addEventListener("input",eFillOffer);
$("eFill").onclick=async()=>{
  const f=await closestFilament($("eBrand").value,$("eMat").value,$("eHex").value.replace("#",""));
  if(!f){$("eFillMsg").textContent="No match found for that brand.";return}
  const d=brandDetails($("eBrand").value.trim(),f);
  $("eCName").value=d.color_name; $("eNozzle").value=d.nozzle_temp; $("eBed").value=d.bed_temp;
  if(d.tare_g){$("eTare").value=d.tare_g; applyWeigh()}
  $("eFillMsg").textContent=`From ${d.brand} ${f.m} · ${f.n}`+(f.c.toUpperCase()!==$("eHex").value.replace("#","").toUpperCase()?` (nearest colour, #${f.c})`:"")+". Check it matches the label.";
};
$("editor").onclick=e=>{if(e.target===$("editor"))closeEditor()};
document.addEventListener("keydown",e=>{if(e.key!=="Escape")return; if(!$("editor").hidden)closeEditor(); else if(selecting)setSelecting(false)});
$("eSave").onclick=async()=>{
  const rec={...editing,material:$("eMat").value,color:$("eHex").value,total_g:$("eTotal").value,remaining_g:$("eLeft").value,
    cost:$("eCost").value,tare_g:$("eTare").value,purchased:$("eDate").value,source:$("eSource").value,notes:$("eNotes").value,brand:$("eBrand").value,
    color_name:$("eCName").value,nozzle_temp:$("eNozzle").value,bed_temp:$("eBed").value,print_speed:$("eSpeed").value,flow:$("eFlow").value};
  try{const {spool}=await call("/api/inv/save",rec);closeEditor();
    status(`Saved: ${groupName(spool)}, ${fmtG(spool.remaining_g)} g left.`,"ok","istatus");await loadInv()}
  catch(e){alert(e.message)}
};
$("eDelete").onclick=async()=>{
  const id=editing.id, name=groupName(spools.find(s=>s.id===id)||{material:"",color:""});
  try{await call("/api/inv/delete",{id});closeEditor();
    toast(`Deleted ${name}`,"var(--bad)",{label:"Undo",fn:()=>undoDelete([id])});await loadInv()}
  catch(e){alert(e.message)}
};

