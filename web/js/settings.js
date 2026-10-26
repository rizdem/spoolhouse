// Spoolhouse - Settings: menu bar/tray and login, notifications, backups and export.
// ---------- settings
async function loadSettings(){
  // the other sections load regardless: only the menu bar/tray options need the desktop app
  loadBackups();
  loadNotify();
  try{
    const s=await call("/api/app/settings");
    $("appNotNative").hidden=s.native; ["setMenubar","setLogin"].forEach(id=>$(id).disabled=!s.native);
    if(s.native){
      $("setMenubar").checked=s.menubar; $("setLogin").checked=s.login; $("setLogin").disabled=!s.login_available;
      if(!s.login_available) $("loginNote").textContent="Available in the built app (not when running from source).";
    }
  }catch(e){}
}
async function saveSetting(values){
  try{await call("/api/app/settings",values)}catch(e){alert(e.message)}
  loadSettings();
}
$("setMenubar").onchange=e=>saveSetting({menubar:e.target.checked});
$("setLogin").onchange=e=>saveSetting({login:e.target.checked});

// ---------- notifications
async function loadNotify(values){
  try{
    const s=await call("/api/notify/settings",values||{});
    $("ntNotNative").hidden=s.available; $("ntTest").disabled=!s.available;
    if(document.activeElement!==$("ntHum")) $("ntHum").value=s.humidity_max; settings.humidity_max=s.humidity_max;
    const box=$("ntKinds"); box.replaceChildren();
    for(const k of s.kinds){
      const row=el("div","setrow"), t=el("div"); t.appendChild(el("div","stt",k.label)); t.appendChild(el("div","mute",k.help)); row.appendChild(t);
      const sw=el("label","switch"), cb=el("input"); cb.type="checkbox"; cb.checked=k.on; cb.disabled=!s.available;
      cb.onchange=()=>loadNotify({[k.kind]:cb.checked}); sw.append(cb,el("span")); row.appendChild(sw); box.appendChild(row);
    }
  }catch(e){}
}
$("ntHum").onchange=()=>{const v=Math.max(20,Math.min(90,+$("ntHum").value||50));$("ntHum").value=v;loadNotify({humidity_max:v})};
$("ntTest").onclick=async()=>{try{await call("/api/notify/test");toast("Test notification sent","var(--ok)")}catch(e){alert(e.message)}};

// ---------- backups
["bkFreq","bkKeep"].forEach(id=>makePicker($(id),{search:false}));
const when=t=>t?new Date(t*1000).toLocaleString([], {weekday:"short",day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"}):"";
async function loadBackups(){
  try{
    const s=await call("/api/backup/status");
    $("bkDir").textContent=s.backup_dir||"Not set"; $("bkDb").textContent=s.db_path;
    $("bkFreq").value=s.backup_freq; $("bkKeep").value=String(s.backup_keep);
    ["bkChoose","bkRestore"].forEach(id=>{$(id).disabled=!s.native;$(id).title=s.native?"":"Available in the app, not in a browser"});
    $("bkRunNow").disabled=!s.backup_dir;
    const st=$("bkStatus");
    if(s.backup_error){st.className="warn";st.textContent=`${s.backup_error} Last tried ${when(s.backup_tried)}; it will try again within ${Math.round(s.check_secs/60)} minutes.`+(s.backup_last?` Last good backup: ${when(s.backup_last)}.`:"")}
    else if(!s.backup_dir){st.className="mute";st.textContent="Choose a folder to turn on automatic backups."}
    else if(s.backup_freq==="off"){st.className="mute";st.textContent="Automatic backups are off."+(s.backup_last?` Last backup: ${when(s.backup_last)}.`:"")}
    else{st.className="mute";st.textContent=(s.backup_last?`Last backup: ${when(s.backup_last)}. `:"No backup yet. ")+`Next: ${s.next_due&&s.next_due>Date.now()/1000?when(s.next_due):"within a few minutes"}.`}
  }catch(e){}
}
async function bkSet(values){try{await call("/api/backup/settings",values)}catch(e){alert(e.message)} loadBackups()}
$("bkFreq").onchange=e=>bkSet({backup_freq:e.target.value});
$("bkKeep").onchange=e=>bkSet({backup_keep:+e.target.value});
$("bkChoose").onclick=async()=>{try{await call("/api/backup/choose_dir")}catch(e){alert(e.message)} loadBackups()};
$("bkRunNow").onclick=async()=>{$("bkRunNow").disabled=true;
  try{const r=await call("/api/backup/run_now");toast("Backed up to "+r.path.split("/").slice(-2).join("/"),"var(--ok)")}catch(e){alert(e.message)}
  loadBackups()};
$("bkSave").onclick=async()=>{try{const r=await call("/api/backup/save");if(r.path)toast("Backup saved: "+r.path.split("/").pop(),"var(--ok)")}catch(e){alert(e.message)}};
$("bkRestore").onclick=async()=>{
  try{
    const p=await call("/api/backup/pick_restore"); if(p.cancelled)return;
    if(!confirm(`Restore "${p.name}"?\n\nIt has ${p.spools} spool${p.spools===1?"":"s"} and was saved ${when(p.modified)}. This replaces everything you have now. A copy of your current data is saved first.`))return;
    await call("/api/backup/restore",{path:p.path}); toast("Backup restored","var(--ok)");
    await loadInv(); loadPrinters(); loadBackups();
  }catch(e){alert(e.message)}
};
async function exportCsv(kind){
  try{
    const r=await call("/api/export",{kind}); if(r.cancelled)return;
    if(r.csv){const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["\ufeff"+r.csv],{type:"text/csv"}));a.download=r.name;a.click();return}
    toast("Exported: "+r.path.split("/").pop(),"var(--ok)");
  }catch(e){alert(e.message)}
}
$("exSpools").onclick=()=>exportCsv("spools");
$("exUsage").onclick=()=>exportCsv("usage");

