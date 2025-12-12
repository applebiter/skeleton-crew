"""Database setup and management commands."""

import asyncio
import logging

import click
from rich.console import Console

from skeleton_app.config import EnvSettings
from skeleton_app.database import Database

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def db():
    """Database management commands."""
    pass


@db.command()
@click.option('--url', help='Database URL (overrides .env)')
def init(url: str):
    """Initialize database schema."""
    asyncio.run(init_database(url))


async def init_database(url: str = None):
    """Initialize the database schema."""
    env = EnvSettings()
    db_url = url or env.database_url
    
    console.print(f"[cyan]Connecting to database...[/cyan]")
    console.print(f"URL: {db_url.split('@')[1] if '@' in db_url else db_url}")
    
    try:
        db = Database(db_url)
        await db.connect()
        
        console.print("[cyan]Creating schema...[/cyan]")
        await db.initialize_schema()
        
        console.print("[green]✓[/green] Database schema initialized successfully!")
        console.print("\nCreated tables:")
        console.print("  • nodes - Node registry")
        console.print("  • corpora - Document collections")
        console.print("  • documents - Media files and documents")
        console.print("  • chunks - Text chunks with embeddings (pgvector)")
        console.print("  • sessions - User sessions")
        console.print("  • messages - Conversation history")
        console.print("  • transcription_jobs - Batch transcription queue")
        
        await db.disconnect()
        
    except Exception as e:
        console.print(f"[red]✗[/red] Error initializing database: {e}")
        raise


@db.command()
@click.option('--url', help='Database URL (overrides .env)')
def check(url: str):
    """Check database connection and schema."""
    asyncio.run(check_database(url))


async def check_database(url: str = None):
    """Check database connection and list tables."""
    env = EnvSettings()
    db_url = url or env.database_url
    
    console.print(f"[cyan]Connecting to database...[/cyan]")
    
    try:
        db = Database(db_url)
        await db.connect()
        
        # Check for pgvector extension
        has_vector = await db.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            )
        """)
        
        if has_vector:
            console.print("[green]✓[/green] pgvector extension is installed")
        else:
            console.print("[yellow]⚠[/yellow] pgvector extension not found")
            console.print("Run: CREATE EXTENSION vector;")
        
        # List tables
        tables = await db.fetch("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        
        if tables:
            console.print(f"\n[green]✓[/green] Found {len(tables)} tables:")
            for table in tables:
                console.print(f"  • {table['tablename']}")
        else:
            console.print("[yellow]⚠[/yellow] No tables found. Run: skeleton db init")
        
        await db.disconnect()
        
    except Exception as e:
        console.print(f"[red]✗[/red] Error connecting to database: {e}")
        raise


@db.command()
@click.option('--url', help='Database URL (overrides .env)')
def nodes(url: str):
    """List registered nodes."""
    asyncio.run(list_nodes(url))


async def list_nodes(url: str = None):
    """List all nodes in the registry."""
    env = EnvSettings()
    db_url = url or env.database_url
    
    try:
        db = Database(db_url)
        await db.connect()
        
        nodes = await db.fetch("""
            SELECT id, name, host, port, roles, status, last_seen
            FROM nodes
            ORDER BY status DESC, last_seen DESC
        """)
        
        if not nodes:
            console.print("[yellow]No nodes registered yet[/yellow]")
        else:
            console.print(f"\n[bold]Registered Nodes ({len(nodes)}):[/bold]\n")
            for node in nodes:
                status_color = "green" if node['status'] == 'online' else "red"
                console.print(f"[{status_color}]●[/{status_color}] {node['id']} - {node['name']}")
                console.print(f"  {node['host']}:{node['port']}")
                console.print(f"  Roles: {', '.join(node['roles'])}")
                console.print(f"  Status: {node['status']} (last seen: {node['last_seen']})")
                console.print()
        
        await db.disconnect()
        
    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
        raise
