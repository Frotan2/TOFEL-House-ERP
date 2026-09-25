// Entry point wired by frappe's socketio.js.
//
// Frappe loads per-app realtime hooks in one of two conventions, depending on
// version: (a) the module receives the socket.io Server and must register its
// own listeners; (b) the module is invoked once per connected Socket. We
// support both. Either way the broadcast/join guard must attach to every
// socket on every namespace (including per-site namespaces like
// /foundation.localhost), because clients connect to those namespaces, not
// the default '/'.
'use strict';
let guard;
try { guard = require('../realtime/handlers'); }
catch (e) {
    // Fail open only into a log line — if guard doesn't load, we have no
    // authorization; the bootstrap log will show the error.
    process.stderr.write('[foundation_security realtime] failed to load handlers: ' + (e && e.stack || e) + '\n');
    module.exports = function(){};
    return;
}
function log(msg) {
    try {
        if (process.env.FOUNDATION_REALTIME_BOOT_LOG) {
            require('fs').appendFileSync(process.env.FOUNDATION_REALTIME_BOOT_LOG,
                '[rt-entry ' + new Date().toISOString() + '] ' + msg + '\n');
        }
    } catch {}
}
process.on('uncaughtException', e => log('uncaughtException: ' + (e && e.stack || e)));
process.on('unhandledRejection', e => log('unhandledRejection: ' + (e && e.stack || e)));
function apply(socket) {
    if (!socket || !socket.nsp) return;
    try {
        log('apply socket id=' + socket.id + ' nsp=' + socket.nsp.name + ' user=' + socket.user);
        guard(socket);
    } catch (e) {
        log('apply error: ' + String(e && e.stack || e).slice(0,800));
        try { socket.disconnect(true); } catch {}
    }
}
function installNsp(nsp) {
    if (!nsp || nsp.__foundationInstalled) return;
    nsp.__foundationInstalled = true;
    try {
        log('install namespace ' + nsp.name);
        nsp.on('connection', apply);
        // Retro-actively guard sockets already on this namespace (late attach).
        if (nsp.sockets instanceof Map) {
            for (const s of nsp.sockets.values()) apply(s);
        }
    } catch (e) { log('installNsp ' + nsp.name + ' err: ' + e); }
}
function installServer(io) {
    try {
        const nsps = io._nsps;
        if (nsps && typeof nsps.forEach === 'function') {
            nsps.forEach(nsp => installNsp(nsp));
        }
        if (typeof io.on === 'function') io.on('new_namespace', installNsp);
        log('installed on server');
    } catch (e) { log('installServer err: ' + e); }
}
module.exports = function(entry) {
    try {
        if (entry && typeof entry.of === 'function') {
            // socket.io Server instance
            installServer(entry);
            return;
        }
        if (entry && entry.nsp) {
            // single socket
            apply(entry);
            return;
        }
        log('unknown entry arg type=' + typeof entry);
    } catch (e) { log('module error: ' + e); }
};
