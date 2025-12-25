#!/usr/bin/env python3
"""Test script to verify MIDI port discovery and connections."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from skeleton_app.audio.jack_client import JackClientManager

def main():
    print("Testing JACK MIDI connection discovery...\n")
    
    # Create JACK client
    jack_mgr = JackClientManager("test_midi_client")
    
    try:
        # Connect
        print("1. Connecting to JACK...")
        jack_mgr.connect()
        print("   ✓ Connected!\n")
        
        # Get all ports (should include MIDI)
        print("2. Getting all ports...")
        all_ports = jack_mgr.get_ports()
        midi_ports = [p for p in all_ports if 'a2j' in p]
        print(f"   Total ports: {len(all_ports)}")
        print(f"   MIDI ports (a2j): {len(midi_ports)}")
        if midi_ports:
            print("   Sample MIDI ports:")
            for port in midi_ports[:5]:
                print(f"     - {port}")
        print()
        
        # Get MIDI output ports specifically
        print("3. Getting MIDI output ports...")
        midi_outputs = [p for p in jack_mgr.get_ports(is_output=True) if 'a2j' in p]
        print(f"   Found {len(midi_outputs)} MIDI output ports")
        if midi_outputs:
            for port in midi_outputs[:3]:
                print(f"     - {port}")
        print()
        
        # Get all connections
        print("4. Getting all connections...")
        connections = jack_mgr.get_all_connections()
        midi_connections = {k: v for k, v in connections.items() if 'a2j' in k or any('a2j' in p for p in v)}
        print(f"   Total connections: {len(connections)}")
        print(f"   MIDI connections: {len(midi_connections)}")
        if midi_connections:
            print("   MIDI Connections found:")
            for src, dests in midi_connections.items():
                for dest in dests:
                    print(f"     {src}")
                    print(f"       -> {dest}")
        else:
            print("   No MIDI connections found!")
        print()
        
        # Try to connect/disconnect a MIDI port
        if len(midi_outputs) >= 2:
            print("5. Testing MIDI connection/disconnection...")
            # Find first two MIDI ports (one output, one input)
            midi_output = None
            midi_input = None
            
            for port in jack_mgr.get_ports():
                if 'a2j' in port:
                    if 'capture' in port.lower() and not midi_output:
                        midi_output = port
                    elif 'playback' in port.lower() and not midi_input:
                        midi_input = port
                
                if midi_output and midi_input:
                    break
            
            if midi_output and midi_input:
                print(f"   Testing: {midi_output}")
                print(f"         -> {midi_input}")
                
                try:
                    jack_mgr.connect_ports(midi_output, midi_input)
                    print("   ✓ Connection created successfully")
                    
                    # Verify it exists
                    updated_connections = jack_mgr.get_all_connections()
                    if midi_output in updated_connections and midi_input in updated_connections[midi_output]:
                        print("   ✓ Connection verified in graph")
                    else:
                        print("   ✗ Connection NOT found in graph!")
                    
                    # Disconnect
                    jack_mgr.disconnect_ports(midi_output, midi_input)
                    print("   ✓ Disconnection successful")
                    
                except Exception as e:
                    print(f"   ✗ Error: {e}")
            else:
                print("   Could not find suitable MIDI ports for testing")
        
        print("\n✓ All tests completed!")
        
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
