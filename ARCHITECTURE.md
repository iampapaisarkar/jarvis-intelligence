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

- Transport: HTTP for chat/intent/speech; WebSocket `/v1/mac` for the Mac body
- Bind: configurable LAN host/port (default `0.0.0.0:8765`)
- Auth: optional shared token (`X-Jarvis-Token` / Bearer, or `?token=` on the Mac socket)
- Sessions: server-issued `session_id`
- Unknown message types are rejected
- TLS is a later addition; do not port-forward this service to the internet

## Memory

SQLite (Phase 8) stores allowlisted preferences, aliases, known apps, project locations, and short task history. Example: `default_projects_directory = ~/Projects`. The database is local (`data/jarvis.sqlite` by default). Secrets, tokens, and passwords are not accepted as keys.

## Logging

Structured local logs: timestamp, session, transcript, intent, tool, arguments, confirmation, result, duration, errors. Stack traces go to logs only. Passwords, tokens, and credentials are never logged.

## Implementation phases

| Phase | Scope | Status |
|-------|--------|--------|
| **1** | Python FastAPI server, llama.cpp, GGUF load, `/health`, `/v1/chat`, config, logging | **complete** (see issues below) |
| **2** | Local STT (whisper.cpp), microphone/audio input, `/v1/transcribe`, `/v1/listen` | **complete** (see issues below) |
| **3** | Local TTS (Piper), `/v1/speak`, optional speaker playback | **complete** (see issues below) |
| **4** | Intent parser, tool registry, structured tool calls | **complete** (see issues below) |
| **5** | Safety engine, risk levels, confirmation, command policy | **complete** (see issues below) |
| **6** | Windows tools (apps, filesystem, safe terminal) | **complete** (see issues below) |
| **7** | Mac client (WebSocket, auth, macOS tool executor) | **complete** (see issues below) |
| **8** | SQLite memory (preferences, history, aliases) | **complete** (see issues below) |
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

## Phase 3 detail

Phase 3 proves the brain can speak offline:

1. Abstract `TextToSpeech.speak(text, language) -> SynthesizedSpeech`.
2. Piper ONNX for English (`en_US-lessac-low`, CPU, no CUDA).
3. Official Piper has no Bangla voice. Bengali script uses local **espeak-ng** (`-v bn`) when installed, or an optional `TTS_BN_MODEL_PATH` Piper voice. If neither exists, English Piper is used and `fallback=true`.
4. `POST /v1/speak` returns a WAV. `play: true` also plays on the server’s default output.
5. `voice_ready` is true only when LLM, STT, and TTS model files are all present.

## Phase 3 issues (open)

Verified on macOS arm64 / Python 3.12: English `POST /v1/speak` returned a Piper WAV (`en_US-lessac-low`, ~723 ms, ~2.1 s audio). Whisper round-trip transcribed it as `"Opening Visual Studio Code"`. Bangla used local espeak-ng (`-v bn`, ~61 ms). 44 tests passed. `voice_ready` is true when all three model files are on disk.

1. **No official Piper Bangla voice.** Neural Bangla TTS is not in this milestone unless you add a community `.onnx` via `TTS_BN_MODEL_PATH`.
2. **espeak-ng is required for decent Bangla.** Windows must install it separately (`choco install espeak`); otherwise Bangla falls back to English Piper with `X-Jarvis-Fallback: true`.
3. **Playback is best-effort.** `play: true` uses `sounddevice`; synthesis still succeeds if speakers are missing. Live speaker playback was not tested here (default `play: false`).
4. **Not proven on the Windows i3.** First speak loads the ONNX; keep `TTS_PRELOAD=false` unless you want that cost at startup.
5. **Do not load Piper, Whisper, and the LLM at once on 8 GB if the machine swaps.** All three are lazy-loaded independently.
6. **WAV out only.** `/v1/speak` returns PCM WAV. The Mac client (Phase 7) can play that locally.

## Phase 4 detail

Phase 4 proves the brain can plan actions without executing them:

