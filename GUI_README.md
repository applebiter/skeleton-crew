# Skeleton GUI - Phase 1 Complete ✅

## What's Working

**Phase 1: Core Desktop App + JACK** is now implemented!

### Features

1. **PySide6 Desktop Application**
   - Modern Qt-based GUI
   - Main window with menu bar, toolbars, status bar
   - Tabbed interface for different views

2. **JACK Integration**
   - Connect/disconnect from JACK server
   - Real-time transport controls (play/pause/stop)
   - SMPTE timecode display (HH:MM:SS:FF)
   - Frame-accurate position tracking
   - Transport state monitoring

3. **Visual Patchbay**
   - View all JACK audio ports
   - See current connections
   - Connect/disconnect ports visually
   - Auto-refresh port list
   - Grouped by client application

4. **xjadeo Manager**
   - Launch JACK transport-synced video players
   - Support multiple simultaneous instances
   - Control window positioning and fullscreen
   - SMPTE timecode overlay
   - A/V offset adjustment

5. **Cluster Status Panel**
   - Monitor distributed nodes (placeholder for Phase 4)
   - Node health and load display
   - Expandable for future capabilities

## Running the GUI

### Prerequisites

Make sure JACK is running:
```bash
# If using jackd directly
jackd -d alsa -r 48000

# Or if using PipeWire-JACK (most modern systems)
# It's already running if you have PipeWire
```

### Launch

```bash
# From the skeleton-app directory
source .venv/bin/activate
skeleton-gui
```

Or directly:
```bash
python -m skeleton_app.gui.app
```

## Usage

### Transport Controls

- **Play/Pause**: Start/pause JACK transport (all synced apps will follow)
- **Stop**: Stop and return to frame 0
- **Position Slider**: Seek to specific frames
- **Timecode Display**: Shows current position in SMPTE format

### JACK Patchbay

1. **Connect Ports**:
   - Select an output port (left tree)
   - Select an input port (right tree)
   - Click "Connect Selected"

2. **Disconnect Ports**:
   - Select a connected output port
   - Click "Disconnect Selected" (disconnects all its connections)

3. **Refresh**: Click "Refresh" to update port lists

### xjadeo Video (Coming in Phase 1.5)

The xjadeo manager is implemented but not yet exposed in the GUI. Next steps:
- Add "Open Video" menu item
- Add video player controls tab
- Support multiple monitors

## What's Next

### Phase 2: MIDI/OSC Integration
- QmidiNet integration
- OSC server/client
- MIDI routing controls
- OSC command mapping

### Phase 3: Voice + Agent Layer
- Wake word detection
- STT pipeline (Vosk)
- Command bus (ZeroMQ)
- Natural language routing

### Phase 4: Distributed Session
- Multi-node transport sync
- Session save/load
- Remote audio/MIDI discovery
- JackTrip automation

### Phase 5: Media Library + Playout
- Video/audio database
- Playlist editor
- Channel scheduling
- HLS/Icecast streaming

## Architecture

```
skeleton-app/
├── gui/
│   ├── app.py                  # Main application entry
│   ├── main_window.py          # Main window
│   └── widgets/
│       ├── transport_panel.py  # Transport controls
│       ├── patchbay_widget.py  # Visual patchbay
│       └── cluster_panel.py    # Node status
│
├── audio/
│   ├── jack_client.py          # JACK client wrapper
│   └── xjadeo_manager.py       # Video player manager
│
└── [existing modules...]       # CLI, database, providers, etc.
```

## Known Issues

- Position slider maximum is set dynamically (needs video length info for proper scaling)
- Cluster panel shows placeholder data (will be implemented in Phase 4)
- No video controls in GUI yet (xjadeo manager is ready, needs UI)

## Testing Tips

1. **Test JACK Connection**:
   - Start JACK first (jackd or PipeWire)
   - Launch skeleton-gui
   - Should auto-connect and show ports

2. **Test Transport**:
   - Click Play
   - Watch timecode update
   - Click Stop
   - Should return to 00:00:00:00

3. **Test Patchbay**:
   - Start another JACK app (e.g., Ardour, QJackCtl)
   - See its ports appear
   - Try connecting them

## Film Scoring Workflow (Future)

Once complete, the workflow will be:

```
1. Load reference video in xjadeo (synced to JACK transport)
2. Play MIDI keyboard → routed to synth on remote node (QmidiNet)
3. Synth audio returns via JACK → mixed locally
4. Record to DAW (following JACK transport)
5. Export stems with accurate timecode
```

All controlled by voice commands and distributed across your 6-node cluster!
