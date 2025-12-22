"""Integration between LLM provider and tool registry.

This allows LLM responses with tool calls to be executed safely.
"""

import logging
from typing import Any, Dict, List, Optional

from skeleton_app.providers.tools import ToolRegistry
from skeleton_app.core.types import LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class ToolExecutionRequest:
    """A tool call requested by the LLM."""
    
    def __init__(self, name: str, parameters: Dict[str, Any]):
        self.name = name
        self.parameters = parameters
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None


async def execute_tool_call(
    tool_registry: ToolRegistry,
    tool_name: str,
    parameters: Dict[str, Any],
    requester: str = "llm"
) -> Dict[str, Any]:
    """Execute a tool call and return result for LLM feedback."""
    
    result = await tool_registry.execute(
        tool_name=tool_name,
        parameters=parameters,
        requester=requester
    )
    
    return result


def extract_tool_calls(llm_response: LLMResponse) -> List[ToolExecutionRequest]:
    """Extract tool calls from an LLM response.
    
    This is a placeholder - actual implementation depends on how
    the LLM provider encodes tool calls in the response.
    """
    # This will be implemented when we integrate with the actual LLM response format
    # For now, this is a stub
    return []


async def execute_tool_loop(
    tool_registry: ToolRegistry,
    llm_response: LLMResponse,
    max_iterations: int = 10
) -> List[Dict[str, Any]]:
    """Execute a tool loop where the LLM can make multiple tool calls.
    
    Args:
        tool_registry: The registry with available tools
        llm_response: Initial LLM response
        max_iterations: Maximum number of tool calls to execute
    
    Returns:
        List of execution results
    """
    
    results = []
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        # Extract tool calls from response
        tool_calls = extract_tool_calls(llm_response)
        
        if not tool_calls:
            # No more tool calls, we're done
            break
        
        # Execute each tool call
        for call in tool_calls:
            try:
                result = await execute_tool_call(
                    tool_registry,
                    tool_name=call.name,
                    parameters=call.parameters
                )
                call.result = result
                results.append(result)
                logger.info(f"Tool execution result: {call.name} - {result.get('status')}")
            except Exception as e:
                call.error = str(e)
                logger.error(f"Tool execution failed: {call.name} - {e}")
        
        # TODO: Feed results back to LLM for next iteration
        # This requires calling the LLM again with tool results
        break
    
    return results
