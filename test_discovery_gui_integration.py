#!/usr/bin/env python3
"""
Test service discovery with GUI integration.

This script tests the complete flow of service discovery from the GUI,
including the bridge signals that update the UI.

Run on multiple hosts to see cross-host discovery:
  Machine 1: python3 test_discovery_gui_integration.py --node "indigo" --host 192.168.32.7
  Machine 2: python3 test_discovery_gui_integration.py --node "karate" --host 192.168.32.11
  Machine 3: python3 test_discovery_gui_integration.py --node "green" --host 192.168.32.5
"""

import asyncio
import logging
import socket
import sys
from pathlib import Path
from typing import Optional

import click

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from skeleton_app.service_discovery import ServiceDiscovery, ServiceInfo, ServiceType
from skeleton_app.config import Config, NodeConfig, DatabaseConfig

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)8s] %(name)s: %(message)s'
)

logger = logging.getLogger(__name__)


def get_local_ip(host_hint: Optional[str] = None):
    """Get the local IP address."""
    if host_hint and host_hint != "0.0.0.0" and host_hint != "localhost":
        return host_hint
    
    try:
        # Create a socket to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"


async def main(node_name: str, host: Optional[str] = None):
    """Run the discovery test."""
    # Get hostname and IP
    hostname = socket.gethostname()
    local_ip = get_local_ip(host)
    
    node_id = f"test-{node_name or hostname}"
    
    logger.info("=" * 80)
    logger.info(f"Service Discovery Test - {node_name or 'Unnamed Node'}")
    logger.info("=" * 80)
    logger.info(f"Node ID: {node_id}")
    logger.info(f"Node Name: {node_name or hostname}")
    logger.info(f"IP Address: {local_ip}")
    logger.info("=" * 80)
    
    # Try to create and use service discovery WITHOUT database
    # (This removes the requirement for PostgreSQL to be running)
    logger.info("\n[TEST 1] Basic Service Discovery (No Database)")
    logger.info("-" * 80)
    
    discovery = ServiceDiscovery(
        node_id=node_id,
        node_name=node_name or hostname,
        node_host=local_ip,
        database=None,  # No database - just UDP + ZeroMQ
        heartbeat_interval=5
    )
    
    # Add callback to see discoveries
    async def discovery_callback(action: str, data):
        if action == "node_discovered":
            node_data = data
            logger.info(f"✅ DISCOVERED: {node_data['node_name']} at {node_data['host']}")
        else:
            logger.info(f"📢 SERVICE {action}: {data.service_name if hasattr(data, 'service_name') else data}")
    
    discovery.add_callback(discovery_callback)
    
    logger.info("Starting service discovery...")
    await discovery.start()
    logger.info("✓ Service discovery started!")
    
    # Register some test services
    logger.info("\n[TEST 2] Service Registration")
    logger.info("-" * 80)
    
    services = [
        ServiceInfo(
            node_id=node_id,
            service_type=ServiceType.JACK_AUDIO,
            service_name=f"jack_audio_{node_name or hostname}",
            endpoint=f"{local_ip}:9000",
            port=9000,
            capabilities={"sample_rate": 48000, "buffer_size": 256}
        ),
        ServiceInfo(
            node_id=node_id,
            service_type=ServiceType.LLM_INFERENCE,
            service_name=f"ollama_{node_name or hostname}",
            endpoint=f"http://{local_ip}:11434",
            port=11434,
            capabilities={"models": ["llama2", "mistral"], "embedding": True}
        ),
    ]
    
    for service in services:
        await discovery.register_service(service)
        logger.info(f"✓ Registered: {service.service_name}")
    
    # Keep running to receive discoveries
    logger.info("\n[TEST 3] Listening for Discoveries")
    logger.info("-" * 80)
    logger.info("Listening for other nodes... (Press Ctrl+C to stop)")
    logger.info("Expected: Should see broadcasts from other nodes every 5 seconds")
    logger.info("-" * 80)
    
    try:
        while True:
            await asyncio.sleep(5)
            
            # Print current state
            known = discovery.get_known_nodes()
            services = discovery.get_all_services()
            
            if known:
                logger.info(f"\n📊 KNOWN NODES ({len(known)}):")
                for node in known:
                    logger.info(f"  • {node['node_name']} ({node['node_id']}) @ {node['host']}")
            
            if services:
                total = sum(len(svcs) for svcs in services.values())
                logger.info(f"\n📦 DISCOVERED SERVICES ({total}):")
                for node_id, node_services in services.items():
                    for service in node_services:
                        logger.info(f"  • {service.service_name} ({service.service_type.value}) on {node_id[:8]}")
            else:
                logger.info("\n🔍 No services discovered yet...")
    
    except KeyboardInterrupt:
        logger.info("\n\nShutting down...")
        await discovery.stop()
        logger.info("✓ Service discovery stopped")


@click.command()
@click.option("--node", "-n", default=None, help="Node name (e.g., 'indigo', 'karate', 'green')")
@click.option("--host", "-h", default=None, help="Host IP address (auto-detected if not specified)")
def cli(node, host):
    """Run the discovery test."""
    try:
        asyncio.run(main(node, host))
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
