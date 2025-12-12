# Quick Start Guide

## What We've Built

A foundational Python framework for the distributed voice/agent system described in PLAN.md. This is **Phase 1A** of the implementation - core infrastructure ready to grow.

## Current Features

### ✅ Implemented

1. **Configuration Management**
   - YAML-based config with environment variable substitution
   - Pydantic models for type safety
   - Per-node role and capability definitions
   - Support for multiple LLM providers

2. **Node Registry & Capability Routing**
   - Track distributed nodes and their capabilities
   - Smart routing based on capability requirements
   - Local-first with remote fallback
   - Load balancing preparation

3. **LLM Provider Abstraction**
   - Ollama (local, default)
   - OpenAI (cloud)
   - Anthropic (cloud)
   - Unified interface for chat and embeddings
   - Streaming support

4. **CLI Tools**
   - Interactive REPL for testing LLM conversations
   - System info command
   - Placeholder for transcription

## Getting Started

### 1. Verify Installation

```bash
# Activate your virtual environment
source .venv/bin/activate

# Check that the CLI works
skeleton --help
skeleton info
```

### 2. Test the LLM REPL

The REPL will automatically try:
1. Ollama (localhost:11434) first
2. OpenAI API (if key in .env)
3. Anthropic API (if key in .env)

```bash
skeleton repl
```

In the REPL:
- Type messages naturally to chat with the LLM
- `/stream` - Toggle streaming mode
- `/clear` - Clear conversation history
- `/quit` - Exit

### 3. Configure for Your Network

Edit `config.yaml` to match your hardware setup:

```yaml
node:
  id: "linux-01"  # Unique ID for this node
  name: "Main Linux Node"
  host: "0.0.0.0"
  port: 8000
  roles:
    - "stt_realtime"    # Will run Vosk
    - "tts"             # Will run Piper
    - "llm_light"       # 3B models
    - "audio_hub"       # JACK audio routing
  
  tags:
    platform: "linux"
    gpu: "nvidia-1050ti"
    ram: "32GB"
```

For your Windows node:

```yaml
node:
  id: "windows-main"
  name: "Windows Heavy Compute"
  roles:
    - "llm_heavy"       # 8B models
    - "stt_batch"       # Whisper transcription
    - "rag_engine"      # Vector search
  
  tags:
    platform: "windows"
    gpu: "nvidia-3060"
```

### 4. Add Remote Nodes

In `config.yaml`, register other nodes on your LAN:

```yaml
network:
  registry:
    nodes:
      - id: "windows-main"
        host: "192.168.1.100"
        port: 8000
        roles: ["llm_heavy", "stt_batch"]
        tags:
          platform: "windows"
          gpu: "nvidia-3060"
```

## Next Steps - Phase 1B

Now that the foundation is in place, here's what to build next:

### Priority 1: Voice Pipeline (Single Node)
- [ ] Integrate Vosk for real-time STT
- [ ] Integrate Piper for TTS
- [ ] Simple wake-word detection
- [ ] Basic command matching
- [ ] Text-only flow first (simulate voice)

### Priority 2: JACK Audio
- [ ] Audio Manager with JACK client
- [ ] Input/output port management
- [ ] VAD (Voice Activity Detection)
- [ ] Audio streaming to/from STT/TTS

### Priority 3: Media Transcription
- [ ] Whisper integration
- [ ] Batch job queue
- [ ] File chunking for large media
- [ ] Transcript storage (Postgres)

### Priority 4: Multi-Node Communication
- [ ] FastAPI server for node API
- [ ] Remote STT/TTS endpoints
- [ ] Remote LLM routing
- [ ] Health checks and heartbeats

### Priority 5: RAG & Persistence
- [ ] PostgreSQL schema setup
- [ ] pgvector for embeddings
- [ ] Corpus ingestion pipeline
- [ ] Semantic search

## Development Workflow

### Add a New Provider

Create `src/skeleton_app/providers/stt.py`:

```python
from skeleton_app.core.types import STTProvider, STTRequest, STTResult

class VoskProvider(STTProvider):
    async def transcribe(self, request: STTRequest) -> STTResult:
        # Implementation
        pass
```

### Add a Command

Edit your config:

```yaml
commands:
  builtin:
    - name: "lights_on"
      aliases: ["turn on the lights", "lights on"]
      handler: "plugins.home.lights_on"
```

### Test Locally

```bash
# Run tests (when we add them)
pytest

# Type checking
mypy src

# Code formatting
black src
ruff check src
```

## Architecture Highlights

- **Modular**: Each subsystem (STT, TTS, LLM, Audio) is independent
- **Extensible**: Plugin system ready for custom commands and tools
- **Distributed**: Nodes can specialize and delegate to each other
- **Local-first**: Prefer local resources, fallback to remote
- **Type-safe**: Pydantic models throughout

## File Structure

```
skeleton-app/
├── src/skeleton_app/
│   ├── __init__.py
│   ├── cli.py              # CLI commands
│   ├── daemon.py           # Main daemon (skeleton)
│   ├── config.py           # Configuration models
│   ├── registry.py         # Node registry & routing
│   ├── core/
│   │   ├── types.py        # Core abstractions
│   │   └── __init__.py
│   └── providers/
│       ├── llm.py          # LLM implementations
│       └── __init__.py
├── config.yaml             # Your node config
├── config.example.yaml     # Template
├── .env                    # API keys (not in git)
├── .env.example            # Template
├── pyproject.toml          # Python package config
└── README.md               # Overview
```

## Tips

1. **Start with the REPL**: Get comfortable with LLM interactions before adding voice
2. **Test Ollama first**: Faster iteration without API costs
3. **One feature at a time**: Don't try to implement everything at once
4. **Use the plan**: PLAN.md has detailed architecture - refer to it often

## Troubleshooting

**REPL won't connect to Ollama:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama if needed
ollama serve
```

**Import errors:**
```bash
# Reinstall in editable mode
pip install -e .
```

**Config validation errors:**
- Check YAML syntax
- Ensure all required fields are present
- Look at config.example.yaml for reference

## Questions?

Refer to PLAN.md for the complete architectural vision. This implementation follows Phase 1 closely and sets up the structure for Phases 2 and 3.
