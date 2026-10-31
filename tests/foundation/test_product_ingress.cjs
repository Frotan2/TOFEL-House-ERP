"use strict";
const assert = require("node:assert/strict");
const http = require("node:http");
const net = require("node:net");
const { test } = require("node:test");
const { createIngress } = require("../../product/web.cjs");
const { internalUrl } = require("../../product/realtime.cjs");

async function listen(t, server) {
	const sockets = new Set();
	server.on("connection", socket => {
		sockets.add(socket);
		socket.on("close", () => sockets.delete(socket));
	});
	await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
	t.after(() => { for (const socket of sockets) socket.destroy(); server.close(); });
	return `http://127.0.0.1:${server.address().port}`;
}

async function request(base, path, options = {}, body = "") {
	return new Promise((resolve, reject) => {
		const req = http.request(new URL(base), { path, ...options }, res => {
			let result = "";
			res.setEncoding("utf8");
			res.on("data", chunk => { result += chunk; });
			res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, body: result }));
		});
		req.on("error", reject);
		req.end(body);
	});
}

test("normal native traffic preserves method, query, body, cookies and native response", async t => {
	const backend = await listen(t, http.createServer((req, res) => {
		let body = "";
		req.on("data", chunk => { body += chunk; });
		req.on("end", () => {
			res.writeHead(201, { "Set-Cookie": "sid=SYN; HttpOnly", "Content-Type": "application/json" });
			res.end(JSON.stringify({ method: req.method, url: req.url, body, cookie: req.headers.cookie }));
		});
	}));
	const ingress = await listen(t, createIngress({ web: backend }));
	const result = await request(ingress, "/api/method/example?x=1", {
		method: "POST", headers: { Cookie: "sid=SYN" },
	}, "synthetic-body");
	assert.equal(result.status, 201);
	assert.deepEqual(JSON.parse(result.body), { method: "POST", url: "/api/method/example?x=1", body: "synthetic-body", cookie: "sid=SYN" });
	assert.deepEqual(result.headers["set-cookie"], ["sid=SYN; HttpOnly"]);
});

test("Engine.IO polling reaches realtime and preserves native unauthorized status", async t => {
	const realtime = await listen(t, http.createServer((req, res) => {
		assert.equal(req.url, "/socket.io/?EIO=4&transport=polling");
		assert.equal(req.headers.origin, "http://127.0.0.1:8000");
		res.writeHead(401); res.end("Native refusal");
	}));
	const web = await listen(t, http.createServer((_req, res) => { res.end("wrong target"); }));
	const ingress = await listen(t, createIngress({ web, realtime }));
	const result = await request(ingress, "/socket.io/?EIO=4&transport=polling", { headers: { Origin: "http://127.0.0.1:8000" } });
	assert.equal(result.status, 401);
	assert.equal(result.body, "Native refusal");
});

test("WebSocket handshake and initial bytes tunnel in both directions", async t => {
	const realtimeServer = http.createServer();
	realtimeServer.on("upgrade", (req, socket, head) => {
		assert.equal(req.headers.cookie, "sid=SYN");
		socket.write("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\nSERVER-HEAD");
		if (head.length) socket.write(head);
		socket.on("data", data => socket.write(data));
	});
	const realtime = await listen(t, realtimeServer);
	const ingress = await listen(t, createIngress({ realtime }));
	const port = Number(new URL(ingress).port);
	await new Promise((resolve, reject) => {
		const socket = net.connect(port, "127.0.0.1");
		t.after(() => socket.destroy());
		socket.setTimeout(3000, () => reject(new Error("Upgrade did not complete")));
		let received = "";
		let sent = false;
		socket.on("connect", () => socket.write("GET /socket.io/?EIO=4&transport=websocket HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nCookie: sid=SYN\r\n\r\nCLIENT-HEAD"));
		socket.on("error", reject);
		socket.on("data", data => {
			received += data.toString();
			if (received.includes("CLIENT-HEAD") && !sent) { sent = true; socket.write("AFTER-UPGRADE"); }
			if (received.includes("AFTER-UPGRADE")) {
				assert.match(received, /^HTTP\/1.1 101/);
				assert.ok(received.includes("SERVER-HEAD"));
				socket.destroy(); resolve();
			}
		});
	});
});

test("same-origin polling gets native proxy Origin; explicit foreign Origin stays rejectable", async t => {
	const realtime = await listen(t, http.createServer((req, res) => {
		res.end(JSON.stringify({ origin: req.headers.origin, host: req.headers.host,
			site: req.headers["x-frappe-site-name"] }));
	}));
	const ingress = await listen(t, createIngress({ realtime }));
	const same = JSON.parse((await request(ingress, "/socket.io/?EIO=4&transport=polling")).body);
	assert.equal(same.origin, "http://" + same.host);
	assert.equal(same.site, "toeflhouse.localhost");
	const foreign = JSON.parse((await request(ingress, "/socket.io/", {
		headers: { Origin: "https://outside.test", "X-Frappe-Site-Name": "other.localhost" },
	})).body);
	assert.equal(foreign.origin, "https://outside.test");
	assert.equal(foreign.site, "toeflhouse.localhost");
});

test("failed internal HTTP service gives generic 502 without credentials", async t => {
	const closed = http.createServer();
	await new Promise(resolve => closed.listen(0, "127.0.0.1", resolve));
	const port = closed.address().port;
	await new Promise(resolve => closed.close(resolve));
	const ingress = await listen(t, createIngress({ web: `http://127.0.0.1:${port}` }));
	const result = await request(ingress, "/", { headers: { Cookie: "sid=PRIVATE" } });
	assert.equal(result.status, 502);
	assert.equal(result.body, "ERP service is temporarily unavailable.");
	assert.ok(!result.body.includes("PRIVATE"));
});

test("callback URL ignores browser origin and refuses absolute/network-path URLs", () => {
	assert.equal(internalUrl("http://web:8000", "/api/method/frappe.realtime.get_user_info"), "http://web:8000/api/method/frappe.realtime.get_user_info");
	for (const path of ["https://outside.test/", "//outside.test/", "relative"]) {
		assert.throws(() => internalUrl("http://web:8000", path));
	}
	for (const base of ["file:///", "http://user:secret@web:8000", "http://web:8000/unexpected"]) {
		assert.throws(() => internalUrl(base, "/api/method/example"));
	}
});
