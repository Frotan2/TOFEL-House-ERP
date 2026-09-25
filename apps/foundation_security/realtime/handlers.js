 'use strict';
const fs = require('fs');
const guarded = Symbol.for('foundation.resource.broadcast.guard');
const LOG = process.env.FOUNDATION_REALTIME_BOOT_LOG;
function lg(msg){ try{if(LOG){fs.appendFileSync(LOG,'[rt-guard '+new Date().toISOString()+'] '+String(msg).slice(0,600)+'\n');}}catch(e){} }
function safeStringify(o){try{return JSON.stringify(o,(k,v)=>{
   if(v instanceof Set)return [...v];
   if(v instanceof Error)return {message:v.message};
   return v;
 },2);}catch(e){return String(o);}}
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
 if(!socket.foundationResourceGuard || !socket.connected || !args){lg(`allowed deny pre: guard=${!!socket.foundationResourceGuard} connected=${socket.connected} args=${!!args} room=${room}`);return false;}
 try {
  const response=await socket.frappe_request('/api/method/foundation_security.realtime.authorize',args,{signal:AbortSignal.timeout(5000)});
  const ok = response.ok && (await response.json()).message===true;
  lg(`allowed room=${room} user=${socket.user} -> ${ok} (http ${response.status})`);
  return ok;
 }catch(e){lg(`allowed error room=${room}: ${String(e&&e.message||e).slice(0,200)}`);return false;}
}
module.exports=function(socket) {
 socket.foundationResourceGuard=true;
 const adapter=socket.nsp.adapter;
 lg(`guard attached socket=${socket.id} nsp=${socket.nsp.name} user=${socket.user} adapterGuarded=${!!adapter[guarded]}`);
 if(!adapter[guarded]) {
  adapter[guarded]=true;
  const broadcast=adapter.broadcast.bind(adapter);
  adapter.broadcast=function(packet,opts) {
   // Never guess which resource an unscoped or multi-resource payload belongs to.
   if(!opts.rooms || opts.rooms.size!==1){lg(`broadcast skip multi/no room rooms=${opts.rooms?opts.rooms.size:0}`);return;}
   const room=[...opts.rooms][0];
   const args = resource(room);
   if(!args){return;} // not a guarded room shape (e.g. user:<sid>)
   const candidates=[...socket.nsp.sockets.values()].filter(s=>s.rooms.has(room)&&![...(opts.except||[])].some(r=>s.rooms.has(r)));
   lg(`broadcast room=${room} candidates=${candidates.map(c=>c.user+'/'+c.id).join(',')}`);
   Promise.all(candidates.map(async s=>await allowed(s,room)?s:null)).then(sockets=>{
    const ids=new Set(sockets.filter(s=>s&&s.connected).map(s=>s.id));
    lg(`broadcast authorized ids=${[...ids].join(',')}`);
    // Explicit checked recipients: a new room join cannot race into this packet.
    if(ids.size)broadcast(packet,{...opts,rooms:ids,except:new Set()});
   }).catch(e=>{lg(`broadcast auth err: ${e}`);}); // authorization/backend outage fails closed
  };
 }
 for(const room of [...socket.rooms]) if(room!==socket.id && room!==`user:${socket.user}`)socket.leave(room);
 // Remove native unchecked or subscribe-once handlers. Every broadcast is also
 // reauthorized; revoking a live session/scope therefore stops subsequent data.
 for(const event of ['doctype_subscribe','task_subscribe','progress_subscribe','doc_subscribe','doc_open','open_in_editor'])socket.removeAllListeners(event);
 function subscribe(event,roomFor) {
  socket.on(event,async(...args)=>{
    const room=roomFor(...args);
    const ok = await allowed(socket,room);
    lg(`subscribe event=${event} room=${room} user=${socket.user} ok=${ok}`);
    if(ok) socket.join(room);
  });
 }
 subscribe('doc_subscribe',(dt,name)=>`doc:${dt}/${name}`);
 subscribe('doc_open',(dt,name)=>`open_doc:${dt}/${name}`);
 subscribe('task_subscribe',id=>`task_progress:${id}`);
 subscribe('progress_subscribe',id=>`task_progress:${id}`);
};
module.exports.resource=resource;
