Below is a high‑level architecture that you can grow into a fairly sophisticated distributed, JACK‑centric voice/agent system. I’ll keep it top‑down and Linux‑oriented, but with enough specificity that you can see how the pieces will talk to each other and evolve.

---

## 0. Overall Architectural Style

Think in terms of **modular services** with a few shared foundations:

- **Core process**: A main daemon per host, responsible for:
  - Attaching to JACK, MIDI, OSC, JackTrip, etc.
  - Hosting a **plugin system** (for commands, tools, STT/TTS backends, LLM tools).
  - Exposing a **network API** to other hosts.
- **Shared data & config**:
  - PostgreSQL (+ pgvector) for long‑term state, corpora, sessions.
  - A config/registry layer for:
    - Hosts and their capabilities (STT/TTS/LLM).
    - User-level settings (preferred models, wakewords, keys).
- **Protocol boundaries**:
  - Internally: local event bus (in‑process, e.g., pub/sub) between modules.
  - Externally: HTTP/JSON or gRPC between hosts (keep it boring and debuggable).

You can implement this “skeleton app” initially as a **single process per host** (monolith with good internal boundaries), then later peel off subsystems into separate services if/when needed.

---

## 1. JACK‑centric Audio Subsystem (Backbone)

**Goal:** A clean, reusable audio spine so everything else can attach without re‑inventing I/O.

**Key roles:**
- Manage JACK client(s) per host.
- Expose named JACK ports:
  - `system:capture_X` or arbitrary user‑signatured ports.
  - Internal ports for STT “listeners”, TTS playback, etc.
- Provide a small API to other modules:
  - Subscribe to audio streams (for STT or analysis).
  - Create audio output sinks.
  - Manage JACK connections (autoconnect, routing rules).

**Core design:**
- One **Audio Manager** component:
  - Written in a JACK‑friendly language (C++/Rust/C).
  - Thin wrapper that:
    - Registers a few default ports: `voice_in`, `voice_out`, `system_out`.
    - Handles JACK callbacks, real‑time constraints.
  - Internally hands off audio buffers to:
    - STT module (or an STT plugin chain).
    - “Monitoring” pipeline (for wakeword, VAD).

Keep **real‑time safe** code in the JACK callback; push heavy work (STT, LLM, TTS) to worker threads via lock‑free queues/ringbuffers.

---

## 2. “Always‑On” Speech & Wake‑Word Subsystem

**Goal:** Continuous listening on one or more JACK inputs, with:

- Wake‑word detection (per‑host configurable).
- Voice activity detection (VAD) to gate STT.
- Interaction state machine (listening / speaking / barged‑in, etc.).
- Command recognition and plugin integration.

### 2.1. Audio Pipeline Topology

1. **Raw audio from JACK** →  
2. **VAD & wake‑word detector** (low‑latency, always‑on) →  
3. **STT request pipeline** (only when “awake” + VAD=voice) →  
4. **Command dispatcher** (match transcripts against commands / aliases) →  
5. **Agent / LLM orchestration** (if needed) →  
6. **Response (TTS, MIDI/OSC, actions, etc.)**

### 2.2. Wake‑Word & VAD

- Consider a small, embeddable wake‑word / VAD stack:
  - E.g., WebRTC VAD, Silero VAD, or something similar; small models.
  - Wake‑word: off‑the‑shelf engine (e.g., Porcupine) or your own small model.
- Requirements:
  - Low latency: process short frames (10–30 ms).
  - Non‑blocking: pass data to a dedicated audio analysis thread.

**Per‑host config**:
- `wakeword`: string (“Computer”, “Helena”, etc.), and model/thresholds.
- Input JACK ports to monitor.
- VAD sensitivity, silence timeout, etc.

### 2.3. Speech Recognition (STT)

You’ll probably want multiple STT backends:

- Local offline (e.g., Vosk, Whisper.cpp, Coqui, etc.).
- Remote (e.g., Whisper API, or any service over HTTP).

**Design:**
- A **STT Service Interface**:
  - Methods: `start_stream()`, `feed_audio()`, `end_stream()`, `cancel()`.
  - Returns partial and final transcripts via callbacks or async events.
