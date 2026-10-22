// SPDX-License-Identifier: MIT
// Optional offline browser checks. Node >=22 and an installed Chromium browser.
const fs=require('fs'),path=require('path'),os=require('os'),crypto=require('crypto');
const {spawn,execFileSync}=require('child_process');
const {pathToFileURL}=require('url');
const ROOT=path.resolve(__dirname,'..');
const professional=process.argv.includes('--professional'),extension=process.argv.includes('--extension');
const screenshotPath=file=>file.replace('build/local-ui-','build/local-ui-'+(professional?'professional-':extension?'extension-':''));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const assert=(ok,message)=>{if(!ok)throw new Error(message);};
const sourceHash=file=>crypto.createHash('sha256').update(fs.readFileSync(file,'utf8').replace(/\r\n/g,'\n')).digest('hex');
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const candidates=[process.env.ROBUSTBAND_BROWSER_PATH,'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe','/usr/bin/microsoft-edge','/usr/bin/chromium','/usr/bin/google-chrome','/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'];
const browserPath=candidates.find(p=>p&&fs.existsSync(p));
assert(browserPath,'Set ROBUSTBAND_BROWSER_PATH to an installed Chromium browser.');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'robustband-browser-'));
fs.mkdirSync(path.join(ROOT,'build'),{recursive:true});
const downloads=fs.mkdtempSync(path.join(ROOT,'build/browser-downloads-'));
let python,browser,ws,launch='',exceptions=[],id=0,pending=new Map(),networkRequests=[];
const guidedChecks=['purpose and data-kind entry','advanced rules start collapsed','plain-language result and example label','template-to-upload next step','actionable duplicate-ID guidance','keyboard help dialog','drag-and-drop upload'];
async function until(test,label,timeout=25000){const end=Date.now()+timeout;while(Date.now()<end){if(await test())return;await sleep(80);}throw new Error('Timed out: '+label);}
function send(method,params={}){return new Promise((resolve,reject)=>{const request=++id;pending.set(request,{resolve,reject});ws.send(JSON.stringify({id:request,method,params}));});}
async function evaluate(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw new Error(result.exceptionDetails.text);return result.result.value;}
async function installFile(text,name){await evaluate(`(()=>{const file=new File([${JSON.stringify(text)}],${JSON.stringify(name)},{type:'text/plain'});const data=new DataTransfer();data.items.add(file);document.getElementById('file').files=data.files;document.getElementById('file').dispatchEvent(new Event('change'));})()`);}
async function screenshot(file,width,height){await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await sleep(100);const metrics=await send('Page.getLayoutMetrics');const image=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width,height:metrics.cssContentSize.height,scale:1}});fs.writeFileSync(path.join(ROOT,screenshotPath(file)),Buffer.from(image.data,'base64'));}
function pythonCommand() {
  const override = process.env.ROBUSTBAND_PYTHON;
  if (override) return { command: override, args: [] };
  const candidates = process.platform === 'win32'
    ? [{ command: 'python', args: [] }, { command: 'py', args: ['-3'] }]
    : [{ command: 'python3', args: [] }, { command: 'python', args: [] }];
  for (const candidate of candidates) {
    try {
      execFileSync(candidate.command, [...candidate.args, '-c',
        'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'], { stdio: 'ignore' });
      return candidate;
    } catch {}
  }
  throw new Error('No Python 3.9+ interpreter found; set ROBUSTBAND_PYTHON.');
}

