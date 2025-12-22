#!/usr/bin/env python3
"""Simple UDP broadcast test - run on both machines to verify connectivity."""

import socket
import json
import time
import sys

BROADCAST_PORT = 5557

def test_broadcast():
    """Test sending and receiving UDP broadcasts."""
    
    # Get hostname
    hostname = socket.gethostname()
    
    print(f"Starting UDP broadcast test on {hostname}")
    print(f"Broadcasting on port {BROADCAST_PORT}")
    print("=" * 60)
    
    # Create broadcast socket
    broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    # Create listen socket
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen_sock.bind(('', BROADCAST_PORT))
    listen_sock.settimeout(1.0)  # 1 second timeout
    
    print(f"✓ Sockets created and bound")
    print(f"✓ Listening on 0.0.0.0:{BROADCAST_PORT}")
    print()
    
    # Get local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"
    
    print(f"Local IP: {local_ip}")
    print(f"Broadcasting every 2 seconds...")
    print(f"Listening for broadcasts from other machines...")
    print()
    
    while True:
        # Send broadcast
        message = {
            'hostname': hostname,
            'ip': local_ip,
            'timestamp': time.time()
        }
        
        data = json.dumps(message).encode('utf-8')
        try:
            broadcast_sock.sendto(data, ('<broadcast>', BROADCAST_PORT))
            print(f"→ SENT: {hostname} @ {local_ip}")
        except Exception as e:
            print(f"✗ Send error: {e}")
        
        # Try to receive
        try:
            data, addr = listen_sock.recvfrom(4096)
            msg = json.loads(data.decode('utf-8'))
            
            # Ignore our own broadcasts
            if msg['hostname'] != hostname:
                print(f"← RECEIVED from {addr[0]}: {msg['hostname']} @ {msg['ip']}")
                print(f"  ✓ DISCOVERY WORKING!")
            
        except socket.timeout:
            pass  # No data received
        except Exception as e:
            print(f"✗ Receive error: {e}")
        
        time.sleep(2)

if __name__ == "__main__":
    try:
        test_broadcast()
    except KeyboardInterrupt:
        print("\n\nStopped.")