- Backends as plugins implementing this interface:
  - A default minimal STT.
  - Optional plugins for remote APIs, specialized domains, etc.

**Latency vs quality strategy:**
- For always‑on wake‑word & commands:
  - Prefer fast, small models or low‑bitrate remote endpoints.
- For complex, longer queries:
  - Accept higher latency (larger models, higher accuracy).
- You can treat “wake‑word + short command” as a separate STT mode (e.g. smaller context window, limited vocabulary or grammar).

### 2.4. Command Recognition & Plugins

**Command registry:**

- A **Command Manager** with:
  - Command definitions:
    - `name`: canonical command.
    - `aliases`: list of strings/patterns.
    - `intent_type`: “local function”, “agent task”, “remote call”, etc.
    - `handler`: plugin hook.
  - Simple pattern matching first:
    - Rule‑based (regex, keyword, or template).
    - Optionally, a small intent classifier or LLM‑aided parser later.

**Plugin system basics:**

- Define a minimal plugin contract:
  - Register commands (names, aliases, help text).
  - Optionally expose tools/functions to the LLM subsystem.
  - Optionally register TTS/STT backends, audio responders, etc.
- Implementation approach:
  - Dynamic libraries (C‑ABI) or language‑level plugins (e.g., Python entry points).
  - Start with a simple “plugins folder” and config entries per plugin.

**Stateful interaction:**

- Maintain per‑session context:
  - Current “mode” (e.g., “music control mode”, “system admin mode”).
  - Context should influence which commands are active or prioritized.
- Command handlers may:
  - Execute local actions.
  - Initiate LLM workflows.
  - Emit events to MIDI/OSC.

---

## 3. LLM / Agentic Subsystem

**Goal:** A flexible framework that:

- Supports **frontier** APIs (OpenAI, Anthropic, etc.).
- Favors **Ollama** by default (localhost & multiple LAN hosts).
- Uses PostgreSQL + pgvector for RAG and persistence.
- Encourages “tiny steps” workflows for constrained hardware.

### 3.1. Model & Provider Abstraction

Create a **Model Provider** interface:

- Methods:
  - `list_models()`
  - `completion(request)` (chat/completion)
  - `embedding(request)`
  - Possibly: `tool_calling(request)` or `function_calling`.

Backends:

- **Ollama Provider**:
  - Default host: `http://localhost:11434`.
  - Configurable multiple hosts: keep a table in Postgres (host, tags, capabilities, priority).
- **Cloud Providers**:
  - OpenAI, Anthropic, etc.
  - On first call:
    - Check stored API keys.
    - If missing, prompt user (CLI/web UI), then store encrypted in Postgres (or at least hashed / obfuscated on disk).
- **Selection logic:**
  - Per‑request policy (from config or plugin):
    - “Prefer local Ollama if model available, else fallback to cloud.”
    - Or “Send heavy generative tasks to remote frontier model, use local for RAG or summarization.”

3.2. Agent Framework (continued)

Design your “agent” as a small, composable runtime rather than a heavyweight framework. Think:

- A **planner** that decides “what’s the next tiny step?”
- An **executor** that calls tools or sub‑models.
- A **state store** that remembers where we are in the task.

### Agent Manager responsibilities

- Maintain **agent sessions**:
  - Session ID, user, active tools, current goal, step history.
- Provide a **standard call**:
  - Input: instructions, current context, tools available.
  - Output: next action:
    - `call_tool(tool_name, arguments)`
    - or `send_reply(text)`
    - or `decompose(task into subtasks)`

Even if everything runs in one process initially, keep clear boundaries:

- **Planner**: wraps an LLM call with a prompt that:
  - Encourages short, atomic actions.
  - Exposes a list of tools with their natural‑language descriptions and parameter schemas.
- **Executor**:
  - Validates tool arguments.
  - Calls the tool (local code, network endpoint, or another agent).
  - Writes results into session state and returns back to the planner.

You can run this in **loop** mode for complex tasks:

1. User speaks: “Back up my music folder, then summarize the last week’s logs.”
2. STT → command → agent: initial goal.
3. Planner: break into `["backup_music", "summarize_logs"]`.
4. Executor: calls corresponding tools.
5. Planner: once subtasks complete, generate final answer.

