"""Cluster management CLI commands."""

import asyncio

import click
from rich.console import Console
from rich.table import Table

from skeleton_app.config import Config, EnvSettings
from skeleton_app.database import Database, get_nodes_from_db
from skeleton_app.remote import ClusterManager, SSHExecutor

console = Console()


@click.group()
def cluster():
    """Cluster management commands."""
    pass


@cluster.command()
@click.option('--config', type=click.Path(exists=True), default="config.yaml")
def status(config: str):
    """Check status of all nodes in the cluster."""
    asyncio.run(check_cluster_status(config))


async def check_cluster_status(config_path: str):
    """Check status of all nodes."""
    env = EnvSettings()
    
    try:
        # Get nodes from database
        db = Database(env.database_url)
        await db.connect()
        
        nodes = await get_nodes_from_db(db)
        
        if not nodes:
            console.print("[yellow]No nodes registered in database[/yellow]")
            await db.disconnect()
            return
        
        # Create SSH executor and cluster manager
        executor = SSHExecutor()
        manager = ClusterManager(executor)
        
        # Get all hosts
        hosts = [node['host'] for node in nodes]
        
        console.print(f"\n[cyan]Checking {len(hosts)} nodes...[/cyan]\n")
        
        # Perform health check
        health = await manager.health_check_all(hosts)
        
        # Create status table
        table = Table(title="Cluster Status")
        table.add_column("Node ID", style="cyan")
        table.add_column("Host", style="blue")
        table.add_column("Daemon", style="green")
        table.add_column("Load", justify="right")
        table.add_column("Memory", justify="right")
        table.add_column("GPU", style="yellow")
        
        for node in nodes:
            host = node['host']
            node_health = health.get(host, {})
            
            daemon_status = "✓" if node_health.get('daemon_running') else "✗"
            daemon_color = "green" if node_health.get('daemon_running') else "red"
            
            table.add_row(
                node['id'],
                host,
                f"[{daemon_color}]{daemon_status}[/{daemon_color}]",
                node_health.get('load_avg', 'N/A'),
                node_health.get('total_memory', 'N/A'),
                node_health.get('gpu', 'none')[:30]
            )
        
        console.print(table)
        
        await db.disconnect()
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cluster.command()
@click.argument('command')
@click.option('--node', help='Execute on specific node (default: all)')
@click.option('--config', type=click.Path(exists=True), default="config.yaml")
def exec(command: str, node: str, config: str):
    """Execute a command on one or all nodes."""
    asyncio.run(execute_remote_command(command, node, config))


async def execute_remote_command(command: str, node_id: str, config_path: str):
    """Execute command on remote nodes."""
    env = EnvSettings()
    
    try:
        db = Database(env.database_url)
        await db.connect()
        
        if node_id:
            # Execute on specific node
            node_data = await db.fetchrow("SELECT * FROM nodes WHERE id = $1", node_id)
            if not node_data:
                console.print(f"[red]Node not found: {node_id}[/red]")
                return
            nodes = [dict(node_data)]
        else:
            # Execute on all nodes
            nodes = await get_nodes_from_db(db)
        
        if not nodes:
            console.print("[yellow]No nodes found[/yellow]")
            await db.disconnect()
            return
        
        executor = SSHExecutor()
        manager = ClusterManager(executor)
        
        hosts = [n['host'] for n in nodes]
        console.print(f"[cyan]Executing on {len(hosts)} node(s)...[/cyan]\n")
        
        results = await manager.execute_on_all(hosts, command)
        
        for node in nodes:
            host = node['host']
            exit_code, stdout, stderr = results[host]
            
            status_color = "green" if exit_code == 0 else "red"
            console.print(f"[bold {status_color}]{node['id']} ({host}):[/bold {status_color}]")
            
            if stdout:
                console.print(stdout)
            if stderr:
                console.print(f"[red]{stderr}[/red]")
            console.print()
        
        await db.disconnect()
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cluster.command()
@click.option('--node', help='Deploy to specific node (default: all)')
@click.option('--source', default=".", help='Source directory to deploy')
@click.option('--dest', default="/home/sysadmin/Programs/skeleton-app", help='Destination on nodes')
def deploy(node: str, source: str, dest: str):
    """Deploy code to one or all nodes."""
    asyncio.run(deploy_code(node, source, dest))


async def deploy_code(node_id: str, source: str, dest: str):
    """Deploy code to nodes."""
    env = EnvSettings()
    
    try:
        db = Database(env.database_url)
        await db.connect()
        
        if node_id:
            node_data = await db.fetchrow("SELECT * FROM nodes WHERE id = $1", node_id)
            if not node_data:
                console.print(f"[red]Node not found: {node_id}[/red]")
                return
            nodes = [dict(node_data)]
        else:
            nodes = await get_nodes_from_db(db)
        
        if not nodes:
            console.print("[yellow]No nodes found[/yellow]")
            await db.disconnect()
            return
        
        executor = SSHExecutor()
        manager = ClusterManager(executor)
        
        hosts = [n['host'] for n in nodes]
        console.print(f"[cyan]Deploying to {len(hosts)} node(s)...[/cyan]\n")
        
        results = await manager.deploy_code(hosts, source, dest)
        
        for node in nodes:
            host = node['host']
            success = results[host]
            
            if success:
                console.print(f"[green]✓[/green] {node['id']} ({host})")
            else:
                console.print(f"[red]✗[/red] {node['id']} ({host})")
        
        await db.disconnect()
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cluster.command()
@click.argument('action', type=click.Choice(['start', 'stop', 'restart']))
@click.option('--node', help='Control specific node (default: all)')
@click.option('--app-path', default="/home/sysadmin/Programs/skeleton-app")
def daemon(action: str, node: str, app_path: str):
    """Start, stop, or restart daemons on nodes."""
    asyncio.run(control_daemons(action, node, app_path))


