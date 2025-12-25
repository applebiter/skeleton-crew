#!/usr/bin/env python3
"""Test to reproduce the GUI MIDI connection issue."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from skeleton_app.audio.jack_client import JackClientManager

def test_connection_workflow():
    """Simulate what the GUI does when connecting ports."""
    print("Simulating GUI connection workflow...\n")
    
    jack_mgr = JackClientManager("gui_test")
    jack_mgr.connect()
    
    try:
        # Step 1: Get all ports (like the canvas does)
        all_ports = jack_mgr.get_ports()
        print(f"1. Canvas gets {len(all_ports)} total ports")
        
        # Step 2: Find MIDI ports
        midi_ports = [p for p in all_ports if 'a2j' in p]
        print(f"2. Found {len(midi_ports)} MIDI ports")
        
        # Step 3: Get output classification
        output_ports = set(jack_mgr.get_ports(is_output=True))
        print(f"3. Found {len(output_ports)} output ports (includes MIDI)")
        
        # Step 4: Try to create a MIDI connection (like canvas does)
        midi_output = "a2j:Keystation 88 MK3 [20] (capture): [0] Keystation 88 MK3 Keystation 88"
        midi_input = "a2j:AudioBox USB 96 [24] (playback): [0] AudioBox USB 96 MIDI 1"
        
        print(f"\n4. Attempting MIDI connection:")
        print(f"   {midi_output}")
        print(f"   -> {midi_input}")
        
        try:
            jack_mgr.connect_ports(midi_output, midi_input)
            print("   ✓ JACK connection created successfully!")
        except Exception as e:
            print(f"   ✗ JACK connection failed: {e}")
            return False
        
        # Step 5: Verify connection appears in get_all_connections
        connections = jack_mgr.get_all_connections()
        if midi_output in connections and midi_input in connections[midi_output]:
            print("   ✓ Connection appears in get_all_connections()")
        else:
            print("   ✗ Connection NOT in get_all_connections()!")
            print(f"     All connections: {connections}")
            return False
        
        # Step 6: Try to disconnect (like clicking connection in GUI)
        print(f"\n5. Attempting MIDI disconnection:")
        try:
            jack_mgr.disconnect_ports(midi_output, midi_input)
            print("   ✓ JACK disconnection successful!")
        except Exception as e:
            print(f"   ✗ JACK disconnection failed: {e}")
            return False
        
        # Step 7: Verify it's gone
        connections = jack_mgr.get_all_connections()
        if midi_output not in connections or midi_input not in connections.get(midi_output, []):
            print("   ✓ Connection removed from get_all_connections()")
        else:
            print("   ✗ Connection still in get_all_connections()!")
            return False
        
        print("\n✓ All workflow steps completed successfully!")
        print("  → MIDI connections should work in GUI")
        return True
        
    finally:
        jack_mgr.disconnect()

if __name__ == "__main__":
    success = test_connection_workflow()
    sys.exit(0 if success else 1)
