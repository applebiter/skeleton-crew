#!/usr/bin/env python3
"""
Simple example client for voice command service.

Shows how to connect to the WebSocket and receive voice commands in real-time.
"""

import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("Error: websockets not installed")
    print("Install with: pip install websockets")
    sys.exit(1)


async def listen_for_commands(host: str = "localhost", port: int = 8001):
    """
    Connect to voice command service and listen for commands.
    
    Args:
        host: Service host
        port: Service port
    """
    ws_url = f"ws://{host}:{port}/ws"
    
    print(f"Connecting to {ws_url}...")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            print("✓ Connected!")
            print("\nListening for voice commands...")
            print("Speak into your microphone:")
            print("  1. Say wake word (e.g., 'computer indigo')")
            print("  2. Say command (e.g., 'play', 'stop', 'record')")
            print("\nPress Ctrl+C to exit\n")
            print("-" * 60)
            
            # Send keepalive ping every 10 seconds
            async def keepalive():
                while True:
                    await asyncio.sleep(10)
                    try:
                        await websocket.send("ping")
                    except Exception:
                        break
            
            keepalive_task = asyncio.create_task(keepalive())
            
            try:
                async for message in websocket:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    if msg_type == 'connected':
                        print(f"[INIT] {data.get('message', '')}")
                        wake_words = data.get('wake_words', {})
                        if wake_words:
                            print(f"[INIT] Available wake words: {wake_words}")
                        print("-" * 60)
                    
                    elif msg_type == 'transcription':
                        if not data.get('partial'):
                            # Only show final transcriptions
                            text = data.get('text', '')
                            confidence = data.get('confidence', 0.0)
                            print(f"[SPEECH] {text} (confidence: {confidence:.2f})")
                    
                    elif msg_type == 'wake_word':
                        node_id = data.get('node_id', '')
                        print(f"\n🎤 [WAKE] Activated for: {node_id}")
                        print("    → Listening for command...")
                    
                    elif msg_type == 'command':
                        target = data.get('target_node', '')
                        command = data.get('command', '')
                        raw = data.get('raw_text', '')
                        confidence = data.get('confidence', 0.0)
                        
                        print(f"\n⚡ [COMMAND]")
                        print(f"    Target:     {target}")
                        print(f"    Command:    {command}")
                        print(f"    Raw text:   {raw}")
                        print(f"    Confidence: {confidence:.2f}")
                        print()
                        
                        # Here you would execute the command
                        # For example:
                        if command == 'transport_start':
                            print("    → Starting JACK transport")
                        elif command == 'transport_stop':
                            print("    → Stopping JACK transport")
                        elif command == 'recording_start':
                            print("    → Starting recording")
                        else:
                            print(f"    → Unknown command: {command}")
                        
                        print("-" * 60)
            
            finally:
                keepalive_task.cancel()
    
    except websockets.exceptions.WebSocketException as e:
        print(f"\n✗ WebSocket error: {e}")
        print("\nMake sure the voice service is running:")
        print("  skeleton voice")
        return False
    except KeyboardInterrupt:
        print("\n\nDisconnected")
        return True
    
    return True


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Listen for voice commands',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Listen on localhost
  %(prog)s
  
  # Listen on remote node
  %(prog)s --host 192.168.32.5
  
  # Custom port
  %(prog)s --port 8002
        """
    )
    parser.add_argument(
        '--host',
        default='localhost',
        help='Service host (default: localhost)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8001,
        help='Service port (default: 8001)'
    )
    
    args = parser.parse_args()
    
    print("═" * 60)
    print("  Voice Command Client")
    print("═" * 60)
    
    try:
        asyncio.run(listen_for_commands(args.host, args.port))
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
