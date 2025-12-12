# Database Setup Guide

## Architecture: Centralized PostgreSQL

All nodes in your LAN connect to a **shared PostgreSQL database** on `karate` (192.168.32.11). This provides:

- **Node Discovery**: Automatic registration and discovery of all nodes
- **Shared RAG Corpus**: All transcribed media searchable from any node
- **Session Continuity**: Pick up conversations on any node
- **Job Coordination**: Distribute transcription tasks across nodes

## Initial Setup on karate (192.168.32.11)

### 1. Install PostgreSQL + pgvector

```bash
# On karate (your database server)
sudo apt update
sudo apt install postgresql postgresql-contrib

# Install pgvector extension
sudo apt install postgresql-15-pgvector
# Or build from source if not in repos:
# git clone https://github.com/pgvector/pgvector.git
# cd pgvector && make && sudo make install
```

### 2. Configure PostgreSQL for LAN Access

Edit `/etc/postgresql/15/main/postgresql.conf`:
```conf
listen_addresses = '*'  # Listen on all interfaces
max_connections = 100
shared_buffers = 256MB  # Adjust based on your 32GB RAM
```

Edit `/etc/postgresql/15/main/pg_hba.conf`:
```conf
# Allow connections from your LAN (adjust subnet as needed)
host    skeleton_app    skeleton    192.168.32.0/24    scram-sha-256
```

Restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

### 3. Create Database and User

```bash
sudo -u postgres psql

-- Create user
CREATE USER skeleton WITH PASSWORD 'your_secure_password_here';

-- Create database
CREATE DATABASE skeleton_app OWNER skeleton;

-- Connect to the new database
\c skeleton_app

-- Enable pgvector extension
CREATE EXTENSION vector;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE skeleton_app TO skeleton;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO skeleton;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO skeleton;

\q
```

## Setup on Each Node

### 1. Update .env File

On **each node** (all 6 Linux boxes + Windows), edit `.env`:

```bash
# Database - Shared PostgreSQL on karate
DATABASE_URL=postgresql://skeleton:your_secure_password_here@192.168.32.11:5432/skeleton_app

# Other settings...
NODE_ID=linux-01  # Unique for each node
OLLAMA_HOST=http://localhost:11434
```

### 2. Initialize Schema (Run Once)

From **any node**, initialize the database schema:

```bash
cd /home/sysadmin/Programs/skeleton-app
source .venv/bin/activate

# Check connection
skeleton db check

# Initialize schema (only needs to be run once)
skeleton db init
```

You should see:
```
✓ Database schema initialized successfully!

Created tables:
  • nodes - Node registry
  • corpora - Document collections
  • documents - Media files and documents
  • chunks - Text chunks with embeddings (pgvector)
  • sessions - User sessions
  • messages - Conversation history
  • transcription_jobs - Batch transcription queue
```

### 3. Verify Setup

```bash
# Check schema
skeleton db check

# List registered nodes (will be empty until nodes start)
skeleton db nodes
```

## Node Configuration

Each node should have a unique config. Example configs:

### Linux Node 1 (STT + TTS + Light LLM)
`config.yaml`:
```yaml
node:
  id: "linux-01"
  name: "Linux Node 1"
  host: "192.168.32.21"  # This node's IP
  port: 8000
  roles:
    - "stt_realtime"
    - "tts"
    - "llm_light"
    - "audio_hub"
```

### Linux Node 2-6 (Similar, adjust IPs and roles)
```yaml
node:
  id: "linux-02"  # Change for each node
  name: "Linux Node 2"
  host: "192.168.32.22"  # This node's IP
  # ... adjust roles as needed
```

### Windows Node (Heavy Compute)
```yaml
node:
  id: "windows-main"
  name: "Windows Heavy Compute"
  host: "192.168.32.100"  # Windows machine IP
  port: 8000
  roles:
    - "llm_heavy"
    - "stt_batch"
    - "rag_engine"
  tags:
    platform: "windows"
    gpu: "nvidia-3060"
```

## Testing Multi-Node Setup

### 1. Start Daemon on First Node

```bash
# On linux-01
skeleton-daemon --config config.yaml
```

The daemon will:
1. Connect to PostgreSQL on karate
2. Register itself in the `nodes` table
3. Start heartbeat updates

### 2. Check Node Registry

```bash
# From any node
skeleton db nodes
```

Should show:
```
● linux-01 - Linux Node 1
  192.168.32.21:8000
  Roles: stt_realtime, tts, llm_light, audio_hub
  Status: online (last seen: ...)
```

### 3. Start Additional Nodes

Repeat on each node. They will all register themselves automatically.

## Database Schema Overview

### Node Registry
```sql
nodes (
    id,              -- "linux-01", "windows-main", etc.
    name,            -- Human-readable name
    host, port,      -- Network location
    roles[],         -- Capabilities
    capabilities,    -- Detailed capability info (JSON)
    tags,            -- Hardware info (JSON)
    status,          -- "online", "offline", "degraded"
    last_seen        -- Heartbeat timestamp
)
```

### RAG Corpus
```sql
corpora -> documents -> chunks
                        └─ embedding (vector)
```

### Sessions & Messages
```sql
sessions (user sessions, can be picked up on any node)
    └─ messages (conversation history)
```

### Transcription Queue
```sql
transcription_jobs (
    file_path,
    status,          -- "pending", "processing", "completed"
    assigned_node,   -- Which node is processing
    result           -- Transcript when done
)
```

## Benefits of Centralized Database

1. **Automatic Node Discovery**: No manual configuration of node lists
2. **Shared Knowledge**: All nodes can search the same RAG corpus
3. **Session Roaming**: Start conversation on one node, continue on another
4. **Load Balancing**: See which nodes are busy, distribute work
5. **Unified Logging**: All activity in one place
6. **Easy Backup**: Single database to backup/restore

## Optional: Connection Pooling

If you experience connection issues with many nodes, consider PgBouncer on karate:

```bash
# On karate
sudo apt install pgbouncer

# Configure pgbouncer to pool connections
# Then point nodes to pgbouncer instead of direct PostgreSQL
DATABASE_URL=postgresql://skeleton:password@192.168.32.11:6432/skeleton_app
```

## Troubleshooting

### Can't connect to database
```bash
# On any node, test connection
psql postgresql://skeleton:password@192.168.32.11:5432/skeleton_app

# Check firewall on karate
sudo ufw allow 5432/tcp

# Check PostgreSQL is listening
sudo netstat -plnt | grep 5432
```

### pgvector not found
```sql
-- On karate, as postgres user
sudo -u postgres psql skeleton_app
CREATE EXTENSION vector;
```

### Stale nodes showing as online
The system automatically marks nodes offline after 5 minutes of no heartbeat. To manually clean up:

```sql
UPDATE nodes SET status = 'offline' 
WHERE last_seen < NOW() - INTERVAL '5 minutes';
```

## Next Steps

Once the database is set up:
1. ✅ All nodes can discover each other automatically
2. Start implementing the daemon to use the registry
3. Add STT/TTS providers that coordinate via the database
4. Build the media transcription pipeline with the job queue
