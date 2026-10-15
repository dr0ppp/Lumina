/* Pure JavaScript startup regression test; no browser, file picker or network. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function main() {
  const nodes = new Map();
  function node() { return {value:'',checked:false,disabled:false,hidden:false,textContent:'',children:[],
    addEventListener(){},appendChild(child){this.children.push(child);},removeChild(){this.children.shift();},
    get firstChild(){return this.children[0];}}; }
  const replaced=[];
  const requests=[];
  const ctx={console, document:{getElementById(id){if(!nodes.has(id)) nodes.set(id,node()); return nodes.get(id);},createElement:node},
    location:{origin:'http://127.0.0.1:8765',pathname:'/',hash:'#test-connection-token'},
    history:{replaceState(...args){replaced.push(args);}},
    fetch:async(url,options)=> {requests.push({url,options}); return {ok:true,json:async()=>({result:url.endsWith('/status')?{connected:true,provider:null}:[]})};}};
  ctx.window=ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/lumina/app/assets/panel.js'),'utf8'),ctx);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(typeof ctx.history.replaceState,'function','UI must not shadow browser history');
  assert.equal(replaced.length,1,'connection token removed from address');
  assert.equal(nodes.get('connection-state').textContent,'已连接本机');
  assert.equal(nodes.get('apply').disabled,true);
  assert.equal(nodes.get('consent').checked,false);
  assert.equal(requests.length,3);
  for(const request of requests) assert.equal(request.options.headers.Authorization,'Bearer test-connection-token');
  console.log('Panel automatic connection regression passed (no real network).');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
