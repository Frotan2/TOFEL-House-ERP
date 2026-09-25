// Socket.IO room authorization hook for foundation_security.
//
// Loaded by frappe's socketio.js at apps/<app>/<app>/realtime.js (and, via
// a shim, apps/<app>/realtime.js). Handles both loading conventions:
//   * Server factory: module receives the socket.io Server; installs
//     the guard on every existing and future namespace via the
//     new_namespace event so per-site namespaces (e.g.
//     /foundation.localhost) are covered. handlers.js installs safe
//     subscribe handlers and wraps adapter.broadcast for delivery-time
//     re-authorization on the first socket that arrives.
//   * Per-socket: module receives a single connected Socket (fallback).
'use strict';
let guard, wrapAdapter;
try {
    guard = require('../realtime/handlers');
    wrapAdapter = guard.wrapAdapter;
} catch (e) {
    process.stderr.write('[foundation_security realtime] failed to load handlers: ' + (e && e.stack || e) + '\n');
    module.exports = function(){};
    return;
}
const fs = require('fs');
function log(msg) {
    try {
        if (process.env.FOUNDATION_REALTIME_BOOT_LOG) {
            fs.appendFileSync(process.env.FOUNDATION_REALTIME_BOOT_LOG,
                '[rt-entry ' + new Date().toISOString() + '] ' + String(msg).slice(0,600) + '\n');
        }
    } catch {}
}
process.on('uncaughtException', function(e){ log('uncaughtException: '+(e&&e.stack||e)); });
process.on('unhandledRejection', function(e){ log('unhandledRejection: '+(e&&e.stack||e)); });
function apply(socket) {
    if (!socket || !socket.nsp) return;
    if (socket.__foundationGuarded) return;
    socket.__foundationGuarded = true;
    try {
        log('apply socket id='+socket.id+' nsp='+socket.nsp.name+' user='+socket.user);
        guard(socket);
    } catch (e) {
        log('apply error: '+String(e&&e.stack||e).slice(0,800));
        try { socket.disconnect(true); } catch(x){}
    }
}
function installNsp(nsp) {
    if (!nsp || nsp.__foundationInstalled) return;
    nsp.__foundationInstalled = true;
    try {
        log('install namespace '+nsp.name);
        wrapAdapter(nsp);
        nsp.on('connection', apply);
        if (nsp.sockets instanceof Map) nsp.sockets.forEach(apply);
    } catch (e) { log('installNsp '+nsp.name+' err: '+e); }
}
function installServer(io) {
    try {
        if (typeof io.on === 'function') io.on('new_namespace', installNsp);
        const nsps = io._nsps;
        if (nsps && typeof nsps.forEach === 'function') nsps.forEach(installNsp);
        log('installed on server; namespaces='+(nsps?nsps.size:'?'));
    } catch (e) { log('installServer err: '+e); }
}
module.exports = function(entry) {
    try {
        if (entry && typeof entry.of === 'function') { installServer(entry); return; }
        if (entry && entry.nsp) { apply(entry); return; }
        log('unknown entry arg type='+typeof entry);
    } catch (e) { log('module error: '+e); }
};
