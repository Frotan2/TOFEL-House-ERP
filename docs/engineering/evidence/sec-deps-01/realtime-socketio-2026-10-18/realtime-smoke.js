const http = require("http");
const { Server } = require("socket.io");
const { io: connect } = require("socket.io-client");
const server = http.createServer();
const io = new Server(server, { cors: { origin: "*" } });
io.on("connection", (s) => { s.on("ping-test", (msg, cb) => cb({ echo: msg })); s.emit("hello", { ok: true }); });
server.listen(0, "127.0.0.1", async () => {
  const port = server.address().port;
  const url = `http://127.0.0.1:${port}`;
  const results = {};
  for (const transports of [["polling"], ["websocket"]]) {
    const c = connect(url, { transports, reconnection: false, timeout: 5000 });
    const hello = await new Promise((res, rej) => { c.on("hello", res); c.on("connect_error", rej); setTimeout(() => rej(new Error("timeout")), 6000); }).catch((e) => "ERR " + e.message);
    const echo = hello.ok ? await new Promise((res) => c.emit("ping-test", "x", res)) : null;
    results[transports[0]] = { hello, echo, upgraded: c.io.engine && c.io.engine.transport && c.io.engine.transport.name };
    c.close();
  }
  // oversized polling payload must be refused by engine.io's default 1 MB cap
  const c2 = connect(url, { transports: ["polling"], reconnection: false, timeout: 5000 });
  await new Promise((res) => c2.on("connect", res));
  const big = "a".repeat(1_500_000);
  const r = await new Promise((res) => { let done = false; c2.io.engine.once("close", (reason) => { if (!done) { done = true; res("engine closed: " + reason); } }); c2.emit("ping-test", big, () => { if (!done) { done = true; res("delivered"); } }); setTimeout(() => { if (!done) { done = true; res("no-response-after-5s"); } }, 5000); });
  results.oversize_1_5MB = r;
  console.log(JSON.stringify(results, null, 1));
  c2.close(); io.close(); server.close(); process.exit(0);
});
