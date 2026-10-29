// Spoolhouse - brands: filament makers' colours, temperatures and empty spool weights (filaments.json, from
// SpoolmanDB, MIT licence), for picking a brand when writing tags and for filling in a spool's details.
// The tag itself only has room for a Creality material code, colour, length and serial, so a brand's
// filament is written as the matching Generic type; the rest is kept with the spool in the inventory.
let FILAMENT_DB=null;
async function filamentDb(){
  if(!FILAMENT_DB){try{FILAMENT_DB=await (await fetch("filaments.json")).json()}catch(e){FILAMENT_DB={brands:[]}}}
  return FILAMENT_DB;
}
// a brand's material name ("PLA+", "HTPLA+", "ABS+MATTE", "EASYASA"...) -> the nearest Generic CFS material
const CFS_RULES=[["PLA-CF","00006"],["PETG-CF","00014"],["PETG-GF","00027"],["PETG","00003"],["HTPET","00003"],
  ["PET-CF","00013"],["PCTG","00032"],["PET","00020"],["ASA-CF","00033"],["EASYASA","00007"],["ASA","00007"],
  ["ABS","00004"],["TPU-64D","00026"],["TPU","00005"],["TPE","00005"],["PA6-CF","00015"],["PAHT-CF","00016"],
  ["PA12-CF","00009"],["PA-CF","00009"],["PA","00008"],["PC","00021"],["PVA","00011"],["BVOH","00010"],
  ["HIPS","00012"],["PPS-CF","00018"],["PPS","00017"],["PP","00019"],["HTPLA","00001"],["PLA","00001"],
  ["WOOD","00001"],["GREENTEC","00001"],["BIOFUSION","00001"],["PVB","00001"]];
function cfsCode(material){
  const m=(material||"").toUpperCase().replace(/\s+/g,"");
  if(m.includes("SILK"))return "00002";
  const r=CFS_RULES.find(([p])=>m.startsWith(p));
  return r?r[1]:null;
}
// net weight -> the nearest spool size a tag can say
function weightKey(g){
  const sizes=[[1000,"1kg"],[750,"750g"],[600,"600g"],[500,"500g"],[250,"250g"]];
  g=+g||1000; return sizes.reduce((a,b)=>Math.abs(b[0]-g)<Math.abs(a[0]-g)?b:a)[1];
}
// "210" (or the middle of the range when there's no single figure), and "190-220" for the range
const tempOf=(t,r)=>t?String(Math.round(t)):(r?String(Math.round((r[0]+r[1])/2)):"");
const rangeOf=(t,r)=>r?`${r[0]}-${r[1]}`:(t?String(Math.round(t)):"");
// what a brand's filament fills in on a spool
function brandDetails(brand,f){
  return {brand, color_name:f.n||"", nozzle_temp:rangeOf(f.t,f.tr), bed_temp:rangeOf(f.b,f.br),
          tare_g:f.sw||null, material:cfsCode(f.m), color:f.c, weight:weightKey(f.w)};
}
function hexDist(a,b){
  const p=h=>[0,2,4].map(i=>parseInt(h.slice(i,i+2),16)); try{const x=p(a),y=p(b);return Math.hypot(x[0]-y[0],x[1]-y[1],x[2]-y[2])}catch(e){return 999}
}
// the brand's filament most like a spool (same Generic type, nearest colour), for "Fill in from <brand>"
async function closestFilament(brand,material,color){
  const b=(await filamentDb()).brands.find(x=>x.name.toLowerCase()===(brand||"").trim().toLowerCase());
  if(!b)return null;
  const same=b.filaments.filter(f=>cfsCode(f.m)===material);
  const pool=same.length?same:b.filaments;
  return pool.reduce((best,f)=>!best||hexDist(f.c,color)<hexDist(best.c,color)?f:best,null);
}

