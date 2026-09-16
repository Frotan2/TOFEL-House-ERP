// Frappe's app realtime entry point. No upstream files or identity store modified.
// Qualification is pinned to the native in-process Socket.IO adapter contract.
const guarded = Symbol.for('foundation.resource.broadcast.guard');
function resource(room) {
 if(typeof room!=='string'||room.length>1024)return null;
 if(room.startsWith('user:'))return {kind:'user',resource:room.slice(5)};
 if(room.startsWith('task_progress:'))return {kind:'task',resource:room.slice(14)};
 for(const prefix of ['doc:','open_doc:']) if(room.startsWith(prefix)) {
  const key=room.slice(prefix.length), slash=key.indexOf('/');
  if(slash<1)return null;
  return {kind:'document',resource:key.slice(0,slash),name:key.slice(slash+1)};
 }
 return null;
}
async function allowed(socket,room) {
 const args=resource(room);
 if(!socket.foundationResourceGuard || !socket.connected || !args)return false;
 try {
  const response=await socket.frappe_request('/api/method/foundation_security.realtime.authorize',args,{signal:AbortSignal.timeout(5000)});
  return response.ok && (await response.json()).message===true;
 }catch{return false;}
}
module.exports=function(socket) {
 socket.foundationResourceGuard=true;
 const adapter=socket.nsp.adapter;
 if(!adapter[guarded]) {
  adapter[guarded]=true;
  const broadcast=adapter.broadcast.bind(adapter);
  adapter.broadcast=function(packet,opts) {
   // Never guess which resource an unscoped or multi-resource payload belongs to.
   if(!opts.rooms || opts.rooms.size!==1)return;
   const room=[...opts.rooms][0];
   if(!resource(room))return;
   const candidates=[...socket.nsp.sockets.values()].filter(s=>s.rooms.has(room)&&![...(opts.except||[])].some(r=>s.rooms.has(r)));
   Promise.all(candidates.map(async s=>await allowed(s,room)?s:null)).then(sockets=>{
    const ids=new Set(sockets.filter(s=>s&&s.connected).map(s=>s.id));
    // Explicit checked recipients: a new room join cannot race into this packet.
    if(ids.size)broadcast(packet,{...opts,rooms:ids,except:new Set()});
   }).catch(()=>{}); // authorization/backend outage fails closed
  };
 }
 for(const room of [...socket.rooms]) if(room!==socket.id && room!==`user:${socket.user}`)socket.leave(room);
 // Remove native unchecked or subscribe-once handlers. Every broadcast is also
 // reauthorized; revoking a live session/scope therefore stops subsequent data.
 for(const event of ['doctype_subscribe','task_subscribe','progress_subscribe','doc_subscribe','doc_open','open_in_editor'])socket.removeAllListeners(event);
 function subscribe(event,roomFor) {
  socket.on(event,async(...args)=>{const room=roomFor(...args);if(await allowed(socket,room))socket.join(room);});
 }
 subscribe('doc_subscribe',(dt,name)=>`doc:${dt}/${name}`);
 subscribe('doc_open',(dt,name)=>`open_doc:${dt}/${name}`);
 subscribe('task_subscribe',id=>`task_progress:${id}`);
 subscribe('progress_subscribe',id=>`task_progress:${id}`);
};
module.exports.resource=resource;