This tiny‑step, iterative structure matches your desktop hardware limits: models can be smaller and used more times rather than one giant, long‑context call.

---

### 3.3. RAG & Vector Store (PostgreSQL + pgvector)

Use Postgres for:

- **Corpus metadata**: documents, chunks, tags, source paths.
- **Text + embeddings** (pgvector) for RAG.
- **Session context** (messages, tool calls, summary vectors).

#### Corpus design

Tables (conceptually):

- `corpus`: name, description, owner, creation time.
- `document`: corpus_id, path/URI, metadata (JSON), timestamps.
- `chunk`: document_id, text, embedding (pgvector), position/order, tags.

Capabilities:

- Ingest pipeline:
  - Text / Markdown / PDF / code, etc., broken into chunks.
  - Use an embedding model (local via Ollama or remote).
  - Insert into `chunk` with embedding column.
- Query pipeline:
  - Given user question and optional corpus:
    - Embed query.
    - `SELECT ... ORDER BY embedding <-> query_embedding LIMIT k`
    - Return top‑k chunks to include in LLM context.

#### Session management and context length

You’ll need to manage tokens strictly:

- Track **per‑session message history**:
  - Role (`user`, `assistant`, `tool`).
  - Content + any references to RAG chunk IDs.
- Before each LLM call:
  - Estimate token usage.
  - Implement a **context manager** that:
    - Summarizes older parts of the dialog into shorter abstractions.
    - Drops irrelevant messages beyond some horizon.
- Use Postgres to:
  - Store raw messages.
  - Store compressed “summary states” (e.g., last N turns summarized).
  - Optionally store a vector embedding for the conversation so far to do retrieval of past turns.

---

### 3.4. API Key & Model Configuration

Config should centralize:

- **Model registry**:
  - Name, provider, endpoint, type (chat, embedding, both).
  - Cost, speed hints, max context length.
- **API key store**:
  - Encrypted at rest using a host secret (e.g., libsodium, OpenSSL).
  - Key per provider, per user or per system account.
- **User preferences**:
  - Default model for chit‑chat.
  - Default model for agent planning.
  - Embedding model choice.

Interaction:

- On first call to a provider that needs a key:
  - The LLM subsystem raises a “credentials required” event.
  - UI component (CLI / web) prompts user.
  - Key stored securely and provider marked as “usable”.

---

## 4. Text‑to‑Speech Subsystem

You’re constrained to Piper‑TTS (which is fine, it’s efficient). Architect it as a pluggable service just like STT.

### 4.1. TTS Service Interface

Define a simple abstraction:

- Input: text (possibly with SSML / markup), voice parameters, language.
- Output: audio stream (e.g., PCM) or file handle.
- Modes:
  - **Synchronous**: generate audio, then hand to JACK for playback.
  - **Streaming**: generate audio in chunks while speaking (ideal for near real‑time).

Initial implementation can be synchronous Piper, then you can refine.

### 4.2. Sentence‑level or chunked synthesis

To reduce response latency:

- Preprocess text into **sentences** or sub‑sentences.
- Start TTS generation for the first sentence while the LLM finishes the next.
- For longer agent responses:
  - Ask the LLM to produce output in controlled chunks (e.g., sentences separated by a special token).
  - Dispatch to TTS as soon as each unit arrives.

Audio pipeline:

1. Agent / LLM generates text.
2. TTS Manager:
   - Chunk text.
   - Schedule TTS jobs.
   - Stream PCM back to the Audio Manager.
3. Audio Manager plays into a JACK output port dedicated to “assistant voice”.

### 4.3. Integration with Speech Recognition

You’ll want **barging‑in** behavior:

- The same module that manages **interaction state** (wake‑word & commands) should:
  - Know when TTS is speaking (e.g., “assistant talking” flag).
  - Detect new voice activity while TTS is playing.
  - If a “barge‑in” event occurs:
    - Fade out / cut TTS audio on JACK.
    - Switch the pipeline back to STT listening state.
    - Possibly store truncated response as “interrupted” if you want to recover later.

The coordination is mostly state‑machine logic:

