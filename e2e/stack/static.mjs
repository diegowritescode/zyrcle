// Serve a built single-page app, falling back to index.html for client-side routes.
//   node static.mjs DIR PORT
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const [dir, port] = process.argv.slice(2);
const TYPES = {
  ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".map": "application/json", ".wasm": "application/wasm",
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
  ".svg": "image/svg+xml", ".ico": "image/x-icon", ".ttf": "font/ttf", ".woff": "font/woff",
  ".woff2": "font/woff2", ".mp3": "audio/mpeg", ".txt": "text/plain",
};
createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^(\.\.[/\\])+/, "");
  for (const file of [join(dir, path), join(dir, "index.html")]) {
    try {
      const body = await readFile(file);
      res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
      return res.end(body);
    } catch {
      // not a file: try the next candidate
    }
  }
  res.writeHead(404).end();
}).listen(Number(port));
