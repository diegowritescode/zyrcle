// Stand-ins for the external services the end-to-end tests touch:
// - Pinata's pinJSONToIPFS and an IPFS gateway (/ipfs/<cid>). The CID is a stand-in too: "bafkrei"
//   + the start of the sha256 of the JSON as sent.
// - Anthropic's Messages API, for reading scale tickets: it answers with the reading a test set
//   with POST /control/ticket-reading, and keeps the last request at GET /control/last-message.
//   node fake-services.mjs PORT
import { createHash } from "node:crypto";
import { createServer } from "node:http";

const JWT = "e2e-pinata-jwt";
const ANTHROPIC_KEY = "e2e-anthropic-key";
const pins = new Map();
let ticketReading = { readable: false, center_name: null, ticket_ref: null, date: null, lines: [], total_cop: null, notes: "no reading set" };
let lastMessage = null;
const body = (req) => new Promise((resolve) => {
  let text = "";
  req.on("data", (chunk) => (text += chunk));
  req.on("end", () => resolve(text));
});
createServer((req, res) => {
  const cors = { "access-control-allow-origin": "*" };
  if (req.method === "POST" && req.url === "/pinning/pinJSONToIPFS") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      if (req.headers.authorization !== `Bearer ${JWT}`) return res.writeHead(401).end("{}");
      const text = JSON.stringify(JSON.parse(body).pinataContent);
      const cid = "bafkrei" + createHash("sha256").update(text).digest("hex").slice(0, 52);
      pins.set(cid, text);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ IpfsHash: cid, PinSize: text.length, isDuplicate: false }));
    });
    return;
  }
  if (req.method === "POST" && req.url === "/control/ticket-reading") {
    body(req).then((text) => {
      ticketReading = JSON.parse(text);
      res.writeHead(204).end();
    });
    return;
  }
  if (req.method === "GET" && req.url === "/control/last-message") {
    return res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(lastMessage));
  }
  if (req.method === "POST" && req.url.startsWith("/v1/messages")) {
    body(req).then((text) => {
      const key = req.headers["x-api-key"] ?? String(req.headers.authorization ?? "").replace(/^Bearer /, "");
      if (key !== ANTHROPIC_KEY) return res.writeHead(401, { "content-type": "application/json" }).end('{"type":"error","error":{"type":"authentication_error","message":"bad key"}}');
      const request = JSON.parse(text);
      lastMessage = { model: request.model, fallbacks: request.fallbacks, format: request.output_config?.format?.type, beta: req.headers["anthropic-beta"] };
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({
        id: "msg_e2e", type: "message", role: "assistant", model: request.model,
        content: [{ type: "text", text: JSON.stringify(ticketReading) }],
        stop_reason: "end_turn", stop_sequence: null, usage: { input_tokens: 1, output_tokens: 1 },
      }));
    });
    return;
  }
  const match = req.url.match(/^\/ipfs\/([A-Za-z0-9]+)$/);
  if (req.method === "GET" && match && pins.has(match[1])) {
    return res.writeHead(200, { ...cors, "content-type": "application/json" }).end(pins.get(match[1]));
  }
  res.writeHead(404, cors).end();
}).listen(Number(process.argv[2]));