- `idle` → `wakeword_detected` → `listening_for_command` → `processing` → `responding` → back to `idle`.
- Override transitions when barging‑in is detected.

---

## 5. Network API & Multi‑Node Topology

You want multiple nodes on a LAN, each potentially specializing in STT, TTS, LLM, etc.

### 5.1. Node Registry & Discovery

Maintain a **Node Registry** in PostgreSQL (or a small config file distributed manually at first):

- For each host:
  - `node_id`, `hostname`, `IP`, `capabilities` (JSON).
  - `role` tags: `["stt", "tts", "llm", "corpus"]`, etc.
  - Status (online/offline, health check timestamp).

Discovery options:

- **Static**: you pre‑configure nodes.
- **Semi‑dynamic**: nodes register themselves with a central database or a “directory service” upon startup.
- **Peer‑to‑peer** later if you want (e.g., mDNS or gossip).

### 5.2. Network Protocol Basics

Use something you can easily debug:

- **HTTP/JSON** or HTTP+WebSocket:
  - e.g., `/api/v1/stt/stream`, `/api/v1/tts/synthesize`, `/api/v1/llm/chat`.
- You can add gRPC later for efficiency, but JSON gets you off the ground quickly.

Expose a minimal but consistent set of APIs:

- LLM node:
  - `POST /chat`
  - `POST /embed`
  - `POST /agent/run`
- STT node:
  - `POST /stt/stream` (or WebSocket for streaming audio)
- TTS node:
  - `POST /tts/synthesize` (returns audio or a URL to an audio stream/file)
- Utility endpoints:
  - `/health`
  - `/capabilities` (what models/backends are available, load, etc.)

### 5.3. Remote Execution Policies

On any node that can *delegate* work, you want a simple policy layer that decides:

- “Do I run this **locally**, or send it to another node?”
- “If remote, **which** node?”

#### Capability Router

Conceptually, have a **Capability Router** with:

- Inputs:
  - Requested capability (e.g., `stt`, `tts`, `llm`, `rag`, specific model name).
  - Optional constraints:
    - Latency sensitivity (“interactive”, “batch”).
    - Privacy requirements (“must stay local”).
    - Preferred hardware tags (e.g., “GPU”, “low‑power”).
- Outputs:
  - A target: `local` or `node_id` + endpoint URL.

Use information from the **Node Registry**:

- Each node advertises:
  - Capabilities (`stt`, `tts`, `llm`, etc.).
  - List of models, languages, or voices.
  - Optional load metrics (simple: recent QPS or a “busy” flag).

Routing policies (start simple, then refine):

- **Capability‑first, then locality**:
  - If capability is available locally, use it.
  - Else choose a remote node advertising that capability.
- **Model‑specific**:
  - If a specific model is requested (e.g., `llama3:8b`):
    - Prefer node(s) that actually host it.
- **Preference / weighting**:
  - Configurable per capability:
    - “Always use remote LLM for big models.”
    - “Prefer remote TTS node with better CPU.”
    - “Force all STT local for privacy.”

This router becomes the central “traffic cop” whenever a plugin, command, or agent asks for STT/TTS/LLM/RAG.

---

## 6. MIDI, OSC, and JackTrip Integration

You want the system to also act as a **musical/interactive node** in a JACK/JackTrip environment with MIDI and OSC support.

### 6.1. MIDI Subsystem

Design a **MIDI Manager** parallel to the Audio Manager:

- Responsibilities:
  - Open ALSA/JACK MIDI ports.
  - Expose virtual MIDI ports:
    - `assistant:midi_out` (for sending notes/CCs).
    - `assistant:midi_in` (for receiving).
  - Provide a simple API/event bus:
    - Other modules can subscribe to MIDI input events.
    - Plugins can send MIDI messages (for lighting control, synths, etc.).

Integration points:

- Commands:
  - “Play C major chord” → command handler → MIDI Manager emits notes to a synth.
- Agents:
  - Tools that query current MIDI state, send control changes, etc.
- State:
  - Keep track of active notes, modes, and mapping rules (e.g., map certain MIDI CCs to assistant commands).

### 6.2. OSC Subsystem

An **OSC Manager**:

