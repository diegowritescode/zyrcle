import os
from typing import Annotated

import requests
from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter()

PINATA_UPLOAD_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
MAX_BYTES = 10 * 1024 * 1024


@router.post("/evidence")
async def upload_evidence(file: Annotated[UploadFile, File()]):
    """Pin a collection photo to IPFS. The Pinata credential stays on the server."""
    jwt = os.getenv("PINATA_JWT", "")
    if not jwt:
        raise HTTPException(status_code=503, detail="Evidence storage is not configured.")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="Only images are accepted.")

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image is larger than 10 MB.")

    response = requests.post(
        PINATA_UPLOAD_URL,
        headers={"Authorization": f"Bearer {jwt}"},
        files={"file": (file.filename or "evidence", data, file.content_type)},
        timeout=30,
    )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Evidence storage rejected the upload.")
    return {"cid": response.json()["IpfsHash"]}