async def control_daemons(action: str, node_id: str, app_path: str):
    """Control daemons on nodes."""
    env = EnvSettings()
    
    try:
        db = Database(env.database_url)
        await db.connect()
        
        if node_id:
            node_data = await db.fetchrow("SELECT * FROM nodes WHERE id = $1", node_id)
            if not node_data:
                console.print(f"[red]Node not found: {node_id}[/red]")
                return
            nodes = [dict(node_data)]
        else:
            nodes = await get_nodes_from_db(db)
        
        if not nodes:
            console.print("[yellow]No nodes found[/yellow]")
            await db.disconnect()
            return
        
        executor = SSHExecutor()
        manager = ClusterManager(executor)
        
        console.print(f"[cyan]{action.capitalize()}ing daemon on {len(nodes)} node(s)...[/cyan]\n")
        
        for node in nodes:
            host = node['host']
            
            if action == "start":
                success = await manager.start_daemon(host, app_path)
            elif action == "stop":
                success = await manager.stop_daemon(host)
            elif action == "restart":
                success = await manager.restart_daemon(host, app_path)
            
            status = "[green]✓[/green]" if success else "[red]✗[/red]"
            console.print(f"{status} {node['id']} ({host})")
        
        await db.disconnect()
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cluster.command()
@click.option('--source-node', required=True, help='Source node with models')
@click.option('--target-node', help='Target node (default: all others)')
@click.option('--models-path', default="/home/sysadmin/Programs/skeleton-app/models")
def sync_models(source_node: str, target_node: str, models_path: str):
    """Synchronize models from one node to others."""
    asyncio.run(synchronize_models(source_node, target_node, models_path))


async def synchronize_models(source_id: str, target_id: str, models_path: str):
    """Sync models between nodes."""
    env = EnvSettings()
    
    try:
        db = Database(env.database_url)
        await db.connect()
        
        # Get source node
        source_data = await db.fetchrow("SELECT * FROM nodes WHERE id = $1", source_id)
        if not source_data:
            console.print(f"[red]Source node not found: {source_id}[/red]")
            return
        source_node = dict(source_data)
        
        # Get target nodes
        if target_id:
            target_data = await db.fetchrow("SELECT * FROM nodes WHERE id = $1", target_id)
            if not target_data:
                console.print(f"[red]Target node not found: {target_id}[/red]")
                return
            target_nodes = [dict(target_data)]
        else:
            all_nodes = await get_nodes_from_db(db)
            target_nodes = [n for n in all_nodes if n['id'] != source_id]
        
        if not target_nodes:
            console.print("[yellow]No target nodes found[/yellow]")
            await db.disconnect()
            return
        
        executor = SSHExecutor()
        manager = ClusterManager(executor)
        
        console.print(f"[cyan]Syncing models from {source_id} to {len(target_nodes)} node(s)...[/cyan]\n")
        
        target_hosts = [n['host'] for n in target_nodes]
        results = await manager.sync_models(source_node['host'], target_hosts, models_path)
        
        for node in target_nodes:
            host = node['host']
            success = results.get(host, False)
            
            status = "[green]✓[/green]" if success else "[red]✗[/red]"
            console.print(f"{status} {node['id']} ({host})")
        
        await db.disconnect()
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cluster.command()
@click.option('--node', help='Collect from specific node (default: all)')
@click.option('--lines', default=100, help='Number of log lines to collect')
@click.option('--log-path', default="logs/skeleton.log")
@click.option('--output-dir', default="collected_logs")
def logs(node: str, lines: int, log_path: str, output_dir: str):
    """Collect logs from nodes."""
    asyncio.run(collect_cluster_logs(node, lines, log_path, output_dir))


async def collect_cluster_logs(node_id: str, lines: int, log_path: str, output_dir: str):
    """Collect logs from nodes."""
    env = EnvSettings()
    
    try:
        db = Database(env.database_url)
        await db.connect()
        
        if node_id:
            node_data = await db.fetchrow("SELECT * FROM nodes WHERE id = $1", node_id)
            if not node_data:
                console.print(f"[red]Node not found: {node_id}[/red]")
                return
            nodes = [dict(node_data)]
        else:
            nodes = await get_nodes_from_db(db)
        
        if not nodes:
            console.print("[yellow]No nodes found[/yellow]")
            await db.disconnect()
            return
        
        executor = SSHExecutor()
        manager = ClusterManager(executor)
        
        console.print(f"[cyan]Collecting logs from {len(nodes)} node(s)...[/cyan]\n")
        
        for node in nodes:
            host = node['host']
            local_file = f"{output_dir}/{node['id']}.log"
            
            success = await manager.collect_logs(host, log_path, local_file, lines)
            
            status = "[green]✓[/green]" if success else "[red]✗[/red]"
            console.print(f"{status} {node['id']} -> {local_file}")
        
        await db.disconnect()
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise
