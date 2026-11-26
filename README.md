# NOVA Voice Service

A small Python/FastAPI service that converts text to Egyptian Arabic speech using the community `edge-tts` package and Microsoft's online Edge TTS service.

## Deploy on Railway

1. Create a new Railway project and choose **GitHub Repository**.
2. Select `eslammohamedk123450-netizen/nova-server`.
3. Railway detects Python from `requirements.txt` and starts the app using the `Procfile`.
4. In Railway, open the service **Settings → Networking → Generate Domain**.
5. Test `https://YOUR-DOMAIN/health`.

No Gemini key or Microsoft API key is required by edge-tts. It relies on Microsoft's online TTS service, so availability and usage are subject to that service's limits and may change.

## Endpoints

- `GET /` — service information
- `GET /health` — health check
- `POST /tts` — generate an MP3

Example request:

```bash
curl -X POST "https://YOUR-DOMAIN/tts" \
  -H "Content-Type: application/json" \
  -d '{"text":"أهلاً، أنا سولي. عامل إيه؟","persona":"soly"}' \
  --output soly.mp3
```

Allowed personas:
- `soly` → `ar-EG-ShakirNeural`
- `soleen` → `ar-EG-SalmaNeural`

Optional protection:
- Set Railway variable `NOVA_VOICE_API_KEY` to a long random secret.
- If set, clients must send it in the `X-API-Key` header.
- Leave it unset only for initial manual testing. Do not expose a permanent secret in public frontend JavaScript.

## Limits and safety

- Text length is limited to 1,500 characters per request.
- Only the two configured Egyptian voices are accepted.
- CORS is restricted to the NOVA GitHub Pages origin by default.
- This is a prototype relay, not a guaranteed unlimited or always-on TTS API.
