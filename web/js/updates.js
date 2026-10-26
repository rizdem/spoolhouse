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
    $("updText").textContent=`You have ${s.current}.`+(d?` Released ${d}.`:"")+(IS_WIN?" Download and run the new installer. Your data is kept.":" Download it from GitHub, quit Spoolhouse and replace the app in Applications. Your data is kept.");
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
$("updLater").onclick=()=>{store.set("updLater",UPD.latest.version+"|"+START);$("updCard").hidden=true};
$("updSkip").onclick=async()=>{try{showUpdate(await call("/api/update/skip"))}catch(e){}};
$("updLink").onclick=()=>{store.set("updLater","");showUpdate(UPD)};
loadUpdates(); setInterval(loadUpdates,30*60*1000);
