// Isolate actual function bodies; narrow signature erasure is not a full TS build.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const api = fs.readFileSync(path.join(root,'pos/src/lib/invoice-api.ts'),'utf8');
const orchestration = fs.readFileSync(path.join(root,'pos/src/lib/print.ts'),'utf8');
function body(source, name) {
 const start = source.indexOf(`export async function ${name}(`);
 assert(start >= 0);
 const begin = source.indexOf(' {\n', start) + 3;
 const end = source.indexOf('\n}', begin);
 assert(begin > 2 && end > begin);
 return source.slice(begin,end).replaceAll("call.post<{ message: unknown }>", 'call.post').replaceAll(' as string', '');
}
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
function wrapper(name, response) {
 return new AsyncFunction('call', 'orderId', 'printer', 'printFormat', 'posProfile', body(api,name))(
  {post: async()=>{if(response instanceof Error)throw response;return {message:response};}},'REG-TEST','queue','receipt','profile');
}
(async()=>{
 let checks=0;
 for(const name of ['networkPrint','selectNetworkPrinter']) {
  for(const response of ['Failed to print: rejected', undefined, null, {status:'Failure'}, new Error('HTTP rejection')]) {
   await assert.rejects(()=>wrapper(name,response));checks++;
  }
  await wrapper(name,'Success');checks++;
 }
 for(const multiple of [0,1]) {
  for(const fail of [true,false]) {
   let updates=0;
   const network=async()=>{if(fail)throw new Error('CUPS rejected');};
   const fn=new AsyncFunction('getInvoicePrintHtml','printWithQz','updatePrintStatus','networkPrint','selectNetworkPrinter','window','orderId','posProfile','printFormat',body(orchestration,'printOrder'));
   const invoke=()=>fn(null,null,async()=>{updates++;},network,network,{},'REG-TEST',{
    print_type:'network',cashier:'cashier',multiple_cashier:multiple,name:'profile',printer:'queue',print_format:'receipt'
   },null);
   if(fail)await assert.rejects(invoke);else assert.equal(await invoke(),'network');
   assert.equal(updates,fail?0:1);checks++;
  }
 }
 console.log(`${checks} print submission assertions passed.`);
})().catch(e=>{console.error(e);process.exitCode=1;});
