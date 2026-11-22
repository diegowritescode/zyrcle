import os

import requests
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
)


def optimize_route_with_gemini(containers, user_location):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Route optimization is not configured.")

    prompt = generate_prompt(containers, user_location)

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    # Key goes in a header, not the query string, so it never lands in access logs.
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}

    response = requests.post(GEMINI_URL, headers=headers, json=payload, timeout=30)

    if response.status_code == 200:
        reply = response.json()
        return parse_ids_from_response(reply["candidates"][0]["content"]["parts"][0]["text"])
    else:
        raise HTTPException(status_code=502, detail="Route optimization provider failed.")


def generate_prompt(containers, user_location):
    return f"""
Dado el siguiente listado de contenedores de reciclaje en Medellín con su ubicación,
tipo, peso estimado y porcentaje de llenado, y la ubicación del recolector, responde una
lista de IDs ordenados desde el más cercano y necesario de recolectar hasta el último.

Ubicación del recolector:
Latitud: {user_location["latitude"]}, Longitud: {user_location["longitude"]}

Contenedores:
{format_containers(containers)}

Solo responde una lista JSON como esta: [8, 3, 6, 1]
"""


def format_containers(containers):
    return "\n".join(
        f"ID: {c.id}, Tipo: {c.type}, Peso: {c.estimatedWeight}, "
        f"Llenado: {c.fillPercentage}%, Lat: {c.latitude}, Lon: {c.longitude}"
        for c in containers
    )


def parse_ids_from_response(text):
    import json
    import re

    try:
        # Quitar markdown ```json ... ``` si existe
        cleaned = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()

        # Parsear directamente como JSON
        return json.loads(cleaned)
    except Exception as e:
        print("❌ Error al parsear JSON:", e)
        return []
