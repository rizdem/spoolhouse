// Spoolhouse - Projects: prints grouped together, with the filaments they used, their print time and cost.
// Prints are added from a printer's print log (printlog.js); a print is in one project at most.
let projects=[], curProject=null;
const kgOrG=g=>g>=1000?`${(g/1000).toFixed(2)} kg`:`${fmtG(g)} g`;
// "Elegoo Red PLA", or "Elegoo PLA" for a colour with no name (its hex code shows beside it)
const named=c=>c&&!colorName(c).startsWith("#");
const filName=f=>`${f.brand?f.brand+" ":""}${named(f.color)?colorName(f.color)+" ":""}${f.material?matName(f.material).replace(/^Generic /,""):"Filament"}`;

async function loadProjects(){
  if(curProject!=null) return openProject(curProject);
  try{projects=(await call("/api/projects/list")).projects}catch(e){projects=[]}
  renderProjects();
}
function renderProjects(){
  $("prjList").hidden=false; $("prjDetail").hidden=true;
  const tb=$("prjTable"); tb.replaceChildren();
  if(!projects.length){tb.appendChild(el("tr")).appendChild(el("td","mute prjempty","No projects yet. Create one, then add prints to it from a printer's print log."));return}
  const h=el("tr");["Project","Prints","Print time","Filament","Cost","Last print"].forEach((x,i)=>h.appendChild(el("th",i>=1&&i<=4?"num":null,x)));tb.appendChild(h);
  for(const p of projects){
    const tr=el("tr","click"); tr.onclick=()=>openProject(p.id);
    const n=el("td"); n.appendChild(el("b",null,p.name)); tr.appendChild(n);
    tr.appendChild(el("td","num",String(p.prints)));
    tr.appendChild(el("td","num",p.prints?fmtDur(p.duration):"—"));
    tr.appendChild(el("td","num",p.grams?kgOrG(p.grams):"—"));
    tr.appendChild(el("td","num",p.cost!=null?money(p.cost)+(p.unpriced_g>0?"+":""):"—"));
    tr.appendChild(el("td","mute",p.last?fmtWhen(p.last):"—"));
    tb.appendChild(tr);
  }
}

