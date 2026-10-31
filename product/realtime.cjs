"use strict";

// Native realtime callbacks must reach the web service inside Compose, not
// the browser's loopback origin inside the separate Socket.IO container.
function internalUrl(base, path) {
	const target = new URL(base);
	if (target.protocol !== "http:" || target.username || target.password || target.pathname !== "/"
		|| typeof path !== "string" || !path.startsWith("/") || path.startsWith("//")) {
		throw new Error("Invalid internal realtime destination");
	}
	return target.origin + path;
}

function serve() {
	process.env.FRAPPE_SITE = process.env.SITE_NAME || "toeflhouse.localhost";
	const utils = require("/home/frappe/bench/apps/frappe/realtime/utils.js");
	const backend = process.env.ERP_HTTP_BACKEND || "http://web:8000";
	internalUrl(backend, "/");
	utils.get_url = (_socket, path) => internalUrl(backend, path || "/");
	require("/home/frappe/bench/apps/frappe/socketio.js");
}

module.exports = { internalUrl };
if (require.main === module) serve();