1. `ToolRegistry` is the only catalog of names the LLM may emit.
2. Each tool declares schema, allowed targets (`windows` | `mac`), risk, and confirmation. `execute()` raises until Phase 6.
3. `IntentParser` asks the local GGUF for JSON (`tool_call` | `clarification` | `reply`), extracts an object even if the model wraps it, and validates arguments against the registry.
4. Risk and `requires_confirmation` come from the registry, never from the model.
5. `POST /v1/intent` returns a validated plan with `executed: false`. `GET /v1/tools` lists the catalog.
6. Default tools: `open_application`, `list_directory`, `get_system_info`, `create_folder`, `create_file`. No shell, no delete.

## Phase 4 issues (open)

Verified on macOS arm64 / Python 3.12: 65 tests passed. Live `POST /v1/intent` for `"VS Code ta open kore dao."` with `target: mac` returned `open_application` / Visual Studio Code / `mac` with `executed: false` (~4.7 s including GGUF load). Health reports 5 registered tools and `execution: disabled`.

1. **Plans only.** Nothing opens apps or touches the filesystem yet. Phase 5 adds safety; Phase 6/7 execute.
2. **1.5B JSON quality varies.** Intent uses `json_mode` and one retry. Ambiguous speech may become a clarification instead of a tool call.
3. **Delete and terminal waited for Phase 5.** They are now in the catalog and gated by safety.
4. **Not proven on the Windows i3.**
5. **Caller `target` wins.** If `POST /v1/intent` sets `"target":"mac"`, that overrides the model's target. Otherwise the model target is used, then `JARVIS_DEFAULT_TARGET` (windows).

## Phase 5 detail

Phase 5 proves the brain can refuse and confirm without trusting the LLM:

1. `SafetyEngine` reviews every tool plan. Risk, blocked paths, and blocked commands are deterministic.
2. LOW actions that pass policy are `allowed` (still not executed). MEDIUM/HIGH need confirmation. Independently blocked actions are `denied` even if the user says yes.
3. Confirmation is bound to `session_id` + `confirmation_id`. Another session cannot approve it. Spoken "yes"/"জি"/"no" on the same session works; `POST /v1/confirm` is the explicit API.
4. Hard denies include system/root paths, credential files, disk formatting, firewall/defender tampering, and download-and-run style commands.
5. `delete_path` and `run_terminal` are in the catalog so the model can name them; safety still blocks the dangerous cases.
6. `executed` remains false until Phase 6.

## Phase 5 issues (open)

Verified on macOS arm64 / Python 3.12: 82 tests passed. Live `POST /v1/intent` for create `~/Projects/demo` returned `confirmation_required`; `POST /v1/confirm` returned `confirmed: true` with `executed: false`. `Delete C:\Windows` returned `denied` / `blocked_by_policy` without echoing the action. Health reports 7 tools, `execution: disabled`, local safety policy.

1. **Execution moved to Phase 6.** Confirmation still cannot bypass hard denies.
2. **Policy is lexical.** Paths are normalized without touching the real filesystem, so some equivalent spellings could slip through until execution-time checks in Phase 6.
3. **Pending state is in-memory.** A process restart drops confirmations. TTL default is 120 seconds.
4. **Not proven on the Windows i3.**
5. **Spoken yes/no is a small phrase list.** Longer replies fall through to a new intent and cancel the pending action.

## Phase 6 detail

Phase 6 proves the brain can act on the local machine after safety:

1. `LocalToolExecutor` runs approved tools. The LLM still never calls the shell.
2. Windows backend launches known apps, lists/creates/deletes files inside the user home (and optional `JARVIS_WORKSPACE`), reports system info, and runs an allowlisted terminal (`python --version`, `git status`, `ls`/`dir`, …) with `shell=False`.
3. macOS/Linux dev uses `JARVIS_TOOLS_BACKEND=posix` (`open -a` for apps). `target: mac` is deferred until Phase 7.
4. Execution re-checks path roots and the command allowlist. `python -c` and shell metacharacters are rejected.
5. Health `tools.execution` is `windows`, `posix`, or `disabled`.

## Phase 6 issues (open)

Verified on macOS arm64 / Python 3.12: 91 tests passed. Live `POST /v1/intent` for system info returned `get_system_info` with `executed: true` (`Darwin 25.4.0` / arm64, posix backend). Health reports version `0.6.0` and `tools.execution: posix`. Mac `open_application` stays `deferred_mac`.

