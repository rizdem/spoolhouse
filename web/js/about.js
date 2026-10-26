// Spoolhouse - About box: version, links, credits and the Buy Me a Coffee button.
function openAbout(){$("aboutSheet").hidden=false;$("abClose").focus()}
$("aboutLink").onclick=openAbout;
$("aboutBtn").onclick=openAbout;
$("abClose").onclick=()=>{$("aboutSheet").hidden=true};
$("abSupport").onclick=()=>call("/api/support").catch(()=>{});
$("abSupport").hidden=!HAS_SUPPORT;
document.querySelectorAll("#aboutSheet [data-link]").forEach(b=>b.onclick=()=>call("/api/open",{link:b.dataset.link}).catch(()=>{}));
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("aboutSheet").hidden)$("aboutSheet").hidden=true});
