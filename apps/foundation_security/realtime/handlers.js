'use strict';
const fs = require('fs');
const LOG = process.env.FOUNDATION_REALTIME_BOOT_LOG;
function lg(msg){ try{if(LOG){fs.appendFileSync(LOG,'[rt-guard '+new Date().toISOString()+'] '+String(msg).slice(0,600)+'\n');}}catch(e){} }
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
    if(!socket.foundationResourceGuard || !socket.connected || !args){
        lg('allowed deny pre: guard='+!!socket.foundationResourceGuard+' connected='+socket.connected+' args='+!!args+' room='+room);
        return false;
    }
    try {
        const response=await socket.frappe_request('/api/method/foundation_security.realtime.authorize',args,{signal:AbortSignal.timeout(5000)});
        const ok = response.ok && (await response.json()).message===true;
        lg('allowed room='+room+' user='+socket.user+' -> '+ok+' (http '+response.status+')');
        return ok;
    }catch(e){lg('allowed error room='+room+': '+String(e&&e.message||e).slice(0,200));return false;}
}
module.exports=function(socket) {
    socket.foundationResourceGuard=true;
    // Expose per-socket authorizer for the adapter wrapper.
    socket.__foundationAuthorized = function(room){ return allowed(socket,room); };
    lg('guard attached socket='+socket.id+' nsp='+socket.nsp.name+' user='+socket.user);
    // Drop any rooms the socket is sitting in that were joined before the guard
    // was installed (i.e. the default frappe auth-time user:<sid> room stays).
    for(const room of [...socket.rooms]) if(room!==socket.id && room!=='user:'+socket.user){
        lg('leaking pre-guard room '+room+' for socket '+socket.id);
        socket.leave(room);
    }
    // Remove native unchecked subscribe handlers and replace with checked ones.
    for(const event of ['doctype_subscribe','task_subscribe','progress_subscribe','doc_subscribe','doc_open','open_in_editor']) socket.removeAllListeners(event);
    function subscribe(event,roomFor) {
        socket.on(event,async function(...args){
            const room=roomFor(...args);
            const ok = await allowed(socket,room);
            lg('subscribe event='+event+' room='+room+' user='+socket.user+' ok='+ok);
            if(ok) socket.join(room);
        });
    }
    subscribe('doc_subscribe',function(dt,name){return 'doc:'+dt+'/'+name;});
    subscribe('doc_open',function(dt,name){return 'open_doc:'+dt+'/'+name;});
    subscribe('task_subscribe',function(id){return 'task_progress:'+id;});
    subscribe('progress_subscribe',function(id){return 'task_progress:'+id;});
};
module.exports.resource=resource;
