"""Example of using the tool registry system."""

import asyncio
import json
import logging

from skeleton_app.providers import (
    ToolRegistry,
    get_tool_registry,
    register_builtin_tools,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Demo of tool registry usage."""
    
    # Create and populate registry
    registry = ToolRegistry()
    register_builtin_tools(registry)
    
    print("\n" + "="*60)
    print("TOOL REGISTRY DEMO")
    print("="*60)
    
    # Show summary
    summary = registry.get_summary()
    print(f"\nRegistry Summary:")
    print(f"  Total tools: {summary['total_tools']}")
    print(f"  Tools by category:")
    for cat, count in summary['tools_by_category'].items():
        print(f"    - {cat}: {count}")
    
    # Show all tool schemas
    print(f"\nAvailable Tools (JSON Schema):")
    schemas = registry.get_json_schemas()
    for schema in schemas:
        func = schema['function']
        print(f"\n  • {func['name']}")
        print(f"    Description: {func['description']}")
        if func['parameters']['properties']:
            print(f"    Parameters:")
            for param_name, param_spec in func['parameters']['properties'].items():
                required = param_name in func['parameters'].get('required', [])
                req_str = " [REQUIRED]" if required else ""
                print(f"      - {param_name}: {param_spec['type']}{req_str}")
    
    # Test tool execution
    print(f"\n{'='*60}")
    print("TEST TOOL EXECUTION")
    print(f"{'='*60}")
    
    print("\n1. Executing: jack_status")
    result = await registry.execute("jack_status", {}, requester="demo")
    print(f"   Status: {result['status']}")
    print(f"   Output: {json.dumps(result['output'], indent=4)}")
    
    print("\n2. Executing: list_jack_ports (filtered to 'audio')")
    result = await registry.execute(
        "list_jack_ports",
        {"port_type": "audio"},
        requester="demo"
    )
    print(f"   Status: {result['status']}")
    
    print("\n3. Executing: get_node_status")
    result = await registry.execute("get_node_status", {}, requester="demo")
    print(f"   Status: {result['status']}")
    print(f"   Output: {json.dumps(result['output'], indent=4)}")
    
    # Show execution history
    print(f"\n{'='*60}")
    print("EXECUTION HISTORY (Audit Trail)")
    print(f"{'='*60}")
    history = registry.get_execution_history()
    print(f"\nLast {len(history)} executions:")
    for entry in history:
        print(f"\n  [{entry['timestamp']}] {entry['tool']}")
        print(f"    Requester: {entry['requester']}")
        print(f"    Status: {entry['status']}")
        if entry['error']:
            print(f"    Error: {entry['error']}")
    
    print("\n" + "="*60)
    print("✓ Demo complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
