// Spoolhouse - Start-up: background refreshes and opening the first page.
// keep things fresh while the app is open
setInterval(()=>{
  if(!$("view-printer").hidden&&!$("pDetail").hidden&&$("pEditor").hidden) loadPrinter(true,false);
  else loadPrinters();
  if(!$("view-inventory").hidden&&!selecting&&$("editor").hidden) loadInv();
},15000);
loadPrinters();

loadInv();
show(VIEWS.includes(location.hash.slice(1))?location.hash.slice(1):store.get("view","inventory"));
