# Jarvis Architecture

Jarvis is a fully local, offline personal voice assistant. The Windows laptop is the **brain** (STT, LLM, TTS, planning, safety). The Mac is the **body** for macOS control. No cloud LLM APIs are used at runtime.

## Hardware constraint

The default brain is a CPU-only Windows laptop:

- 11th Gen Intel Core i3 (~2 GHz)
- 8 GB RAM
- no dedicated GPU assumed

All inference choices follow from that: one small quantized GGUF model, one llama.cpp process, lazy loading, a short context window, and no concurrent model copies.

## System diagram

```
                MAC CLIENT
                    |
                    | WebSocket / HTTP  (LAN only)
                    |
                    v
          WINDOWS JARVIS SERVER
                    |
    +---------------+----------------+
    |               |                |
    v               v                v
   STT             LLM              TTS
    |               |
    |               v
    |         Intent Parser
    |               |
    |               v
    |         Task Planner
    |               |
    |               v
    |         Safety Engine
    |               |
    |               v
    |         Tool Executor
    |               |
    +---------------+
                    |
          +---------+---------+
          |                   |
          v                   v
   WINDOWS TOOLS         MAC TOOLS
                          via Mac Client
```

The LLM never executes shell commands. It only emits structured JSON. Deterministic code validates, safety-checks, and dispatches tools.

## Control flow

```
User speech
    → Wake word or push-to-talk
    → STT (local Whisper)
    → LLM (local GGUF via llama.cpp)
    → Structured intent JSON
    → Schema validation
    → Safety engine
    → Confirmation (if required)
    → Tool registry lookup
    → Tool executor (Windows local or Mac client)
    → Result
    → TTS (local Piper)
```

If the LLM cannot produce a confident structured intent, it returns a clarification instead of guessing a dangerous action.

## LLM contract

The reasoning layer is abstract (`LLMEngine`). Phase 1 uses llama.cpp through `llama-cpp-python`. The model file is a GGUF on disk.

Default model (CPU / 8 GB RAM):

- Qwen2.5 1.5B Instruct
- Quantization: Q4_K_M
- Runtime: llama.cpp
- Context: 2048 tokens
- GPU layers: 0

The LLM is instructed to produce strict JSON for tool use, for example:

```json
{
  "type": "tool_call",
  "tool": "open_application",
  "target": "mac",
  "arguments": { "application": "Visual Studio Code" },
  "risk": "low",
  "requires_confirmation": false
}
```

Clarification:

```json
{
  "type": "clarification",
  "message": "Which folder should I create the project in?"
}
```

Raw model text is never passed to `os.system`, `subprocess.run(..., shell=True)`, or any unrestricted shell.

## Personality and language

Jarvis is a calm, concise, slightly futuristic personal computer assistant. It may use "sir" occasionally. Spoken replies stay short.

Supported input:

- English
- Bangla
- Indian English
- Banglish (Bengali mixed with English words)

Example: `"VS Code ta open kore dao."` → `open_application` / Visual Studio Code.

Reply language follows the user when practical.

## Safety model

Safety is **not** delegated to the LLM.

| Risk | Examples | Policy |
|------|----------|--------|
| LOW | open app, list dir, system info | Execute after schema validation |
| MEDIUM | create file/folder, write file, create project | Validate paths; confirm if ambiguous |
| HIGH | delete, arbitrary terminal, install software, system settings | Explicit per-session confirmation required |

The safety engine independently rejects:

- disk formatting
- deletion of system/root paths
- credential / password access
- disabling security software
- firewall/security setting changes
- unknown downloaded executables
- unrestricted remote code execution

Confirmation is bound to `session_id` + pending action. A "yes" from another session cannot authorize it.

## Tool system

`ToolRegistry` is the only way to run OS actions. Each tool declares name, description, JSON schema, target (`windows` | `mac`), risk, confirmation flag, `validate()`, and `execute()`.

The LLM may only name tools that exist in the registry.

## Communication

- Transport: HTTP now; WebSocket for the Mac client in Phase 7
- Bind: configurable LAN host/port (default `0.0.0.0:8765`)
- Auth: optional shared token (`X-Jarvis-Token` / Bearer)
- Sessions: server-issued `session_id`
- Unknown message types are rejected
- TLS is a later addition; do not port-forward this service to the internet

## Memory

SQLite (Phase 8) stores preferences, aliases, known apps, project locations, and short task history. Example: `default_projects_directory = ~/Projects`.

## Logging

Structured local logs: timestamp, session, transcript, intent, tool, arguments, confirmation, result, duration, errors. Stack traces go to logs only. Passwords, tokens, and credentials are never logged.

## Implementation phases

