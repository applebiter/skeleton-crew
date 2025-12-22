# JACK Transport Coordination System

## Overview

This system enables synchronized JACK transport control across multiple Linux machines on a LAN, using OSC (Open Sound Control) for robust, music-friendly messaging. It's designed for distributed recording scenarios where multiple musicians need to start/stop recording in sync while following the same video timeline with xjadeo.

## Architecture

### Components

1. **TransportAgent** (`transport_agent.py`)
   - Runs on each musician's machine
   - Listens for OSC commands on port 5555 (configurable)
   - Controls local JACK transport
   - Reports state back to coordinator

2. **TransportCoordinator** (`transport_coordinator.py`)
   - Runs on director/conductor machine
   - Sends synchronized commands to all agents
   - Manages list of registered agents
   - Provides unified control interface

3. **Service Integration** (`transport_services.py`)
   - Wraps agents/coordinator for service discovery
   - Integrates with existing skeleton_app registry
   - Provides status/health monitoring

4. **GUI Widgets** (`transport_nodes.py`)
   - Visual node representations for canvas
   - Control panels for coordinator
   - Status displays for agents

## OSC Protocol

### Agent Commands (received by agents)

- `/transport/start [timestamp]` - Start transport at time (or immediately)
- `/transport/stop [timestamp]` - Stop transport at time (or immediately)
- `/transport/locate <frame>` - Locate to frame immediately
- `/transport/locate_start <frame> <timestamp>` - Locate then start at time
- `/transport/query` - Request current state

### Coordinator Commands (received by coordinator from agents)

- `/transport/state <state> <frame> <timestamp>` - Agent state report

## Setup

### Requirements

```bash
pip install JACK-Client python-osc PySide6
```

### Time Synchronization (Recommended)

For best results, synchronize system clocks across all machines:

**Option 1: PTP (Best precision)**

```bash
sudo apt-get install linuxptp

# On grandmaster (director machine):
sudo ptp4l -i enp3s0 -m

# On all machines:
sudo phc2sys -s /dev/ptp0 -c CLOCK_REALTIME -O 0 -m
```

**Option 2: NTP (Simpler)**

```bash
sudo apt-get install chrony

# Edit /etc/chrony/chrony.conf to point to local NTP server
# Restart: sudo systemctl restart chrony
```

### JACK Setup

Each machine should have JACK running:

```bash
# Example: start JACK with 128 frame buffer at 48kHz
jackd -d alsa -r 48000 -p 128 -n 2
```

Or use QjackCtl, Cadence, or your preferred JACK launcher.

## Usage

### Basic Standalone Example

**On each musician machine:**

```bash
python examples/launch_transport_agent.py musician1 5555
```

**On director machine:**

```bash
python examples/launch_transport_coordinator.py director 192.168.1.101 192.168.1.102
```

Then use the coordinator GUI to:
1. Set pre-roll time (default: 3 seconds)
2. Set start frame (usually 0)
3. Click "Locate & Start" to begin synchronized recording

### Integration with Main App

```python
from skeleton_app.audio.transport_services import (
    TransportAgentService,
    TransportCoordinatorService
)

# On musician node:
agent = TransportAgentService(
    node_id="musician1",
    jack_client_name="transport_agent",
    osc_port=5555
)
agent.start()

# On director node:
coordinator = TransportCoordinatorService(
    node_id="director",
    listen_port=5556
)
coordinator.add_agent("192.168.1.101", port=5555, name="musician1")
coordinator.add_agent("192.168.1.102", port=5555, name="musician2")

# Coordinate transport:
coordinator.locate_and_start_all(frame=0, pre_roll_seconds=3.0)
```

### Integration with Service Discovery

```python
from skeleton_app.service_discovery import ServiceDiscovery, ServiceType

# Register agent service
service_info = agent.get_service_info()
await discovery.register_service(service_info)

# Coordinator can discover agents automatically:
agents = await discovery.find_services(
    service_type=ServiceType.JACK_TRANSPORT_AGENT,
    status="available"
)

for agent_service in agents:
    coordinator.add_agent_from_service_info(agent_service)
```

### Integration with Node Canvas

