'use strict';
const fs = require('fs');
const http = require('http');
const LOG = process.env.FOUNDATION_REALTIME_BOOT_LOG;
const GUARDED = Symbol.for('foundation.resource.broadcast.guard');
function lg(msg){ try{if(LOG){fs.appendFileSync(LOG,'[rt-guard '+new Date().toISOString()+'] '+String(msg).slice(0,600)+'\n');}}catch(e){} }
function stripSitePrefix(room) {
    // Frappe v14/15 sockets live in a single io (no per-site namespace), so
    // rooms are prefixed with "<site>:" e.g. "foundation.localhost:doc:Student/STUD-1".
    // Frappe v16+ uses per-site namespaces ("/foundation.localhost") and bare
    // room names like "doc:Student/STUD-1". Recognize both by stripping an
    // optional site prefix — any token that precedes a known suffix.
    const suffixes = ['user:','task_progress:','doc:','open_doc:','doctype:','all','website'];
    for(const s of suffixes){
        const idx = room.indexOf(':'+s);
        if(idx>0){
            const head = room.slice(0,idx);
            // A site prefix must look like a hostname (no colon, no slash,
            // contains a dot or equals "localhost").
            if(head && !head.includes(':') && !head.includes('/')){
                return {site:head,suffix:room.slice(idx+1)};
            }
        }
    }
    return {site:null,suffix:room};
}
function resource(room) {
    if(typeof room!=='string'||room.length>1024)return null;
    const {suffix} = stripSitePrefix(room);
    if(suffix.startsWith('user:'))return {kind:'user',resource:suffix.slice(5)};
    if(suffix.startsWith('task_progress:'))return {kind:'task',resource:suffix.slice(14)};
    // doctype:* rooms are NOT re-authorized: DocType-level broadcasts carry
    // aggregate list-view events without a per-record authorization contract,
    // so the adapter wrapper drops them outright.
    if(suffix.startsWith('doctype:'))return null;
    for(const prefix of ['doc:','open_doc:']) if(suffix.startsWith(prefix)) {
        const key=suffix.slice(prefix.length), slash=key.indexOf('/');
        if(slash<1)return null;
        return {kind:'document',resource:key.slice(0,slash),name:key.slice(slash+1)};
    }
    return null;
}
function getSiteName(socket) {
    try {
        const nsp=socket&&socket.nsp&&socket.nsp.name;
        if(nsp&&nsp.length>1&&nsp.startsWith('/'))return nsp.slice(1);
    }catch(e){}
    try{if(socket.site_name)return socket.site_name;}catch(e){}
    try{const h=socket.request&&socket.request.headers;const s=h&&(h['x-frappe-site-name']);if(s)return s;if(h&&h.origin){const u=new URL(h.origin);return u.hostname;}}catch(e){}
    return 'localhost';
}
function authorizeRequest(socket,args,timeoutMs) {
    // Direct loopback request to the local bench web server using the sid
    // cookie from the authenticated socket. Avoids relying on get_url(),
    // which points at the proxied origin (8080/9000) rather than the
    // authoritative 127.0.0.1:8000 web server.
    return new Promise(function(resolve){
        try{
            const site=getSiteName(socket);
            // URLSearchParams percent-encodes '/' which is significant in
            // document names like 'Student/STUD-0001'; build the query by
            // hand so names pass through verbatim.
            const parts=[];
            for(const k of Object.keys(args||{})){
                parts.push(encodeURIComponent(k)+'='+encodeURIComponent(String(args[k])));
            }
            const path='/api/method/foundation_security.realtime.authorize?'+parts.join('&');
            const headers={'Host':site,'X-Frappe-Site-Name':site};
            if(socket.sid){headers['Cookie']='sid='+encodeURIComponent(socket.sid);}
            else if(socket.authorization_header){headers['Authorization']=socket.authorization_header;}
            const req=http.request({host:'127.0.0.1',port:8000,path,method:'GET',headers,timeout:timeoutMs||5000},function(res){
                let body='';res.setEncoding('utf8');res.on('data',function(c){body+=c;});
                res.on('end',function(){
                    let ok=false;
                    try{ok=res.statusCode===200&&JSON.parse(body).message===true;}catch(e){lg('authorize json parse err '+e+' body='+String(body).slice(0,200));}
                    lg('authorize site='+site+' kind='+args.kind+' resource='+args.resource+' user='+socket.user+' http='+res.statusCode+' ok='+ok);
                    resolve({status:res.statusCode||0,ok:!!ok,json:async()=>({message:ok})});
                });
            });
            req.on('timeout',function(){try{req.destroy();}catch(e){}resolve({status:0,ok:false,json:async()=>({message:false})});});
            req.on('error',function(e){lg('authorize request err: '+String(e&&e.message||e).slice(0,200));resolve({status:0,ok:false,json:async()=>({message:false})});});
            req.end();
        }catch(e){lg('authorize setup err: '+e);resolve({status:0,ok:false,json:async()=>({message:false})});}
    });
}
async function allowed(socket,room) {
    const args=resource(room);
    if(!socket.foundationResourceGuard || !socket.connected || !args){
        lg('allowed deny pre: guard='+!!socket.foundationResourceGuard+' connected='+socket.connected+' args='+!!args+' room='+room);
        return false;
    }
    try {
        // Prefer socket.frappe_request when present (v15/v16 middleware
        // installs it with the correct X-Frappe-Socket-Secret and auth
        // headers), but construct the query string manually so '/' in
        // document names is preserved (URLSearchParams percent-encodes
        // '/' to '%2F', which fails frappe's document lookup). Fall
        // back to our loopback authorizeRequest for older/v14 layouts
        // where socket.frappe_request does not exist.
        let response;
        if(typeof socket.frappe_request === 'function'){
            const parts=[];
            for(const k of Object.keys(args||{})){
                parts.push(encodeURIComponent(k)+'='+encodeURIComponent(String(args[k])));
            }
            const path='/api/method/foundation_security.realtime.authorize?'+parts.join('&');
            // socket.frappe_request(path, args, opts) signs the request
            // but we have already built a full path with query string,
            // so pass empty args.
            response=await socket.frappe_request(path, {}, {signal:AbortSignal.timeout(5000)});
        }else{
            response=await authorizeRequest(socket,args,5000);
        }
        const ok = response.ok && (await response.json()).message===true;
        lg('allowed room='+room+' user='+socket.user+' -> '+ok+' (http '+response.status+')');
        return ok;
    }catch(e){lg('allowed error room='+room+': '+String(e&&e.message||e).slice(0,200));return false;}
}
function wrapAdapter(nsp) {
    if(!nsp || !nsp.adapter || nsp.adapter[GUARDED]) return;
    nsp.adapter[GUARDED] = true;
    const broadcast = nsp.adapter.broadcast.bind(nsp.adapter);
    nsp.adapter.broadcast = function(packet,opts) {
        try {
            // Never guess which resource an unscoped or multi-room payload
            // belongs to. Only a single resource room proceeds.
            if(!opts || !opts.rooms || opts.rooms.size !== 1) return;
            let room = null;
            for(const r of opts.rooms){ room=r; break; }
            const args = resource(room);
            if(!args) return; // not a guarded room shape (e.g. user:<sid>, all, website)
            // Resource room: re-authorize every subscribed socket.
            const candidates = [];
            if(nsp.sockets instanceof Map) {
                nsp.sockets.forEach(function(s){
                    if(s && s.connected && s.rooms && s.rooms.has(room)) candidates.push(s);
                });
            }
            if(opts.except && opts.except.size) {
                for(let i=candidates.length-1;i>=0;i--){
                    if(opts.except.has(candidates[i].id)) candidates.splice(i,1);
                }
            }
            Promise.all(candidates.map(function(s){
                return s.__foundationAuthorized ? s.__foundationAuthorized(room).then(function(ok){return ok?s:null;}) : Promise.resolve(null);
            })).then(function(authorized){
                const ids = new Set();
                authorized.forEach(function(s){ if(s && s.connected) ids.add(s.id); });
                lg('broadcast room='+room+' candidates='+candidates.length+' authorized='+ids.size);
                if(ids.size) {
                    const newOpts = Object.assign({}, opts);
                    newOpts.rooms = ids;
                    newOpts.except = new Set();
                    broadcast(packet, newOpts);
                }
            }).catch(function(e){lg('broadcast auth err: '+e);});
        } catch(e) { lg('broadcast wrapper err: '+e); }
    };
}
module.exports=function(socket) {
    socket.foundationResourceGuard=true;
    socket.__foundationAuthorized = function(room){ return allowed(socket,room); };
    lg('guard attached socket='+socket.id+' nsp='+(socket.nsp&&socket.nsp.name)+' user='+socket.user);
    wrapAdapter(socket.nsp);
    // Evict any guarded resource rooms (doc:*, open_doc:*, task_progress:*,
    // doctype:*) the socket may have been auto-joined into before our
    // guard ran. Keep identity (socket.id), per-user room (user:<sid>),
    // and default broadcast rooms (all/website/...) which frappe core
    // joins before/around app handlers and which carry no per-record data.
    function isGuardedRoom(r){
        if(typeof r!=='string') return false;
        const s = stripSitePrefix(r).suffix;
        return s.startsWith('doc:')||s.startsWith('open_doc:')||s.startsWith('task_progress:')||s.startsWith('doctype:');
    }
    // Rooms are bare names like 'doc:Student/a' when the socket is in a
    // per-site namespace (v15+) or '<site>:doc:Student/a' when the socket
    // is in the root io (legacy v14 single-io mode). Detect namespaces by
    // checking nsp.name: '/' is the root namespace; anything else is a
    // per-site child namespace that uses bare room names.
    function sitePrefix(){
        const nspName = socket.nsp && socket.nsp.name;
        if(typeof nspName === 'string' && nspName.length > 1 && nspName !== '/') return '';
        if(socket.site_name) return socket.site_name+':';
        return '';
    }
    const SP = sitePrefix();
    for(const room of [...socket.rooms]) if(isGuardedRoom(room) && room!==socket.id){
        lg('evicting pre-guard resource room '+room+' for socket '+socket.id);
        socket.leave(room);
    }
    // Wrap socket.join so that ANY attempt to join a guarded resource room
    // — whether from our guarded listeners, from frappe core's own
    // subscribe handlers which run AFTER installed apps, or from any
    // future third-party code — is re-authorized before the socket
    // actually joins. Non-resource rooms pass through untouched. join()
    // accepts a string, an Array or a Set of rooms; each guarded room is
    // authorized individually.
    const origJoin = socket.join.bind(socket);
    socket.join = async function(rooms, ...rest){
        const list = (rooms instanceof Set) ? [...rooms] : (Array.isArray(rooms) ? rooms : [rooms]);
        const okRooms = [];
        for(const room of list){
            if(typeof room !== 'string' || !isGuardedRoom(room) || room===socket.id){ okRooms.push(room); continue; }
            const args = resource(room);
            if(!args){ lg('reject join unrecognized shape '+room+' for '+socket.id); continue; }
            const ok = await allowed(socket,room);
            lg('join room='+room+' user='+socket.user+' ok='+ok);
            if(ok) okRooms.push(room);
        }
        if(okRooms.length===0) return socket;
        return origJoin(okRooms.length===1?okRooms[0]:okRooms, ...rest);
    };
    // Suppress frappe core's own subscribe listeners (added after our
    // handler by v16 realtime/handlers.js and which would otherwise join
    // rooms based only on an HTTP has_permission call that we do not
    // trust to re-run against the current session). Replace them with
    // guarded handlers that use our wrapped join.
    const GUARDED_EVENTS = new Set(['doctype_subscribe','task_subscribe','progress_subscribe','doc_subscribe','doc_open','open_in_editor']);
    const origOn = socket.on.bind(socket);
    socket.on = function(event, handler) {
        if(GUARDED_EVENTS.has(event)) {
            lg('suppress insecure handler registration for event='+event+' socket='+socket.id);
            return socket;
        }
        return origOn(event, handler);
    };
    function subscribe(event,roomFor) {
        origOn(event,async function(...args){
            const room=SP+roomFor(...args);
            // socket.join is now our guarded wrapper; it will re-authorize.
            try{ await socket.join(room); }catch(e){ lg('subscribe err: '+e); }
        });
    }
    subscribe('doc_subscribe',function(dt,name){return 'doc:'+dt+'/'+name;});
    subscribe('doc_open',function(dt,name){return 'open_doc:'+dt+'/'+name;});
    subscribe('task_subscribe',function(id){return 'task_progress:'+id;});
    subscribe('progress_subscribe',function(id){return 'task_progress:'+id;});
    // doctype_subscribe has no per-record authorization contract; reject it.
    origOn('doctype_subscribe',function(){
        lg('reject doctype_subscribe from user='+socket.user);
    });
};
module.exports.resource=resource;
module.exports.wrapAdapter=wrapAdapter;

