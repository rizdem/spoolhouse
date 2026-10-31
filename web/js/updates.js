// Spoolhouse - Updates: the "new version available" card, sidebar link and Settings → Updates.
let UPD=null;
const START=Date.now();  // "Later" lasts until the app is next opened
const updWhen=t=>t?new Date(t*1000).toLocaleString([], {day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"}):"";
function showUpdate(s){
  UPD=s; const v=s.latest&&s.latest.version;
  $("updLink").hidden=!s.available;
  // the card shows once per version per run of the app; "Later" hides it until next time
  const card=s.available&&store.get("updLater","")!==v+"|"+START;
  $("updCard").hidden=!card;
  if(card){
    $("updTitle").textContent=`Spoolhouse ${v} is available`;
    const d=s.latest.published?new Date(s.latest.published).toLocaleDateString([], {day:"numeric",month:"long",year:"numeric"}):"";
    $("updText").textContent=`You have ${s.current}.`+(d?` Released ${d}.`:"")+(s.can_install
      ?" Install it now: Spoolhouse downloads it, checks it and restarts. Your data is kept."
      :(IS_WIN?" Download and run the new installer. Your data is kept.":" Download it from GitHub, quit Spoolhouse and replace the app in Applications. Your data is kept."));
    $("updInstall").hidden=!s.can_install;
    $("updGet").textContent=s.can_install?"What's new":"Download";
    $("updGet").classList.toggle("pri",!s.can_install);
    if(s.install&&s.install.stage)showInstall(s.install);
  }
  const st=$("upStatus"); if(!st)return;
  $("upAuto").checked=s.auto;
  if(s.available) st.textContent=`Version ${v} is available.`;
  else if(s.skipped) st.textContent=`You skipped version ${v}. Check now to see it again.`;
  else if(s.problem) st.textContent=s.problem+(s.checked?` (last checked ${updWhen(s.checked)})`:"");
  else st.textContent=s.checked?`You're up to date. Last checked ${updWhen(s.checked)}.`:"Not checked yet.";
}
async function loadUpdates(values){try{showUpdate(await call("/api/update/status",values||{}))}catch(e){}}
$("upAuto").onchange=e=>loadUpdates({auto:e.target.checked});
$("upCheck").onclick=async()=>{
  $("upCheck").disabled=true;
  try{store.set("updLater","");const s=await call("/api/update/check",{unskip:true});showUpdate(s);
    if(!s.available&&!s.problem)toast("You're up to date","var(--ok)")}
  catch(e){alert(e.message)}
  $("upCheck").disabled=false;
};
$("updGet").onclick=()=>call("/api/update/open").catch(()=>{});
// installing: download, check, restart; the card shows how it's going until the app closes
let installTimer=null;
function showInstall(p){
  const busy=["downloading","checking","restarting"].includes(p.stage);
  $("updProg").hidden=!p.stage; $("updBtns").hidden=busy;
  const pct=p.total?Math.min(100,Math.round(p.done/p.total*100)):0;
  $("updBar").style.width=(p.stage==="downloading"?pct:p.stage==="error"?0:100)+"%";
  $("updStage").textContent={downloading:`Downloading… ${pct}%`,checking:"Checking the download…",
    restarting:"Restarting Spoolhouse…",error:p.error||"The update didn't install."}[p.stage]||"";
  if(!busy&&installTimer){clearInterval(installTimer);installTimer=null}
}
$("updInstall").onclick=async()=>{
  try{showInstall(await call("/api/update/install"));
    installTimer=installTimer||setInterval(async()=>{try{showInstall(await call("/api/update/progress"))}catch(e){}},500)}
  catch(e){showInstall({stage:"error",error:e.message})}
};
$("updLater").onclick=()=>{store.set("updLater",UPD.latest.version+"|"+START);$("updCard").hidden=true};
$("updSkip").onclick=async()=>{try{showUpdate(await call("/api/update/skip"))}catch(e){}};
$("updLink").onclick=()=>{store.set("updLater","");showUpdate(UPD)};
loadUpdates(); setInterval(loadUpdates,30*60*1000);