- Responsibilities:
  - Open a UDP port for OSC.
  - Allow registration of OSC address handlers:
    - `/assistant/command`, `/assistant/state`, `/lights/*`, etc.
  - Provide an outbound API:
    - Send OSC messages to external hosts or DAWs.

Use cases:

- External systems triggering assistant commands:
  - `/assistant/command "start recording"`
- Assistant controlling visual feedback or remote systems:
  - `/lights/scene 3`
  - `/fx/reverb amount 0.5`
- Expose high‑level assistant state over OSC:
  - `/assistant/state "listening"`, `/assistant/state "speaking"`.

This makes your assistant automatable from DAWs, performance rigs, or Max/MSP/Pd environments.

### 6.3. JackTrip & Multi‑Host Audio

Given you’re already using JACK over Ethernet with JackTrip:

- Treat JackTrip links as part of the **audio topology**, not as a separate subsystem.
- On each host:
  - Audio Manager exposes JACK ports that can be fed into/out of JackTrip.
  - That way, audio from remote hosts appears locally as JACK inputs/outputs.

Scenarios:

- **Centralized STT/TTS**:
  - A “voice hub” host:
    - JackTrip‑connected to other machines.
    - Receives their audio through JACK.
    - Runs STT and TTS centrally.
- **Distributed processing**:
  - One host specializes in STT (fast CPU).
  - Another host is a performance machine using MIDI/OSC, but sends its spoken command inputs over JackTrip to the STT node.

The **Node Registry** and Capability Router should be aware that:

- Some nodes expose **audio** capabilities via JackTrip/JACK (for low‑latency cross‑host audio),
- While high‑level **STT/LLM/TTS** may go via HTTP/JSON over the regular LAN.

---

## 7. Putting It All Together (Baseline Skeleton) – resumed

Think of one **daemon per host** with clearly separated internal modules. This gives you a “skeleton app” that can grow without needing to re‑architect every time.

### 7.1. Core Modules in the Daemon

Each node runs these main components (all in one process at first):

1. **Config & Registry Layer**
2. **Audio Manager (JACK)**
3. **Speech Subsystem (Wake‑word + STT + Command layer)**
4. **LLM / Agentic Subsystem**
5. **TTS Subsystem**
6. **MIDI / OSC Subsystem**
7. **Network/API Layer**
8. **Plugin System**

Below is how they interact conceptually.

---

### 7.2. High‑Level Data Flow

#### 7.2.1. Voice‑in → Command/Agent → Voice‑out

1. **Audio in (JACK)**  
   - Audio Manager reads from `voice_in` JACK port (which you can patch from any mic or JackTrip input).
   - Frames are passed to a **VAD + wake‑word** pipeline in the Speech Subsystem.

2. **Wake‑word & VAD**  
   - If no speech or wake‑word: stay idle, low CPU.  
   - When wake‑word is detected:
     - Switch state to `listening_for_command`.
     - Start capturing buffered audio for STT.

3. **STT & Command Recognition**
   - Speech Subsystem chooses an **STT backend**:
     - Local plugin, or via Capability Router to a remote STT node.
   - Transcription goes into the **Command Manager**:
     - Match against registered commands + aliases.
     - If a simple command: dispatch to that plugin/tool directly.
     - If more free‑form or complex: hand off to the **Agent Manager**.

4. **Agent / LLM Processing**
   - Agent Manager:
     - Uses the LLM Provider layer (prefer local Ollama if available).
     - Optionally does RAG using Postgres+pgvector, depending on the tool/command.
     - Executes a sequence of tiny steps:
       - Tool calls, sub‑tasks, clarifications.
   - Produces **response text** and possibly side effects (MIDI/OSC messages, external API calls, file operations…).

5. **TTS & Voice‑out**
   - TTS Subsystem:
     - Takes response text, chunks by sentence (or smaller).
     - Uses Piper backend (locally or routed to a TTS node).
     - Streams audio back to the Audio Manager as PCM.
   - Audio Manager:
     - Plays the assistant’s voice through `voice_out` JACK port.
     - Interaction state becomes `speaking`.

