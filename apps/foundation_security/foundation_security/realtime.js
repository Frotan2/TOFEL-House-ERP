// Dual entry point for frappe socketio.
//
// Frappe loads per-app realtime hooks from apps/<app>/<app>/realtime.js with
// one of two conventions depending on version:
//   (a) server-factory: the module receives the socket.io Server and must
//       register its own `connection` listeners;
//   (b) per-socket: the module is invoked once per connected Socket, after
//       frappe's auth handler has populated socket.user / sid.
//
// Either way, the guard (../realtime/handlers.js) must be attached to every
// socket that arrives on *any* namespace, because frappe v14+ multiplexes
// per-site traffic onto site-named namespaces (e.g. /foundation.localhost),
// not the default `/` namespace.
'use strict';
const fs = require('fs');
const guard = require('../realtime/handlers');
const LOG = process.env.FOUNDATION_REALTIME_BOOT_LOG;
function log(msg) {
    try { if (LOG) fs.appendFileSync(LOG, `[rt-entry ${new Date().toISOString()}] ${msg}\n`); } catch {}
}
function apply(socket) {
    try {
        if (!socket || !socket.nsp) return log('apply: no socket/nsp');
        log(`apply socket id=${socket.id} nsp=${socket.nsp.name} user=${socket.user}`);
        guard(socket);
    } catch (e) {
        log(`apply error: ${String(e && e.stack || e)}`);
        try { socket.disconnect(true); } catch {}
    }
}
function installNsp(nsp) {
    if (nsp[Symbol.for('foundation.nsp.installed')]) return;
    nsp[Symbol.for('foundation.nsp.installed')] = true;
    log(`install namespace ${nsp.name}`);
    nsp.on('connection', apply);
}
function serverFactory(io) {
    if (!io || typeof io.of !== 'function') return false;
    try {
        for (const nsp of io._nsps.values()) installNsp(nsp);
    } catch (e) { log(`iter nsps err: ${e}`); }
    if (io.sockets && io.sockets.on) io.sockets.on('connection', apply);
    if (typeof io.on === 'function') {
        try { io.on('new_namespace', installNsp); }
        catch (e) { log(`new_namespace hook err: ${e}`); }
    }
    // v2 compatibility: if io.of(/^\/.+/) pattern is needed
    return true;
}
module.exports = function(entry) {
    if (serverFactory(entry)) {
        log(`loaded as server factory; nsps=${require('util').inspect([...(entry._nsps||[]).map?.(p=>p) || '?'])}`);
        return;
    }
    if (entry && entry.nsp) {
        log('loaded as per-socket hook');
        apply(entry);
        return;
    }
    log(`unknown arg: ${typeof entry}`);
};
module.exports.apply = apply;
module.exports.installNsp = installNsp;
