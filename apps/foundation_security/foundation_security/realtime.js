// Entry point wired by frappe's socketio.js. The per-app realtime module is
// invoked at server startup with the socket.io Server instance. We install
// the resource-authorization guard on every namespace (including per-site
// namespaces like `/foundation.localhost`) so that doc/task rooms cannot
// leak across users on Socket.IO delivery.
//
// The guard itself lives in ../realtime/handlers.js relative to the app
// package directory (apps/foundation_security/foundation_security/ ->
// apps/foundation_security/realtime/handlers.js).
'use strict';
const guard = require('../realtime/handlers');
function apply(socket) {
    try {
        if (socket && socket.nsp && socket.nsp.adapter) guard(socket);
    } catch (e) {
        try { socket.disconnect(true); } catch {}
    }
}
module.exports = function(io) {
    // Support two calling conventions: newer frappe passes the Server; an
    // in-connection hook would pass a single connected Socket.
    if (io && io.sockets && typeof io.of === 'function') {
        // Server instance: cover every namespace, present and future.
        const install = nsp => nsp.on('connection', apply);
        for (const nsp of io._nsps.values()) install(nsp);
        io.on('new_namespace', install);
    } else if (io && io.nsp) {
        // Single Socket (called from inside a connection handler).
        apply(io);
    }
};
