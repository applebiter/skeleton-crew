"""Node registry for tracking available nodes and their capabilities."""

import asyncio
import logging
import time
from typing import Dict, List, Optional

from skeleton_app.core.types import CapabilityRequest, CapabilityRoute, NodeCapability, NodeInfo

logger = logging.getLogger(__name__)


class NodeRegistry:
    """Registry for managing distributed nodes."""
    
    def __init__(self):
        self._nodes: Dict[str, NodeInfo] = {}
        self._local_node_id: Optional[str] = None
        self._lock = asyncio.Lock()
    
    def set_local_node(self, node_id: str):
        """Set the ID of the local node."""
        self._local_node_id = node_id
    
    async def register_node(self, node: NodeInfo):
        """Register a node in the registry."""
        async with self._lock:
            node.last_seen = time.time()
            self._nodes[node.id] = node
            logger.info(f"Registered node: {node.id} ({node.name}) with roles: {node.roles}")
    
    async def unregister_node(self, node_id: str):
        """Remove a node from the registry."""
        async with self._lock:
            if node_id in self._nodes:
                del self._nodes[node_id]
                logger.info(f"Unregistered node: {node_id}")
    
    async def update_node_status(self, node_id: str, status: str):
        """Update node status."""
        async with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].status = status
                self._nodes[node_id].last_seen = time.time()
    
    async def heartbeat(self, node_id: str):
        """Update node last_seen timestamp."""
        async with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].last_seen = time.time()
    
    async def get_node(self, node_id: str) -> Optional[NodeInfo]:
        """Get node information by ID."""
        async with self._lock:
            return self._nodes.get(node_id)
    
    async def list_nodes(
        self,
        role: Optional[str] = None,
        status: Optional[str] = "online"
    ) -> List[NodeInfo]:
        """List nodes, optionally filtered by role and status."""
        async with self._lock:
            nodes = list(self._nodes.values())
        
        if role:
            nodes = [n for n in nodes if role in n.roles]
        
        if status:
            nodes = [n for n in nodes if n.status == status]
        
        return nodes
    
    async def find_nodes_with_capability(
        self,
        capability_type: str,
        subtype: Optional[str] = None,
        model: Optional[str] = None
    ) -> List[NodeInfo]:
        """Find nodes that provide a specific capability."""
        nodes = await self.list_nodes(status="online")
        matching = []
        
        for node in nodes:
            for cap in node.capabilities:
                if cap.type != capability_type:
                    continue
                
                if subtype and cap.subtype != subtype:
                    continue
                
                if model and cap.models and model not in cap.models:
                    continue
                
                matching.append(node)
                break
        
        return matching
    
    def is_local_node(self, node_id: str) -> bool:
        """Check if a node ID refers to the local node."""
        return node_id == self._local_node_id
    
    async def cleanup_stale_nodes(self, timeout: float = 300):
        """Remove nodes that haven't been seen recently."""
        current_time = time.time()
        stale_nodes = []
        
        async with self._lock:
            for node_id, node in self._nodes.items():
                if node.last_seen and (current_time - node.last_seen) > timeout:
                    stale_nodes.append(node_id)
        
        for node_id in stale_nodes:
            await self.unregister_node(node_id)
            logger.warning(f"Removed stale node: {node_id}")


class CapabilityRouter:
    """Routes capability requests to appropriate nodes."""
    
    def __init__(self, registry: NodeRegistry):
        self.registry = registry
        self.prefer_local = True
        self.fallback_to_remote = True
        self.overrides: Dict[str, Dict[str, str]] = {}
    
    def configure(
        self,
        prefer_local: bool = True,
        fallback_to_remote: bool = True,
        overrides: Optional[Dict[str, Dict[str, str]]] = None
    ):
        """Configure routing behavior."""
        self.prefer_local = prefer_local
        self.fallback_to_remote = fallback_to_remote
        if overrides:
            self.overrides = overrides
    
    async def route(self, request: CapabilityRequest) -> Optional[CapabilityRoute]:
        """Route a capability request to an appropriate node."""
        
        # Check for explicit overrides
        override_key = f"{request.type}_{request.subtype}" if request.subtype else request.type
        if override_key in self.overrides:
            override = self.overrides[override_key]
            if "prefer_node" in override:
                node = await self.registry.get_node(override["prefer_node"])
                if node and node.status == "online":
                    capability = self._find_capability(node, request)
                    if capability:
                        return self._create_route(node, capability)
        
        # Find candidate nodes
        candidates = await self.registry.find_nodes_with_capability(
            request.type,
            request.subtype,
            request.model
        )
        
        if not candidates:
            logger.warning(f"No nodes found for capability: {request.type}/{request.subtype}")
            return None
        
        # Separate local and remote candidates
        local_candidates = [n for n in candidates if self.registry.is_local_node(n.id)]
        remote_candidates = [n for n in candidates if not self.registry.is_local_node(n.id)]
        
        # Apply routing policy
        selected_node = None
        
        if self.prefer_local and request.prefer_local and local_candidates:
            selected_node = self._select_best_node(local_candidates, request)
        elif self.fallback_to_remote and remote_candidates:
            selected_node = self._select_best_node(remote_candidates, request)
        elif not request.prefer_local and remote_candidates:
            selected_node = self._select_best_node(remote_candidates, request)
        elif local_candidates:
            selected_node = self._select_best_node(local_candidates, request)
        
        if not selected_node:
            logger.warning(f"Could not route capability request: {request.type}/{request.subtype}")
            return None
        
        capability = self._find_capability(selected_node, request)
        return self._create_route(selected_node, capability)
    
    def _find_capability(
        self,
        node: NodeInfo,
        request: CapabilityRequest
    ) -> Optional[NodeCapability]:
        """Find matching capability in a node."""
        for cap in node.capabilities:
            if cap.type != request.type:
                continue
            
            if request.subtype and cap.subtype != request.subtype:
                continue
            
            if request.model and cap.models and request.model not in cap.models:
                continue
            
            return cap
        
        return None
    
    def _select_best_node(
        self,
        candidates: List[NodeInfo],
        request: CapabilityRequest
    ) -> Optional[NodeInfo]:
        """
        Select the best node from candidates.
        Philosophy: Work with what's available, favor least-loaded nodes.
        """
        if not candidates:
            return None
        
        # Filter by required tags if specified
        if request.required_tags:
            filtered = []
            for node in candidates:
                if all(node.tags.get(k) == v for k, v in request.required_tags.items()):
                    filtered.append(node)
            
            if filtered:
                candidates = filtered
        
        # Opportunistic selection: favor available and least-loaded
        # Check 'available' tag (can be updated dynamically)
        available = [n for n in candidates if n.tags.get('available', True)]
        if available:
            candidates = available
        
        # Simple load balancing: rotate through candidates
        # In a real implementation, check actual load from database
        # For now, just return first available (can add round-robin later)
        return candidates[0]
    
    def _create_route(self, node: NodeInfo, capability: NodeCapability) -> CapabilityRoute:
        """Create a capability route."""
        is_local = self.registry.is_local_node(node.id)
        
        endpoint = None
        if not is_local:
            # Construct remote endpoint URL
            endpoint = f"http://{node.host}:{node.port}/api/v1/{capability.type}"
            if capability.subtype:
                endpoint += f"/{capability.subtype}"
        
        return CapabilityRoute(
            node_id=node.id,
            is_local=is_local,
            endpoint=endpoint,
            capability=capability
        )
