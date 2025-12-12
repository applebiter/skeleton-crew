# SSH Deep Integration Guide

## Overview

With passwordless SSH access across all nodes, the skeleton-app provides **native cluster orchestration** capabilities. This enables:

- **Remote execution**: Run commands on any node from any other node
- **Code deployment**: Push updates across the cluster
- **Process management**: Start/stop/restart daemons remotely  
- **Model synchronization**: Distribute Vosk/Whisper/Piper models efficiently
- **Log aggregation**: Collect logs from all nodes centrally
- **Health monitoring**: Check system resources and daemon status

## Cluster Management Commands

### Check Cluster Status

View the health and status of all nodes:

```bash
skeleton cluster status
```

Output shows:
- Node ID and host
- Daemon running status (✓/✗)
- System load average
- Available memory
- GPU information
- Disk space

### Execute Commands on Nodes

Run a command on all nodes:
```bash
skeleton cluster exec "uptime"
skeleton cluster exec "df -h"
skeleton cluster exec "nvidia-smi"
```

Run on a specific node:
```bash
skeleton cluster exec "free -h" --node linux-01
```

### Deploy Code

Deploy your code changes to all nodes:
```bash
# From your dev node
cd /home/sysadmin/Programs/skeleton-app
skeleton cluster deploy
```

Deploy to specific node:
```bash
skeleton cluster deploy --node windows-main
```

Custom paths:
```bash
skeleton cluster deploy --source /path/to/code --dest /remote/path
```

**What gets deployed:**
- All Python code
- Configuration files
- Scripts and utilities

**What's excluded:**
- `.venv/` (virtual environments)
- `__pycache__/`, `*.pyc`
- `.git/`
- `logs/`

### Daemon Control

Start daemons on all nodes:
```bash
skeleton cluster daemon start
```

Stop all daemons:
```bash
skeleton cluster daemon stop
```

Restart all daemons:
```bash
skeleton cluster daemon restart
```

Control specific node:
```bash
skeleton cluster daemon restart --node linux-02
```

### Synchronize Models

After downloading a model on one node, distribute it to others:

```bash
# Download Vosk model on linux-01
# Then sync to all other nodes:
skeleton cluster sync-models --source-node linux-01
```

Sync to specific node:
```bash
skeleton cluster sync-models --source-node linux-01 --target-node linux-02
```

Custom model path:
```bash
skeleton cluster sync-models \
  --source-node linux-01 \
  --models-path /path/to/models
```

**Use cases:**
- Vosk models (~1-2GB)
- Whisper models (up to 3GB)
- Piper voices (~10-50MB each)
- Ollama models (via `ollama pull` + model file sync)

### Collect Logs

Gather logs from all nodes:
```bash
skeleton cluster logs
```

This creates `collected_logs/` directory with logs from each node.

From specific node:
```bash
skeleton cluster logs --node linux-03
```

More log lines:
```bash
skeleton cluster logs --lines 500
```

## Deep Integration Examples

### 1. Rolling Deployment

Update code and restart daemons with zero manual SSH:

```bash
# Stop all daemons
skeleton cluster daemon stop

# Deploy new code
skeleton cluster deploy

# Start daemons with new code
skeleton cluster daemon start

# Check status
skeleton cluster status
```

### 2. Model Distribution

Download a model once, distribute everywhere:

```bash
# On linux-01, download Vosk model
cd /home/sysadmin/Programs/skeleton-app/models
wget https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
unzip vosk-model-en-us-0.22.zip

# Distribute to all nodes
skeleton cluster sync-models --source-node linux-01
```

### 3. Centralized Monitoring

Create a monitoring script that checks all nodes:

```bash
# Check system health
skeleton cluster exec "uptime && free -h && df -h /"

# Check JACK status
skeleton cluster exec "jack_lsp | wc -l"

# Check Ollama
skeleton cluster exec "ollama list"
```

### 4. Debugging Across Nodes

Collect logs when troubleshooting:

```bash
# Gather recent logs
skeleton cluster logs --lines 1000

# Check for errors
grep -i error collected_logs/*.log

# Check specific node
skeleton cluster exec "journalctl -u skeleton-daemon -n 50" --node linux-02
```

### 5. Configuration Synchronization

Update configs across the cluster:

```bash
# Edit config.yaml locally
vim config.yaml

# Deploy to all nodes
skeleton cluster deploy

# Restart to pick up changes
skeleton cluster daemon restart
```

## Advanced: Remote STT/TTS Processing

The SSH integration enables **direct remote execution** for voice processing:

### Remote Transcription

Instead of HTTP API, you can execute Whisper directly via SSH:

```python
from skeleton_app.remote import SSHExecutor

executor = SSHExecutor()

# Copy audio file to windows node
await executor.copy_file(
    "192.168.32.100",
    "local_audio.wav",
    "/tmp/audio.wav",
    direction="to"
)

# Run Whisper remotely
exit_code, transcript, stderr = await executor.execute(
    "192.168.32.100",
    "cd /home/sysadmin/Programs/skeleton-app && "
    "source .venv/bin/activate && "
    "python -m whisper /tmp/audio.wav --model medium --language en",
    timeout=300.0
)

# Process transcript
print(transcript)
```

### Remote TTS Synthesis

Similarly for Piper TTS:

```python
# Generate audio remotely
await executor.execute(
    "192.168.32.21",
    "echo 'Hello world' | piper --model en_US-lessac-medium --output_file /tmp/out.wav"
)

# Copy result back
await executor.copy_file(
    "192.168.32.21",
    "/tmp/result.wav",
    "local_result.wav",
    direction="from"
)
```

## Remote JACK Control

Manage JACK connections remotely:

```bash
# Start JACK on all nodes
skeleton cluster exec "jack_control start"

# Check JACK status
skeleton cluster exec "jack_lsp"

# Connect ports remotely
skeleton cluster exec "jack_connect system:capture_1 skeleton_app:voice_in" \
  --node linux-01
```

## Integration with Database

The cluster commands **automatically use the database** to discover nodes:

1. Nodes register themselves in PostgreSQL on startup
2. Cluster commands query the database for active nodes
3. SSH connections are made to registered hosts
4. Results can be written back to the database

Example workflow:
```python
# Node registers on startup
await register_node_in_db(db, {
    'id': 'linux-01',
    'name': 'Linux Node 1',
    'host': '192.168.32.21',
    'port': 8000,
    'roles': ['stt_realtime', 'tts'],
    # ...
})

# Cluster command discovers it
nodes = await get_nodes_from_db(db)

# SSH to execute command
for node in nodes:
    await executor.execute(node['host'], "uptime")
```

## Security Considerations

### SSH Key Management

Your setup with `ssh-copy-id` is perfect. Ensure:

```bash
# Verify SSH keys are in place
for host in 192.168.32.{21..26} 192.168.32.100; do
  ssh -o ConnectTimeout=2 sysadmin@$host "echo OK" || echo "Failed: $host"
done
```

### Restricted Commands (Optional)

For production, consider restricting SSH commands using `authorized_keys`:

```bash
# In ~/.ssh/authorized_keys on each node:
command="/home/sysadmin/bin/restricted_command.sh" ssh-rsa AAAA...
```

### Firewall Rules

Ensure SSH (port 22) is allowed between nodes:

```bash
# On each node
sudo ufw allow from 192.168.32.0/24 to any port 22
```

## Performance Considerations

### Parallel Execution

Cluster commands execute in parallel by default:

```python
# All nodes execute simultaneously
results = await manager.execute_on_all(hosts, "uptime", parallel=True)
```

### Rsync for Efficiency

Code deployment uses `rsync` which:
- Only transfers changed files
- Compresses data during transfer
- Preserves permissions and timestamps

### Connection Pooling

For frequent operations, consider connection reuse:

```python
# Keep SSH master connection alive
executor = SSHExecutor()
# Add ControlMaster options if needed
```

## Typical Workflows

### Daily Operations

Morning startup:
```bash
skeleton cluster daemon start
skeleton cluster status
```

### Development Cycle

```bash
# Make code changes locally
vim src/skeleton_app/...

# Deploy to test node
skeleton cluster deploy --node linux-05

# Test
skeleton cluster daemon restart --node linux-05

# If good, deploy everywhere
skeleton cluster deploy
skeleton cluster daemon restart
```

### Model Updates

```bash
# Download new model on one node
ssh sysadmin@192.168.32.21
cd ~/Programs/skeleton-app/models
ollama pull llama3.2:3b

# Sync to others (if needed)
skeleton cluster exec "ollama pull llama3.2:3b"
```

### Troubleshooting

```bash
# Check which nodes are responsive
skeleton cluster status

# Collect logs from all nodes
skeleton cluster logs --lines 500

# Check for specific issues
skeleton cluster exec "journalctl -xe | tail -20"

# Restart problematic node
skeleton cluster daemon restart --node linux-03
```

## Next Steps

With deep SSH integration, you can now:

1. **Implement distributed STT**: Route audio to the best available node
2. **Coordinate transcription**: Use the job queue + SSH execution
3. **Manage JACK mesh**: Control JackTrip connections remotely
4. **Automate failover**: Detect dead nodes and redistribute work
5. **Centralized logging**: Aggregate logs from all nodes in real-time

The combination of **centralized database** + **SSH orchestration** gives you a powerful, deeply integrated cluster system.