The transport services can be represented as nodes in your visual graph:

```python
from skeleton_app.gui.widgets.transport_nodes import (
    TransportAgentNodeWidget,
    TransportCoordinatorNodeWidget
)

# Create node widget for agent
agent_widget = TransportAgentNodeWidget(agent_service)

# Create node widget for coordinator
coordinator_widget = TransportCoordinatorNodeWidget(coordinator_service)

# Add to your canvas as custom nodes
# The widgets provide status indicators and controls
```

## Workflow: Distributed Recording Session

### 1. Setup Phase

Each musician's machine:
- JACK running
- xjadeo configured with video file
- DAW/recorder armed and set to follow JACK transport
- Transport agent running

Director's machine:
- Transport coordinator running
- All musician hosts registered as agents

### 2. Recording Take

1. Director sets frame to 0 (or desired start point)
2. Director sets pre-roll (e.g., 3 seconds)
3. Director clicks "Locate & Start"
4. Coordinator sends `/transport/locate_start 0 <T>` to all agents
5. All agents:
   - Wait until system time reaches T
   - Locate JACK transport to frame 0
   - Start JACK transport
6. All xjadeo instances show synchronized video
7. All DAWs/recorders capture audio in sync

### 3. Post-Production

Each musician's machine exports recorded tracks. In the master DAW:
- Import all stems
- Align by shared start point (frame 0)
- Minor drift correction if needed (rare with PTP)

## Advanced Features

### Shared Parameters

You can extend the system to synchronize other parameters beyond transport:

```python
# In your parameter node:
class ParameterBroadcaster:
    def set_parameter(self, namespace, name, value):
        # Send to all registered nodes
        for agent in agents:
            osc_client.send_message(
                f"/param/{namespace}/{name}",
                [value]
            )
```

### xjadeo Integration

Extend `XjadeoManager` to respond to transport commands:

```python
from skeleton_app.audio.xjadeo_manager import XjadeoManager

# Launch xjadeo in JACK sync mode
xjadeo = XjadeoManager()
xjadeo.launch(
    video_file,
    sync_to_jack=True,
    fullscreen=False
)

# xjadeo automatically follows JACK transport
# When agents locate/start, xjadeo updates accordingly
```

### Network Audio (JackTrip)

Combine with JackTrip for real-time audio monitoring:

```bash
# On hub machine:
jacktrip -s

# On each musician machine:
jacktrip -c <hub_ip>
```

Musicians hear each other in real-time while recording synchronized to the video timeline.

## Timing Accuracy

With proper setup:
- **PTP**: Sub-millisecond synchronization (< 0.1ms typical on wired LAN)
- **NTP**: 1-5ms synchronization (adequate for recording alignment)
- **No sync**: 10-100ms drift (still usable for post-production alignment)

The transport commands include timing error logging:
```
Transport STARTED at 1703000000.123456 (target: 1703000000.123400, error: 0.56ms)
```

## Troubleshooting

### Agents not responding

1. Check firewall (allow UDP port 5555):
   ```bash
   sudo ufw allow 5555/udp
   ```

2. Verify network connectivity:
   ```bash
   ping <agent_host>
   ```

3. Check JACK is running:
   ```bash
   jack_lsp
   ```

### Timing drift

1. Verify time sync:
   ```bash
   # PTP:
   pmc -u -b 0 'GET TIME_STATUS_NP'
   
   # NTP:
   chronyc tracking
   ```

2. Check for different sample rates across machines

3. Consider hardware clock sync if sample-accurate alignment needed

### OSC messages not received

1. Check ports aren't in use:
   ```bash
   sudo netstat -ulnp | grep 5555
   ```

2. Test OSC manually:
   ```bash
   # Send test message with oscsend (from liblo-tools):
   oscsend <agent_host> 5555 /transport/query
   ```

## Future Enhancements

- Automatic agent discovery via mDNS/Zeroconf
- Master clock display showing sync quality
- Recording automation (arm all agents for recording)
- Take management (numbered takes, auto-naming)
- Distributed mixer control
- MIDI sync integration
- MTC/LTC timecode generation/sync

## License

Part of skeleton-app project. See main README for license information.
