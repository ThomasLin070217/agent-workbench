/* Desktop-profile plugin: only restores an existing native Session. */
window.__ModuleLoader__.load({id:'@sharednet/dsh-session-link',factory:()=>({
 inject:['uiWorkspace'],
 apply(ctx){
  ctx.effect(()=>{
   let stopped=false,timer,last=null;
   const post=data=>fetch('/api/sharednet.handoff',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
   const poll=async()=>{
    try{
     const response=await fetch('/api/sharednet.handoff',{cache:'no-store'});
     if(!response.ok)throw new Error('handoff unavailable');
     const request=await response.json();
     if(stopped)return;
     if(request && request.id!==last && /^session-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(request.session_id)){
      last=request.id;let status='failed';
      try{ctx.uiWorkspace.openSession(request.session_id);status=ctx.uiWorkspace.selection.getSnapshot().sessionId===request.session_id?'selected':'failed';}catch{}
      await post({id:request.id,session_id:request.session_id,status});
     }
     await post({status:'heartbeat',selected:ctx.uiWorkspace.selection.getSnapshot().sessionId});
    }catch{/* The workbench reports missing desktop acknowledgement; never creates a fallback Session. */}
    finally{if(!stopped)timer=setTimeout(poll,1500);}
   };
   poll();return()=>{stopped=true;clearTimeout(timer);};
  },'sharednet: desktop session handoff');
 }
})});