6. **Barge‑in / Interruption**
   - If VAD detects user speech while `speaking`:
     - Trigger **barge‑in**:
       - Fade or stop TTS playback.
       - Return to `listening_for_command`.
     - Allow overlapped interactions in a natural way.

---

### 7.3. Multi‑Node & Network Layer

#### 7.3.1. Node Roles

Each node uses the same software skeleton but can **specialize** via config:

- Node A: `roles = ["stt", "tts"]`
- Node B: `roles = ["llm", "rag"]`
- Node C: `roles = ["client", "jack_performance"]`

Each node:

- Registers itself in a **Node Registry** (central Postgres or simple config):
  - Hostname/IP, roles, capabilities, active models, languages, voices.
- Exposes HTTP/JSON (or WebSocket where useful) endpoints for:
  - `/stt/*`, `/tts/*`, `/llm/*`, `/agent/*`, `/rag/*`, `/capabilities`, `/health`.

#### 7.3.2. Capability Routing

The **Capability Router** in each daemon:

- Given a request like “need STT (English, low latency)”:
  - Check local capabilities first.
  - Otherwise select a remote node with `role="stt"` and matching language.
- Given “need LLM model=llama3:8b or similar”:
  - Prefer local Ollama if host has that model.
  - Else find a remote LLM node that advertises that model.

All this remains **transparent** to higher‑level modules:

- Speech Subsystem just asks “STT:English:fast”.
- Agent Manager just asks “LLM:chat:preferred_for_planning”.
- TTS Subsystem just asks “TTS:en:voice=default”.

---

### 7.4. Plugin System as the Growth Engine

Plugins are how you turn this skeleton into “any small or medium‑sized app.”

**Plugin capabilities could include:**

- New commands:
  - “control DAW transport”, “launch backup job”, “search file system”, etc.
- New tools for the Agent:
  - “search logs”, “query monitoring DB”, “convert music format”.
- New STT/TTS/LLM backends:
  - Another local engine, or wrappers around remote services.
- New MIDI/OSC behaviors:
  - Map commands to specific MIDI notes/CCs.
  - Map state to OSC feedback.
- New RAG corpora or ingestion flows:
  - Code base documentation, music metadata, personal notes.

The core daemon only needs a **stable plugin API** that exposes:

- Registration of commands, tools, event handlers.
- Access to core services (LLM, STT, TTS, RAG, MIDI, OSC, registry, etc.).

---

### 7.5. Initial Minimal Implementation (Pragmatic Starting Point) – resumed

Start with a **single host** and keep the skeleton thin but correctly separated. Then grow.

#### Phase 1: Single‑Node, Voice → LLM → Voice

**Subsystems to implement first:**

1. **Config & Registry (minimal)**
   - Local config file (YAML/TOML/JSON) for:
     - Node ID, host name.
     - Role: `"all"` for now.
     - Ollama host: `http://localhost:11434`.
     - Path to Postgres (or even skip Postgres in v0 and stub RAG).
   - Hard‑coded or file‑based commands:
     - `time`, `joke`, `say <text>`, etc.

2. **Audio + Speech**
   - JACK client with:
     - Input port `assistant:voice_in`
     - Output port `assistant:voice_out`
   - Attach `voice_in` to your mic (or JackTrip feed) manually first.
   - Implement:
     - Basic VAD (e.g., any simple energy‑based or small model).
     - Simple wake‑word detection (fixed word and threshold).
   - On wake‑word:
     - Capture audio for a fixed window (e.g., 3–5 seconds) and send to STT.

3. **STT (single backend)**
   - One local STT backend only (e.g., Whisper.cpp or Vosk).
   - Interface is still abstract (`stt.transcribe(audio)`) to keep room for future plugins.
   - Return a full transcript once the captured window is over.

4. **Command Layer**
   - Very small command registry:
     - `“what time is it”` → local time response.
     - `“say <something>”` → echo text back.
     - `“ask model <question>”` → send to LLM.
   - Matching:
     - Simple string/regex matching for now.
   - If no direct match:
     - Fallback to an LLM call (“assistant mode”).

5. **LLM Subsystem**
   - Single provider: Ollama.
   - Single chat model: configurable name (e.g., `llama3`).
   - No agent loops yet:
     - One request, one reply.
   - Minimal RAG stub:
     - Skip Postgres/pgvector in this phase, or just hard‑code a couple of “knowledge snippets” if you need.