1. **Mac actions wait for a connected client.** `target: mac` returns `deferred_mac` until Phase 7's WebSocket body is attached.
2. **App launch is best-effort.** Unknown names fail if the executable is not in PATH or the usual install folders.
3. **Safe terminal is a small allowlist.** Arbitrary commands stay blocked even after confirmation.
4. **Not proven on the Windows i3.**
5. **Writes go to the real user home** unless tests override `HOME` / `JARVIS_WORKSPACE`.

## Phase 7 detail

Phase 7 proves the Mac body can act after the brain has planned and gated:

1. The brain keeps a single Mac WebSocket at `WS /v1/mac`. A new client replaces the old one.
2. Auth is the same shared token (`X-Jarvis-Token`, Bearer, or `?token=`). Bad auth closes with `1008`.
3. First message must be `hello` (`role: mac-client`). Unknown types are rejected.
4. `target: mac` tools are dispatched as `tool_request`. If no client is connected, the brain still returns `deferred_mac`.
5. The Mac client re-validates the tool name, schema, target, and hard safety denies before `LocalToolExecutor(force_local=True)` runs. It does not trust the network.
6. Health reports `mac.connected`, `hostname`, and client `version`.

## Phase 7 issues (open)

Verified on macOS arm64 / Python 3.12: 105 tests passed. Live `WS /v1/mac` connected (`Papais-MacBook-Air.local`, client `0.7.0`). Live `POST /v1/intent` `"VS Code ta open kore dao."` with `target: mac` returned `open_application` with `executed: true` (`open -a Visual Studio Code`) via the Mac client. Health reports version `0.7.0` and `mac.connected: true`. With no client, the same tool stays `deferred_mac`.

1. **One Mac at a time.** A second connection closes the first. No queue of bodies.
2. **The Mac still uses the brain's confirmation.** High-risk actions are confirmed on the brain session, then executed on the Mac. The client will still hard-deny blocked paths/commands.
3. **LAN only.** No TLS. Do not port-forward `/v1/mac`.
4. **Not proven on a separate Windows brain + Mac body pair.** Live checks in this environment run both on the same Mac.
5. **Timeouts return `mac_timeout`.** Default `JARVIS_MAC_TIMEOUT_SECONDS=20`.

## Phase 8 detail

Phase 8 proves the brain can remember a few facts locally:

1. SQLite at `JARVIS_MEMORY_PATH` (default `data/jarvis.sqlite`) using stdlib `sqlite3`. No SQLAlchemy.
2. Allowlisted preferences (`default_projects_directory`, `preferred_language`, `address_as`), path/application aliases, and a capped task history.
3. `"My projects are normally inside ~/Projects."` is captured without the LLM. `remember_preference` is also in the catalog.
4. Bare folder/file names are joined to `default_projects_directory` before safety. Path aliases cover Downloads/Documents/Desktop/Projects.
5. Successful `open_application` names are learned as aliases. Memory tools always run on the brain, not the Mac.
6. Health reports `memory.ok` plus counts. CRUD lives at `/v1/memory/*`.

## Phase 8 issues (open)

Verified on macOS arm64 / Python 3.12: 119 tests passed. Live `POST /v1/intent` `"My projects are normally inside ~/Projects."` returned `remember_preference` with `executed: true` and `reason: remembered` without loading the GGUF. Health reports version `0.8.0`, 8 tools, `memory.ok: true` (1 preference, 4 path aliases). `GET /v1/memory/history` showed that task.

1. **Allowlisted keys only.** Arbitrary facts, conversation summaries, and secrets are not stored.
2. **History is short.** Default 200 rows; arguments are truncated. This is not a full chat log.
3. **Path expansion is lexical.** `~/Projects/TestApp` is still confirmed before create.
4. **Not proven on the Windows i3.**
5. **The 1.5B model may still reply instead of calling `remember_preference`.** The projects-directory phrase is handled by a matcher so that example works anyway.


## Runtime layout (target)

```
JARVIS/
├── server/          # Windows brain (FastAPI)
│   ├── ai/          # LLM, STT, TTS, intent parser
│   ├── tools/       # registry + local executor (Windows/posix)
│   ├── safety/      # policy, confirmation store
│   ├── memory/      # SQLite preferences, aliases, history
│   ├── mac/         # WebSocket bridge to the Mac body
│   └── api/
├── mac_client/      # macOS body (Phase 7)
├── data/            # local SQLite (gitignored db files)
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
