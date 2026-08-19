# Jarvis

Local, offline personal voice assistant. The AI brain runs on a Windows laptop (CPU-only). A Mac client (later phases) executes macOS actions over the local network.

**No cloud AI APIs.** After models and dependencies are installed, Jarvis can run with the internet disabled.

Current milestone: **Phase 6** — local LLM + STT + TTS + intent + safety + Windows/posix tools.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design, Phase 1 issues, and remaining phases.

---

## Requirements (Windows brain)

| Item | Notes |
|------|--------|
| OS | Windows 10/11 |
| CPU | 11th Gen Intel Core i3 or better (CPU inference) |
| RAM | 8 GB (close other heavy apps while the model is loaded) |
| GPU | Not required. Do not assume CUDA. |
| Python | **3.11, 3.12, or 3.13** (64-bit). Avoid 3.14 until llama-cpp-python ships wheels for it. |
| Disk | ~2.3 GB for the 1.5B GGUF + Whisper `ggml-base.bin` + Piper ONNX plus the Python venv |

Optional build tools (only if `pip` has to compile `llama-cpp-python`):

- [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with “Desktop development with C++”
- CMake

---

## Windows setup (exact)

### 1. Install Python 3.12

1. Download the 64-bit installer from [python.org](https://www.python.org/downloads/windows/).
2. Enable **Add python.exe to PATH**.
3. Confirm:

```powershell
python --version
```

You should see `Python 3.11.x`, `3.12.x`, or `3.13.x`.

### 2. Open this repository

```powershell
cd path\to\JARVIS
```

### 3. Run the setup script

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_windows.ps1
```

This creates `.venv`, installs `requirements.txt`, and copies `.env.example` to `.env` if `.env` does not exist.

Manual equivalent:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If `llama-cpp-python` fails to install, try the CPU wheel index, then a local compile:

```powershell
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

```powershell
$env:CMAKE_ARGS = "-DGGML_BLAS=OFF"
pip install llama-cpp-python --force-reinstall --no-cache-dir
```

### 4. Download the GGUF model (needs internet once)

Default model: **Qwen2.5 1.5B Instruct, Q4_K_M** (~1.0 GB).

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\download_model.py
```

This writes:

```
models\llm\qwen2.5-1.5b-instruct-q4_k_m.gguf
```

If 8 GB RAM is too tight, use the 0.5B variant:

```powershell
python scripts\download_model.py --small
```

Then set in `.env`:

```
LLM_MODEL_PATH=models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

You may also place any compatible Instruct GGUF at the path in `LLM_MODEL_PATH`.

### 4b. Download the Whisper STT model (needs internet once)

Default: multilingual **ggml-base.bin** (~142 MB). Needed for English, Bangla, and mixed speech.

```powershell
python scripts\download_model.py --stt
```

This writes:

```
models\stt\ggml-base.bin
```

If RAM is tight, use tiny (~75 MB, weaker Bangla):

```powershell
python scripts\download_model.py --stt --tiny
```

Then set `STT_MODEL_PATH=models/stt/ggml-tiny.bin` in `.env`.

On Windows, `pywhispercpp` may need the same C++ Build Tools as llama-cpp-python. Microphone capture needs a working input device; WAV upload works without a mic.

### 4c. Download the Piper TTS voice (needs internet once)

Default: **en_US-lessac-low** (~63 MB ONNX, CPU).

```powershell
python scripts\download_model.py --tts
```

This writes:

```
models\tts\en_US-lessac-low.onnx
models\tts\en_US-lessac-low.onnx.json
```

Piper has no official Bangla voice. For Bengali speech, install [espeak-ng](https://github.com/espeak-ng/espeak-ng) (`choco install espeak`) or set `TTS_BN_MODEL_PATH` to a local Bangla Piper ONNX.

### 5. Configure

Edit `.env` (never commit it):

```
JARVIS_HOST=0.0.0.0
JARVIS_PORT=8765
JARVIS_AUTH_TOKEN=change-me-to-a-long-random-string
LLM_MODEL_PATH=models/llm/qwen2.5-1.5b-instruct-q4_k_m.gguf
STT_MODEL_PATH=models/stt/ggml-base.bin
TTS_MODEL_PATH=models/tts/en_US-lessac-low.onnx
LOG_LEVEL=INFO
```

Bind to the LAN if the Mac client will connect later. **Do not port-forward this port on your router.**

### 6. Start the server

```powershell
.\scripts\start_server.ps1
```

Or:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn server.main:app --host 0.0.0.0 --port 8765
```

The first `/v1/chat` request loads the model (often 10–60 seconds on an i3). Set `LLM_PRELOAD=true` in `.env` to load at startup instead.

### 7. Health check

```powershell
.\scripts\health_check.ps1
```

Or:

```powershell
curl http://127.0.0.1:8765/health
```

Expected JSON includes `"status": "ok"` and nested `llm` / `stt` / `tts` file state. `"voice_ready"` is true when all three model files are on disk. Each `"model_loaded"` becomes `true` after that engine’s first successful load.

### 8. Chat (local LLM)

```powershell
curl -X POST http://127.0.0.1:8765/v1/chat `
  -H "Content-Type: application/json" `
  -H "X-Jarvis-Token: change-me-to-a-long-random-string" `
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"Say hello in one short sentence.\"}]}"
```

Disconnect the internet and repeat. The reply must still come from the local GGUF.

### 8b. Transcribe a WAV file (local Whisper)

```powershell
curl -X POST http://127.0.0.1:8765/v1/transcribe `
  -H "X-Jarvis-Token: change-me-to-a-long-random-string" `
  -F "audio=@command.wav" `
  -F "language=en"
```

Push-to-talk (records from the default microphone):

```powershell
curl -X POST http://127.0.0.1:8765/v1/listen `
  -H "Content-Type: application/json" `
  -H "X-Jarvis-Token: change-me-to-a-long-random-string" `
  -d "{\"duration_seconds\":5,\"language\":\"auto\"}"
```

### 8c. Speak a reply (local Piper)

```powershell
curl -X POST http://127.0.0.1:8765/v1/speak `
  -H "Content-Type: application/json" `
  -H "X-Jarvis-Token: change-me-to-a-long-random-string" `
  -d "{\"text\":\"Opening Visual Studio Code.\",\"language\":\"en\"}" `
  --output jarvis.wav
```

### 8d. Parse an intent (local tools after safety)

```powershell
curl -X POST http://127.0.0.1:8765/v1/intent `
  -H "Content-Type: application/json" `
  -H "X-Jarvis-Token: change-me-to-a-long-random-string" `
  -d "{\"text\":\"VS Code ta open kore dao.\",\"target\":\"windows\"}"
```

`target: mac` is deferred until Phase 7. Medium/high actions still need confirmation. Blocked actions return `denied`. After confirm, Windows/posix tools may set `executed: true`.

Confirm a pending action (same `session_id`):

```powershell
curl -X POST http://127.0.0.1:8765/v1/confirm `
  -H "Content-Type: application/json" `
  -H "X-Jarvis-Token: change-me-to-a-long-random-string" `
  -d "{\"session_id\":\"your-session\",\"confirmation_id\":\"the-id\",\"approved\":true}"
```

Or send `"yes"` / `"জি"` to `/v1/intent` with the same session.

List the catalog:

```powershell
curl http://127.0.0.1:8765/v1/tools `
  -H "X-Jarvis-Token: change-me-to-a-long-random-string"
```

### 9. Tests

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest tests -q
```

Unit tests do not need a GGUF. The integration test talks to the real model and is skipped if the file is missing:

```powershell
python -m pytest tests -q -m integration
```

---

## macOS / Linux development

Python 3.11–3.13 recommended.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/download_model.py
python scripts/download_model.py --stt
python scripts/download_model.py --tts
python -m uvicorn server.main:app --host 127.0.0.1 --port 8765
python -m pytest tests -q
```

---

## API (Phase 6)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | no | LLM + STT + TTS + tool + safety state |
| POST | `/v1/chat` | token | Local chat completion |
| POST | `/v1/transcribe` | token | WAV → transcript (whisper.cpp) |
| POST | `/v1/listen` | token | Microphone capture → transcript |
| POST | `/v1/speak` | token | Text → WAV (Piper / espeak-ng) |
| POST | `/v1/intent` | token | Text → gated tool plan; executes local tools when allowed |
| GET | `/v1/tools` | token | Registered tool schemas |
| GET | `/v1/pending` | token | Pending confirmation for a session |
| POST | `/v1/confirm` | token | Approve or reject a pending action |

`POST /v1/chat` body:

```json
{
  "messages": [
    { "role": "user", "content": "Hello" }
  ],
  "session_id": "optional-uuid",
  "max_tokens": 128,
  "temperature": 0.7,
  "stream": false
}
```

Header: `X-Jarvis-Token: <JARVIS_AUTH_TOKEN>` or `Authorization: Bearer <token>`.

---

## Project layout

```
server/     Phase 1 FastAPI brain
models/     Local model files (not in git)
scripts/    Windows setup / start / health
tests/      Unit + integration tests
```

STT, TTS, intent, safety, and local Windows/posix tools are implemented. Mac client and memory are documented in ARCHITECTURE.md.

---

## License

MIT. See [LICENSE](LICENSE).
