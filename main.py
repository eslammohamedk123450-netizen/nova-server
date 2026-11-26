from __future__ import annotations

import asyncio
import hmac
import os
import re
from collections import defaultdict, deque
from time import monotonic
from typing import Literal

import edge_tts
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

APP_VERSION = "0.2.0"
MAX_TEXT_LENGTH = 1500
TTS_TIMEOUT_SECONDS = 45
MAX_CONCURRENT_SYNTHESIS = 3
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 60

VOICES = {
    "soly": "ar-EG-ShakirNeural",
    "soleen": "ar-EG-SalmaNeural",
}

# Conservative presets: the voice identity stays fixed; only prosody changes.
PROSODY = {
    "natural": {"rate": "-4%", "pitch": "+0Hz"},
    "calm": {"rate": "-8%", "pitch": "-1Hz"},
    "lively": {"rate": "+0%", "pitch": "+1Hz"},
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
    style: Literal["natural", "calm", "lively"] = "natural"


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


async def synthesize_mp3(text: str, voice: str, style: str) -> bytes:
    prosody = PROSODY[style]
    communicator = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=prosody["rate"],
        pitch=prosody["pitch"],
    )
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
    "voices": "Fixed Egyptian male/female neural voices",
    "styles": "natural, calm, lively",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "nova-voice", "version": APP_VERSION}



@app.get("/test", response_class=HTMLResponse)
async def test_page() -> str:
    return """<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="theme-color" content="#080B14">
  <title>NOVA Voice Test</title>
  <style>
    *{box-sizing:border-box}body{margin:0;padding:24px;background:#080b14;color:#f5f0e2;font-family:system-ui, sans-serif}
    main{max-width:560px;margin:5vh auto;padding:24px;background:#151a27;border:1px solid #30384b;border-radius:20px}
    h1{margin-top:0;color:#d4af37}p{color:#c4c9d4;line-height:1.7}
    textarea,input,select,button{width:100%;margin:8px 0 14px;padding:13px;border-radius:10px;border:1px solid #46506a;background:#080b14;color:#fff;font:inherit}
    textarea{min-height:110px;resize:vertical}button{background:#d4af37;color:#111;font-weight:700;border:0;cursor:pointer}
    audio{width:100%;margin-top:14px}#status{min-height:28px;color:#d4af37}
    label{display:block;margin-top:10px}
  </style>
</head>
<body><main>
  <h1>NOVA · اختبار الصوت</h1>
  <p>اكتب جملة قصيرة واختار سولي أو سولين. أول طلب بعد فترة خمول ممكن يتأخر.</p>
  <label for="persona">الشخصية</label>
  <select id="persona"><option value="soly">سولي · صوت مصري رجالي</option><option value="soleen">سولين · صوت مصري نسائي</option></select>
  <label for="style">طريقة الإلقاء</label>
  <select id="style"><option value="natural">طبيعي ومتوازن (مقترح)</option><option value="calm">هادي ورايق</option><option value="lively">حيوي ونشيط</option></select>
  <label for="text">النص</label>
  <textarea id="text">أهلاً بيك! عامل إيه النهارده؟ أنا سولي، موجود معاك. تحب نبدأ بإيه؟</textarea>
  <label for="key">مفتاح الاختبار (اتركه فارغاً إذا لم تضبط مفتاحاً على Railway)</label>
  <input id="key" type="password" autocomplete="off" placeholder="NOVA_VOICE_API_KEY">
  <button id="speak">ولّد الصوت واسمعه</button>
  <div id="status" role="status" aria-live="polite"></div>
  <audio id="audio" controls></audio>
</main>
<script>
let previousUrl;
document.getElementById("speak").addEventListener("click", async () => {
  const button = document.getElementById("speak");
  const status = document.getElementById("status");
  const audio = document.getElementById("audio");
  button.disabled = true;
  status.textContent = "جاري توليد الصوت…";
  try {
    const headers = {"Content-Type":"application/json"};
    const key = document.getElementById("key").value.trim();
    if (key) headers["X-API-Key"] = key;
    const response = await fetch("/tts", {
      method:"POST", headers,
      body:JSON.stringify({
        text:document.getElementById("text").value,
        persona:document.getElementById("persona").value,
        style:document.getElementById("style").value
      })
    });
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.detail || "فشل توليد الصوت: " + response.status);
    }
    const blob = await response.blob();
    if (previousUrl) URL.revokeObjectURL(previousUrl);
    previousUrl = URL.createObjectURL(blob);
    audio.src = previousUrl;
    await audio.play();
    status.textContent = "الصوت اشتغل بنجاح.";
  } catch (error) {
    status.textContent = error.message || "حصل خطأ أثناء تشغيل الصوت.";
  } finally {
    button.disabled = false;
  }
});
</script></body></html>"""


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
                synthesize_mp3(text, voice, payload.style),
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
            "X-NOVA-Style": payload.style,
        },
    )
