import {spawn} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {z} from 'zod';
import {createModuleServer,ModuleError} from '../../lib/module-server.mjs';
import {stateRoot} from '../../lib/accounts.mjs';
const root=fileURLToPath(new URL('../../../tweetkit-x/',import.meta.url));
export const catalog=JSON.parse(readFileSync(join(root,'tweetkit_x/operations.json'),'utf8'));
function schema(s){
 let v=s.type==='string'?z.string():s.type==='integer'?z.number().int():s.type==='boolean'?z.boolean():z.array(schema(s.items));
 if(s.minimum!==undefined)v=v.min(s.minimum);if(s.maximum!==undefined)v=v.max(s.maximum);
 if(s.minLength!==undefined)v=v.min(s.minLength);if(s.maxLength!==undefined)v=v.max(s.maxLength);
 if(s.minItems!==undefined)v=v.min(s.minItems);if(s.maxItems!==undefined)v=v.max(s.maxItems);
 if(s.pattern)v=v.regex(new RegExp(s.pattern));if(s.enum)v=v.refine(x=>s.enum.includes(x));
 if(s.default!==undefined)v=v.default(s.default);else if(s.optional)v=v.optional();return v;
}
export const schemas=Object.fromEntries(Object.entries(catalog).map(([op,s])=>[op,z.strictObject(Object.fromEntries(Object.entries(s.fields).map(([k,v])=>[k,schema(v)])))]));
export function run(operation,input,cookie){return new Promise((resolve,reject)=>{
 const p=spawn(join(root,'.venv/bin/python'),['-m','tweetkit_x.runner'],{cwd:root,env:{PATH:'/usr/bin:/bin',PYTHONNOUSERSITE:'1',PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
 let output='',overflow=false,timedout=false;
 const timer=setTimeout(()=>{timedout=true;p.kill('SIGKILL');},55000);
 p.stdout.on('data',b=>{if(Buffer.byteLength(output)+b.length>2_000_000){overflow=true;p.kill('SIGKILL');}else output+=b;});p.stderr.resume();p.stdin.on('error',()=>{});
 p.on('error',()=>{clearTimeout(timer);reject(new ModuleError('runner_unavailable','X runner unavailable',503));});
 p.on('close',()=>{clearTimeout(timer);
  if(timedout||overflow)return reject(new ModuleError('outcome_unknown','X operation interrupted; inspect state before repeating any write.',504));
  try{const parsed=JSON.parse(output);if(!parsed.ok)throw new ModuleError('x_request_failed',String(parsed.error).slice(0,250),502);resolve(parsed.result);}catch(e){reject(e instanceof ModuleError?e:new ModuleError('runner_failed','Unexpected X runner response; outcome may be unknown.',502));}
 });
 p.stdin.end(JSON.stringify({operation,input,cookie}));
});}
export function createTweetkitServer({resolve,session,runner=run,pinPath=join(stateRoot,'tweetkit-identity.json')}={}){
 let pending=false;
 const operations=Object.fromEntries(Object.entries(catalog).map(([op,spec])=>[op,async(input,{account})=>{
   if(account.id!=='tweetkit-personal')throw new ModuleError('account_not_configured','X bridge is bound to the personal account.',403);
   const parsed=schemas[op].safeParse(input);if(!parsed.success)throw new ModuleError('invalid_input','Input does not match the operation schema.',400);
   if(pending)throw new ModuleError('busy','Another X operation is running; no retry was attempted.',409);
   pending=true;
   try{
    let auth;try{auth=await session();}catch(e){const code=['x_tab_required','x_login_required','x_identity_required','ambiguous_session'].includes(e.message)?e.message:'browser_unavailable';throw new ModuleError(code,'Open X in the connected Chrome profile and sign in; session is unavailable.',409);}
    if(!auth?.cookie||!/^\d+$/.test(auth.userId))throw new ModuleError('session_unavailable','Chrome session is unavailable.',409);
    let pin;try{pin=JSON.parse(readFileSync(pinPath,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
    if(!pin){
      if(spec.write)throw new ModuleError('identity_not_pinned','Run status first to establish the account identity.',409);
      mkdirSync(stateRoot,{recursive:true,mode:0o700});writeFileSync(pinPath,JSON.stringify({userId:auth.userId})+'\n',{flag:'wx',mode:0o600});pin={userId:auth.userId};
    }
    if(pin.userId!==auth.userId)throw new ModuleError('account_changed','X account differs from the linked identity; refusing the operation.',403);
    if(op==='status')return {sessionPresent:true,userId:auth.userId,networkVerified:false,operations:Object.keys(catalog).length,unsupported:['direct messages','list management','Spaces'],transport:'local Chrome session'};
    return await runner(op,parsed.data,auth.cookie);
   }finally{pending=false;}
 }]));
 return createModuleServer({module:'tweetkit',service:'tweetkit-bridge',maxBody:350000,operations,...(resolve?{resolve}:{})});
}
