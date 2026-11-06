import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createTweetkitServer,schemas,catalog} from '../server.mjs';
import {readXSession} from '../../chrome/x-session.mjs';
const fixture={cookie:'auth_token=synthetic-secret; ct0=synthetic-csrf; twid=u%3D123',userId:'123'};
async function serverTest(fn,options={}){
 const dir=mkdtempSync(join(tmpdir(),'tweetkit-test-'));let calls=0;
 const server=createTweetkitServer({resolve:h=>h==='Bearer test'?{id:'tweetkit-personal'}:h==='Bearer other'?{id:'different-account'}:null,session:async()=>fixture,runner:async()=>{calls++;return {ok:true};},pinPath:join(dir,'identity.json'),...options});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const url='http://127.0.0.1:'+server.address().port;
 const call=(operation,input={},headers={authorization:'Bearer test'})=>fetch(url+'/rpc',{method:'POST',headers,body:JSON.stringify({operation,input})});
 try{await fn({call,url,dir,calls:()=>calls});}finally{server.closeAllConnections();await new Promise(r=>server.close(r));rmSync(dir,{recursive:true,force:true});}
}
test('all operations have strict schemas; no raw cookies, paths or bulk deletion',()=>{
 for(const [op,s] of Object.entries(schemas)){assert.equal(s.safeParse({cookie:'secret'}).success,false);}
 assert(!catalog.deleteMany);assert(!catalog.setSessionCookie);
 assert.equal(schemas.publish.safeParse({text:'hi',image_path:'/etc/passwd'}).success,false);
});
test('authentication and Origin rejection occur before browser access',()=>serverTest(async({call,calls})=>{
 assert.equal((await call('status',{},{})).status,401);
 assert.equal((await call('status',{}, {authorization:'Bearer test',origin:'https://evil.test'})).status,403);
 assert.equal((await call('status',{}, {authorization:'Bearer other'})).status,403);assert.equal(calls(),0);
}));
test('writes require pinned identity; status returns no cookie',()=>serverTest(async({call,calls})=>{
 assert.equal((await call('publish',{text:'hi'})).status,409);
 const status=await (await call('status')).text();assert(!status.includes('synthetic-secret'));assert(!status.includes('synthetic-csrf'));
 assert.equal((await call('profile',{username:'test'})).status,200);assert.equal(calls(),1);
}));
test('changed browser identity fails closed',()=>serverTest(async({call,dir,calls})=>{
 writeFileSync(join(dir,'identity.json'),JSON.stringify({userId:'456'}));
 assert.equal((await call('profile',{username:'test'})).status,403);assert.equal(calls(),0);
}));
test('unknown operations and invalid inputs cannot start requests',()=>serverTest(async({call,calls})=>{
 assert.equal((await call('constructor')).status,404);
 assert.equal((await call('home',{limit:100000})).status,400);assert.equal(calls(),0);
}));
test('session handoff requests only x.com cookies and filters unrelated values',async()=>{
 const requests=[];
 const result=await readXSession(async(op,input)=>{requests.push({op,input});if(op==='tabs.list')return [{id:1,url:'https://x.com/home'}];return {cookies:[{name:'auth_token',value:'secret',domain:'.x.com',secure:true},{name:'ct0',value:'csrf',domain:'x.com',secure:true},{name:'twid',value:'u%3D123',domain:'.x.com',secure:true},{name:'unrelated',value:'never-export',domain:'.x.com',secure:true},{name:'auth_token',value:'foreign',domain:'evil.test',secure:true}]};});
 assert.equal(result.userId,'123');assert(!result.cookie.includes('never-export'));assert(!result.cookie.includes('foreign'));assert.deepEqual(requests[1].input.params,{urls:['https://x.com/']});
});
test('session handoff fails without an existing X tab',async()=>{await assert.rejects(readXSession(async()=>[]),/x_tab_required/);});
