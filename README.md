# Skeleton Crew

A distributed, JACK-centric voice/agent system for Linux audio workstations. Manage a network of JACK systems from a single machine - like running a ship with a skeleton crew.

## Features

- **Multi-node architecture**: Distribute STT, TTS, and LLM processing across LAN
- **Real-time audio**: JACK integration for low-latency voice interaction
- **Flexible STT**: Vosk for commands, Whisper for transcription
- **Local-first LLM**: Ollama with cloud fallbacks (OpenAI, Anthropic)
- **Media transcription**: Batch processing pipeline for archival content
- **RAG support**: PostgreSQL + pgvector for semantic search
- **MIDI/OSC**: Integration for musical and performance use cases

## Architecture

See [PLAN.md](PLAN.md) for detailed architectural documentation.

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 14+ with pgvector extension
- JACK Audio Connection Kit (for audio nodes)
- Ollama (recommended) or cloud LLM API keys

### Installation

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install core dependencies
pip install -e .

# Install optional dependencies based on node role
pip install -e ".[audio,stt,tts,llm]"

# For development
pip install -e ".[dev]"
```

### Configuration

1. Copy example config:
   ```bash
   cp config.example.yaml config.yaml
   ```

2. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. Initialize database:
   ```bash
   skeleton db init
   ```

### Running

```bash
# Start daemon on a node
skeleton-daemon --config config.yaml

# Interactive REPL for testing
skeleton repl

# Transcribe media file
skeleton transcribe input.wav --model whisper:medium
```

## Node Roles

- **audio_hub**: JACK audio routing, real-time voice I/O
- **stt_realtime**: Vosk-based low-latency speech recognition
- **stt_batch**: Whisper-based high-accuracy transcription
- **tts**: Piper TTS synthesis
- **llm_light**: 3B models for quick responses
- **llm_heavy**: 8B+ models for complex reasoning
- **rag_engine**: Vector search and corpus management

## Development

```bash
# Run tests
pytest

# Format code
black src tests
ruff check src tests

# Type checking
mypy src
```

## License

TBD
