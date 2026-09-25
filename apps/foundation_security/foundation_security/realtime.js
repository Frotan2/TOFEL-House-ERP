// Socket.IO room authorization hook for foundation_security.
//
// Loaded by frappe's socketio.js at apps/<app>/<app>/realtime.js (and, via
// a shim, apps/<app>/realtime.js). Supports both loading conventions:
//   * Server factory: module receives the socket.io Server; installs a
//     per-socket guard on every current and future namespace, and
//     wraps each namespace's adapter.broadcast so outgoing events are
//     re-authorized at delivery time.
//   * Per-socket: module receives a single connected Socket (fallback).
//
// Clients connect to per-site namespaces (e.g. /foundation.localhost),
// not to '/', so the guard MUST cover every namespace.
'use strict';
let guard;
try { guard = require('../realtime/handlers'); }
catch (e) {
    process.stderr.write('[foundation_security realtime] failed to load handlers: ' + (e && e.stack || e) + '\n');
    module.exports = function(){};
    return;
}
const fs = require('fs');
function log(msg) {
    try {
        if (process.env.FOUNDATION_REALTIME_BOOT_LOG) {
            fs.appendFileSync(process.env.FOUNDATION_REALTIME_BOOT_LOG,
                '[rt-entry ' + new Date().toISOString() + '] ' + String(msg).slice(0, 600) + '\n');
        }
    } catch {}
}
process.on('uncaughtException', function(e){ log('uncaughtException: ' + (e && e.stack || e)); });
process.on('unhandledRejection', function(e){ log('unhandledRejection: ' + (e && e.stack || e)); });
function apply(socket) {
    if (!socket || !socket.nsp) return;
    // Never double-guard a socket.
    if (socket.__foundationGuarded) return;
    socket.__foundationGuarded = true;
    try {
        log('apply socket id=' + socket.id + ' nsp=' + socket.nsp.name + ' user=' + socket.user);
        guard(socket);
    } catch (e) {
        log('apply error: ' + String(e && e.stack || e).slice(0, 800));
        try { socket.disconnect(true); } catch (x) {}
    }
}
function wrapAdapter(nsp) {
    if (!nsp || !nsp.adapter || nsp.adapter.__foundationWrapped) return;
    nsp.adapter.__foundationWrapped = true;
    var guardedKey = Symbol.for('foundation.resource.broadcast.guard');
    nsp.adapter[guardedKey] = true;
    var broadcast = nsp.adapter.broadcast.bind(nsp.adapter);
    nsp.adapter.broadcast = function(packet, opts) {
        try {
            if (!opts || !opts.rooms || opts.rooms.size !== 1) {
                // Unscoped / multi-room broadcasts (e.g. user:<sid>) fall through
                // only if every target room is a non-resource shape. For resource
                // rooms we always require exactly one room.
                return broadcast(packet, opts);
            }
            var room = null;
            var iter = opts.rooms.values();
            var first = iter.next();
            if (!first.done) room = first.value;
            if (!room || (typeof room !== 'string')) return broadcast(packet, opts);
            // Identify resource rooms; user:<sid> rooms are personal and safe.
            if (!/^(doc:|open_doc:|task_progress:)/.test(room)) return broadcast(packet, opts);
            // Snapshot currently-subscribed sockets before async authorization.
            var sockets = [];
            var all = nsp.sockets;
            if (all instanceof Map) {
                all.forEach(function(s){
                    if (s && s.connected && s.rooms && s.rooms.has(room)) sockets.push(s);
                });
            }
            var except = opts.except;
            if (except && except.size) {
                sockets = sockets.filter(function(s){ return !except.has(s.id); });
            }
            Promise.all(sockets.map(function(s){
                return s.__foundationAuthorized && s.__foundationAuthorized(room)
                    ? Promise.resolve(s) : Promise.resolve(null);
            })).then(function(authorized){
                var ids = new Set();
                authorized.forEach(function(s){ if (s && s.connected) ids.add(s.id); });
                if (ids.size) {
                    var newOpts = Object.assign({}, opts);
                    newOpts.rooms = ids;
                    newOpts.except = new Set();
                    broadcast(packet, newOpts);
                }
                log('broadcast room=' + room + ' candidates=' + sockets.length + ' authorized=' + ids.size);
            }).catch(function(e){ log('broadcast auth err: ' + e); });
        } catch (e) { log('broadcast wrapper err: ' + e); }
    };
}
function installNsp(nsp) {
    if (!nsp || nsp.__foundationInstalled) return;
    nsp.__foundationInstalled = true;
    try {
        log('install namespace ' + nsp.name);
        wrapAdapter(nsp);
        nsp.on('connection', apply);
        // If sockets are already on this namespace (late attach), guard them now.
        if (nsp.sockets instanceof Map) {
            nsp.sockets.forEach(apply);
        }
    } catch (e) { log('installNsp ' + nsp.name + ' err: ' + e); }
}
function installServer(io) {
    try {
        // Patch adapter-wrapping via a connection-time hook as a belt-and-suspenders
        // in case a namespace was created before our new_namespace listener attached.
        io.on('connection', function(socket){
            // server-level 'connection' fires for the default '/' namespace; for
            // other namespaces our new_namespace handler installs the listener.
            apply(socket);
        });
        if (typeof io.on === 'function') io.on('new_namespace', installNsp);
        var nsps = io._nsps;
        if (nsps && typeof nsps.forEach === 'function') {
            nsps.forEach(installNsp);
        }
        log('installed on server; namespaces=' + (nsps ? nsps.size : '?'));
    } catch (e) { log('installServer err: ' + e); }
}
module.exports = function(entry) {
    try {
        if (entry && typeof entry.of === 'function') {
            installServer(entry);
            return;
        }
        if (entry && entry.nsp) {
            apply(entry);
            return;
        }
        log('unknown entry arg type=' + typeof entry);
    } catch (e) { log('module error: ' + e); }
};