6. **TTS (Piper only)**
   - Wrap Piper as a blocking call:
     - Input text → generate WAV/PCM → push to JACK output.
   - Keep chunking simple:
     - Split on sentence boundaries but still synthesize sequentially.
   - Basic integration:
     - Once command/LLM returns text, send to TTS; no barging‑in yet.

7. **Network/API**
   - Expose just:
     - `/health` (always OK),
     - `/capabilities` (hard‑coded JSON).
   - Do not yet route STT/LLM/TTS to other nodes.

8. **Plugin System**
   - For v0, you can:
     - Implement commands as built‑ins, but **structure them like plugins** (e.g., a registry API in your code).
   - No dynamic loading yet; just static registration.
   - But define a clear interface so dynamic plugins are easy later.

This gives you a working, **single‑machine voice assistant over JACK**, LLM via Ollama, TTS via Piper, with a clear modular boundary.

---

### 7.6. Phase 2: Solidify Boundaries & Add Minimal Persistence

Once v0 works end‑to‑end:

1. **Introduce PostgreSQL (+ optional pgvector)**
   - Use it for:
     - Sessions:
       - Store user utterances and assistant replies.
     - Model/host registry (even if single node).
   - Start with RAG for a single small corpus:
     - Ingest a few text files.
     - Use Ollama to embed and store vectors.

2. **Session & Context Management**
   - Add basic conversation history:
     - Maintain last N messages in memory.
     - Flush to Postgres.
   - Implement simple context window control:
     - Limit to e.g., 20 message pairs.
     - Optionally summarize older parts and store a “summary” string.

3. **Refine Agent Skeleton**
   - Wrap the LLM call with:
     - A lighter “planner” prompt for tasks that could need steps.
   - Add at least one tool:
     - E.g., a file system tool (“read file X”).
   - Implement a 2–3 step loop for a specific scenario:
     - “Summarize file X” → plan: read file → call LLM on contents.

4. **Basic Plugin Mechanism**
   - Move a couple of built‑in commands into separately loadable modules (even if still built with the same language build system).
   - Require each plugin to:
     - Register commands.
     - Optionally register tools.
   - Internally still static, but conceptually pluginized.

---

### 7.7. Phase 3: Multi‑Node & Realtime Niceties – resumed

At this stage, the single‑node skeleton is working. Now you make it **distributed and more conversationally polished**.

#### 7.7.1. Node Registry & Capability Routing (operational)

You already defined the schema conceptually; now you actually **use it** at runtime:

- Each node:
  - On startup, registers itself in Postgres (or via a small “directory service” daemon) with:
    - Network address (host/IP + port).
    - Roles (e.g., `["stt","tts"]`, `["llm","rag"]`).
    - Detailed capabilities:
      - Available models, languages, voices, hardware tag (CPU/GPU).
  - Periodically sends a heartbeat (`last_seen`) or `/health` ping.

- The **Capability Router** becomes the standard entry point for:
  - STT requests: “need STT:lang=en, mode=interactive”.
  - LLM requests: “need LLM:model=llama3 or class=‘planner’”.
  - TTS requests: “need TTS:voice=xyz”.

Routing rules (now applied concretely):

- Default: **prefer local**, fallback to remote.
- For heavy jobs (e.g., long LLM tasks, large RAG contexts):
  - Prefer nodes tagged with better hardware (`gpu=true`, `high_mem=true`).
- For privacy‑sensitive tasks:
  - Config flag: “no remote calls for this capability”.

---

#### 7.7.2. Make STT and TTS Fully Delegatable

You expose **full STT/TTS APIs** and teach the local subsystems to use them.

**Remote STT:**

- On STT node:
  - Provide HTTP/WS endpoints:
    - Batch: `/stt/transcribe` with an audio file or raw PCM.
    - Streaming: `/stt/stream` (WebSocket or chunked HTTP).
- On client node:
  - Speech Subsystem uses Capability Router:
    - If local STT unavailable or undesired:
      - Send audio (or audio stream) to remote STT.
      - Receive transcripts incrementally.
  - Integration with wake‑word / VAD still local:
    - Only send the audio segments that correspond to “commands” to STT.

