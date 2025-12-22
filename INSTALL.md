# Installation Guide

## Quick Install

### On Each Node (indigo, green, karate)

1. **Clone the repository** (if not already done):
   ```bash
   cd /home/sysadmin/Programs
   git clone https://github.com/applebiter/skeleton-crew.git
   cd skeleton-crew
   ```

2. **Create virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   # Option 1: Using pip with requirements.txt (simpler)
   pip install -r requirements.txt
   
   # Option 2: Using pip with pyproject.toml (includes optional deps)
   pip install -e ".[audio,stt,midi,osc]"
   ```

4. **Install as editable package**:
   ```bash
   pip install -e .
   ```

5. **Verify installation**:
   ```bash
   skeleton --help
   skeleton-gui --version
   ```

## System Requirements

### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    jackd2 libjack-jackd2-dev \
    portaudio19-dev \
    git
```

### JACK Audio
JACK should be installed and running for audio features:
```bash
# Check if JACK is running
jack_lsp

# Start JACK if needed (adjust settings for your hardware)
jackd -d alsa -r 48000 -p 256
```

## Configuration

1. **Copy example config**:
   ```bash
   cp config.example.yaml config.yaml
   ```

2. **Edit config.yaml** with your settings:
   - Update `node.name` to match the hostname
   - Set `node.host` to the machine's IP address
   - Adjust `node.roles` based on the machine's purpose

3. **Optional: Database setup** (only needed if using PostgreSQL features):
   ```bash
   # Install PostgreSQL
   sudo apt-get install postgresql postgresql-contrib
   
   # Setup database
   sudo -u postgres createdb skeleton_crew
   sudo -u postgres psql skeleton_crew -c "CREATE EXTENSION vector;"
   ```

## Testing Node Discovery

Test that nodes can discover each other on the LAN:

```bash
# On each node, run:
source .venv/bin/activate
python3 test_udp_discovery.py
```

You should see nodes discover each other within 5-10 seconds.

## Running the Application

### GUI Mode (on a machine with display)
```bash
source .venv/bin/activate
skeleton-gui
```

### Daemon Mode (headless)
```bash
source .venv/bin/activate
skeleton-daemon --config config.yaml
```

### As a Service (systemd)
See `deployment/skeleton-voice.service` for an example systemd service file.

## Downloading Models

### Vosk Speech Recognition Model
```bash
cd models/vosk
wget https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
unzip vosk-model-en-us-0.22.zip
rm vosk-model-en-us-0.22.zip
```

## Troubleshooting

### Import Errors
If you get import errors, make sure you're in the virtual environment:
```bash
source .venv/bin/activate
which python  # Should show .venv/bin/python
```

### JACK Connection Issues
```bash
# List JACK ports
jack_lsp

# Check JACK status
jack_control status
```

### UDP Discovery Not Working
- Check firewall settings allow UDP port 5557
- Verify machines are on the same subnet
- Test with: `python3 test_udp_discovery.py`

### Missing Dependencies
```bash
# Reinstall all dependencies
pip install --force-reinstall -r requirements.txt
```
