"""
Service discovery and health monitoring.

Hybrid approach:
- ZeroMQ pub/sub for real-time service announcements
- PostgreSQL for persistent service registry
"""

import asyncio
import json
import logging
import socket
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from enum import Enum

import zmq
import zmq.asyncio

from skeleton_app.database import Database

logger = logging.getLogger(__name__)


class ServiceType(str, Enum):
    """Types of services that can be registered."""
    JACK_AUDIO = "jack_audio"
    XJADEO_VIDEO = "xjadeo_video"
    LLM_INFERENCE = "llm_inference"
    STT_ENGINE = "stt_engine"
    TTS_ENGINE = "tts_engine"
    MIDI_ROUTING = "midi_routing"
    OSC_SERVER = "osc_server"
    MEDIA_LIBRARY = "media_library"
    RECORDING = "recording"
    PLAYBACK = "playback"
    CUSTOM = "custom"


class ServiceStatus(str, Enum):
    """Service availability status."""
    AVAILABLE = "available"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"
    MAINTENANCE = "maintenance"


class HealthStatus(str, Enum):
    """Service health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceInfo:
    """Information about a service."""
    node_id: str
    service_type: ServiceType
    service_name: str
    endpoint: Optional[str] = None
    port: Optional[int] = None
    protocol: str = "tcp"
    capabilities: Dict = None
    metadata: Dict = None
    status: ServiceStatus = ServiceStatus.AVAILABLE
    health_status: HealthStatus = HealthStatus.HEALTHY
    
    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = {}
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert enums to strings
        data['service_type'] = self.service_type.value if isinstance(self.service_type, ServiceType) else self.service_type
        data['status'] = self.status.value if isinstance(self.status, ServiceStatus) else self.status
        data['health_status'] = self.health_status.value if isinstance(self.health_status, HealthStatus) else self.health_status
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ServiceInfo':
        """Create from dictionary."""
        # Convert string enums back to enum types
        if 'service_type' in data and isinstance(data['service_type'], str):
            data['service_type'] = ServiceType(data['service_type'])
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = ServiceStatus(data['status'])
        if 'health_status' in data and isinstance(data['health_status'], str):
            data['health_status'] = HealthStatus(data['health_status'])
        return cls(**data)


class ServiceDiscovery:
    """
    Hybrid service discovery using ZeroMQ and PostgreSQL.
    
    - ZeroMQ pub/sub for real-time announcements
    - PostgreSQL for persistent registry
    """
    
    def __init__(
        self,
        node_id: str,
        database: Database,
        pub_port: int = 5555,
        sub_port: int = 5556,
        heartbeat_interval: int = 10
    ):
        self.node_id = node_id
        self.database = database
        self.pub_port = pub_port
        self.sub_port = sub_port
        self.heartbeat_interval = heartbeat_interval
        
        # ZeroMQ context
        self.zmq_context = zmq.asyncio.Context()
        self.publisher: Optional[zmq.asyncio.Socket] = None
        self.subscriber: Optional[zmq.asyncio.Socket] = None
        
        # Local service registry
        self.local_services: Dict[str, ServiceInfo] = {}
        
        # Cluster-wide service cache
        self.cluster_services: Dict[str, Dict[str, ServiceInfo]] = {}  # node_id -> {service_name -> ServiceInfo}
        
        # Service change callbacks
        self.callbacks: List[Callable] = []
        
        # Running flag
        self.running = False
        
        # Tasks
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.subscriber_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start service discovery."""
        if self.running:
            return
        
        logger.info(f"Starting service discovery for node {self.node_id}")
        
        # Setup ZeroMQ publisher
        self.publisher = self.zmq_context.socket(zmq.PUB)
        self.publisher.bind(f"tcp://*:{self.pub_port}")
        
        # Setup ZeroMQ subscriber (connect to all other nodes)
        self.subscriber = self.zmq_context.socket(zmq.SUB)
        self.subscriber.setsockopt_string(zmq.SUBSCRIBE, "")
        
        # Load known nodes from database and subscribe to them
        await self._subscribe_to_cluster()
        
        # Load existing services from database
        await self._load_services_from_db()
        
        self.running = True
        
        # Start background tasks
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self.subscriber_task = asyncio.create_task(self._subscription_loop())
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("Service discovery started")
    
    async def stop(self):
        """Stop service discovery."""
        if not self.running:
            return
        
        logger.info("Stopping service discovery")
        self.running = False
        
        # Cancel tasks
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.subscriber_task:
            self.subscriber_task.cancel()
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        # Mark our services as unavailable
        for service_name in self.local_services:
            await self.unregister_service(service_name)
        
        # Close ZeroMQ sockets
        if self.publisher:
            self.publisher.close()
        if self.subscriber:
            self.subscriber.close()
        
        logger.info("Service discovery stopped")
    
    async def register_service(self, service: ServiceInfo):
        """
        Register a service on this node.
        
        Args:
            service: Service information
        """
        service.node_id = self.node_id
        service_key = f"{service.service_type.value}:{service.service_name}"
        
        self.local_services[service_key] = service
        
        # Save to database
        await self._save_service_to_db(service)
        
        # Announce via ZeroMQ
        await self._announce_service(service, "registered")
        
        logger.info(f"Registered service: {service.service_name} ({service.service_type.value})")
    
    async def unregister_service(self, service_name: str):
        """
        Unregister a service from this node.
        
        Args:
            service_name: Name of service to remove
        """
        # Find service in local registry
        service_key = None
        service = None
        
        for key, svc in self.local_services.items():
            if svc.service_name == service_name:
                service_key = key
                service = svc
                break
        
        if not service:
            return
        
        # Mark as unavailable
        service.status = ServiceStatus.UNAVAILABLE
        
        # Update database
        await self._save_service_to_db(service)
        
        # Announce removal
        await self._announce_service(service, "unregistered")
        
        # Remove from local registry
        del self.local_services[service_key]
        
        logger.info(f"Unregistered service: {service_name}")
    
    async def update_service_health(
        self,
        service_name: str,
        health_status: HealthStatus,
        response_time_ms: Optional[float] = None,
        error_message: Optional[str] = None
    ):
        """Update service health status."""
        for key, service in self.local_services.items():
            if service.service_name == service_name:
                service.health_status = health_status
                
                # Save to database with health history
                await self._save_service_health(service, response_time_ms, error_message)
                
                # Announce health change
                await self._announce_service(service, "health_update")
                break
    
    def get_services_by_type(self, service_type: ServiceType) -> List[ServiceInfo]:
        """Get all services of a given type across the cluster."""
        services = []
        
        for node_services in self.cluster_services.values():
            for service in node_services.values():
                if service.service_type == service_type and service.status == ServiceStatus.AVAILABLE:
                    services.append(service)
        
        return services
    
    def get_services_by_node(self, node_id: str) -> List[ServiceInfo]:
        """Get all services on a specific node."""
        return list(self.cluster_services.get(node_id, {}).values())
    
    def get_all_services(self) -> Dict[str, List[ServiceInfo]]:
        """Get all services grouped by node."""
        result = {}
        for node_id, services in self.cluster_services.items():
            result[node_id] = list(services.values())
        return result
    
    def add_callback(self, callback: Callable):
        """Add callback for service changes."""
        self.callbacks.append(callback)
    
    async def _subscribe_to_cluster(self):
        """Subscribe to all known nodes."""
        if not self.database.pool:
            return
        
        async with self.database.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, host FROM nodes WHERE status = 'online' AND id != $1",
                self.node_id
            )
            
            for row in rows:
                node_host = row['host']
                self.subscriber.connect(f"tcp://{node_host}:{self.pub_port}")
                logger.info(f"Subscribed to node: {row['id']} at {node_host}")
    
    async def _load_services_from_db(self):
        """Load existing services from database."""
        if not self.database.pool:
            return
        
        async with self.database.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    node_id, service_type, service_name, endpoint, port, protocol,
                    capabilities, metadata, status, health_status
                FROM services
                WHERE status != 'unavailable'
                AND last_heartbeat > NOW() - INTERVAL '1 minute'
            """)
            
            for row in rows:
                service = ServiceInfo(
                    node_id=row['node_id'],
                    service_type=ServiceType(row['service_type']),
                    service_name=row['service_name'],
                    endpoint=row['endpoint'],
                    port=row['port'],
                    protocol=row['protocol'],
                    capabilities=row['capabilities'] or {},
                    metadata=row['metadata'] or {},
                    status=ServiceStatus(row['status']),
                    health_status=HealthStatus(row['health_status'])
                )
                
                if service.node_id not in self.cluster_services:
                    self.cluster_services[service.node_id] = {}
                
                service_key = f"{service.service_type.value}:{service.service_name}"
                self.cluster_services[service.node_id][service_key] = service
    
    async def _save_service_to_db(self, service: ServiceInfo):
        """Save service to database."""
        if not self.database.pool:
            return
        
        async with self.database.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO services (
                    node_id, service_type, service_name, endpoint, port, protocol,
                    capabilities, metadata, status, health_status, last_heartbeat
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                ON CONFLICT (node_id, service_type, service_name)
                DO UPDATE SET
                    endpoint = EXCLUDED.endpoint,
                    port = EXCLUDED.port,
                    protocol = EXCLUDED.protocol,
                    capabilities = EXCLUDED.capabilities,
                    metadata = EXCLUDED.metadata,
                    status = EXCLUDED.status,
                    health_status = EXCLUDED.health_status,
                    last_heartbeat = NOW(),
                    updated_at = NOW()
            """, service.node_id, service.service_type.value, service.service_name,
                service.endpoint, service.port, service.protocol,
                json.dumps(service.capabilities), json.dumps(service.metadata),
                service.status.value, service.health_status.value)
    
    async def _save_service_health(
        self,
        service: ServiceInfo,
        response_time_ms: Optional[float],
        error_message: Optional[str]
    ):
        """Save service health to database."""
        if not self.database.pool:
            return
        
        async with self.database.pool.acquire() as conn:
            # Get service ID
            row = await conn.fetchrow("""
                SELECT id FROM services 
                WHERE node_id = $1 AND service_type = $2 AND service_name = $3
            """, service.node_id, service.service_type.value, service.service_name)
            
            if row:
                await conn.execute("""
                    INSERT INTO service_health_history (
                        service_id, health_status, response_time_ms, error_message
                    )
                    VALUES ($1, $2, $3, $4)
                """, row['id'], service.health_status.value, response_time_ms, error_message)
            
            # Update service health
            await self._save_service_to_db(service)
    
    async def _announce_service(self, service: ServiceInfo, action: str):
        """Announce service change via ZeroMQ."""
        if not self.publisher:
            return
        
        message = {
            "action": action,
            "service": service.to_dict(),
            "timestamp": datetime.now().isoformat()
        }
        
        await self.publisher.send_json(message)
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats for our services."""
        while self.running:
            try:
                for service in self.local_services.values():
                    await self._save_service_to_db(service)
                    await self._announce_service(service, "heartbeat")
                
                await asyncio.sleep(self.heartbeat_interval)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(1)
    
    async def _subscription_loop(self):
        """Listen for service announcements from other nodes."""
        while self.running:
            try:
                if not self.subscriber:
                    await asyncio.sleep(1)
                    continue
                
                # Receive message (non-blocking with timeout)
                try:
                    message = await asyncio.wait_for(
                        self.subscriber.recv_json(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                action = message.get('action')
                service_data = message.get('service')
                
                if not service_data:
                    continue
                
                service = ServiceInfo.from_dict(service_data)
                
                # Skip our own announcements
                if service.node_id == self.node_id:
                    continue
                
                # Update cluster registry
                if service.node_id not in self.cluster_services:
                    self.cluster_services[service.node_id] = {}
                
                service_key = f"{service.service_type.value}:{service.service_name}"
                
                if action == "unregistered":
                    self.cluster_services[service.node_id].pop(service_key, None)
                else:
                    self.cluster_services[service.node_id][service_key] = service
                
                # Notify callbacks
                for callback in self.callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(action, service)
                        else:
                            callback(action, service)
                    except Exception as e:
                        logger.error(f"Error in service callback: {e}")
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in subscription loop: {e}")
                await asyncio.sleep(1)
    
    async def _cleanup_loop(self):
        """Remove stale services from registry."""
        while self.running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                if not self.database.pool:
                    continue
                
                # Mark services as unavailable if no heartbeat in 2x interval
                timeout = timedelta(seconds=self.heartbeat_interval * 2)
                
                async with self.database.pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE services
                        SET status = 'unavailable', updated_at = NOW()
                        WHERE last_heartbeat < NOW() - $1
                        AND status != 'unavailable'
                    """, timeout)
                    
                    # Clean up old health history (keep last 1000 per service)
                    await conn.execute("""
                        DELETE FROM service_health_history
                        WHERE id NOT IN (
                            SELECT id FROM (
                                SELECT id,
                                       ROW_NUMBER() OVER (PARTITION BY service_id ORDER BY checked_at DESC) as rn
                                FROM service_health_history
                            ) sub
                            WHERE rn <= 1000
                        )
                    """)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
