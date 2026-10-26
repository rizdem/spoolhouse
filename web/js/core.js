// Spoolhouse - Shared state and helpers, the filament pickers, page switching and the NFC reader status.
// filled in by the server (see cfs_gui.page): materials, weights, grams per weight, support link on/off
const {materials:MATERIALS, weights:WEIGHTS, grams:GRAMS, support:HAS_SUPPORT}=window.CFS_CONFIG;
const COLORS=[["FFFFFF","White"],["000000","Black"],["808080","Grey"],["C0C0C0","Silver"],["FF0000","Red"],["C12E1F","Dark red"],["FF6B35","Orange"],["FFD700","Yellow"],["00A651","Green"],["006400","Dark green"],["0047AB","Blue"],["87CEEB","Sky blue"],
["800080","Purple"],["FF69B4","Pink"],["8B4513","Brown"],["F5DEB3","Beige"],["D4AF37","Gold"],["B87333","Copper"],["40E0D0","Turquoise"],["000080","Navy"],["E6E6FA","Lavender"],["FFFDD0","Cream"],["7FFF00","Lime"],["F0F8FF","Clear/natural"]];
const $=id=>document.getElementById(id);
// create an element with an optional class and text (used everywhere)
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
const store={get(k,d){try{return JSON.parse(localStorage.getItem(k))??d}catch(e){return d}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};
const region=(navigator.language||"en-GB").split("-")[1]||"GB";
const CUR={GB:"GBP",US:"USD",AU:"AUD",NZ:"NZD",CA:"CAD",IE:"EUR",DE:"EUR",FR:"EUR",ES:"EUR",IT:"EUR",NL:"EUR"}[region]||"GBP";
const fmtG=x=>{x=+x||0;return Math.abs(x)<10&&Math.round(x)!==x?x.toFixed(1):String(Math.round(x))};
const money=x=>x==null?"—":new Intl.NumberFormat(undefined,{style:"currency",currency:CUR}).format(x);
const colorName=h=>{const c=COLORS.find(x=>x[0]===h);return c?c[1]:"#"+h};
const matName=id=>MATERIALS[id]||id||"Unknown";
const today=()=>new Date().toISOString().slice(0,10);
let weight="1kg";

// ---------- shared
// Creality's own filaments first, then Generic; A-Z within each
const MAT_GROUPS=[["Creality",[]],["Generic",[]]];
for(const [id,n] of Object.entries(MATERIALS)) MAT_GROUPS[n.startsWith("Generic")?1:0][1].push([id,n.replace(/^(Generic|Creality) /,"")]);
MAT_GROUPS.forEach(([,list])=>list.sort((a,b)=>a[1].localeCompare(b[1],undefined,{numeric:true})));
document.querySelectorAll(".matsel").forEach(sel=>{
  for(const [g,list] of MAT_GROUPS){const og=document.createElement("optgroup");og.label=g;
    list.forEach(([id,n])=>{const o=document.createElement("option");o.value=id;o.textContent=n;og.appendChild(o)});sel.appendChild(og)}
  makePicker(sel,{search:true,placeholder:"Search filament, e.g. hyper pla, petg, cf…"});
});
["printer","count"].forEach(id=>makePicker($(id),{search:false}));

function makePicker(sel,{search=false,placeholder="Search…"}={}){
  // a styled picker in front of the real <select>, which stays the source of truth.
  // Options and groups come from the select itself; groups show as headings and as a badge.
  const wrap=document.createElement("div"); wrap.className="combo"; sel.parentNode.insertBefore(wrap,sel); wrap.appendChild(sel);
  const btn=el("button","combo-btn"); btn.type="button"; if(sel.id){btn.id=sel.id+"Btn"; const lab=document.querySelector(`label[for="${sel.id}"]`); if(lab) lab.htmlFor=btn.id}
  wrap.appendChild(btn);
  const groups=()=>{const out=[];for(const c of sel.children){
    if(c.tagName==="OPTGROUP") out.push([c.label,[...c.children].map(o=>[o.value,o.textContent])]);
    else{if(!out.length||out[out.length-1][0]!==null) out.push([null,[]]); out[out.length-1][1].push([c.value,c.textContent])}}
    return out};
  let pop=null, active=0, shown=[];
  const label=()=>{const o=sel.selectedOptions[0], grp=o&&o.parentElement.tagName==="OPTGROUP"?o.parentElement.label:null;
    btn.replaceChildren(el("span","nm",o?o.textContent:"Choose…")); if(grp) btn.appendChild(el("span","grp",grp))};
  // keep the button in step when code sets sel.value
  const desc=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,"value");
  Object.defineProperty(sel,"value",{get(){return desc.get.call(sel)},set(v){desc.set.call(sel,v);label()}});
  const choose=v=>{sel.value=v;sel.dispatchEvent(new Event("change",{bubbles:true}));close();btn.focus()};
  const hl=(text,q)=>{const s=el("span"), w=(q.split(/\s+/)[0]||""), i=w?text.toLowerCase().indexOf(w):-1;
    if(i<0){s.textContent=text;return s} const m=document.createElement("mark"); m.textContent=text.slice(i,i+w.length);
    s.append(text.slice(0,i),m,text.slice(i+w.length)); return s};
  function renderList(){
    const inp=pop.querySelector("input"), q=inp?inp.value.trim().toLowerCase():"", words=q.split(/\s+/).filter(Boolean), list=pop.querySelector(".combo-list");
    list.replaceChildren(); shown=[];
    for(const [g,items] of groups()){
      const hits=items.filter(([v,n])=>{const hay=`${g||""} ${n} ${v}`.toLowerCase();return words.every(w=>hay.includes(w))});
      if(!hits.length)continue; if(g) list.appendChild(el("div","combo-h",g));
      for(const [v,n] of hits){const o=el("div","combo-opt"+(v===sel.value?" sel":"")); o.dataset.v=v; o.appendChild(hl(n,q));
        o.onmousedown=e=>{e.preventDefault();choose(v)}; o.onmousemove=()=>{active=shown.indexOf(o);paint()}; shown.push(o); list.appendChild(o)}
    }
    if(!shown.length) list.appendChild(el("div","combo-empty",'No matches. Try a shorter search, e.g. "PLA".'));
    active=q?0:Math.max(0,shown.findIndex(o=>o.dataset.v===sel.value)); paint();
  }
  function paint(){shown.forEach((o,i)=>o.classList.toggle("active",i===active)); const a=shown[active]; if(a) a.scrollIntoView({block:"nearest"})}
  function keys(e){
    if(e.key==="ArrowDown"){e.preventDefault();active=Math.min(shown.length-1,active+1);paint()}
    else if(e.key==="ArrowUp"){e.preventDefault();active=Math.max(0,active-1);paint()}
    else if(e.key==="Enter"||(!search&&e.key===" ")){e.preventDefault();if(shown[active])choose(shown[active].dataset.v)}
    else if(e.key==="Escape"){e.preventDefault();e.stopPropagation();close();btn.focus()}
    else if(e.key==="Tab") close();
  }
  function open(){
    if(pop)return; pop=el("div","combo-pop"+(search?"":" plain"));
    if(search){const inp=el("input"); inp.type="search"; inp.placeholder=placeholder; inp.autocomplete="off"; inp.oninput=renderList; inp.onkeydown=keys; pop.appendChild(inp)}
    pop.appendChild(el("div","combo-list")); wrap.appendChild(pop); renderList();
    (pop.querySelector("input")||btn).focus();
    setTimeout(()=>document.addEventListener("mousedown",outside),0);
  }
  function close(){if(!pop)return; pop.remove(); pop=null; document.removeEventListener("mousedown",outside)}
  function outside(e){if(!wrap.contains(e.target))close()}
  btn.onclick=()=>pop?close():open();
  btn.onkeydown=e=>{
    if(pop&&!search){keys(e);return}   // no search box: the button itself drives the list
    if(e.key==="ArrowDown"||e.key==="Enter"||e.key===" "){e.preventDefault();open()}
    else if(search&&/^[a-z0-9]$/i.test(e.key)){open();const i=pop.querySelector("input");i.value=e.key;renderList()}
  };
  label();
}
function status(msg,cls="mute",id="status"){const el=$(id);el.hidden=false;el.className="status "+cls;el.textContent=msg}
async function call(path,body={}){
  const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-CFS":"1"},body:JSON.stringify(body)});
  const j=await r.json(); if(j.error) throw new Error(j.error); return j;
}
let cancelled=false;
function busy(on){["write","read","fmt","scan"].forEach(i=>$(i).disabled=on);document.querySelectorAll(".cancel").forEach(b=>b.hidden=!on);if(on)cancelled=false}
document.querySelectorAll(".cancel").forEach(b=>b.onclick=()=>{cancelled=true;call("/api/cancel").catch(()=>{})});
const fail=(e,id)=>e.message==="Cancelled."?status("Cancelled.","mute",id):status(e.message,"bad",id);

