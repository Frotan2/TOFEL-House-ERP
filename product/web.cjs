"use strict";

// Same-origin product ingress. Destinations are service configuration, never
// request headers/URLs. Native Frappe and Socket.IO retain authentication.
const http = require("node:http");
const { spawn } = require("node:child_process");

function createIngress({ web = "http://127.0.0.1:8001", realtime = "http://socketio:9000" } = {}) {
	const webTarget = new URL(web);
	const realtimeTarget = new URL(realtime);
	for (const target of [webTarget, realtimeTarget]) {
		if (target.protocol !== "http:" || target.username || target.password || target.pathname !== "/") {
			throw new Error("Invalid internal service configuration");
		}
	}
	function isRealtime(url) {
		return url.startsWith("/socket.io/");
	}
	function requestFor(req, target) {
		const headers = { ...req.headers };
		delete headers["proxy-authorization"];
		delete headers["proxy-connection"];
		if (isRealtime(req.url)) {
			// Native Bench supplies Origin for same-origin polling GETs, where
			// browsers omit it. Keep an explicit foreign Origin so native
			// authentication still rejects cross-origin connections.
			if (!headers.origin && headers.host) headers.origin = "http://" + headers.host;
			headers["x-frappe-site-name"] = process.env.SITE_NAME || "toeflhouse.localhost";
		}
		return http.request({
			hostname: target.hostname, port: target.port || 80,
			method: req.method, path: req.url, headers,
		});
	}
	const server = http.createServer((req, res) => {
		const upstream = requestFor(req, isRealtime(req.url) ? realtimeTarget : webTarget);
		upstream.setTimeout(125000, () => upstream.destroy());
		upstream.on("response", (reply) => {
			res.writeHead(reply.statusCode, reply.headers);
			reply.on("error", () => res.destroy());
			reply.pipe(res);
		});
		upstream.on("error", () => {
			if (res.headersSent) return res.destroy();
			res.writeHead(502, { "Content-Type": "text/plain", "Cache-Control": "no-store" });
			res.end("ERP service is temporarily unavailable.");
		});
		req.on("aborted", () => upstream.destroy());
		req.on("error", () => upstream.destroy());
		res.on("close", () => { if (!res.writableFinished) upstream.destroy(); });
		req.pipe(upstream);
	});
	server.on("upgrade", (req, socket, head) => {
		if (!isRealtime(req.url) || req.method !== "GET" || req.headers.upgrade?.toLowerCase() !== "websocket") {
			socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n");
			return;
		}
		const upstream = requestFor(req, realtimeTarget);
		upstream.setTimeout(10000, () => upstream.destroy());
		upstream.on("upgrade", (reply, remote, remoteHead) => {
			remote.setTimeout(0);
			socket.write(`HTTP/${reply.httpVersion} ${reply.statusCode} ${reply.statusMessage}\r\n`);
			for (let index = 0; index < reply.rawHeaders.length; index += 2) {
				socket.write(`${reply.rawHeaders[index]}: ${reply.rawHeaders[index + 1]}\r\n`);
			}
			socket.write("\r\n");
			if (remoteHead.length) socket.write(remoteHead);
			if (head.length) remote.write(head);
			remote.on("error", () => socket.destroy());
			socket.on("error", () => remote.destroy());
			remote.on("close", () => socket.destroy());
			socket.on("close", () => remote.destroy());
			remote.pipe(socket).pipe(remote);
		});
		upstream.on("response", (reply) => {
			// Preserve a native refusal without exposing its body or credentials.
			socket.end(`HTTP/1.1 ${reply.statusCode} Rejected\r\nConnection: close\r\n\r\n`);
			reply.resume();
		});
		upstream.on("error", () => socket.destroy());
		socket.on("error", () => upstream.destroy());
		socket.on("close", () => upstream.destroy());
		upstream.end();
	});
	return server;
}

function serve() {
	const child = spawn("/home/frappe/bench/env/bin/gunicorn", [
		"--bind", "127.0.0.1:8001", "--workers", "2", "--timeout", "120",
		"--pythonpath", "/product", "wsgi:application",
	], { cwd: "/home/frappe/bench/sites", stdio: "inherit" });
	const server = createIngress({ realtime: process.env.ERP_REALTIME_BACKEND || "http://socketio:9000" });
	let stopping = false;
	function stop(code) {
		if (stopping) return;
		stopping = true;
		process.exitCode = code;
		server.close();
		child.kill("SIGTERM");
		setTimeout(() => { child.kill("SIGKILL"); process.exit(code); }, 5000).unref();
		child.once("exit", () => process.exit(code));
	}
	child.on("error", () => stop(1));
	child.on("exit", () => { if (!stopping) process.exit(1); });
	server.on("error", () => stop(1));
	process.on("SIGTERM", () => stop(0));
	process.on("SIGINT", () => stop(0));
	server.listen(8000, "0.0.0.0");
}

module.exports = { createIngress };
if (require.main === module) serve();
