"use strict";
const $ = id => document.getElementById(id);
const localVoice = "echon-narrator", defaultVoice = "en-US-ChristopherNeural";
const uniqueId = () => Array.from(crypto.getRandomValues(new Uint32Array(4)), n=>n.toString(16).padStart(8,"0")).join("");
const draftKey = "tts-studio-project-v1";
const fresh = () => ({version:1, name:"Untitled session", offline:false, lines:[], rules:[], gains:{}, job:"Ready"});
let project = fresh(), stopping = false, busy = false;
try { project = JSON.parse(localStorage.getItem(draftKey)) || project; } catch { /* A portable file can restore a draft. */ }

// IndexedDB keeps long sessions beyond the browser's localStorage quota.
const database = new Promise((resolve, reject) => {
  const req = indexedDB.open("tts-studio-drafts", 1);
  req.onupgradeneeded = () => req.result.createObjectStore("sessions");
  req.onsuccess = () => resolve(req.result);
  req.onerror = () => reject(req.error);
});
function status(text) { $("status").textContent = text; }
function persist() {
  const saved = structuredClone(project);
  return database.then(db => new Promise((resolve,reject) => {
    const tx=db.transaction("sessions","readwrite");
    tx.objectStore("sessions").put(saved,"current");
    tx.oncomplete=resolve; tx.onerror=()=>reject(tx.error); tx.onabort=()=>reject(tx.error);
  })).catch(() => {
    try { localStorage.setItem(draftKey,JSON.stringify(saved)); }
    catch { status("Draft storage is full. Save a portable project to keep these edits."); }
  });
}
function el(tag, text, parent) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (parent) parent.append(item);
  return item;
}
function controls(parent, className="actions") {
  const box = el("div", undefined, parent);
  box.className = className;
  return box;
}
function button(parent, label, action) {
  const b = el("button", label, parent);
  b.type = "button";
  b.onclick = () => Promise.resolve().then(action).catch(e => status(e.message));
  return b;
}
function field(parent, label, value, change, type="text") {
  const wrap = el("label", label, parent);
  const input = el(type === "textarea" ? "textarea" : "input", undefined, wrap);
  if (type !== "textarea") input.type = type;
  if (type === "number") input.step = "any";
  input.value = value ?? "";
  input.oninput = () => { change(input.value); persist(); invalidateMix(); };
  return input;
}
function invalidateMix() {
  $("exports").replaceChildren();
  $("meter").textContent = "";
  if (!$("player").hidden) { $("player").pause(); $("player").hidden = true; }
}
async function api(route, data, binary=false) {
  const options = data === undefined ? {} : {method:"POST", headers:{"Content-Type":binary ? "application/octet-stream" : "application/json"}, body:binary ? data : JSON.stringify(data)};
  const r = await fetch(route, options);
  const result = await r.json();
  if (!r.ok || result.error) {
    const error = new Error(result.error || r.statusText);
    error.retry = r.status >= 500;
    throw error;
  }
  return result;
}
function snapshot(line) {
  const locale = line.voice.startsWith("echon") ? "en-us" : line.voice.split("-").slice(0,2).join("-").toLowerCase();
  const rules = project.rules.filter(r => r.word && r.spoken && (!r.locale || [locale,locale.slice(0,2)].includes(r.locale.toLowerCase())) && line.text.includes(r.word));
  return {text:line.text, voice:line.voice, rate:line.rate, pitch:line.pitch, volume:line.volume, rules};
}
const signature = line => JSON.stringify(snapshot(line));
function current(line) {
  const approved = line.takes.find(t => t.key === line.active && (!line.takeId || line.takeId === t.id));
  return approved && (line.approvedSource || approved.settings) === signature(line) ? approved : null;
}
function lineModel(data={}) {
  return {id:uniqueId(),speaker:"Narrator",text:"",voice:project.offline ? localVoice : defaultVoice,
    rate:"+0%",pitch:"+0Hz",volume:"+0%",pause:.35,start:null,takes:[],active:null,...data};
}
function placeLines() {
  let cursor = 0;
  return project.lines.map(line => {
    const start = line.start ?? cursor;
    const duration = (current(line)?.frames ?? 0) / 24000;
    cursor = start + duration + line.pause;
    return {line,start,duration};
  });
}
function drawTracks() {
  const box = $("tracks"); box.replaceChildren();
  const placed = placeLines();
  const end = Math.max(1,...placed.map(c=>c.start+c.duration));
  for (const speaker of new Set(placed.map(c=>c.line.speaker))) {
    const row = controls(box,"track");
    el("strong",speaker,row);
    const rail = controls(row,"rail");
    for (const {line,start,duration} of placed.filter(c=>c.line.speaker === speaker)) {
      const b = button(rail,line.text || "Blank",()=>document.getElementById(line.id)?.focus());
      b.className="clip"; b.style.left=(start/end*98)+"%"; b.style.width=(duration/end*98)+"%";
      b.title = speaker+" · "+start.toFixed(2)+" s · "+line.text;
      b.draggable=true;
      b.ondragstart = e => e.dataTransfer.setData("text/plain",line.id);
    }
    rail.ondragover = e=>e.preventDefault();
    rail.ondrop = e=>{
      e.preventDefault();
      const line=project.lines.find(l=>l.id===e.dataTransfer.getData("text/plain"));
      if (!line || line.speaker!==speaker) return;
      const rect=rail.getBoundingClientRect();
      line.start=Math.max(0,Math.round((e.clientX-rect.left)/rect.width*end*100/0.98)/100);
      changed();
    };
  }
}
function changed() { persist(); invalidateMix(); draw(); }
function move(index, delta) {
  const target=index+delta;
  if(target<0 || target>=project.lines.length) return;
  [project.lines[index],project.lines[target]]=[project.lines[target],project.lines[index]];
  changed();
}
async function locked(fn, cancel=false) {
  if (busy) return;
  busy=true; stopping=false; $("editor").disabled=true; $("stop").hidden=!cancel;
  try { await fn(); } catch(e) { project.job=e.message; status(e.message); persist(); }
  finally {busy=false; $("editor").disabled=false; $("stop").hidden=true; draw();}
}
async function getTake(line, force=false) {
  const s = snapshot(line);
  const take = await api("/api/project/take",{line:{...s,speaker:line.speaker},rules:s.rules,offline:project.offline,force});
  take.settings=JSON.stringify(s);
  return take;
}
async function renderLine(line,force=false) {
  const take=await getTake(line,force);
  const previous=line.takes.find(t=>t.key===take.key && t.settings===take.settings);
  if (!previous) {
    take.id=uniqueId();
    line.takes.push(take);
  }
  line.active=take.key;
  line.approvedSource=take.settings;
  line.takeId=(previous || take).id;
  await persist(); invalidateMix();
}
async function pending() {
  for(const [i,line] of project.lines.entries()) {
    if(stopping) break;
    if(current(line)) continue;
    project.job="Rendering line "+(i+1)+" of "+project.lines.length;
    status(project.job); persist();
    for(let attempt=0;;attempt++) {
      try {await renderLine(line);break;}
      catch(e) {
        if(stopping || attempt===2 || !(e.retry || e instanceof TypeError)) throw e;
        await new Promise(resolve=>setTimeout(resolve,500*2**attempt));
      }
    }
  }
  project.job=stopping ? "Stopped. Render pending lines to resume." : "All lines are ready.";
  persist();status(project.job);
}
function captionEditor(parent, take) {
  const panel=el("details",undefined,parent);
  el("summary","Edit captions · times in seconds",panel);
  const rows=el("div",undefined,panel);
  function repaint() {
    rows.replaceChildren();
    take.cues.forEach((cue,i)=>{
      const row=controls(rows,"cue");
      field(row,"Start",cue[0]/1000,v=>cue[0]=Math.round(Number(v)*1000),"number");
      field(row,"End",cue[1]/1000,v=>cue[1]=Math.round(Number(v)*1000),"number");
      field(row,"Caption",cue[2],v=>cue[2]=v);
      button(row,"Split",()=>{
        const middle=Math.floor((cue[0]+cue[1])/2);
        if(middle<=cue[0]) throw new Error("Increase the cue duration before splitting.");
        const words=cue[2].split(/\s+/), split=Math.ceil(words.length/2);
        take.cues.splice(i,1,[cue[0],middle,words.slice(0,split).join(" ")],[middle,cue[1],words.slice(split).join(" ")]);
        persist();invalidateMix();repaint();
      });
    });
  }
  repaint();
}
function audition(parent,line,input) {
  const panel=el("details",undefined,parent);
  el("summary","Compare voices on this line",panel);
  const sample=field(panel,"Audition text",line.text,()=>{},"textarea");
  panel.ontoggle=()=>{if(panel.open) sample.value=input.value.slice(input.selectionStart,input.selectionEnd)||input.value;};
  const shortlist=field(panel,"Voices, separated by commas",project.offline ? localVoice : [line.voice,"en-US-JennyNeural","en-US-GuyNeural"].filter((v,i,a)=>a.indexOf(v)===i).join(", "),()=>{});
  const results=el("div",undefined,panel);
  button(panel,"Compare",async()=>{
    results.replaceChildren();
    const voices=[...new Set(shortlist.value.split(",").map(v=>v.trim()).filter(Boolean))];
    if(!sample.value.trim() || !voices.length) throw new Error("Enter audition text and at least one voice.");
    for(const voice of voices) {
      const take=await getTake({...line,voice,text:sample.value});
      el("strong",voice,results);
      const player=el("audio",undefined,results);player.controls=true;player.src="/static/takes/"+take.key+".wav";
      button(results,"Assign to "+line.speaker,()=>{
        for(const other of project.lines) if(other.speaker===line.speaker) other.voice=voice;
        changed();
      });
    }
  });
}
function drawLine(line,index) {
  const row=controls($("lines"),"line"), meta=controls(row,"fields");
  const edit=(key,value)=>{line[key]=value;};
  const speaker=field(meta,"Speaker",line.speaker,v=>edit("speaker",v));
  speaker.onchange=()=>draw();
  const voice=field(meta,"Voice",line.voice,v=>edit("voice",v));voice.setAttribute("list","voices");
  const input=field(row,"Line "+(index+1),line.text,v=>edit("text",v),"textarea");input.id=line.id;
  const values=controls(row,"fields");
  const voiceControls={};
  for(const [name,label] of [["rate","Rate (%)"],["pitch","Pitch (Hz)"],["volume","Voice volume (%)"]])
    voiceControls[name]=field(values,label,line[name],v=>edit(name,v));
  function setVoiceControls() {
    for(const name of ["pitch","volume"]) {
      voiceControls[name].disabled=line.voice.startsWith("echon");
      voiceControls[name].title=voiceControls[name].disabled ? "ECHON supports speed. Adjust speaker gain in the mix." : "";
    }
  }
  voice.onchange=setVoiceControls;
  setVoiceControls();
  field(values,"Start (s), blank = auto",line.start,v=>edit("start",v===""?null:Math.max(0,Number(v))),"number").onchange=drawTracks;
  field(values,"Pause after (s)",line.pause,v=>edit("pause",Math.max(0,Number(v))),"number").onchange=drawTracks;
  const action=controls(row);
  const take=current(line);
  button(action,take?"Record another take":"Render line",()=>locked(async()=>{await renderLine(line,!!current(line));status("Line "+(index+1)+" is ready.");}));
  button(action,"Move up",()=>move(index,-1)).disabled=index===0;
  button(action,"Move down",()=>move(index,1)).disabled=index===project.lines.length-1;
  button(action,"Remove",()=>{if(confirm("Remove this line and its takes from the project?")){project.lines.splice(index,1);changed();}});
  if(line.takes.length) {
    const label=el("label","Recorded takes ",action);
    const select=el("select",undefined,label);
    el("option","Choose a take",select).value="";
    line.takes.forEach((t,i)=>{const opt=el("option","Take "+(i+1)+" · "+(t.frames/24000).toFixed(2)+" s",select);opt.value=String(i);opt.selected=t===take;});
    select.onchange=()=>{
      if(select.value==="")return;
      const t=line.takes[Number(select.value)], s=JSON.parse(t.settings);
      Object.assign(line,{text:s.text,voice:s.voice,rate:s.rate,pitch:s.pitch,volume:s.volume});
      line.active=t.key; line.takeId=t.id;
      line.approvedSource=signature(line);
      changed();
    };
  }
  if(take) {
    const player=el("audio",undefined,row);player.controls=true;player.preload="none";player.src="/static/takes/"+take.key+".wav";
    captionEditor(row,take);
  }
  audition(row,line,input);
}
function draw() {
  $("name").value=project.name; $("offline").checked=project.offline; $("catalog").disabled=project.offline;
  $("lines").replaceChildren(); project.lines.forEach(drawLine);drawTracks();
  $("rules").replaceChildren();
  project.rules.forEach((rule,i)=>{
    const row=controls($("rules"),"fields");
    for(const [k,label] of [["word","Spelling"],["spoken","Spoken form"],["locale","Locale (optional)"]])
      field(row,label,rule[k],v=>rule[k]=v);
    button(row,"Remove",()=>{project.rules.splice(i,1);changed();});
  });
  $("gains").replaceChildren();
  for(const speaker of new Set(project.lines.map(l=>l.speaker)))
    field($("gains"),speaker+" gain (dB)",Object.hasOwn(project.gains,speaker)?project.gains[speaker]:0,v=>Object.defineProperty(project.gains,speaker,{value:Number(v),writable:true,configurable:true,enumerable:true}),"number");
}
function link(box,label,url,filename) {
  const a=el("a",label,box);a.href=url;a.download=filename;return a;
}
async function mix(stems) {
  if(!project.lines.length) throw new Error("Add a line to the timeline first.");
  await pending();
  if(stopping)return;
  status("Mixing audio…");
  const result=await api("/api/project/mix",{project,stems});
  const url=result.url;
  $("player").hidden=false;$("player").src=url+"master.wav";
  $("exports").replaceChildren();
  for(const [label,file] of [["Master WAV","master.wav"],["SRT","captions.srt"],["WebVTT","captions.vtt"]])
    link($("exports"),label,url+file,project.name+"."+file.split(".").pop());
  if(stems)link($("exports"),"Download master and speaker tracks",url+"mix.zip",project.name+"-mix.zip");
  $("meter").textContent=result.seconds.toFixed(2)+" s · RMS "+(result.rms_dbfs??"−∞")+" dBFS · Peak "+(result.peak_dbfs??"−∞")+" dBFS";
  status("Mix ready.");
}
$("name").oninput=()=>{project.name=$("name").value;persist();};
$("script").value=project.scriptDraft||"";
$("script").oninput=()=>{project.scriptDraft=$("script").value;persist();};
$("new").onclick=()=>{if(confirm("Start a new project? Save a portable copy to keep this session.")){project=fresh();$("script").value="";changed();status("New project ready.");}};
$("import").onclick=()=>locked(async()=>{
  const lines=await api("/api/project/parse",{text:$("script").value});
  if(!lines.length)throw new Error("Enter some script text first.");
  for(const line of lines)project.lines.push(lineModel({...line,voice:project.offline?localVoice:line.voice}));
  project.scriptDraft="";$("script").value="";changed();status("Added "+lines.length+" lines.");
});
$("add").onclick=()=>{project.lines.push(lineModel());changed();$(project.lines.at(-1).id).focus();};
$("addRule").onclick=()=>{project.rules.push({word:"",spoken:"",locale:""});changed();};
$("offline").onchange=()=>{project.offline=$("offline").checked;changed();status(project.offline?"Offline only. Select ECHON for any pending lines.":"Online voices enabled.");};
$("catalog").onclick=()=>locked(async()=>{const voices=await api("/api/voices");$("voices").replaceChildren();voices.forEach(v=>el("option",v.ShortName,$("voices")));status("Loaded "+voices.length+" voices.");});
$("testLocal").onclick=()=>locked(async()=>{
  const line=lineModel({voice:localVoice,text:"The offline studio is ready."});
  const take=await getTake(line,true);$("testPlayer").src="/static/takes/"+take.key+".wav";$("testPlayer").hidden=false;
  status("Local synthesis passed. Play the sample to hear it.");
});
$("save").onclick=()=>locked(async()=>{
  const {url}=await api("/api/project/save",project);
  const a=link(document.body,"",url,(project.name||"Session")+".ttsp");a.click();a.remove();status("Portable project ready.");
});
$("open").onclick=()=>$("file").click();
$("file").onchange=()=>locked(async()=>{
  const f=$("file").files[0];$("file").value="";if(!f)return;
  if(project.lines.length&&!confirm("Replace the current draft with the selected project?"))return;
  project=await api("/api/project/open",f,true);$("script").value=project.scriptDraft||"";changed();status("Opened "+project.name+".");
});
$("render").onclick=()=>locked(pending,true);
$("stop").onclick=()=>{stopping=true;status("Stopping after the current line…");};
$("preview").onclick=()=>locked(()=>mix(false),true);
$("export").onclick=()=>locked(()=>mix(true),true);
async function openDraft() {
  $("editor").disabled=true;
  try {
    const db=await database;
    const saved=await new Promise((resolve,reject)=>{
      const req=db.transaction("sessions").objectStore("sessions").get("current");
      req.onsuccess=()=>resolve(req.result); req.onerror=()=>reject(req.error);
    });
    if(saved) project=saved;
  } catch { /* Small drafts use localStorage when IndexedDB is unavailable. */ }
  $("editor").disabled=false; $("script").value=project.scriptDraft||"";
  draw();
  status(project.job.startsWith("Rendering")?"Interrupted render. Render pending lines to resume.":project.job);
}
openDraft();
api("/api/project/offline").then(s=>{
  $("offlineStatus").textContent="Inference runtime "+(s.runtime?"found":"missing")+" · Model checkpoint "+(s.checkpoint?"found":"missing")+" · "+s.path+". Set ECHON_HOME to the local model repository.";
}).catch(e=>status(e.message));
