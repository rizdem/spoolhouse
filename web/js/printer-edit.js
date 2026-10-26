// Spoolhouse - Adding, editing and removing printers.
// ---------- add / edit printer
function openPrinterEditor(p){
  editingPrinter=p;
  $("peTitle").textContent=p?"Edit printer":"Add printer";
  const ms=$("peModel"); ms.replaceChildren(); (models.length?models:["K2","K2 Pro","K2 Plus","Hi","K1","K1C","K1 Max","K1 SE","Other"]).forEach(m=>ms.appendChild(new Option(m,m)));
  $("peName").value=p?p.name:""; ms.value=p&&p.model?p.model:"K2 Pro"; $("peHost").value=p?p.host:"";
  $("peTestOut").textContent=""; $("peTestOut").className="ptest"; $("peDelete").hidden=!p;
  $("pEditor").hidden=false; setTimeout(()=>$(p?"peName":"peName").focus(),0);
}
function closePrinterEditor(){$("pEditor").hidden=true;editingPrinter=null}
$("pAdd").onclick=()=>openPrinterEditor(null);
$("pEdit").onclick=()=>openPrinterEditor(printers.find(x=>x.id===curPrinter)||(pState&&{id:pState.id,name:pState.name,model:pState.model,host:pState.host}));
$("peCancel").onclick=closePrinterEditor;
$("pEditor").onclick=e=>{if(e.target===$("pEditor"))closePrinterEditor()};
$("peTest").onclick=async()=>{
  const out=$("peTestOut"); out.className="ptest mute"; out.textContent="Connecting…"; $("peTest").disabled=true;
  try{const r=await call("/api/printers/test",{host:$("peHost").value.trim()});
    out.className="ptest ok";
    out.textContent=(r.cfs?`Connected. CFS found with ${r.loaded} spool${r.loaded===1?"":"s"} loaded.`:"Connected. No CFS found: you can link the spool on the holder.")
      +(r.moonraker?" Usage tracking available.":" Usage tracking isn't available on this printer (Moonraker not reachable).");}
  catch(e){out.className="ptest bad";out.textContent=e.message}
  $("peTest").disabled=false;
};
$("peSave").onclick=async()=>{
  const rec={id:editingPrinter?editingPrinter.id:null,name:$("peName").value.trim(),model:$("peModel").value,host:$("peHost").value.trim()};
  try{const {printer}=await call("/api/printers/save",rec); const wasNew=!editingPrinter; closePrinterEditor(); await loadPrinters();
    if(wasNew||curPrinter===printer.id) openPrinter(printer.id);}
  catch(e){$("peTestOut").className="ptest bad";$("peTestOut").textContent=e.message}
};
$("peDelete").onclick=async()=>{
  if(!editingPrinter||!confirm(`Remove "${editingPrinter.name}"?\n\nIts slot links are removed. Spools and the filament already deducted are kept.`))return;
  try{await call("/api/printers/delete",{id:editingPrinter.id});closePrinterEditor();await loadInv();showPrinterList()}catch(e){alert(e.message)}
};
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("pEditor").hidden)closePrinterEditor()});
$("peHost").addEventListener("keydown",e=>{if(e.key==="Enter")$("peSave").click()});

