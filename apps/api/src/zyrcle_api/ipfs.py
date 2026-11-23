"""A permanent public copy of each impact certificate on IPFS, pinned through Pinata
(docs/adr/0027, amendment of 2026-11-22).

IPFS names a file by the hash of its content (the CID), so the CID written on chain is both a
pointer to the document and a fingerprint of it: anyone can fetch it from any IPFS gateway, and a
changed byte would give another CID. Pinata keeps ("pins") the file online. Only the JWT is used;
Pinata's older API key and secret pair is not needed.

API: https://docs.pinata.cloud/api-reference/endpoint/ipfs/pin-json-to-ipfs
"""

from typing import Any

import httpx


class PinUnavailable(Exception):
    """Pinata could not pin the document now (network error, 5xx, rate limit): try again later."""


class PinRejected(Exception):
    """Pinata refused the request (bad JWT, plan limit, malformed body): a person must look."""


class PinataPin:
    def __init__(self, http: httpx.AsyncClient, base_url: str, jwt: str):
        self._http = http
        self._url = base_url.rstrip("/") + "/pinning/pinJSONToIPFS"
        self._headers = {"Authorization": f"Bearer {jwt}", "User-Agent": "zyrcle-api/0.1"}

    async def pin_json(self, content: dict[str, Any], name: str, keyvalues: dict[str, str]) -> str:
        """Pin `content` as a JSON file and return its CID (version 1, `bafy...`)."""
        try:
            r = await self._http.post(
                self._url,
                headers=self._headers,
                json={
                    "pinataContent": content,
                    "pinataMetadata": {"name": name, "keyvalues": keyvalues},
                    "pinataOptions": {"cidVersion": 1},
                },
            )
        except httpx.HTTPError as e:
            raise PinUnavailable(f"{type(e).__name__}: {e}") from None
        if r.status_code == 200:
            return str(r.json()["IpfsHash"])
        detail = f"{r.status_code}: {r.text[:200]}"
        if r.status_code == 429 or r.status_code >= 500:
            raise PinUnavailable(detail)
        raise PinRejected(detail)


def gateway_url(gateway: str, cid: str | None) -> str | None:
    """Where a browser can read the pinned document: `<gateway>/<cid>`."""
    return f"{gateway.rstrip('/')}/{cid}" if cid else None