async function openProject(id){
  let p; try{p=await call("/api/projects/get",{id})}catch(e){curProject=null;return loadProjects()}
  curProject=id; $("prjList").hidden=true; $("prjDetail").hidden=false; $("prjRenameCard").hidden=true;
  const t=p.totals;
  $("prjName").textContent=p.name;
  $("prjMeta").textContent=`Created ${new Date(p.created*1000).toLocaleDateString([], {day:"numeric",month:"long",year:"numeric"})}`;
  $("prjPrints").textContent=t.prints;
  $("prjPrintsSub").textContent=t.uncharged?`${t.uncharged} not charged to a spool yet`:"";
  $("prjTime").textContent=t.prints?fmtDur(t.duration):"0m";
  $("prjGrams").textContent=kgOrG(t.grams);
  $("prjGramsSub").textContent=t.unassigned_g>0?`${fmtG(t.unassigned_g)} g not assigned to a spool`:"";
  $("prjCost").textContent=t.cost!=null?money(t.cost)+(t.unpriced_g>0?"+":""):"—";
  $("prjCostSub").textContent=t.unpriced_g>0?`plus ${fmtG(t.unpriced_g)} g from spools with no price`:t.cost==null&&t.grams>0?"Add prices to your spools to see costs":"";

  // the filaments used across the whole project, most used first, with a total row
  const fb=$("prjFil"); fb.replaceChildren();
  if(!p.filaments.length){fb.appendChild(el("tr")).appendChild(el("td","mute","No filament charged yet. Charge the prints to their spools in the print log."))}
  else{
    const h=el("tr");["Filament","Prints","Used","Cost"].forEach((x,i)=>h.appendChild(el("th",i?"num":null,x)));fb.appendChild(h);
    for(const f of p.filaments){
      const tr=el("tr"), n=el("td","filcell"); n.append(swatch(f.color),document.createTextNode(filName(f)));
      if(f.color) n.appendChild(el("span","mute",` #${f.color}`)); tr.appendChild(n);
      tr.appendChild(el("td","num",String(f.prints)));
      tr.appendChild(el("td","num",kgOrG(f.grams)));
      const c=el("td","num",f.cost!=null?money(f.cost)+(f.unpriced_g>0?"+":""):"no price");
      if(f.unpriced_g>0) c.title=`${fmtG(f.unpriced_g)} g came from a spool with no price`; if(f.cost==null) c.classList.add("mute");
      tr.appendChild(c); fb.appendChild(tr);
    }
    if(t.unassigned_g>0){const tr=el("tr");const n=el("td","filcell");n.append(swatch(""),el("span","warn","Not assigned to a spool"));
      tr.append(n,el("td","num",""),el("td","num",kgOrG(t.unassigned_g)),el("td","num mute","—"));fb.appendChild(tr)}
    const tot=el("tr","total"); tot.append(el("td",null,"Total"),el("td","num",""),el("td","num",kgOrG(t.grams)),
      el("td","num",t.cost!=null?money(t.cost)+(t.unpriced_g>0?"+":""):"—")); fb.appendChild(tot);
  }

  // its prints, newest first
  const jb=$("prjJobs"); jb.replaceChildren();
  if(!p.prints.length){jb.appendChild(el("tr")).appendChild(el("td","mute","No prints yet. Open a printer's print log, tick the prints for this project and choose Add to project."));return}
  const h=el("tr");["Started","Print","Printer","Time","Filament","Cost",""].forEach((x,i)=>h.appendChild(el("th",i>=3&&i<=5?"num":null,x)));jb.appendChild(h);
  for(const j of p.prints){
    const tr=el("tr");
    tr.appendChild(el("td",null,fmtWhen(j.start)));
    const n=el("td",null,jobName(j)); if(!j.charged) n.appendChild(el("span","warn"," · not charged")); tr.appendChild(n);
    tr.appendChild(el("td","mute",j.printer||""));
    tr.appendChild(el("td","num",fmtDur(j.duration)));
    tr.appendChild(el("td","num",j.grams?`${fmtG(j.grams)} g`:"—"));
    tr.appendChild(el("td","num",j.cost!=null?money(j.cost)+(j.cost_partial?"+":""):"—"));
    const a=el("td","num"), rm=el("button","btn sm","Remove"); rm.title="Take this print out of the project";
    rm.onclick=async()=>{
      if(!confirm(`Remove "${jobName(j)}" from ${p.name}?\n\nThe print and its filament charges are kept; it's just no longer part of this project.`))return;
      try{await call("/api/projects/remove",{job:j.job});openProject(id)}catch(e){alert(e.message)}};
    a.appendChild(rm); tr.appendChild(a); jb.appendChild(tr);
  }
}

$("prjBack").onclick=()=>{curProject=null;loadProjects()};
$("prjNew").onclick=()=>{$("prjNewCard").hidden=false;$("prjNewName").value="";$("prjNewName").focus()};
$("prjNewCancel").onclick=()=>{$("prjNewCard").hidden=true};
async function createProject(){
  try{const {id}=await call("/api/projects/save",{name:$("prjNewName").value});$("prjNewCard").hidden=true;openProject(id)}
  catch(e){alert(e.message)}
}
$("prjNewSave").onclick=createProject;
$("prjNewName").onkeydown=e=>{if(e.key==="Enter")createProject();if(e.key==="Escape")$("prjNewCard").hidden=true};
$("prjRename").onclick=()=>{$("prjRenameCard").hidden=false;$("prjRenameIn").value=$("prjName").textContent;$("prjRenameIn").select()};
$("prjRenameCancel").onclick=()=>{$("prjRenameCard").hidden=true};
async function renameProject(){
  try{await call("/api/projects/save",{id:curProject,name:$("prjRenameIn").value});openProject(curProject)}catch(e){alert(e.message)}
}
$("prjRenameSave").onclick=renameProject;
$("prjRenameIn").onkeydown=e=>{if(e.key==="Enter")renameProject();if(e.key==="Escape")$("prjRenameCard").hidden=true};
$("prjDelete").onclick=async()=>{
  if(!confirm(`Delete the project "${$("prjName").textContent}"?\n\nIts prints and their filament charges are kept; they're just no longer in a project.`))return;
  try{await call("/api/projects/delete",{id:curProject});curProject=null;loadProjects()}catch(e){alert(e.message)}
};
