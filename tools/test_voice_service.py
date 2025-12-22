#!/usr/bin/env python3
"""
Test client for voice command service.

Tests WebSocket streaming and REST API endpoints.
"""

import asyncio
import json
import sys
from datetime import datetime

import httpx
import websockets


async def test_rest_api(base_url: str):
    """Test REST API endpoints."""
    print("\n" + "="*60)
    print("Testing REST API")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        # Test root endpoint
        print("\n→ GET /")
        response = await client.get(f"{base_url}/")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        # Test health endpoint
        print("\n→ GET /health")
        response = await client.get(f"{base_url}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        # Test stats
        print("\n→ GET /stats")
        response = await client.get(f"{base_url}/stats")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        # Test wake words
        print("\n→ GET /wake-words")
        response = await client.get(f"{base_url}/wake-words")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        # Test aliases
        print("\n→ GET /aliases")
        response = await client.get(f"{base_url}/aliases")
        print(f"Status: {response.status_code}")
        aliases = response.json()['aliases']
        print(f"Found {len(aliases)} aliases:")
        for alias in aliases[:5]:  # Show first 5
            print(f"  '{alias['alias']}' → '{alias['actual_command']}'")
        
        # Test command history
        print("\n→ GET /history")
        response = await client.get(f"{base_url}/history?limit=10")
        print(f"Status: {response.status_code}")
        history = response.json()['history']
        print(f"Found {len(history)} commands in history")


async def test_websocket(ws_url: str, duration: int = 30):
    """Test WebSocket streaming."""
    print("\n" + "="*60)
    print("Testing WebSocket Streaming")
    print("="*60)
    print(f"\nConnecting to: {ws_url}")
    print(f"Will listen for {duration} seconds...")
    print("\nSpeak into your microphone to test:")
    print("  1. Say a wake word (e.g., 'computer indigo')")
    print("  2. Then say a command (e.g., 'play' or 'stop')")
    print("\nPress Ctrl+C to stop early\n")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            print("✓ Connected to WebSocket")
            
            # Start keepalive task
            async def keepalive():
                while True:
                    await asyncio.sleep(10)
                    try:
                        await websocket.send("ping")
                    except Exception:
                        break
            
            keepalive_task = asyncio.create_task(keepalive())
            
            try:
                # Listen for messages
                end_time = asyncio.get_event_loop().time() + duration
                
                while asyncio.get_event_loop().time() < end_time:
                    try:
                        message = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=1.0
                        )
                        
                        data = json.loads(message)
                        message_type = data.get('type', 'unknown')
                        
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        
                        if message_type == 'connected':
                            print(f"[{timestamp}] {data['message']}")
                            wake_words = data.get('wake_words', {})
                            if wake_words:
                                print(f"  Wake words: {wake_words}")
                        
                        elif message_type == 'transcription':
                            partial = data.get('partial', False)
                            text = data.get('text', '')
                            confidence = data.get('confidence', 0.0)
                            
                            if partial:
                                print(f"[{timestamp}] Partial: {text}", end='\r')
                            else:
                                print(f"\n[{timestamp}] Final: {text} (confidence: {confidence:.2f})")
                        
                        elif message_type == 'wake_word':
                            node_id = data.get('node_id', '')
                            print(f"\n[{timestamp}] 🎤 Wake word detected for: {node_id}")
                            print(f"  → Listening for command...")
                        
                        elif message_type == 'command':
                            target = data.get('target_node', '')
                            command = data.get('command', '')
                            raw_text = data.get('raw_text', '')
                            confidence = data.get('confidence', 0.0)
                            
                            print(f"\n[{timestamp}] ⚡ Command received:")
                            print(f"  Target: {target}")
                            print(f"  Command: {command}")
                            print(f"  Raw text: {raw_text}")
                            print(f"  Confidence: {confidence:.2f}")
                        
                        elif message_type == 'pong':
                            pass  # Ignore pong responses
                        
                        else:
                            print(f"\n[{timestamp}] Unknown message type: {message_type}")
                            print(f"  Data: {data}")
                    
                    except asyncio.TimeoutError:
                        continue
                
                print("\n\nTest duration completed")
            
            finally:
                keepalive_task.cancel()
    
    except websockets.exceptions.WebSocketException as e:
        print(f"✗ WebSocket error: {e}")
        return False
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return True
    
    return True


async def test_add_wake_word(base_url: str, node_id: str, wake_word: str):
    """Test adding a wake word."""
    print("\n" + "="*60)
    print("Testing Wake Word Addition")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        print(f"\n→ POST /wake-words/{node_id}")
        print(f"   Wake word: {wake_word}")
        
        response = await client.post(
            f"{base_url}/wake-words/{node_id}",
            params={'wake_word': wake_word}
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")


async def test_add_alias(base_url: str, alias: str, actual_command: str):
    """Test adding a command alias."""
    print("\n" + "="*60)
    print("Testing Alias Addition")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        print(f"\n→ POST /aliases")
        print(f"   Alias: {alias}")
        print(f"   Command: {actual_command}")
        
        response = await client.post(
            f"{base_url}/aliases",
            params={
                'alias': alias,
                'actual_command': actual_command,
                'description': f'Test alias for {actual_command}'
            }
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")


async def main():
    """Main test function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test voice command service')
    parser.add_argument(
        '--host',
        default='localhost',
        help='Service host (default: localhost)'
    )
    parser.add_argument(
        '--port',
        default=8001,
        type=int,
        help='Service port (default: 8001)'
    )
    parser.add_argument(
        '--test',
        choices=['all', 'api', 'websocket', 'wake-word', 'alias'],
        default='all',
        help='Which test to run (default: all)'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=30,
        help='WebSocket test duration in seconds (default: 30)'
    )
    parser.add_argument(
        '--node-id',
        help='Node ID for wake word test'
    )
    parser.add_argument(
        '--wake-word',
        help='Wake word for wake word test'
    )
    parser.add_argument(
        '--alias',
        help='Alias for alias test'
    )
    parser.add_argument(
        '--command',
        help='Command for alias test'
    )
    
    args = parser.parse_args()
    
    base_url = f"http://{args.host}:{args.port}"
    ws_url = f"ws://{args.host}:{args.port}/ws"
    
    print("="*60)
    print("Voice Command Service Test Client")
    print("="*60)
    print(f"Base URL: {base_url}")
    print(f"WebSocket URL: {ws_url}")
    
    try:
        if args.test in ['all', 'api']:
            await test_rest_api(base_url)
        
        if args.test in ['all', 'websocket']:
            await test_websocket(ws_url, args.duration)
        
        if args.test == 'wake-word':
            if not args.node_id or not args.wake_word:
                print("Error: --node-id and --wake-word required for wake-word test")
                sys.exit(1)
            await test_add_wake_word(base_url, args.node_id, args.wake_word)
        
        if args.test == 'alias':
            if not args.alias or not args.command:
                print("Error: --alias and --command required for alias test")
                sys.exit(1)
            await test_add_alias(base_url, args.alias, args.command)
        
        print("\n" + "="*60)
        print("✓ All tests completed")
        print("="*60)
    
    except httpx.ConnectError:
        print(f"\n✗ Cannot connect to service at {base_url}")
        print("  Make sure the voice service is running:")
        print("    skeleton voice")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