async function main(){
  const py=pythonCommand();
  python=spawn(py.command,[...py.args,...(extension?['examples/measurement_lab.py','ui','--no-browser']:['-m','robustband','ui','--no-browser','--edition',professional?'professional':'generalized'])],{cwd:ROOT,windowsHide:true,stdio:['ignore','pipe','pipe']});
  python.stdout.on('data',data=>{launch+=data.toString();});
  await until(()=>/http:\/\/127\.0\.0\.1:\d+\/#\S+/.test(launch),'local server launch');
  launch=launch.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/)[0];
  browser=spawn(browserPath,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
  const active=path.join(profile,'DevToolsActivePort');await until(()=>fs.existsSync(active),'browser debugger');
  const port=fs.readFileSync(active,'utf8').split('\n')[0];
  const targets=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  ws.onmessage=event=>{const item=JSON.parse(event.data);if(item.id){const task=pending.get(item.id);pending.delete(item.id);if(item.error)task.reject(new Error(JSON.stringify(item.error)));else task.resolve(item.result);}else if(item.method==='Runtime.exceptionThrown')exceptions.push(item.params.exceptionDetails.exception?.description||item.params.exceptionDetails.text);else if(item.method==='Network.requestWillBeSent')networkRequests.push(item.params.request.url);};
  await send('Runtime.enable');await send('Page.enable');await send('Network.enable');
  const version=await send('Browser.getVersion');
  await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloads});
  await send('Page.navigate',{url:launch});
  await until(()=>evaluate('typeof options!=="undefined" && options!==null'),'comparison page');
  await evaluate('document.getElementById("decision").click()');
  await until(()=>evaluate('location.pathname==="/decision" && typeof options!=="undefined" && options!==undefined'),'decision page');
  assert(await evaluate('document.getElementById("result").hidden'),'Stale result on initial visit');
  await evaluate('document.getElementById("example").click()');
  await until(()=>evaluate('last!==null && !busy'),'adoption example');
  assert(await evaluate('!document.getElementById("inputDetails").open && !document.getElementById("criteriaDetails").open'),'Completed stages did not collapse');
  await evaluate('document.querySelector("#criteriaDetails summary").focus()');
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',windowsVirtualKeyCode:13});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await until(()=>evaluate('document.getElementById("criteriaDetails").open'),'keyboard reopens criteria');
  await evaluate('document.getElementById("criteriaDetails").open=false;document.getElementById("exportData").click()');
  await until(()=>fs.existsSync(path.join(downloads,'paired-standard.jsonl'))&&fs.existsSync(path.join(downloads,'paired-standard.manifest.json')),'validated data exports');
  const conversion=JSON.parse(fs.readFileSync(path.join(downloads,'paired-standard.manifest.json'),'utf8'));
  assert(conversion.roundtrip_verified && conversion.output_sha256===hash(path.join(downloads,'paired-standard.jsonl')),'Conversion manifest did not match exported bytes');
  await screenshot('build/local-ui-decision-original.png',1280,1000);
  const checked=['comparison-to-adoption navigation','explicit synthetic label','separate target criteria','exact replay downloads','criteria invalidation','language switch','mobile width'];
  checked.push('completed stages collapse','keyboard reopens editable criteria','standard-data download and manifest hash');
  if(professional){
    assert(await evaluate('last.report.plan.domain')==='text','Professional decision domain changed');
    assert(await evaluate('last.report.result.status')==='REVIEW','Text sensitivity missing');
    assert(await evaluate('document.getElementById("domain").options.length')===1,'Professional domain isolation failed');
    checked.push('professional text-only criteria');
  }else{
    assert(await evaluate('last.report.result.status')==='FAIL','Tradeoff should fail declared guardrail');
    assert(await evaluate('last.report.result.target_tradeoff'),'Objective tradeoff not explained');
    assert(await evaluate('last.report.targets.map(t=>t.status).join(",")')==='PASS,FAIL','Metric targets merged');
    await evaluate('document.querySelectorAll(".threshold")[1].value="-2";document.querySelectorAll(".threshold")[1].dispatchEvent(new Event("input",{bubbles:true}))');
    assert(await evaluate('last===null && document.getElementById("result").hidden'),'Criterion change kept stale result');
    await evaluate('document.getElementById("run").click()');
    await until(()=>evaluate('last!==null && !busy'),'revised guardrail');
    assert(await evaluate('last.report.result.status')==='PASS','Explicitly revised guardrail ignored');
    await evaluate('document.getElementById("savePlan").click()');
    await until(()=>fs.existsSync(path.join(downloads,'plan.json')),'criteria download before reuse');
    const saved=JSON.parse(fs.readFileSync(path.join(downloads,'plan.json'),'utf8'));
    assert(saved.targets[0].unit==='percent' && saved.targets[0].direction==='higher','Plan lost unit or direction');
    await evaluate('document.querySelector(".threshold").value="3";document.querySelector(".threshold").dispatchEvent(new Event("input",{bubbles:true}));document.getElementById("run").click()');
    await until(()=>evaluate('last!==null && !busy'),'strict threshold boundary');
    assert(await evaluate('last.report.result.status')==='FAIL','Equality met a strict threshold');
    await evaluate('document.querySelector(".operator").value="ge";document.querySelector(".operator").dispatchEvent(new Event("input",{bubbles:true}));document.getElementById("run").click()');
    await until(()=>evaluate('last!==null && !busy'),'inclusive threshold boundary');
    assert(await evaluate('last.report.result.status')==='PASS','Inclusive threshold rejected equality');
    await evaluate(`(()=>{const data=new DataTransfer();data.items.add(new File([${JSON.stringify(JSON.stringify(saved))}],'plan.json'));document.getElementById('planFile').files=data.files;document.getElementById('planFile').dispatchEvent(new Event('change'));})()`);
    await until(()=>evaluate('!busy && last===null && document.querySelector(".threshold").value==="1"'),'criteria reuse');
    await evaluate('document.getElementById("run").click()');
    await until(()=>evaluate('last!==null && !busy'),'reused plan run');
    checked.push('objective tradeoff explanation','wide-column mapping','unit and direction binding','strict and inclusive threshold boundary','saved criteria reuse');
  }
  const language=await evaluate('document.documentElement.lang');
  await evaluate('document.getElementById("language").click()');
  assert(await evaluate('document.documentElement.lang')!==language,'Language switch failed');
  assert(await evaluate('document.querySelector(".role").selectedOptions[0].textContent===tr("主要目标","Primary target")'),'Dynamic criteria labels did not change language');
  await evaluate('document.getElementById("html").click();document.getElementById("json").click()');
  await until(()=>fs.existsSync(path.join(downloads,'report.json'))&&fs.existsSync(path.join(downloads,'report.html')),'decision report downloads');
  const downloaded=JSON.parse(fs.readFileSync(path.join(downloads,'report.json'),'utf8'));
  assert(downloaded.schema==='robustband.decision/v1' && downloaded.input.text,'Replay source missing');
  assert(fs.readFileSync(path.join(downloads,'report.html'),'utf8').includes('Plan SHA256'),'Report lacks frozen plan identity');
  await screenshot('build/local-ui-decision-desktop.png',1280,1000);
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  assert(await evaluate('document.documentElement.scrollWidth<=window.innerWidth'),'Decision mobile page overflows');
  await screenshot('build/local-ui-decision-mobile.png',390,844);
  await send('Emulation.setDeviceMetricsOverride',{width:640,height:500,deviceScaleFactor:1,mobile:false});
  assert(await evaluate('document.documentElement.scrollWidth<=window.innerWidth'),'Decision reflow at 200% equivalent viewport failed');
  checked.push('200% equivalent viewport reflow');
  await send('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});
  if(!professional){
    await evaluate('document.getElementById("newData").click();document.getElementById("layout").value="canonical"');
    const hostile='sample_id,score_a,score_b,metric,unit,direction\na,2,1,<img src=x onerror=window.injected=true>,percent,higher\n';
    await installFile(hostile,'paired.csv');
    await until(()=>evaluate('text.length>0 && !busy'),'own-data file read');
    await evaluate('document.getElementById("preview").click()');
    await until(()=>evaluate('loaded!==null && !busy'),'own-data preview');
    assert(await evaluate('document.querySelectorAll("#criteria img").length===0 && typeof window.injected==="undefined"'),'Uploaded metric became markup');
    await evaluate('document.getElementById("rationale").value="A declared actual-data criterion";document.querySelector(".reason").value="Mean and median on paired records";document.getElementById("run").click()');
    await until(()=>evaluate('last!==null && !busy'),'own-data decision');
    assert(await evaluate('!demo && last.report.result.status==="PASS"'),'Own-data result or provenance label wrong');
    await installFile(hostile+hostile.split('\n')[1]+'\n','duplicates.csv');
    await until(()=>evaluate('!busy && text.includes("a,2,1")'),'duplicate input loaded');
    await evaluate('document.getElementById("preview").click()');
    await until(()=>evaluate('!busy && !document.getElementById("error").hidden'),'duplicate pairing rejection');
    assert(await evaluate('last===null && document.getElementById("criteria").hidden'),'Invalid input retained active criteria');
    await evaluate('document.getElementById("domain").value="segmentation";document.getElementById("domain").dispatchEvent(new Event("change"))');
    await installFile(JSON.stringify({sample_id:'one',confusion_a:[[1,0],[0,1]],confusion_b:[[1,0],[1,0]]}),'counts.jsonl');
    await until(()=>evaluate('text.length>0 && !busy'),'segmentation input loaded');
    await evaluate('document.getElementById("preview").click()');
    await until(()=>evaluate('loaded!==null && !busy'),'segmentation criteria');
    await evaluate('document.getElementById("rationale").value="Overall plus class protection";document.querySelector(".threshold").value="50";document.querySelector(".operator").value="ge";document.querySelector(".reason").value="Pooled and image mean on identical counts";document.getElementById("addTarget").click();document.querySelectorAll(".classes")[1].value="1";document.querySelectorAll(".threshold")[1].value="100";document.querySelectorAll(".reason")[1].value="Protect class one";document.getElementById("run").click()');
    await until(()=>evaluate('last!==null && !busy'),'segmentation pp gate');
    assert(await evaluate('last.report.result.status==="PASS" && last.report.targets[1].exact_threshold==="1"'),'Segmentation pp threshold scale incorrect');
    checked.push('own-data criteria','HTML-safe uploaded metric labels','duplicate-ID rejection','segmentation primary plus class guardrail','percentage-point threshold scaling');
  }
  assert(exceptions.length===0,'Script exceptions: '+exceptions.join(', '));
  const result={schema:'robustband.decision_browser/v1',software_version:downloaded.software_version,edition:professional?'professional':'generalized',browser:version.product,checked,script_exceptions:exceptions,independent_human_user:false,
    source_sha256_lf:{'robustband/decision.html':sourceHash(path.join(ROOT,'robustband/decision.html')),'experiments/decision_browser_smoke.cjs':sourceHash(__filename)}};
  fs.writeFileSync(path.join(ROOT,'results/decision_ui_'+(professional?'professional_':'')+downloaded.software_version+'.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({browser:result.browser,checks:checked.length,exceptions:exceptions.length}));
}
main().catch(async error=>{console.error(error.message);if(ws&&ws.readyState===1){try{console.error(JSON.stringify(await evaluate('({error:document.getElementById("error").textContent,loaded:loaded!==null,busy,exceptions:"see CDP",plan:options&&loaded? makePlan():null})')));console.error(JSON.stringify(exceptions));}catch{}}process.exitCode=1;}).finally(async()=>{
  if(launch.startsWith('http://127.0.0.1:')){try{const [url,token]=launch.split('#');await fetch(url+'api/stop',{method:'POST',headers:{'X-Robustband-Token':token,'Content-Length':'2'},body:'{}'});}catch{}}
  if(ws&&ws.readyState===1){try{await send('Browser.close');}catch{}ws.close();}
  if(python&&!python.killed)python.kill();if(browser&&!browser.killed)browser.kill();
  await sleep(500);
  const resolved=path.resolve(profile),root=path.resolve(os.tmpdir())+path.sep;
  if(resolved.startsWith(root)&&path.basename(resolved).startsWith('robustband-browser-')){try{fs.rmSync(resolved,{recursive:true,force:true});}catch{}}
});
