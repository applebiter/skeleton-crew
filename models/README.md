# Models Directory

This directory contains AI models used by skeleton-crew. Models are not included in the repository due to their large file sizes.

## Required Models

### Speech-to-Text (STT) - Vosk

Place Vosk models in `models/vosk/`

**Recommended model:**
- **vosk-model-en-us-0.22** (1.8 GB) - Best quality English model
- Download from: https://alphacephei.com/vosk/models
- Direct link: https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip

**Alternative models:**
- **vosk-model-small-en-us-0.15** (40 MB) - Lightweight, faster but less accurate
- Other language models available at the Vosk website

**Installation:**
```bash
cd models/vosk
wget https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
unzip vosk-model-en-us-0.22.zip
rm vosk-model-en-us-0.22.zip
```

### Text-to-Speech (TTS)

TTS models can be placed in `models/tts/` (if using local TTS models)

The application currently supports:
- Piper TTS (lightweight, high-quality)
- Coqui TTS
- Festival TTS (system package)

Refer to the main documentation for TTS setup instructions.

## Directory Structure

```
models/
├── README.md           (this file)
├── vosk/              (Vosk STT models)
│   └── vosk-model-*/
└── tts/               (Optional: local TTS models)
```
