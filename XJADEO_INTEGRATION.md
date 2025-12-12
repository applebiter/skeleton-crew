# xjadeo Integration Guide

## Overview

Skeleton Crew now includes full xjadeo integration for JACK transport-synced video playback. This enables film scoring and composition workflows where video, audio, MIDI, and OSC all follow the same timeline.

## Features

### Video Panel

The Video Players panel (right dock) provides:

- **Open Video**: Load video files (MP4, AVI, MOV, MKV, WebM, OGV)
- **Instance List**: Shows all active xjadeo instances
- **Multi-Instance Support**: Open multiple videos simultaneously for multi-monitor setups
- **Controls**: Stop Selected, Stop All, Refresh
- **Auto-Refresh**: Updates every 2 seconds

### Menu Integration

**File Menu**:
- `File → Open Video... (Ctrl+O)`: Quick access to open video files

**View Menu**:
- `View → Video Players`: Toggle video panel visibility

### JACK Transport Sync

All xjadeo instances automatically sync to JACK transport:
- **Play/Pause**: Transport controls affect all video players
- **Seek**: Position slider moves all videos to the same frame
- **Timecode**: SMPTE display shows current position
- **Frame-Accurate**: Videos stay in perfect sync with audio

## Workflow Example: Film Scoring

1. **Load Reference Video**:
   - Click `File → Open Video...` or use the Video Panel
   - Select your film/scene file
   - xjadeo window opens and syncs to JACK transport

2. **Multi-Monitor Setup**:
   - Open same video on multiple monitors (one instance per screen)
   - Open different angles/versions for comparison
   - All instances follow the same timeline automatically

3. **Compose with Timeline Sync**:
   - Start JACK transport (Play button)
   - All audio, MIDI, and video follow same timeline
   - Record audio/MIDI in sync with video
   - Seek to any position - everything stays in sync

4. **Advanced: Video Sources**:
   - Use v4l2loopback to pipe video files to virtual devices
   - Mix live webcam with pre-recorded files
   - Route video through effects/processing
   - All sources available to xjadeo

## xjadeo Features

Each xjadeo instance includes:
- **OSD (On-Screen Display)**: Shows current frame/time
- **Timecode Display**: SMPTE overlay
- **Fullscreen Mode**: Optional (configured per instance)
- **Window Positioning**: Custom placement per instance
- **Offset Control**: Frame offset for sync adjustment (future)

## Technical Details

### XjadeoManager API

```python
from skeleton_app.audio.xjadeo_manager import XjadeoManager

xjadeo = XjadeoManager()

# Launch instance
instance_id = xjadeo.launch(
    file_path=Path("my_film.mp4"),
    instance_id="video_1",
    sync_to_jack=True,
    show_osd=True,
    show_timecode=True,
    fullscreen=False,
    window_position="1920,0",  # x,y for second monitor
    window_size="1920x1080",
    offset_ms=0
)

# Control instances
xjadeo.stop(instance_id)
xjadeo.stop_all()
is_running = xjadeo.is_running(instance_id)
instances = xjadeo.get_instances()
info = xjadeo.get_instance_info(instance_id)
```

### VideoPanel Signals

The VideoPanel emits signals for integration:

```python
video_panel.video_opened.connect(on_video_opened)  # (instance_id, file_path)
video_panel.video_closed.connect(on_video_closed)  # (instance_id)
```

## Future Enhancements

### Phase 2 (Upcoming)

- **Video Source Nodes**: Show xjadeo instances in node canvas
- **v4l2loopback Integration**: Manage virtual video devices
- **Webcam Sources**: Direct camera feed nodes
- **Video Routing**: Connect sources to players visually
- **Frame Offset Controls**: Fine-tune sync per instance

### Phase 3

- **Voice Commands**: "Open video ~/films/scene1.mp4"
- **Playlist Integration**: Queue multiple videos for scoring sessions
- **Session Save/Load**: Restore video player configurations

### Phase 4

- **Remote Video**: Video players on other cluster nodes
- **Synchronized Playback**: Multi-node video sync via network
- **Distributed Rendering**: Video processing across cluster

## Troubleshooting

### xjadeo Not Found

If you see "xjadeo not found in PATH":

```bash
# Debian/Ubuntu
sudo apt install xjadeo

# Arch
yay -S xjadeo

# From source
git clone https://github.com/x42/xjadeo.git
cd xjadeo
./configure && make && sudo make install
```

### Video Won't Open

Check video codec compatibility:
```bash
xjadeo --help
```

xjadeo supports most common formats, but some codecs may require additional libraries.

### Sync Issues

If video/audio drift:
1. Check JACK buffer size (`jack_control dps period` or in QJackCtl)
2. Use lower buffer for tighter sync (64 or 128 frames)
3. Adjust xjadeo frame offset if needed

### Multiple Instances

For multi-monitor setups:
- Use `window_position` parameter to place on specific screen
- Example: `"1920,0"` for second monitor (1920px to the right)
- Each monitor can have its own instance

## Integration with Other Tools

### Carla

xjadeo instances appear in JACK graph but don't route audio (video-only). You'll see them listed in Carla's patchbay.

### Ardour/Reaper

These DAWs have their own JACK transport controls. Skeleton Crew's transport panel and their transport work together - starting one starts both.

### OBS Studio

Can capture xjadeo windows for streaming/recording film scoring sessions.

### v4l2loopback

Pipe any video file to a virtual camera device:
```bash
# Create virtual device
sudo modprobe v4l2loopback devices=1

# Stream file to /dev/video2
ffmpeg -re -i my_video.mp4 -f v4l2 /dev/video2

# Point xjadeo at /dev/video2
# Or use direct file path - xjadeo handles both
```

## Architecture Notes

The xjadeo integration follows Skeleton Crew's extensible design:

- **XjadeoManager**: Backend process management (audio module)
- **VideoPanel**: GUI controls (widgets module)
- **MainWindow**: Menu integration and lifecycle
- **Future: VideoNode**: Canvas representation (Phase 2)

This architecture allows:
- Multiple backend implementations (xjadeo, VLC, mpv, etc.)
- Custom video node types in canvas
- Distributed video playback across cluster
- Integration with other media types (audio, MIDI, OSC)

## Related Documentation

- [GUI_README.md](./GUI_README.md) - Main GUI documentation
- [PLAN.md](./PLAN.md) - Overall system architecture
- xjadeo manual: `man xjadeo` or https://xjadeo.git.sourceforge.net/

---

**Your crew of nodes working together for film scoring and composition!** 🎬🎵
