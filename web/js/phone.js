// Spoolhouse - Settings → Phone access: switch it on, pair a phone with a QR code, remove phones.
const ago=t=>{if(!t)return"never";const s=Date.now()/1000-t;return s<90?"just now":s<3600?`${Math.round(s/60)} min ago`:s<86400?`${Math.round(s/3600)} h ago`:new Date(t*1000).toLocaleDateString()};
let PH=null, phPoll=null;
function showPhone(s){
  PH=s; $("phOn").checked=s.enabled;
  $("phPairRow").hidden=!s.running;
  $("phStatus").textContent=s.error?s.error:s.running?`On · ${s.computer} at ${s.addresses.join(", ")||"this computer"}`:"Off";
  $("phStatus").className=s.error?"warn":"mute";
  const box=$("phPhones"); box.replaceChildren();
  for(const p of s.phones){
    const row=el("div","setrow"), t=el("div");
    t.appendChild(el("div","stt",p.name)); t.appendChild(el("div","mute",`Paired ${new Date(p.created*1000).toLocaleDateString()} · last used ${ago(p.last_seen)}`));
    const b=el("button","btn danger","Remove"); b.onclick=async()=>{
      if(!confirm(`Remove ${p.name}? It won't be able to connect until it's paired again.`))return;
      try{showPhone(await call("/api/phone/remove",{id:p.id}))}catch(e){alert(e.message)}};
    row.append(t,b); box.appendChild(row);
  }
}
async function loadPhone(){try{showPhone(await call("/api/phone/status"))}catch(e){}}
$("phOn").onchange=async e=>{try{showPhone(await call("/api/phone/enable",{on:e.target.checked}))}catch(err){alert(err.message);loadPhone()}};
$("phPair").onclick=async()=>{
  try{
    const r=await call("/api/phone/pair_start"), before=new Set((PH?.phones||[]).map(p=>p.id));
    $("phQr").innerHTML=r.qr_svg; $("phQr").hidden=false; $("phIntro").hidden=false; $("phDone").hidden=true;
    $("phManual").textContent=`Or enter it by hand: ${r.addresses[0]||"this computer"}, code ${r.code}. The code works once, for ${r.minutes} minutes.`;
    $("phoneSheet").hidden=false; $("phClose").focus();
    clearInterval(phPoll);
    phPoll=setInterval(async()=>{  // spot the phone arriving, then say so
      const s=await call("/api/phone/status").catch(()=>null); if(!s)return;
      const fresh=s.phones.find(p=>!before.has(p.id));
      if(fresh){clearInterval(phPoll);showPhone(s);$("phQr").hidden=true;$("phIntro").hidden=true;$("phManual").textContent="";
        $("phDone").hidden=false;$("phDone").textContent=`✓ Paired with ${fresh.name}. It can now see your inventory.`}
    },2000);
  }catch(e){alert(e.message)}
};
function closePhone(){$("phoneSheet").hidden=true;clearInterval(phPoll);loadPhone()}
$("phClose").onclick=closePhone;
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("phoneSheet").hidden)closePhone()});
loadPhone();
