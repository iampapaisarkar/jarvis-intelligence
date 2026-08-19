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
| **1** | Python FastAPI server, llama.cpp, GGUF load, `/health`, `/v1/chat`, config, logging | **this milestone** |
| 2 | Local STT (whisper.cpp), microphone/audio input | not started |
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