| Phase | Scope | Status |
|-------|--------|--------|
| **1** | Python FastAPI server, llama.cpp, GGUF load, `/health`, `/v1/chat`, config, logging | **complete** (see issues below) |
| **2** | Local STT (whisper.cpp), microphone/audio input, `/v1/transcribe`, `/v1/listen` | **complete** (see issues below) |
| 3 | Local TTS (Piper) | not started |
| 4 | Intent parser, tool registry, structured tool calls | not started |
| 5 | Safety engine, risk levels, confirmation, command policy | not started |
| 6 | Windows tools (apps, filesystem, safe terminal) | not started |
| 7 | Mac client (WebSocket, auth, macOS tool executor) | not started |
| 8 | SQLite memory (preferences, history, aliases) | not started |
| 9 | Wake word "Jarvis" with push-to-talk fallback | not started |

Do not start the next phase until the current phase is tested.

## Phase 1 detail

Phase 1 proves the brain can think offline:

1. Load one GGUF via llama.cpp (lazy, singleton, single worker thread).
2. Serve `GET /health` (process up, model file present, model loaded).
3. Serve `POST /v1/chat` with a short Jarvis system prompt.
4. Return text plus usage and latency. No tools. No STT/TTS.

Subsequent phases wrap this engine; they do not replace it with a cloud API.

## Phase 1 issues (open)

These are real limitations found while implementing and testing Phase 1. They are not blockers for Phase 2.

1. **Not yet proven on the target Windows i3.** Inference was verified on macOS arm64 with Python 3.12. Cold start and tokens/sec on the 8 GB Intel laptop are still unknown.
2. **Python 3.14 is a poor default.** llama-cpp-python is reliable on 3.11–3.13. Use 3.12 on Windows. This Mac’s Homebrew `python3` is 3.14; the project venv is 3.12.
3. **Windows may need a compiler.** If no CPU wheel exists, install Visual Studio C++ Build Tools (and CMake) before `pip install llama-cpp-python`. See README.
4. **Default `JARVIS_AUTH_TOKEN=change-me`.** Must be replaced before any LAN use. Auth is shared-token only; TLS is not implemented.
5. **Streaming is rejected.** `POST /v1/chat` with `stream=true` returns 400. Non-streaming JSON is the Phase 1 contract.
6. **First chat loads the GGUF.** Lazy load saves RAM but the first request is slow (often 10–60s on an i3). `LLM_PRELOAD=true` trades startup RAM for that delay.
7. **Empty env values.** `LLM_N_THREADS=` in `.env.example` used to crash Settings. Fixed with `env_ignore_empty=True`. Leave it blank for auto thread count.
8. **TestClient warning.** Starlette warns that `httpx` TestClient is deprecated in favor of `httpx2`. Harmless; tests still pass.
9. **No STT/TTS/tools yet.** Phase 1 is text in, text out. Voice commands are Phase 2+.

## Phase 2 detail

Phase 2 proves the brain can hear offline:

1. Abstract `SpeechToText.transcribe(audio_path) -> Transcript` (no Whisper types leak out).
2. whisper.cpp backend via `pywhispercpp`, local GGML only (no runtime download).
3. Default multilingual model `ggml-base.bin` so English, Bangla, and mixed speech are possible. `ggml-tiny.bin` is the low-RAM option.
4. `POST /v1/transcribe` accepts a WAV file. Audio is converted to 16 kHz mono PCM, then discarded.
5. `POST /v1/listen` is push-to-talk: record N seconds from the default microphone, transcribe, delete the buffer. Wake-word “Jarvis” stays Phase 9.
6. Health reports LLM and STT file/load state separately. `voice_ready` is true only when both model files are present.

STT is lazy-loaded in its own single worker thread. It must not start a second LLM process. Keep the Whisper model small so it can sit beside the 1.5B GGUF on 8 GB RAM.

## Phase 2 issues (open)

1. **WAV only.** `/v1/transcribe` rejects mp3/webm. The Mac client (Phase 7) must send PCM WAV, or we add a local converter later.
2. **Microphone `/v1/listen` is implemented but not live-tested** on a real input device in this environment (unit tests mock the recorder).
3. **Bangla was not integration-tested.** The model is multilingual `ggml-base`; English “open visual studio code” was verified. Bangla/Banglish accuracy on tiny/base will be weaker than small.
4. **Still not proven on the Windows i3.** `STT_USE_GPU=false` is the default so CPU-only machines match the architecture.
5. **`pywhispercpp` depends on `requests`.** That package can download models if you pass a name like `base`. Jarvis only loads a local GGML path and never calls a cloud STT API.


## Runtime layout (target)

```
JARVIS/
├── server/          # Windows brain (FastAPI)
├── mac-client/      # macOS body (Phase 7+)
├── models/          # local GGUF / Whisper / Piper files (gitignored binaries)
├── scripts/         # Windows setup and health
└── tests/
```

## Non-goals for MVP

- Cloud AI providers
- Public internet exposure
- Unrestricted shell from model output
- Loading multiple LLMs at once
- Perfect wake-word detection before push-to-talk works
