#!/usr/bin/env python3
"""
Test UDP broadcast-based node discovery.

Run this on multiple machines to test that they can discover each other.
"""

import asyncio
import logging
import socket
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from skeleton_app.service_discovery import ServiceDiscovery, ServiceInfo, ServiceType

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def get_local_ip():
    """Get the local IP address."""
    try:
        # Create a socket to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"


async def node_discovered_callback(action, data):
    """Callback when a node is discovered."""
    if action == "node_discovered":
        logger.info(f"🎉 DISCOVERED NODE: {data['node_name']} at {data['host']}")


async def service_change_callback(action, service):
    """Callback when a service changes."""
    logger.info(f"📢 SERVICE {action}: {service.service_name} ({service.service_type.value}) on {service.node_id}")


async def main():
    """Run the test."""
    # Get hostname and IP
    hostname = socket.gethostname()
    local_ip = get_local_ip()
    
    node_id = f"test-{hostname}"
    node_name = f"Test Node ({hostname})"
    
    logger.info(f"Starting test node: {node_name}")
    logger.info(f"Node ID: {node_id}")
    logger.info(f"IP Address: {local_ip}")
    logger.info("=" * 60)
    
    # Create service discovery (no database required)
    discovery = ServiceDiscovery(
        node_id=node_id,
        node_name=node_name,
        node_host=local_ip,
        database=None,  # No database needed for basic discovery
        heartbeat_interval=5
    )
    
    # Add callbacks
    discovery.add_callback(node_discovered_callback)
    discovery.add_callback(service_change_callback)
    
    # Start discovery
    await discovery.start()
    
    logger.info("✓ Service discovery started")
    logger.info("Broadcasting node presence on LAN...")
    logger.info("Listening for other nodes...")
    logger.info("Press Ctrl+C to stop\n")
    
    # Register a test service after 2 seconds
    await asyncio.sleep(2)
    test_service = ServiceInfo(
        node_id=node_id,
        service_type=ServiceType.CUSTOM,
        service_name=f"test-service-{hostname}",
        endpoint=f"http://{local_ip}:8000",
        port=8000,
        metadata={"description": "Test service for UDP discovery demo"}
    )
    await discovery.register_service(test_service)
    logger.info(f"✓ Registered test service: {test_service.service_name}\n")
    
    # Run until interrupted
    try:
        while True:
            await asyncio.sleep(10)
            
            # Show discovered nodes
            nodes = discovery.get_known_nodes()
            if nodes:
                logger.info(f"\n📡 Known Nodes ({len(nodes)}):")
                for node in nodes:
                    logger.info(f"  - {node['node_name']} @ {node['host']}")
            
            # Show services
            all_services = discovery.get_all_services()
            total_services = sum(len(services) for services in all_services.values())
            if total_services > 0:
                logger.info(f"\n🔧 Services ({total_services}):")
                for node_id, services in all_services.items():
                    for service in services:
                        logger.info(f"  - {service.service_name} ({service.service_type.value}) on {node_id}")
            logger.info("")
    
    except KeyboardInterrupt:
        logger.info("\n\nStopping...")
    
    finally:
        await discovery.stop()
        logger.info("Service discovery stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
