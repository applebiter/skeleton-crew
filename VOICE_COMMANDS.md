# Voice Command System

JACK-aware, low-latency voice command system using Vosk STT for real-time speech recognition across distributed nodes.

## Architecture

The voice command system consists of:

1. **Vosk JACK STT Engine** (`vosk_jack_stt.py`)
   - Low-latency audio capture via JACK
   - Real-time speech recognition using Vosk
   - Wake word detection for node-specific commands
   - Continuous transcription with partial results

2. **Voice Command Service** (`voice_command_service.py`)
   - FastAPI-based REST API
   - WebSocket streaming for real-time transcription
   - Command aliasing system
   - Multi-node service discovery integration
   - Command history tracking

3. **Service Discovery Integration**
   - Automatic registration with service discovery
   - Node-to-node communication over LAN
   - Health monitoring and status updates

## Features

### Real-Time Speech Recognition
- **Low Latency**: Direct JACK audio capture, no intermediate buffers
- **Partial Results**: See transcription as you speak
- **Final Results**: High-accuracy complete transcriptions
- **Sample Rate**: 16kHz (Vosk standard), auto-resampling from JACK

### Wake Word System
- **Node-Specific**: Each node has its own wake word (e.g., "computer indigo")
- **Context Switching**: Automatically routes commands to the target node
- **Timeout**: Configurable timeout after wake word (default: 5 seconds)
- **Real-Time Alerts**: Instant notification when wake word detected

### Command Aliasing
- **Natural Language**: Map spoken phrases to actual commands
- **Node-Specific**: Aliases can be global or per-node
- **Dynamic**: Add/remove aliases via API without restart
- **Extensible**: Easy to add custom command handlers

### Network API
- **REST Endpoints**: Manage wake words, aliases, view stats
- **WebSocket Streaming**: Real-time transcription and command events
- **Multi-Client**: Multiple clients can connect simultaneously
- **Service Discovery**: Automatic registration and node discovery

## Installation

### Prerequisites

1. **JACK Audio Server**
   ```bash
   sudo apt install jackd2 qjackctl
   ```

2. **Vosk Model**
   Download a Vosk model from https://alphacephei.com/vosk/models
   
   Recommended for English:
   ```bash
   cd /home/sysadmin/Programs/skeleton-app
   mkdir -p models/vosk
   cd models/vosk
   wget https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
   unzip vosk-model-en-us-0.22.zip
   ```

3. **Python Dependencies**
   ```bash
   pip install -e ".[audio,stt]"
   ```
   
   This installs:
   - `vosk` - Speech recognition
   - `JACK-Client` - JACK audio interface
   - `numpy` - Audio processing
   - `fastapi` - Web API
   - `uvicorn` - ASGI server
   - `websockets` - WebSocket support

### Configuration

Edit `config.yaml`:

```yaml
# Voice Commands Configuration
voice_commands:
  enabled: true
  api_port: 8001
  command_timeout: 5.0
  
  # Wake words for each node
  wake_words:
    indigo: "computer indigo"
    green: "computer green"
    karate: "computer karate"
  
  # Command aliases
  aliases:
    - alias: "play"
      actual_command: "transport_start"
      description: "Start JACK transport"
    
    - alias: "stop"
      actual_command: "transport_stop"
      description: "Stop JACK transport"

# STT Configuration
stt:
  providers:
    realtime:
      backend: "vosk"
      model: "vosk-model-en-us-0.22"
      model_path: "./models/vosk"
  
  vosk:
    sample_rate: 16000

# Audio Configuration
audio:
  jack:
    client_name: "skeleton_app"
    auto_connect: true
```

## Usage

### Start the Voice Service

**Development Mode:**
```bash
skeleton voice --host 0.0.0.0 --port 8001
```

**Production Mode (systemd):**
```bash
sudo systemctl start skeleton-voice
sudo systemctl enable skeleton-voice  # Start on boot
```

### Test the Service

**Test REST API:**
```bash
python tools/test_voice_service.py --test api
```

**Test WebSocket (30 seconds):**
```bash
python tools/test_voice_service.py --test websocket --duration 30
```

**Full Test Suite:**
```bash
python tools/test_voice_service.py --host localhost --duration 60
```

### Using Voice Commands

1. **Start JACK**
   ```bash
   qjackctl &  # Or start jackd manually
   ```

2. **Connect Microphone**
   - In qjackctl, click "Connect"
   - Find your microphone input (e.g., `system:capture_1`)
   - Connect it to `skeleton_app_vosk:voice_in`

3. **Speak Commands**
   - Say wake word: "computer indigo"
   - Wait for acknowledgment
   - Say command: "play"
   
   Example session:
   ```
   You: "computer indigo"
   System: [Wake word detected for node: indigo]
   You: "start recording"
   System: [Command: recording_start]
   ```

## API Reference

### REST Endpoints

#### `GET /`
Get service information and status.

**Response:**
```json
{
  "service": "voice_command",
  "version": "0.1.0",
  "status": "running",
  "stats": {
    "start_time": "2025-12-18T20:00:00",
    "total_commands": 42,
    "total_transcriptions": 156,
    "active_connections": 2
  }
}
```

#### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "healthy": true,
  "stt_engine": "running",
  "websocket_clients": 2
}
```

#### `GET /stats`
Get detailed statistics.

**Response:**
```json
{
  "start_time": "2025-12-18T20:00:00",
  "total_commands": 42,
  "total_transcriptions": 156,
  "active_connections": 2,
  "stt_engine": {
    "frames_processed": 480000,
    "transcriptions": 156,
    "commands_detected": 42,
    "wake_words_detected": 42
  }
}
```

#### `GET /wake-words`
Get configured wake words.

**Response:**
```json
{
  "wake_words": {
    "indigo": "computer indigo",
    "green": "computer green",
    "karate": "computer karate"
  }
}
```

#### `POST /wake-words/{node_id}`
Add or update wake word for a node.

**Parameters:**
- `wake_word` (query): The wake word phrase

**Response:**
```json
{
  "status": "success",
  "node_id": "indigo",
  "wake_word": "computer indigo"
}
```

#### `DELETE /wake-words/{node_id}`
Remove wake word for a node.

#### `GET /aliases`
Get all command aliases.

**Response:**
```json
{
  "aliases": [
    {
      "alias": "play",
      "actual_command": "transport_start",
      "node_id": null,
      "description": "Start JACK transport"
    }
  ]
}
```

#### `POST /aliases`
Add a command alias.

**Parameters:**
- `alias` (query): The alias phrase
- `actual_command` (query): The actual command
- `node_id` (query, optional): Node-specific alias
- `description` (query, optional): Description

#### `DELETE /aliases/{alias}`
Remove a command alias.

#### `GET /history`
Get command history.

**Parameters:**
- `limit` (query, default=50): Number of commands to return

**Response:**
```json
{
  "history": [
    {
      "target_node": "indigo",
      "command": "transport_start",
      "raw_text": "play",
      "confidence": 0.95,
      "timestamp": "2025-12-18T20:15:30"
    }
  ]
}
```

### WebSocket Endpoint

#### `WS /ws`
Real-time transcription and command streaming.

**Message Types:**

**Connected:**
```json
{
  "type": "connected",
  "message": "Connected to voice command service",
  "wake_words": {
    "indigo": "computer indigo"
  }
}
```

**Transcription (Partial):**
```json
{
  "type": "transcription",
  "text": "computer ind",
  "partial": true,
  "confidence": 0.0,
  "timestamp": "2025-12-18T20:15:30"
}
```

**Transcription (Final):**
```json
{
  "type": "transcription",
  "text": "computer indigo",
  "partial": false,
  "confidence": 0.95,
  "timestamp": "2025-12-18T20:15:30"
}
```

**Wake Word:**
```json
{
  "type": "wake_word",
  "node_id": "indigo",
  "timestamp": "2025-12-18T20:15:30"
}
```

**Command:**
```json
{
  "type": "command",
  "target_node": "indigo",
  "command": "transport_start",
  "raw_text": "play",
  "confidence": 0.95,
  "timestamp": "2025-12-18T20:15:31"
}
```

## Multi-Node Deployment

### Deploy to All Nodes

```bash
cd deployment
chmod +x deploy_voice.sh
./deploy_voice.sh
```

### Deploy to Specific Nodes

```bash
./deploy_voice.sh --node indigo --node green
```

### Install as System Service

```bash
./deploy_voice.sh --install-service
```

### Verify Deployment

```bash
# Check service status on each node
for node in indigo green karate; do
  echo "=== $node ==="
  ssh sysadmin@$node "systemctl status skeleton-voice"
done
```

## Network Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Voice Command Network                     │
└─────────────────────────────────────────────────────────────┘

     ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
     │   indigo     │         │    green     │         │   karate     │
     │ 192.168.32.7 │         │192.168.32.5  │         │192.168.32.11 │
     └──────────────┘         └──────────────┘         └──────────────┘
            │                        │                        │
            │                        │                        │
     ┌──────▼──────┐         ┌──────▼──────┐         ┌──────▼──────┐
     │ Voice Svc   │         │ Voice Svc   │         │ Voice Svc   │
     │ :8001       │◄────────┤ :8001       │◄────────┤ :8001       │
     └──────┬──────┘         └──────┬──────┘         └──────┬──────┘
            │                       │                        │
     ┌──────▼──────┐         ┌──────▼──────┐         ┌──────▼──────┐
     │ JACK Audio  │         │ JACK Audio  │         │ JACK Audio  │
     │ Vosk STT    │         │ Vosk STT    │         │ Vosk STT    │
     └─────────────┘         └─────────────┘         └─────────────┘
            │                       │                        │
            └───────────────────────┴────────────────────────┘
                         Service Discovery
                      (PostgreSQL Registry)
```

## Performance

### Latency
- **JACK Audio Capture**: ~5-10ms
- **Vosk Processing**: ~100-200ms per chunk
- **Network Transmission**: ~1-5ms on LAN
- **Total**: ~150-250ms end-to-end

### Resource Usage (per node)
- **CPU**: 10-20% (single core)
- **RAM**: ~500MB (includes Vosk model)
- **Network**: ~10-50 KB/s
- **Disk**: ~1GB (Vosk model)

## Troubleshooting

### JACK Not Running
```bash
# Check JACK status
pgrep -x jackd

# Start JACK manually (48kHz, 128 frames)
jackd -d alsa -r 48000 -p 128

# Or use qjackctl GUI
qjackctl &
```

### Vosk Model Not Found
```bash
# Download and extract model
cd models/vosk
wget https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
unzip vosk-model-en-us-0.22.zip
```

### Microphone Not Recognized
```bash
# List JACK ports
jack_lsp

# Connect microphone to voice_in
jack_connect system:capture_1 skeleton_app_vosk:voice_in
```

### Low Recognition Accuracy
- Check microphone quality and placement
- Reduce background noise
- Try a larger Vosk model (vosk-model-en-us-0.42-gigaspeech)
- Adjust JACK buffer size for lower latency

### WebSocket Connection Issues
```bash
# Test WebSocket with websocat
websocat ws://localhost:8001/ws

# Or with curl
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: $(base64 /dev/urandom | head -c 24)" \
  http://localhost:8001/ws
```

## Future Enhancements

- [ ] Multi-language support
- [ ] Speaker identification
- [ ] Noise cancellation
- [ ] Command templates with parameters
- [ ] Voice feedback (TTS responses)
- [ ] LLM integration for natural language understanding
- [ ] Command macros and sequences
- [ ] Voice authentication
- [ ] Mobile app for remote control

## See Also

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall system architecture
- [SSH_INTEGRATION.md](../SSH_INTEGRATION.md) - Multi-node SSH setup
- [QUICKSTART.md](../QUICKSTART.md) - Getting started guide
