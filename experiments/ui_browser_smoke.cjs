// SPDX-License-Identifier: MIT
// Optional offline browser checks. Node >=22 and an installed Chromium browser.
const fs=require('fs'),path=require('path'),os=require('os'),crypto=require('crypto');
const {spawn}=require('child_process');
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
async function main(){
  python=spawn('python',extension?['examples/measurement_lab.py','ui','--no-browser']:['-m','robustband','ui','--no-browser','--edition',professional?'professional':'generalized'],{cwd:ROOT,windowsHide:true,stdio:['ignore','pipe','pipe']});
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
  await until(()=>evaluate('typeof options!=="undefined" && options!==null && document.querySelectorAll("#choices input").length===13'),'interface initialization');
  assert(await evaluate('document.getElementById("workspace").hidden && !document.getElementById("advanced").open'),'First visit exposed advanced settings');
  assert(await evaluate('document.getElementById("pageTitle").textContent===t("title") && document.querySelectorAll("[data-domain]").length===options.domains.length'),'Purpose or data-kind choices missing');
  await screenshot('build/local-ui-home.png',1280,900);
  await evaluate('document.getElementById("help").click()');
  assert(await evaluate('document.getElementById("helpDialog").open'),'Help did not open');
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27,nativeVirtualKeyCode:27});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27,nativeVirtualKeyCode:27});
  await until(()=>evaluate('!document.getElementById("helpDialog").open'),'keyboard dialog dismissal');
  await evaluate('document.getElementById("example").click()');
  await until(()=>evaluate('last!==null && !busy'),'example audit');
  const example=await evaluate('last.report.result');
  assert(await evaluate('document.getElementById("verdictTitle").textContent===t("UNIDENTIFIABLE") && document.getElementById("dataSource").textContent===t("demo") && !document.getElementById("nextAction").hidden'),'Result or next step was not explained');
  assert(example.exact_band.join(',')==='-1,1'&&example.support_count===1&&example.n_protocols===2,'Hand-checkable example mismatch');
  assert(await evaluate('document.querySelector("input[value=macro_class]").disabled'),'Missing group was silently accepted');
  await screenshot('build/local-ui-desktop.png',1280,1000);
  await screenshot('build/local-ui-mobile.png',390,844);
  assert(await evaluate('document.documentElement.scrollWidth<=window.innerWidth'),'Mobile page overflows horizontally');
  await send('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});
  const language=await evaluate('document.documentElement.lang');await evaluate('document.getElementById("language").click()');
  assert(await evaluate('document.documentElement.lang')!==language,'Language switch failed');
  await evaluate('document.getElementById("html").click();document.getElementById("json").click()');
  await until(()=>fs.existsSync(path.join(downloads,'report.json'))&&fs.existsSync(path.join(downloads,'report.html')),'report downloads');
  const downloaded=JSON.parse(fs.readFileSync(path.join(downloads,'report.json'),'utf8'));
  assert(downloaded.result.exact_band.join(',')==='-1,1','Downloaded report differs from displayed result');
  await evaluate('document.getElementById("useDataNext").click()');
  assert(await evaluate('loaded===null && last===null && !document.getElementById("workspace").hidden && document.getElementById("dataSource").textContent===t("demo")'),'Own-data transition kept an actionable demo result');
  await evaluate('document.getElementById("template").click()');
  await until(()=>fs.existsSync(path.join(downloads,'text-template.csv')),'matching template download');
  assert(fs.readFileSync(path.join(downloads,'text-template.csv'),'utf8').includes('sample_id,prompt,gold,output_a,output_b'),'Template schema mismatch');
  const hostile={sample_id:'unicode-1',prompt:'Unicode 中文 <img src=x onerror="window.injected=true">',gold:'42',output_a:'7 then 42',output_b:'42 then 7',class:'arithmetic',len_bucket:2};
  await installFile(JSON.stringify(hostile),'paired.jsonl');
  await until(()=>evaluate('loaded!==null && !busy && loaded.records[0].sample_id==="unicode-1"'),'JSONL upload');
  assert(await evaluate('document.querySelectorAll("#previewTable img").length===0 && typeof window.injected==="undefined"'),'Uploaded text became executable markup');
  assert(await evaluate('!document.querySelector("input[value=macro_class]").disabled'),'Valid explicit grouping unavailable');
  await evaluate('(()=>{const input=document.querySelector("input[value=macro_class]");input.checked=true;input.dispatchEvent(new Event("change"));document.getElementById("run").click();})()');
  await until(()=>evaluate('last!==null && !busy'),'grouped audit');
  assert(await evaluate('last.report.result.n_protocols')===4,'Explicit selected family mismatch');
  await installFile('sample_id,prompt,gold,output_a,output_b\nx,q,42,42,7\nx,q,42,42,7\n','duplicates.csv');
  await until(()=>evaluate('!busy && !document.getElementById("error").hidden'),'duplicate-ID rejection');
  assert(await evaluate('document.getElementById("error").textContent.includes("duplicate sample_id") && document.getElementById("run").disabled && document.getElementById("results").hidden'),'Bad input retained an actionable stale report');
  assert(await evaluate('document.getElementById("errorAction").textContent.length>20'),'Error omitted a recovery step');
  await evaluate(`(()=>{const file=new File([${JSON.stringify(JSON.stringify(hostile))}],'dropped.jsonl');const data=new DataTransfer();data.items.add(file);document.getElementById('dropZone').dispatchEvent(new DragEvent('drop',{dataTransfer:data,bubbles:true}));})()`);
  await until(()=>evaluate('loaded!==null && !busy && loaded.records[0].sample_id==="unicode-1"'),'drag-and-drop input');
  if(!professional){
  await evaluate('document.getElementById("dataMode").value="segmentation";document.getElementById("dataMode").dispatchEvent(new Event("change"));document.getElementById("example").click()');
  await until(()=>evaluate('last!==null && !busy'),'segmentation example');
  assert(await evaluate('last.report.schema')==='robustband.segmentation_audit/v1','Data mode ignored');
  assert(await evaluate('last.report.result.verdict')==='UNIDENTIFIABLE','Aggregation reversal missed');
  await evaluate('document.getElementById("segClasses").value="1";document.getElementById("segClasses").dispatchEvent(new Event("input"));document.getElementById("run").click()');
  await until(()=>evaluate('last!==null && !busy'),'explicit class target');
  assert(await evaluate('last.report.result.exact_band.join(",")')==='-49/51,1/3','Class target not applied');
  assert(await evaluate('document.getElementById("band").textContent.includes(" pp")'),'Percentage point units missing');
  await screenshot('build/local-ui-segmentation.png',1280,1000);
  const inputIndex=process.argv.indexOf('--segmentation-input');
  if(inputIndex!==-1){
    await installFile(fs.readFileSync(process.argv[inputIndex+1],'utf8'),'paired-confusions.jsonl');
    await until(()=>evaluate('loaded!==null && !busy'),'local segmentation data upload');
    await evaluate('document.getElementById("segClasses").value="all";document.getElementById("segClasses").dispatchEvent(new Event("input"));document.getElementById("run").click()');
    await until(()=>evaluate('last!==null && !busy'),'local segmentation audit');
    assert(await evaluate('last.report.result.n_items')===70,'Expected full 70-image local case');
    assert(await evaluate('last.report.result.verdict')==='ROBUST','Local v3/v2 result changed');
    await screenshot('build/local-ui-uav.png',1280,1000);
  }
  await evaluate('document.getElementById("dataMode").value="scores";document.getElementById("dataMode").dispatchEvent(new Event("change"));document.getElementById("example").click()');
  await until(()=>evaluate('last!==null && !busy'),'numeric metric example');
  assert(await evaluate('last.report.result.exact_band.join(",")')==='-8/3,1','Recorded-score aggregation mismatch');
  assert(await evaluate('last.report.claim.direction')==='lower','Metric direction missing');
  assert(await evaluate('document.getElementById("claim").textContent')==='A < B','Lower-is-better claim displayed incorrectly');
  assert(await evaluate('document.getElementById("band").textContent.includes(" ms")'),'Scalar unit missing');
  await screenshot('build/local-ui-scores.png',1280,1000);
  }
  if(extension){
    await evaluate('document.getElementById("dataMode").value="measurement_lab";document.getElementById("dataMode").dispatchEvent(new Event("change"));document.getElementById("example").click()');
    await until(()=>evaluate('last!==null && !busy'),'registered extension example');
    assert(await evaluate('last.report.result.exact_band.join(",")')==='-8/3,1','Custom algorithm default mismatch');
    await evaluate('document.querySelectorAll("input[name=algorithms]").forEach(e=>e.checked=e.value==="trimmed_mean");const p=document.getElementById("control-measurement_lab-minimum_advantage");p.value="1";p.dispatchEvent(new Event("input"));document.getElementById("run").click()');
    await until(()=>evaluate('last!==null && !busy'),'custom exact parameter');
    assert(await evaluate('last.report.result.exact_band.join(",")')==='0,0','Exact parameter was ignored');
    assert(await evaluate('last.report.result.verdict')==='REFUTED','Strict advantage threshold tie incorrectly supported');
    await evaluate('const precisionParameter=document.getElementById("control-measurement_lab-minimum_advantage");precisionParameter.value="0.9999999999999999999999";precisionParameter.dispatchEvent(new Event("input"));document.getElementById("run").click()');
    await until(()=>evaluate('last!==null && !busy'),'parameter below float resolution');
    assert(await evaluate('last.report.result.verdict')==='ROBUST','Decimal parameter rounded into a tie');
    assert(await evaluate('last.report.result.exact_band[0]')==='1/10000000000000000000000','Decimal parameter precision lost');
    await evaluate('document.getElementById("control-measurement_lab-minimum_advantage").value="1";const s=document.getElementById("control-measurement_lab-trim_side");s.value="lower";s.dispatchEvent(new Event("change"));document.getElementById("run").click()');
    await until(()=>evaluate('last!==null && !busy'),'custom select parameter');
    assert(await evaluate('last.report.result.exact_band.join(",")')==='-11/2,-11/2','Select parameter ignored');
    await screenshot('build/local-ui-extension.png',1280,1000);
  }
  if(professional)assert(await evaluate('options.domains.length===1 && options.domains[0].id==="text"'),'Professional edition leaked general domains');
  let welcome=null;
  const welcomeIndex=process.argv.indexOf('--welcome');
  if(welcomeIndex!==-1){
    const file=path.resolve(ROOT,process.argv[welcomeIndex+1]);networkRequests=[];
    await send('Page.navigate',{url:pathToFileURL(file).href});
    await until(()=>evaluate('typeof options!=="undefined" && options!==null && isOffline'),'standalone preview initialization');
    assert(await evaluate('!document.getElementById("offlineBanner").hidden && document.getElementById("stop").hidden'),'Preview did not identify itself');
    await evaluate('document.getElementById("example").click()');
    await until(()=>evaluate('last!==null && !busy'),'no-install example');
    assert(await evaluate('last.report.result.exact_band.join(",")')==='-1,1','Standalone example differs from exact engine');
    assert(await evaluate('document.getElementById("run").disabled && document.getElementById("modelA").disabled'),'Preview allowed changes it cannot calculate');
    await evaluate('document.getElementById("useDataNext").click()');
    assert(await evaluate('document.getElementById("setupDialog").open && document.getElementById("launchCommand").textContent.includes(options.edition)'),'No-install page omitted real-data setup');
    await evaluate('document.querySelector("[data-close=setupDialog]").click()');
    if(!professional){
      for(const kind of ['segmentation','scores','measurement_lab']){
        await evaluate(`document.querySelector('[data-domain="${kind}"]').click();document.getElementById('example').click()`);
        await until(()=>evaluate('last!==null && !busy'),'standalone '+kind);
        assert(await evaluate('last.report.result.verdict')==='UNIDENTIFIABLE','Standalone domain result mismatch');
      }
    }
    await screenshot('build/local-ui-welcome.png',1280,900);
    await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
    assert(await evaluate('document.documentElement.scrollWidth<=window.innerWidth'),'Standalone mobile preview overflow');
    assert(networkRequests.filter(url=>/^https?:/i.test(url)).length===0,'Standalone preview made network requests');
    welcome={filename:path.basename(file),sha256:hash(file),http_requests:0,checked:['file-open preview','exact saved examples','fixed preview settings','local-app setup instructions','no network requests','mobile width']};
  }
  assert(exceptions.length===0,'Browser raised script exceptions: '+exceptions.join(', '));
  const result={schema:'robustband.browser_smoke/v1',software_version:downloaded.software_version,platform:process.platform,browser:version.product,edition:professional?'professional':'generalized',editable_extension:extension,
    checked:['example exact band','CSV example','JSONL upload','Unicode and HTML escaping','explicit macro grouping','duplicate-ID rejection','stale result invalidation','HTML/JSON downloads','language switch','desktop and mobile layout','segmentation aggregation reversal','explicit class target','percentage point display','numeric metric aggregation reversal','lower-is-better claim and units'],
    example_exact_band:example.exact_band,script_exceptions:exceptions,independent_human_user:false,
    source_sha256_lf:{'robustband/ui.html':sourceHash(path.join(ROOT,'robustband/ui.html')),'experiments/ui_browser_smoke.cjs':sourceHash(__filename)},
    screenshots:Object.fromEntries(['build/local-ui-desktop.png','build/local-ui-mobile.png'].map(file=>[screenshotPath(file),hash(path.join(ROOT,screenshotPath(file)))]))};
  if(professional)result.checked=result.checked.slice(0,10).concat(['professional domain isolation']);
  if(extension)result.checked.push('registered user algorithm','exact decimal parameter','select parameter','strict advantage threshold','decimal parameter below float resolution');
  result.checked.push(...guidedChecks);if(welcome)result.standalone_preview=welcome;
  fs.writeFileSync(path.join(ROOT,'results/local_ui_smoke_'+(professional?'professional_':extension?'extension_':'')+downloaded.software_version+'.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({browser:result.browser,checks:result.checked.length,exact_band:example.exact_band,exceptions:exceptions.length}));
}
main().catch(async error=>{console.error(error.message);if(ws&&ws.readyState===1){try{console.error(JSON.stringify(await evaluate('({error:document.getElementById("error").textContent,loaded:loaded!==null,busy,exceptions:"see CDP",family:options? family():null})')));console.error(JSON.stringify(exceptions));}catch{}}process.exitCode=1;}).finally(async()=>{
  if(launch.startsWith('http://127.0.0.1:')){try{const [url,token]=launch.split('#');await fetch(url+'api/stop',{method:'POST',headers:{'X-Robustband-Token':token,'Content-Length':'2'},body:'{}'});}catch{}}
  if(ws&&ws.readyState===1){try{await send('Browser.close');}catch{}ws.close();}
  if(python&&!python.killed)python.kill();if(browser&&!browser.killed)browser.kill();
  await sleep(500);
  const resolved=path.resolve(profile),root=path.resolve(os.tmpdir())+path.sep;
  if(resolved.startsWith(root)&&path.basename(resolved).startsWith('robustband-browser-')){try{fs.rmSync(resolved,{recursive:true,force:true});}catch{}}
});
