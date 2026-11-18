const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
function load(relative, mocks) {
  let source = fs.readFileSync(path.join(root, relative), 'utf8');
  const mod = require('node:module');
  if (mod.stripTypeScriptTypes) source = mod.stripTypeScriptTypes(source);
  else {
    const ts = require(require.resolve('typescript', { paths: [root, path.join(root, 'pos')] }));
    source = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } }).outputText;
  }
  source = source.replace(/^import[\s\S]*?from ['"][^'"]+['"];?\s*/gm, '').replace(/export /g, '');
  return vm.runInNewContext(`(function(){${source};return {${mocks.exports}};})()`, mocks);
}
(async () => {
  let checks = 0;
  let events = [], failure = '', active = false, signature, certificate, defaultCalls = 0;
  const qz = {
    security: {setSignatureAlgorithm: a => assert.equal(a, 'SHA512'), setSignaturePromise: f => signature=f, setCertificatePromise: f=>certificate=f},
    websocket: {isActive:()=>active, connect:async opts=>{assert.equal(opts.usingSecure,true);events.push('connect');if(failure==='connect')throw Error('connect failed');active=true;},disconnect:()=>{active=false;}},
    printers: {find:async name=>{if(failure==='printer')throw Error('missing printer');return failure==='wrong'?'Other':name;},getDefault:async()=>{defaultCalls++;return 'Default';}},
    configs: {create:printer=>({printer})},
    print:async(config,data)=>{events.push('print');assert.equal(config.printer,'Receipt Test');assert.equal(data[0].type,'pixel');assert.equal(data[0].format,'html');if(failure==='print')throw Error('print failed');}
  };
  const transport=load('packages/core/src/print/qz.ts',{qz,axios:{},KEYUTIL:{},KJUR:{},stob64:()=>{},hextorstr:()=>{},exports:'initPrinting,printWithQz'});
  await assert.rejects(()=>transport.printWithQz('localhost','html','Receipt Test'),/initialized/);checks++;
  transport.initPrinting({sign:async()=> 'signed',certificate:async()=> 'certificate'});
  for (const f of ['connect','printer','wrong','print']) {
    active=false; failure=f;
    await assert.rejects(()=>transport.printWithQz('localhost','html','Receipt Test'));checks++;
  }
  failure='';active=false;events=[];
  await transport.printWithQz('localhost','html','Receipt Test');assert.deepEqual(events,['connect','print']);checks++;
  assert.equal(await new Promise((res,rej)=>signature('payload')(res,rej)),'signed');checks++;
  assert.equal(await new Promise(certificate),'certificate');checks++;
  assert.equal(defaultCalls,0);checks++;
  transport.initPrinting({sign:async()=>{throw Error('denied');},certificate:async()=>{throw Error('no certificate');}});
  await transport.printWithQz('localhost','html','Receipt Test');
  await assert.rejects(()=>new Promise((res,rej)=>signature('x')(res,rej)));checks++;
  await transport.printWithQz('localhost','html','Receipt Test');
  // loadQzPrinter installs the certificate callback even when the transport is already active.
  // Reconnect to install the current callback for this isolated mock.
  active=false;await transport.printWithQz('localhost','html','Receipt Test');
  await assert.rejects(()=>new Promise(certificate));checks++;
  let updates=0, prints=0, htmlCalls=0, selection='Receipt Test';
  const orchestrator=load('pos/src/lib/print.ts',{
    window:{localStorage:{getItem:()=>selection}},getInvoicePrintHtml:async()=>{htmlCalls++;return 'html';},
    printWithQz:async(host,html,printer)=>{prints++;assert.equal(printer,'Receipt Test');if(failure)throw Error('rejected');},
    updatePrintStatus:async()=>{updates++;},networkPrint:async()=>{},selectNetworkPrinter:async()=>{},exports:'printOrder'
  });
  const profile={name:'Test',print_type:'qz',qz_host:'localhost',qz_print:1,print_format:'Receipt'};
  for(const setup of ['disabled','missingPrinter','missingHost','transportError','success']) {
    updates=prints=htmlCalls=0;selection=setup==='missingPrinter'?'':'Receipt Test';failure=setup==='transportError'?'print':'';
    const p={...profile,qz_print:setup==='disabled'?0:1,qz_host:setup==='missingHost'?'':profile.qz_host};
    const invoke=()=>orchestrator.printOrder({orderId:'TEST',posProfile:p});
    if(setup==='success'){assert.equal(await invoke(),'qz');assert.equal(updates,1);}else{await assert.rejects(invoke);assert.equal(updates,0);}
    if(['disabled','missingPrinter','missingHost'].includes(setup)){assert.equal(prints,0);assert.equal(htmlCalls,0);}
    checks++;
  }
  console.log(`${checks} QZ transport and orchestration checks passed.`);
})().catch(e=>{console.error(e);process.exitCode=1;});
