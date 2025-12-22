# Quick Start: Transport Coordination

## Setup (5 minutes)

### 1. Install Dependencies

```bash
cd /home/sysadmin/Programs/skeleton-app
pip install -e ".[audio]"
```

This installs:
- JACK-Client (Python JACK bindings)
- python-osc (OSC messaging)
- Other audio dependencies

### 2. Verify JACK is Running

On each machine:

```bash
# Check JACK is running
jack_lsp

# If not, start JACK (example with alsa):
jackd -d alsa -r 48000 -p 128 -n 2

# Or use QjackCtl/Cadence GUI
```

### 3. Allow OSC Traffic Through Firewall

```bash
# On each machine:
sudo ufw allow 5555/udp   # Agent port
sudo ufw allow 5556/udp   # Coordinator port
```

## Test Run (2 machines)

### Machine 1 (Musician):

```bash
cd /home/sysadmin/Programs/skeleton-app
python examples/launch_transport_agent.py musician1 5555
```

You should see:
```
Connected to JACK as 'transport_agent_musician1'
OSC server listening on 0.0.0.0:5555
```

### Machine 2 (Director):

Replace `192.168.1.101` with Machine 1's actual IP:

```bash
cd /home/sysadmin/Programs/skeleton-app
python examples/launch_transport_coordinator.py director 192.168.1.101
```

You should see a GUI window with:
- Transport controls (Play, Stop, Locate)
- Pre-roll setting
- Agent list showing "musician1"

### Test Coordinated Start:

1. In coordinator window, ensure pre-roll is set to 3.0 seconds
2. Click "▶ Start All"
3. Watch both windows - after 3 seconds, both JACK transports should start
4. Check logs for timing accuracy:
   ```
   Transport STARTED at <time> (target: <time>, error: 0.5ms)
   ```

## Add More Machines

On each additional musician machine:

```bash
python examples/launch_transport_agent.py musician2 5555
python examples/launch_transport_agent.py musician3 5555
# etc.
```

In coordinator window:
- Type the machine's IP in the "Host/IP" field
- Click the "+" button
- Agent appears in the list

Now "Start All" will synchronize all machines!

## Add xjadeo Video Sync

On each musician machine:

```bash
# Ensure same video file exists at same path
VIDEO="/path/to/your/video.mp4"

# Launch xjadeo in JACK sync mode
xjadeo -t jack -f "$VIDEO" -S -O -m smpte &
```

Now when coordinator sends "Locate & Start":
- All JACK transports locate to frame 0 and start
- All xjadeo instances show the synchronized video frame

## Improve Time Sync (Optional but Recommended)

### Option 1: Simple NTP

On all machines, install and configure chrony:

```bash
sudo apt install chrony

# Edit /etc/chrony/chrony.conf and add your local NTP server
# Or use: pool 0.ubuntu.pool.ntp.org iburst

sudo systemctl restart chrony
chronyc tracking  # Check sync status
```

### Option 2: Precision PTP (Best)

```bash
sudo apt install linuxptp

# On director machine (grandmaster):
sudo ptp4l -i enp3s0 -m &
sudo phc2sys -s /dev/ptp0 -c CLOCK_REALTIME -O 0 -m &

# On musician machines (slaves):
sudo ptp4l -i enp3s0 -m &
sudo phc2sys -s /dev/ptp0 -c CLOCK_REALTIME -O 0 -m &

# Replace enp3s0 with your network interface name (find with: ip link)
```

Check sync quality:
```bash
# Should show offset < 1000ns (1 microsecond)
pmc -u -b 0 'GET TIME_STATUS_NP'
```

## Common Issues

### "JACK-Client not available"
```bash
pip install JACK-Client
```

### "python-osc not available"
```bash
pip install python-osc
```

### Agent not responding
1. Check firewall: `sudo ufw status`
2. Check network: `ping <agent-ip>`
3. Check JACK is running: `jack_lsp`
4. Check agent log window for errors

### Large timing errors (>10ms)
- Enable PTP or NTP time sync
- Check network quality (wired Ethernet, not WiFi)
- Reduce network load during recording

## Next Steps

See [TRANSPORT_COORDINATION.md](TRANSPORT_COORDINATION.md) for:
- Integration with main skeleton-app
- Service discovery integration
- Node canvas integration
- Advanced features (shared parameters, etc.)
- Troubleshooting guide

## Recording Workflow

1. **Setup**: All machines have agent running, video loaded in xjadeo
2. **Coordinate**: Director adds all agent IPs to coordinator
3. **Arm**: Each musician arms their DAW tracks (set to follow JACK transport)
4. **Record**: Director clicks "Locate & Start" with 3s pre-roll
5. **Result**: All machines record synchronized audio tracks
6. **Export**: Each musician exports their tracks
7. **Import**: Director imports all tracks into master DAW - they align perfectly!

Enjoy synchronized distributed recording! 🎵
