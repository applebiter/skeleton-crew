#!/usr/bin/env python3
"""Test script to verify JACK port discovery."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from skeleton_app.audio.jack_client import JackClientManager

def main():
    print("Testing JACK connection and port discovery...")
    
    # Create JACK client
    jack_mgr = JackClientManager("test_client")
    
    try:
        # Connect
        print("\n1. Connecting to JACK...")
        jack_mgr.connect()
        print("   ✓ Connected!")
        
        # Get ports
        print("\n2. Getting output ports...")
        output_ports = jack_mgr.get_ports(is_output=True, is_audio=True)
        print(f"   Found {len(output_ports)} output ports:")
        for port in output_ports[:10]:  # Show first 10
            print(f"     - {port}")
        if len(output_ports) > 10:
            print(f"     ... and {len(output_ports) - 10} more")
        
        print("\n3. Getting input ports...")
        input_ports = jack_mgr.get_ports(is_input=True, is_audio=True)
        print(f"   Found {len(input_ports)} input ports:")
        for port in input_ports[:10]:  # Show first 10
            print(f"     - {port}")
        if len(input_ports) > 10:
            print(f"     ... and {len(input_ports) - 10} more")
        
        # Get connections
        print("\n4. Getting all connections...")
        connections = jack_mgr.get_all_connections()
        print(f"   Found {len(connections)} output ports with connections:")
        for out_port, in_ports in list(connections.items())[:5]:
            print(f"     {out_port} ->")
            for in_port in in_ports:
                print(f"       → {in_port}")
        if len(connections) > 5:
            print(f"     ... and {len(connections) - 5} more connections")
        
        # Extract clients
        print("\n5. Extracting unique clients...")
        clients = set()
        for port in output_ports + input_ports:
            client_name = port.split(':')[0]
            clients.add(client_name)
        
        print(f"   Found {len(clients)} unique clients:")
        for client in sorted(clients):
            print(f"     - {client}")
        
        print("\n✓ All tests passed!")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Disconnect
        print("\nDisconnecting...")
        jack_mgr.disconnect()
        print("Done!")

if __name__ == "__main__":
    main()
