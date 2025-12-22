"""Custom tool registry system for controlled agent behavior.

This module provides a lightweight, auditable tool system where every tool
invocation is local, logged, and fully under your control.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    
    name: str
    type: str  # string, number, integer, boolean, array, object
    description: str
    required: bool = False
    enum: Optional[List[Any]] = None
    default: Optional[Any] = None


@dataclass
class ToolDefinition:
    """Definition of an executable tool that the LLM can invoke."""
    
    name: str
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)
    handler: Optional[Callable] = None
    category: str = "general"  # For organizing tools: jack, recording, transport, etc.
    dangerous: bool = False  # Flag if tool can cause system changes
    
    def to_json_schema(self) -> Dict:
        """Convert to JSON schema for LLM."""
        param_schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        for param in self.parameters:
            param_schema["properties"][param.name] = {
                "type": param.type,
                "description": param.description
            }
            
            if param.enum:
                param_schema["properties"][param.name]["enum"] = param.enum
            
            if param.default is not None:
                param_schema["properties"][param.name]["default"] = param.default
            
            if param.required:
                param_schema["required"].append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": param_schema
            }
        }


class ToolRegistry:
    """Registry of available tools that the LLM can invoke."""
    
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self.execution_history: List[Dict] = []
        self.max_history = 1000  # Keep last 1000 executions for audit trail
    
    def register(self, tool_def: ToolDefinition):
        """Register a tool."""
        if tool_def.handler is None:
            raise ValueError(f"Tool {tool_def.name} must have a handler")
        
        self.tools[tool_def.name] = tool_def
        logger.info(f"Registered tool: {tool_def.name} ({tool_def.category})")
    
    def get_json_schemas(self) -> List[Dict]:
        """Get all tool schemas for LLM."""
        return [tool.to_json_schema() for tool in self.tools.values()]
    
    def get_tools_by_category(self, category: str) -> List[ToolDefinition]:
        """Get tools filtered by category."""
        return [t for t in self.tools.values() if t.category == category]
    
    async def execute(
        self, 
        tool_name: str, 
        parameters: Dict[str, Any],
        requester: str = "unknown"
    ) -> Dict[str, Any]:
        """
        Execute a tool with validation.
        
        Args:
            tool_name: Name of the tool to execute
            parameters: Parameters for the tool
            requester: Who is requesting this (for audit trail)
        
        Returns:
            Result dict with status, output, and metadata
        """
        
        execution_record = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "requester": requester,
            "parameters": parameters,
            "status": "pending",
            "output": None,
            "error": None
        }
        
        try:
            # Validate tool exists
            if tool_name not in self.tools:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            tool = self.tools[tool_name]
            
            # Validate parameters
            self._validate_parameters(tool, parameters)
            
            # Log dangerous operations
            if tool.dangerous:
                logger.warning(
                    f"Dangerous tool execution requested: {tool_name} by {requester}"
                )
            
            # Execute handler
            if callable(tool.handler):
                # Check if async
                import asyncio
                import inspect
                
                if inspect.iscoroutinefunction(tool.handler):
                    result = await tool.handler(**parameters)
                else:
                    result = tool.handler(**parameters)
            else:
                raise ValueError(f"Tool handler for {tool_name} is not callable")
            
            execution_record["status"] = "success"
            execution_record["output"] = result
            
            logger.info(f"Tool executed successfully: {tool_name}")
            
        except Exception as e:
            execution_record["status"] = "error"
            execution_record["error"] = str(e)
            logger.error(f"Tool execution failed: {tool_name}: {e}")
        
        # Add to history
        self.execution_history.append(execution_record)
        if len(self.execution_history) > self.max_history:
            self.execution_history.pop(0)
        
        return execution_record
    
    def _validate_parameters(self, tool: ToolDefinition, parameters: Dict[str, Any]):
        """Validate parameters against tool definition."""
        provided_keys = set(parameters.keys())
        required_keys = {p.name for p in tool.parameters if p.required}
        allowed_keys = {p.name for p in tool.parameters}
        
        # Check required parameters
        missing = required_keys - provided_keys
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")
        
        # Check for unexpected parameters
        extra = provided_keys - allowed_keys
        if extra:
            raise ValueError(f"Unexpected parameters: {extra}")
        
        # Validate types and values
        for param in tool.parameters:
            if param.name not in parameters:
                continue
            
            value = parameters[param.name]
            
            # Type validation
            if param.type == "string" and not isinstance(value, str):
                raise ValueError(f"Parameter {param.name} must be string")
            elif param.type == "number" and not isinstance(value, (int, float)):
                raise ValueError(f"Parameter {param.name} must be number")
            elif param.type == "integer" and not isinstance(value, int):
                raise ValueError(f"Parameter {param.name} must be integer")
            elif param.type == "boolean" and not isinstance(value, bool):
                raise ValueError(f"Parameter {param.name} must be boolean")
            
            # Enum validation
            if param.enum and value not in param.enum:
                raise ValueError(f"Parameter {param.name} must be one of {param.enum}")
    
    def get_execution_history(self, tool_name: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get execution history for audit/debugging."""
        history = self.execution_history
        
        if tool_name:
            history = [h for h in history if h["tool"] == tool_name]
        
        return history[-limit:]
    
    def get_summary(self) -> Dict:
        """Get registry summary for debugging."""
        return {
            "total_tools": len(self.tools),
            "tools_by_category": {
                cat: len(self.get_tools_by_category(cat))
                for cat in set(t.category for t in self.tools.values())
            },
            "execution_history_size": len(self.execution_history),
            "tool_names": sorted(self.tools.keys())
        }


# Global tool registry instance
_tool_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the global tool registry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


def create_tool_registry() -> ToolRegistry:
    """Create a new tool registry instance."""
    return ToolRegistry()