**Remote TTS:**

- On TTS node:
  - Provide:
    - `/tts/synthesize` that returns:
      - Either a full audio file (for short responses),
      - Or a URL / stream token to pull chunks.
- On client node:
  - TTS Subsystem:
    - If remote is selected:
      - Send text to TTS node, stream back audio.
      - Pipe returned PCM into local JACK output.
  - You keep the **timing and barge‑in state machine local**.

---

#### 7.7.3. Barge‑In / Interruption (refined)

Add full **conversational turn‑taking** behavior.

Components involved:

- VAD & wake‑word detector (always running on local input).
- TTS playback (local JACK output).
- A simple global **Interaction State** object (in the Speech Subsystem).

**State machine behavior:**

- When TTS is speaking:
  - State is `speaking`.
  - VAD is still monitoring mic input.
- If VAD detects user speech above a threshold:
  - Optionally require wake‑word again (or not, depending on UX choice).
  - Trigger **barge‑in**:
    - Set state to `interrupting`.
    - Signal Audio Manager to:
      - Fade out or immediately stop TTS audio to `voice_out`.
    - Once TTS is stopped:
      - Switch state to `listening_for_command`.
      - Begin STT capture for the new utterance.

**Implementation details to consider:**

- Use a short **hysteresis**:
  - Don’t cut TTS for every tiny noise.
- Optionally support:
  - “Always‑available wake‑word”: require wake‑word to barge.
  - “Continuous conversation”: allow barge‑in on any speech while TTS runs.
- Manage overlapping tasks:
  - The interrupted agent/command run:
    - Mark as `interrupted` in session metadata.
    - Decide whether to cancel fully or leave result to be retrieved later.

---

#### 7.7.4. Richer Agent Flows & Tools

Once multi‑node and barge‑in are stable, make the **Agent Manager** more expressive:

- Add more **tools**:
  - File I/O, system status, music library, home automation, DAW control (via MIDI/OSC).
- Allow **chained tools**:
  - Plan: “Search logs → summarize results → create short spoken summary.”
- Use remote LLM nodes when appropriate:
  - Planner model on a GPU node.
  - Cheap local model for quick follow‑ups and paraphrasing.
- Start using:
  - RAG properly for:
    - Local manual pages, project docs, system configuration, etc.

The skeleton still doesn’t need complex orchestration frameworks; just a clear loop:

1. Planner decides action.
2. Executor calls tool/LLM/RAG (local or remote).
3. Updates state.
4. Repeat until `done` or `max_steps`.

---

#### 7.7.5. MIDI/OSC as First‑Class Behaviors

Now that the core assistant behavior is in place:

- Extend plugin system to **MIDI/OSC plugins**:
  - Commands that trigger MIDI notes or CC changes.
  - Agent tools that send/receive OSC messages to control external systems (lighting, DAW scenes, etc.).
- Tie assistant **state** to OSC:
  - Broadcast `/assistant/state "idle|listening|speaking|processing"`.
- Use MIDI/OSC as alternative input paths:
  - Footswitch sends MIDI to trigger wake‑word bypass or push‑to‑talk.
  - OSC from a performance rig to mute/unmute the assistant or change “mode”.

This makes the skeleton app function well in **audio performance** and **studio** contexts, not just as a desktop assistant.

---

#### 7.7.6. From Skeleton to “Any Small/Medium App”

At this point, the **architecture is stable**:

- You have:
  - Audio backbone via JACK.
  - STT/TTS pluggable and distributable.
  - LLM/Agentic subsystem with model/provider abstraction.
  - RAG via Postgres+pgvector.
  - MIDI/OSC and JackTrip integrated.
  - Network/API and Node Registry for multi‑host orchestration.
  - Plugin system as the extension point.

To create a new “app” (e.g., studio assistant, home automation controller, music performance system), you now mostly:

- Write **plugins** (commands + tools + perhaps custom corpora),
- Adjust **routing policies** and **node roles**,
- Configure **models and corpora** for that domain.

You don’t have to re‑design the skeleton; you just slot in new behaviors and tune configs.