const VIEWS=["inventory","printer","create","settings"];
function show(v){
  document.querySelectorAll("nav button[data-view]").forEach(b=>b.classList.toggle("on",b.dataset.view===v));
  for(const name of VIEWS) $("view-"+name).hidden=v!==name;
  store.set("view",v); if(v==="inventory") loadInv(); else if(selecting) setSelecting(false);
  if(v==="printer") enterPrinters();
  if(v==="settings") loadSettings();
}
document.querySelectorAll("nav button[data-view]").forEach(b=>b.onclick=()=>show(b.dataset.view));

$("support").hidden=!HAS_SUPPORT;
$("support").onclick=()=>call("/api/support").catch(()=>{});
// ---------- reader status: follows plugging the NFC reader in and out
let readerState=null, readerBusy=false;
function toast(msg,color,action){
  document.querySelectorAll(".toast").forEach(t=>t.remove());
  const t=el("div","toast"), d=el("span","rdot"); d.style.background=color; t.append(d,document.createTextNode(msg));
  if(action){const b=el("button","toastbtn",action.label); b.onclick=()=>{t.remove();action.fn()}; t.appendChild(b)}
  document.body.appendChild(t); setTimeout(()=>t.remove(),action?9000:3500);
}
async function undoDelete(ids){
  try{await call("/api/inv/restore",{ids});toast(`Restored ${ids.length} spool${ids.length===1?"":"s"}`,"var(--ok)");await loadInv()}catch(e){alert(e.message)}
}
function showReader(s){
  const state=s.ok?"on":s.stuck?"stuck":"off", box=$("reader");
  box.className="reader "+state;
  box.querySelector(".rt").textContent=s.ok?"Reader connected":s.stuck?"Reader not responding":"No reader";
  box.querySelector(".rn").textContent=s.ok?s.reader.replace(/\s+PICC Interface$/i,""):s.stuck?"Unplug it and plug it back in.":"Plug in your NFC reader. Quit NFC Agent if it's running.";
  if(readerState&&readerState!==state){
    if(state==="on") toast("NFC reader connected","var(--ok)");
    else if(state==="off") toast("NFC reader unplugged","var(--bad)");
    else toast("NFC reader isn't responding: unplug it and plug it back in","#d97706");
  }
  readerState=state;
}
async function checkReader(){
  if(readerBusy||document.visibilityState==="hidden")return;
  readerBusy=true;
  try{showReader(await call("/api/status"))}catch(e){}
  readerBusy=false;
}
checkReader(); setInterval(checkReader,2500);
document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible")checkReader()});

