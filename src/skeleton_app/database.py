"""Database schema and initialization."""

import logging
from typing import Optional

import asyncpg
from pgvector.asyncpg import register_vector

logger = logging.getLogger(__name__)


class Database:
    """Database connection and schema management."""
    
    def __init__(self, url: str, pool_size: int = 5, max_overflow: int = 10):
        self.url = url
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Create connection pool."""
        self.pool = await asyncpg.create_pool(
            self.url,
            min_size=1,
            max_size=self.pool_size + self.max_overflow,
            command_timeout=60
        )
        
        # Register pgvector extension
        async with self.pool.acquire() as conn:
            await register_vector(conn)
        
        logger.info("Database connection pool created")
    
    async def disconnect(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")
    
    async def initialize_schema(self):
        """Create database schema if it doesn't exist."""
        async with self.pool.acquire() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
            # Node registry table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    host VARCHAR(255) NOT NULL,
                    port INTEGER NOT NULL,
                    roles TEXT[] NOT NULL,
                    capabilities JSONB NOT NULL DEFAULT '[]',
                    tags JSONB NOT NULL DEFAULT '{}',
                    status VARCHAR(50) NOT NULL DEFAULT 'online',
                    last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            
            # Create index for node lookups
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_nodes_status 
                ON nodes(status)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_nodes_last_seen 
                ON nodes(last_seen)
            """)
            
            # Corpus table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS corpora (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    description TEXT,
                    owner VARCHAR(255),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            
            # Document table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id SERIAL PRIMARY KEY,
                    corpus_id INTEGER NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    title VARCHAR(500),
                    content_type VARCHAR(100),
                    metadata JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE(corpus_id, path)
                )
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_corpus 
                ON documents(corpus_id)
            """)
            
            # Chunk table with embeddings
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding vector(768),  -- Default for nomic-embed-text
                    start_time FLOAT,       -- For media files
                    end_time FLOAT,         -- For media files
                    metadata JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE(document_id, chunk_index)
                )
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_document 
                ON chunks(document_id)
            """)
            
            # Vector similarity search index
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
                ON chunks USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)
            
            # Session table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id VARCHAR(255) PRIMARY KEY,
                    user_id VARCHAR(255),
                    node_id VARCHAR(255),
                    context JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    last_activity TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_user 
                ON sessions(user_id)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_last_activity 
                ON sessions(last_activity)
            """)
            
            # Message table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session 
                ON messages(session_id, created_at)
            """)
            
            # Transcription jobs table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS transcription_jobs (
                    id SERIAL PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    priority VARCHAR(50) NOT NULL DEFAULT 'normal',
                    model VARCHAR(100),
                    assigned_node VARCHAR(255),
                    result JSONB,
                    error TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    metadata JSONB NOT NULL DEFAULT '{}'
                )
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transcription_jobs_status 
                ON transcription_jobs(status, priority, created_at)
            """)
            
            logger.info("Database schema initialized")
    
    async def execute(self, query: str, *args):
        """Execute a query."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args):
        """Fetch multiple rows."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args):
        """Fetch a single row."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args):
        """Fetch a single value."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)


# Convenience functions for node registry operations

async def register_node_in_db(db: Database, node_info: dict):
    """Register or update a node in the database."""
    await db.execute("""
        INSERT INTO nodes (id, name, host, port, roles, capabilities, tags, status, last_seen)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            host = EXCLUDED.host,
            port = EXCLUDED.port,
            roles = EXCLUDED.roles,
            capabilities = EXCLUDED.capabilities,
            tags = EXCLUDED.tags,
            status = EXCLUDED.status,
            last_seen = NOW(),
            updated_at = NOW()
    """, 
        node_info['id'],
        node_info['name'],
        node_info['host'],
        node_info['port'],
        node_info['roles'],
        node_info['capabilities'],
        node_info['tags'],
        node_info.get('status', 'online')
    )


async def get_nodes_from_db(db: Database, role: Optional[str] = None, status: str = 'online'):
    """Get nodes from database."""
    if role:
        rows = await db.fetch("""
            SELECT * FROM nodes 
            WHERE status = $1 AND $2 = ANY(roles)
            ORDER BY last_seen DESC
        """, status, role)
    else:
        rows = await db.fetch("""
            SELECT * FROM nodes 
            WHERE status = $1
            ORDER BY last_seen DESC
        """, status)
    
    return [dict(row) for row in rows]


async def heartbeat_node_in_db(db: Database, node_id: str):
    """Update node last_seen timestamp."""
    await db.execute("""
        UPDATE nodes 
        SET last_seen = NOW()
        WHERE id = $1
    """, node_id)


async def cleanup_stale_nodes_in_db(db: Database, timeout_seconds: int = 300):
    """Mark nodes as offline if they haven't sent heartbeat."""
    await db.execute("""
        UPDATE nodes 
        SET status = 'offline'
        WHERE status = 'online' 
        AND last_seen < NOW() - INTERVAL '%s seconds'
    """ % timeout_seconds)