// ---------- Create: brand → material → colour
let brandPick=null;  // what the chosen brand filament adds to the spool (cleared when you change things by hand)
(async()=>{
  const db=await filamentDb(), list=$("brandList");
  db.brands.forEach(b=>{const o=document.createElement("option");o.value=b.name;list.appendChild(o)});
  $("brandSrc").textContent=db.brands.length?`${db.brands.length} brands, from SpoolmanDB (${db.fetched}).`:"";
})();
async function brandChosen(){
  const db=await filamentDb(), b=db.brands.find(x=>x.name.toLowerCase()===$("brandIn").value.trim().toLowerCase());
  $("bMatWrap").hidden=!b; $("bCols").replaceChildren(); $("bInfo").hidden=true; $("bColQ").value="";
  if(!b){brandPick=null;return}
  const mats=[...new Set(b.filaments.map(f=>f.m))].sort((x,y)=>x==="PLA"?-1:y==="PLA"?1:x.localeCompare(y));
  $("bMat").replaceChildren(...mats.map(m=>{const o=document.createElement("option");o.value=m;o.textContent=m+(cfsCode(m)?"":" (pick the closest type below)");return o}));
  materialChosen();
}
// "brick", "matte blue": every word somewhere in the colour's name (or its material)
function colourMatches(f,q){
  const hay=(f.n+" "+f.m).toLowerCase();
  return q.toLowerCase().split(/\s+/).filter(Boolean).every(w=>hay.includes(w));
}
function materialChosen(){
  const b=FILAMENT_DB.brands.find(x=>x.name.toLowerCase()===$("brandIn").value.trim().toLowerCase()); if(!b)return;
  const q=$("bColQ").value.trim();
  // searching looks through all the brand's materials, so "brick" finds it whichever material it's under
  const fs=q?b.filaments.filter(f=>colourMatches(f,q)):b.filaments.filter(f=>f.m===$("bMat").value);
  $("bMat").disabled=!!q;
  const esc=t=>t.replace(/[<>&]/g,"");
  $("bCols").replaceChildren(...(fs.length?fs.map(f=>{
    const d=document.createElement("button");d.className="bcol";d.type="button";d.title=`${f.m} · ${f.n}`;
    d.innerHTML=`<span class="sw" style="background:#${f.c}"></span><span>${esc(f.n)}</span>`+(q?`<span class="bmat">${esc(f.m)}</span>`:"");
    d.onclick=()=>pickFilament(b.name,f,d); return d}):[Object.assign(document.createElement("span"),{className:"mute",textContent:`No ${b.name} colour matches "${q}".`})]));
}
function pickFilament(brand,f,el){
  document.querySelectorAll(".bcol").forEach(x=>x.classList.toggle("sel",x===el));
  const d=brandDetails(brand,f);
  if(d.material&&MATERIALS[d.material])$("mat").value=d.material;
  weight=d.weight; setColor(d.color,true);
  brandPick={brand:d.brand,color_name:d.color_name,nozzle_temp:d.nozzle_temp,bed_temp:d.bed_temp,tare_g:d.tare_g};
  const bits=[d.nozzle_temp&&`Nozzle ${d.nozzle_temp} °C`,d.bed_temp&&`Bed ${d.bed_temp} °C`,d.tare_g&&`Empty spool ${d.tare_g} g`].filter(Boolean);
  $("bInfoTxt").innerHTML=`<b>${brand} ${f.m} · ${f.n}</b><br>${bits.join(" · ")||"No temperatures listed for this one."}`+
    `<br><span class="mute">Written as ${MATERIALS[$("mat").value]} (the tag has no room for brands); the details go with the spool in your inventory.</span>`;
  $("bInfo").hidden=false; render();
}
$("brandIn").onchange=brandChosen; $("brandIn").oninput=()=>{if(!$("brandIn").value)brandChosen()};
$("bMat").onchange=materialChosen;
$("bColQ").oninput=materialChosen;
$("brandClear").onclick=()=>{$("brandIn").value="";brandChosen()};
