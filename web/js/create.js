// Spoolhouse - Create: writing, reading and wiping tags.
// ---------- create
{const s=store.get("cfs",{}); $("mat").value=s.mat&&MATERIALS[s.mat]?s.mat:"01001";  // default: Hyper PLA
 if(s.w)weight=s.w; if(s.hex)setTimeout(()=>setColor(s.hex),0);}
COLORS.forEach(([h,n])=>{const d=document.createElement("div");d.className="sw";d.style.background="#"+h;d.title=n;d.dataset.hex=h;d.onclick=()=>setColor(h);$("sw").appendChild(d)});
WEIGHTS.forEach(w=>{const b=document.createElement("button");b.textContent=w.replace(/(\d)(k?g)$/,"$1 $2");b.dataset.w=w;b.onclick=()=>{weight=w;render()};$("wt").appendChild(b)});
function setColor(h,fromBrand){h=h.replace("#","").toUpperCase();if(!/^[0-9A-F]{6}$/.test(h))return;$("hex").value=h;$("picker").value="#"+h;
  // a colour chosen by hand isn't the brand's colour any more: its name and details no longer apply
  if(!fromBrand&&typeof brandPick!=="undefined"&&brandPick){brandPick=null;$("bInfo").hidden=true;document.querySelectorAll(".bcol").forEach(x=>x.classList.remove("sel"))}
  render()}
$("picker").oninput=e=>setColor(e.target.value);
$("hex").oninput=e=>setColor(e.target.value);
$("mat").onchange=render;
function render(){
  const h=$("hex").value.toUpperCase();
  document.querySelectorAll(".sw").forEach(s=>s.classList.toggle("sel",s.dataset.hex===h));
  document.querySelectorAll("#wt button").forEach(b=>b.classList.toggle("on",b.dataset.w===weight));
  const c=COLORS.find(x=>x[0]===h);$("cname").textContent=c?c[1]:"";
  $("spool").style.background="#"+h;
  $("sumMat").textContent=MATERIALS[$("mat").value];
  $("sumRest").textContent="#"+h+" · "+weight;
  store.set("cfs",{mat:$("mat").value,hex:h,w:weight});
}
render();

let lastWritten=null;
$("write").onclick=async()=>{
  busy(true);$("addInv").hidden=true;
  try{
    const n=+$("count").value, {serial}=await call("/api/serial");
    const body={material:$("mat").value,color:$("hex").value,weight,printer:$("printer").value,serial};
    let prev=null, uids=[];
    for(let i=1;i<=n;i++){
      status(`Place tag ${i} of ${n} on the reader…`);
      if(cancelled) throw new Error("Cancelled.");
      const r=await call("/api/write",{...body,exclude_uid:prev});
      prev=r.uid; uids.push(r.uid);
      if(i<n) status(`Tag ${i} written (${r.uid}). Remove it and place tag ${i+1}…`,"ok");
      await new Promise(res=>setTimeout(res,800));
    }
    status(`Done. ${n} tag${n>1?"s":""} written and verified: ${MATERIALS[body.material]}, #${body.color}, ${weight}, serial ${serial}.`,"ok");
    lastWritten={...body,uids:uids.join(" "),...(brandPick?{...brandPick,print_speed:$("bSpeed").value.trim(),flow:$("bFlow").value.trim()}:{})}; $("addInv").hidden=false;
  }catch(e){fail(e)}
  busy(false);
};
$("addInv").onclick=()=>{
  const w=lastWritten; $("addInv").hidden=true; show("inventory");
  openEditor(null,{serial:w.serial,material:w.material,color:w.color,total_g:GRAMS[w.weight],remaining_g:GRAMS[w.weight],uids:w.uids,purchased:today(),
    brand:w.brand,color_name:w.color_name,nozzle_temp:w.nozzle_temp,bed_temp:w.bed_temp,print_speed:w.print_speed,flow:w.flow,tare_g:w.tare_g});
};
$("read").onclick=async()=>{
  busy(true);status("Place the tag on the reader…");
  try{const r=await call("/api/read"),d=r.data;
    status(`${r.uid}: ${d.material_name} · ${d.color} · ${d.weight} · serial ${d.serial}`,"ok");
    if(MATERIALS[d.material]){$("mat").value=d.material;} setColor(d.color); if(WEIGHTS.includes(d.weight)){weight=d.weight;} render();
  }catch(e){fail(e)}
  busy(false);
};
$("fmt").onclick=async()=>{
  if(!confirm("Wipe the next tag placed on the reader back to blank?"))return;
  busy(true);status("Place the tag to wipe on the reader…");
  try{const r=await call("/api/format");status(`Wiped ${r.uid}. It's blank and reusable.`,"ok")}catch(e){fail(e)}
  busy(false);
};

