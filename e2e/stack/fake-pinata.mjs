// Stand-in for Pinata's pinJSONToIPFS and an IPFS gateway (/ipfs/<cid>), for the end-to-end tests.
// The CID is a stand-in too: "bafkrei" + the start of the sha256 of the JSON as sent.
//   node fake-pinata.mjs PORT
import { createHash } from "node:crypto";
import { createServer } from "node:http";

const JWT = "e2e-pinata-jwt";
const pins = new Map();
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
  const match = req.url.match(/^\/ipfs\/([A-Za-z0-9]+)$/);
  if (req.method === "GET" && match && pins.has(match[1])) {
    return res.writeHead(200, { ...cors, "content-type": "application/json" }).end(pins.get(match[1]));
  }
  res.writeHead(404, cors).end();
}).listen(Number(process.argv[2]));
