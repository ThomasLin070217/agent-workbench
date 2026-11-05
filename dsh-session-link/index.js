import {readFile,writeFile,mkdir,rename} from 'node:fs/promises';
import {dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
export const inject=['connection'];
export function apply(ctx, config={}) {
 const mailbox=config.mailboxFile || fileURLToPath(new URL('../.state/native-handoff.json',import.meta.url));
 const ack=mailbox+'.ack'; const health=mailbox+'.health';
 const read=async path=>{try{return JSON.parse(await readFile(path,'utf8'));}catch{return null;}};
 const save=async(path,data)=>{await mkdir(dirname(path),{recursive:true});const tmp=path+'.'+process.pid+'.tmp';await writeFile(tmp,JSON.stringify(data),{mode:0o600});await rename(tmp,path);};
 ctx.connection.fetch.register({path:'/api/sharednet.handoff',methods:['GET','POST'],requestBody:'buffered',fetch:async request=>{
   if(request.method==='GET'){
    const req=await read(mailbox), done=await read(ack);
    const valid=req && /^session-[0-9a-f-]{36}$/.test(req.session_id) && req.expires_at>Date.now() && req.id!==done?.id;
    return Response.json(valid?req:null,{headers:{'cache-control':'no-store'}});
   }
   const body=await request.json();
   if(body.status==='heartbeat'){
    await save(health,{time:Date.now(),selected:body.selected||null});
    return Response.json({ok:true});
   }
   const req=await read(mailbox);
   if(!req || body.id!==req.id || body.session_id!==req.session_id || !['selected','failed'].includes(body.status))return Response.json({ok:false},{status:400});
   await save(ack,{id:req.id,session_id:req.session_id,status:body.status,time:Date.now()});
   return Response.json({ok:true});
 }});
}
