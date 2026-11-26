from __future__ import annotations

import asyncio
import hmac
import os
from collections import defaultdict, deque
from time import monotonic
from typing import Literal

import edge_tts
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

APP_VERSION = "0.1.0"
MAX_TEXT_LENGTH = 1500
TTS_TIMEOUT_SECONDS = 45
MAX_CONCURRENT_SYNTHESIS = 3
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 60

VOICES = {
    "soly": "ar-EG-ShakirNeural",
    "soleen": "ar-EG-SalmaNeural",
}

app = FastAPI(
    title="NOVA Voice Service",
    version=APP_VERSION,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "https://eslammohamedk123450-netizen.github.io",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

synthesis_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SYNTHESIS)
request_times: dict[str, deque[float]] = defaultdict(deque)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    persona: Literal["soly", "soleen"] = "soly"


def verify_optional_api_key(provided_key: str | None) -> None:
    expected_key = os.getenv("NOVA_VOICE_API_KEY", "").strip()
    # An unset key is convenient for the first manual Railway smoke test.
    # Set NOVA_VOICE_API_KEY in Railway before connecting a public client.
    if expected_key and not hmac.compare_digest(provided_key or "", expected_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def enforce_rate_limit(client_ip: str) -> None:
    now = monotonic()
    history = request_times[client_ip]
    while history and now - history[0] > RATE_LIMIT_WINDOW_SECONDS:
        history.popleft()
    if len(history) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(status_code=429, detail="Too many requests; try again shortly")
    history.append(now)

    # Keep this in-memory guard bounded. Railway may run multiple replicas,
    # so this is a basic abuse guard, not a distributed rate limiter.
    if len(request_times) > 2000:
        stale_before = now - RATE_LIMIT_WINDOW_SECONDS
        for ip in list(request_times):
            if not request_times[ip] or request_times[ip][-1] < stale_before:
                request_times.pop(ip, None)


async def synthesize_mp3(text: str, voice: str) -> bytes:
    communicator = edge_tts.Communicate(text=text, voice=voice)
    audio_parts: list[bytes] = []
    async for chunk in communicator.stream():
        if chunk.get("type") == "audio":
            audio_parts.append(chunk["data"])
    audio = b"".join(audio_parts)
    if not audio:
        raise RuntimeError("The speech provider returned an empty audio stream")
    return audio


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "NOVA Voice Service",
        "status": "online",
        "version": APP_VERSION,
        "health": "/health",
        "speech_endpoint": "POST /tts",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "nova-voice", "version": APP_VERSION}


@app.post("/tts")
async def text_to_speech(
    payload: SpeechRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Response:
    verify_optional_api_key(x_api_key)

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Text cannot be blank")

    client_ip = request.client.host if request.client else "unknown"
    enforce_rate_limit(client_ip)
    voice = VOICES[payload.persona]

    try:
        async with synthesis_semaphore:
            audio = await asyncio.wait_for(
                synthesize_mp3(text, voice),
                timeout=TTS_TIMEOUT_SECONDS,
            )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Speech generation timed out")
    except HTTPException:
        raise
    except Exception:
        # Avoid exposing provider internals or request data to public clients.
        raise HTTPException(
            status_code=502,
            detail="Speech generation failed; please try again",
        )

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'inline; filename="nova-speech.mp3"',
            "X-NOVA-Voice": voice,
        },
    )
