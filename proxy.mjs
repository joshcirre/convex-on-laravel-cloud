// Dual-stack TCP forwarder: [::]:LISTEN_PORT -> 127.0.0.1:TARGET_PORT.
//
// Laravel Cloud health-checks and routes over IPv6, but convex-local-backend's
// --interface only accepts an IPv4 address. Forwarding raw TCP keeps HTTP,
// keep-alive and WebSocket sync connections untouched.
//
// One HTTP-aware tweak: Cloud's in-container nginx forwards `Upgrade:
// websocket` but rewrites `Connection`, so Convex rejects the sync socket
// ("Connection header did not include upgrade"). Restore it on the request
// head; once Convex answers 101, nginx tunnels the connection.
import net from "node:net";

const listenPort = Number(process.env.LISTEN_PORT);
const targetPort = Number(process.env.TARGET_PORT);
const targetHost = process.env.TARGET_HOST ?? "127.0.0.1";

const HEAD_END = "\r\n\r\n";

function fixUpgradeHead(head) {
  const lines = head.split("\r\n");
  // nginx drops the hop-by-hop Upgrade/Connection headers, but the
  // end-to-end Sec-WebSocket-Key survives and marks a WebSocket handshake.
  const isUpgrade = lines.some((l) => /^(upgrade:\s*websocket|sec-websocket-key:)/i.test(l));
  if (!isUpgrade) return head;
  const before = lines
    .slice(1)
    .filter((l) => /^(connection|upgrade):/i.test(l))
    .join(" | ");
  const kept = lines.filter((l, i) => i === 0 || !/^(connection|upgrade):/i.test(l));
  kept.splice(1, 0, "Upgrade: websocket", "Connection: Upgrade");
  console.log(`proxy: websocket handshake ${lines[0].split(" ")[1]} (had: ${before || "none"})`);
  return kept.join("\r\n");
}

const server = net.createServer((client) => {
  const upstream = net.connect(targetPort, targetHost);
  client.setNoDelay(true);
  upstream.setNoDelay(true);
  // Backend not up yet or restarting: drop the client instead of hanging.
  client.on("error", () => upstream.destroy());
  upstream.on("error", () => client.destroy());
  upstream.pipe(client);

  // Buffer only the first request head, then switch to raw piping.
  let head = Buffer.alloc(0);
  let piping = false;
  const onData = (chunk) => {
    head = Buffer.concat([head, chunk]);
    const end = head.indexOf(HEAD_END);
    if (end === -1 && head.length < 64 * 1024) return;
    client.off("data", onData);
    if (end !== -1) {
      const fixed = fixUpgradeHead(head.subarray(0, end).toString("latin1"));
      head = Buffer.concat([Buffer.from(fixed, "latin1"), head.subarray(end)]);
    }
    upstream.write(head);
    piping = true;
    client.pipe(upstream);
  };
  client.on("data", onData);
  // Client closed mid-head: flush what arrived and close upstream.
  client.on("end", () => {
    if (!piping) upstream.end(head);
  });
});

// ipv6Only: false makes "::" accept IPv4-mapped connections too.
server.listen({ host: "::", port: listenPort, ipv6Only: false }, () => {
  console.log(`proxy: [::]:${listenPort} -> ${targetHost}:${targetPort}`);
});
