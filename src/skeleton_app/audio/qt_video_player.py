"""
Qt Multimedia video player with JACK transport sync and circular buffer.

Provides frame-accurate video playback synchronized to JACK transport.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Callable
from collections import deque
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot, Qt
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from skeleton_app.audio.jack_client import JackClientManager

logger = logging.getLogger(__name__)


class SyncState(Enum):
    """Video sync state."""
    SYNCED = "synced"
    SYNCING = "syncing"
    DRIFT = "drift"
    LOST = "lost"


@dataclass
class SyncStats:
    """Statistics about sync quality."""
    drift_ms: float = 0.0
    max_drift_ms: float = 0.0
    corrections: int = 0
    dropped_frames: int = 0
    buffer_size: int = 0
    state: SyncState = SyncState.SYNCED


class CircularSyncBuffer:
    """
    Circular buffer for smooth video/audio sync.
    
    Maintains a small buffer of timing corrections to smooth out
    jitter and provide predictable playback.
    """
    
    def __init__(self, size: int = 10):
        self.buffer: deque = deque(maxlen=size)
        self.size = size
    
    def add(self, value: float):
        """Add a timing value to the buffer."""
        self.buffer.append(value)
    
    def average(self) -> float:
        """Get average of buffer values."""
        if not self.buffer:
            return 0.0
        return sum(self.buffer) / len(self.buffer)
    
    def median(self) -> float:
        """Get median of buffer values."""
        if not self.buffer:
            return 0.0
        sorted_values = sorted(self.buffer)
        mid = len(sorted_values) // 2
        if len(sorted_values) % 2 == 0:
            return (sorted_values[mid - 1] + sorted_values[mid]) / 2
        return sorted_values[mid]
    
    def is_stable(self, threshold: float = 10.0) -> bool:
        """Check if buffer values are stable (low variance)."""
        if len(self.buffer) < self.size // 2:
            return False
        
        avg = self.average()
        variance = sum((x - avg) ** 2 for x in self.buffer) / len(self.buffer)
        return variance < threshold
    
    def clear(self):
        """Clear the buffer."""
        self.buffer.clear()


class QtVideoPlayer(QObject):
    """
    Qt Multimedia video player with JACK transport sync.
    
    Features:
    - Frame-accurate JACK transport sync
    - Circular buffer for smooth playback
    - Drift compensation
    - Multiple instances support
    - Embeddable or standalone window
    """
    
    # Signals
    position_changed = Signal(int)  # Position in ms
    duration_changed = Signal(int)  # Duration in ms
    state_changed = Signal(str)  # Playing/paused/stopped
    sync_stats_changed = Signal(SyncStats)
    error_occurred = Signal(str)
    
    def __init__(
        self,
        instance_id: str,
        jack_manager: Optional[JackClientManager] = None,
        sync_interval_ms: int = 50,
        drift_threshold_ms: float = 40.0,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        
        self.instance_id = instance_id
        self.jack_manager = jack_manager
        self.sync_interval_ms = sync_interval_ms
        self.drift_threshold_ms = drift_threshold_ms
        
        # Media player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # Video widget
        self.video_widget: Optional[QVideoWidget] = None
        
        # Sync state
        self.sync_enabled = True
        self.last_jack_frame = 0
        self.last_video_position = 0
        self.sync_buffer = CircularSyncBuffer(size=10)
        self.sync_stats = SyncStats()
        
        # Sync timer
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self._sync_to_jack)
        
        # Connect player signals
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.errorOccurred.connect(self._on_error)
        
        # File info
        self.file_path: Optional[Path] = None
        self.duration_ms = 0
        self.fps = 30.0  # Default, will be detected
        
        logger.info(f"QtVideoPlayer created: {instance_id}")
    
    def create_video_widget(self, parent: Optional[QWidget] = None) -> QVideoWidget:
        """
        Create and return a video widget for display.
        
        Args:
            parent: Parent widget
        
        Returns:
            QVideoWidget that can be embedded or shown standalone
        """
        if not self.video_widget:
            self.video_widget = QVideoWidget(parent)
            self.player.setVideoOutput(self.video_widget)
            self.video_widget.setMinimumSize(640, 360)
        
        return self.video_widget
    
    def load(self, file_path: Path) -> bool:
        """
        Load a video file.
        
        Args:
            file_path: Path to video file
        
        Returns:
            True if loaded successfully
        """
        try:
            self.file_path = file_path
            url = QUrl.fromLocalFile(str(file_path.absolute()))
            self.player.setSource(url)
            
            logger.info(f"[{self.instance_id}] Loaded: {file_path.name}")
            return True
        
        except Exception as e:
            logger.error(f"[{self.instance_id}] Failed to load video: {e}")
            self.error_occurred.emit(str(e))
            return False
    
    def play(self):
        """Start playback."""
        self.player.play()
        if self.sync_enabled and not self.sync_timer.isActive():
            self.sync_timer.start(self.sync_interval_ms)
    
    def pause(self):
        """Pause playback."""
        self.player.pause()
        if self.sync_timer.isActive():
            self.sync_timer.stop()
    
    def stop(self):
        """Stop playback."""
        self.player.stop()
        if self.sync_timer.isActive():
            self.sync_timer.stop()
        self.sync_buffer.clear()
        self.sync_stats = SyncStats()
    
    def seek(self, position_ms: int):
        """
        Seek to position.
        
        Args:
            position_ms: Position in milliseconds
        """
        self.player.setPosition(position_ms)
    
    def set_jack_manager(self, jack_manager: Optional[JackClientManager]):
        """Set or update JACK manager."""
        self.jack_manager = jack_manager
        if jack_manager:
            logger.info(f"[{self.instance_id}] JACK sync enabled")
        else:
            logger.info(f"[{self.instance_id}] JACK sync disabled")
    
    def set_sync_enabled(self, enabled: bool):
        """Enable or disable JACK sync."""
        self.sync_enabled = enabled
        
        if not enabled and self.sync_timer.isActive():
            self.sync_timer.stop()
        elif enabled and self.player.playbackState() == QMediaPlayer.PlayingState:
            self.sync_timer.start(self.sync_interval_ms)
    
    def get_sync_stats(self) -> SyncStats:
        """Get current sync statistics."""
        return self.sync_stats
    
    def get_position_ms(self) -> int:
        """Get current playback position in milliseconds."""
        return self.player.position()
    
    def get_duration_ms(self) -> int:
        """Get video duration in milliseconds."""
        return self.duration_ms
    
    @Slot(int)
    def _on_position_changed(self, position_ms: int):
        """Handle position change from player."""
        self.last_video_position = position_ms
        self.position_changed.emit(position_ms)
    
    @Slot(int)
    def _on_duration_changed(self, duration_ms: int):
        """Handle duration change."""
        self.duration_ms = duration_ms
        self.duration_changed.emit(duration_ms)
        logger.info(f"[{self.instance_id}] Duration: {duration_ms/1000:.2f}s")
    
    @Slot()
    def _on_state_changed(self):
        """Handle playback state change."""
        state = self.player.playbackState()
        
        if state == QMediaPlayer.PlaybackState.PlayingState:
            state_str = "playing"
            if self.sync_enabled:
                self.sync_timer.start(self.sync_interval_ms)
        elif state == QMediaPlayer.PlaybackState.PausedState:
            state_str = "paused"
            self.sync_timer.stop()
        else:
            state_str = "stopped"
            self.sync_timer.stop()
        
        self.state_changed.emit(state_str)
        logger.debug(f"[{self.instance_id}] State: {state_str}")
    
    @Slot()
    def _on_error(self, error, error_string):
        """Handle player error."""
        logger.error(f"[{self.instance_id}] Player error: {error_string}")
        self.error_occurred.emit(error_string)
    
    def _sync_to_jack(self):
        """Synchronize video position to JACK transport."""
        if not self.jack_manager or not self.jack_manager.is_connected():
            self.sync_stats.state = SyncState.LOST
            return
        
        # Get JACK transport state
        jack_state = self.jack_manager.get_transport_state()
        
        # If JACK is stopped, pause video
        if jack_state == "Stopped":
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.pause()
            return
        
        # If JACK is playing, ensure video is playing
        if jack_state == "Rolling":
            if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.play()
        
        # Get JACK frame position
        jack_frame = self.jack_manager.get_frame()
        
        # Convert JACK frame to milliseconds (assuming 48kHz sample rate)
        sample_rate = 48000  # TODO: Get actual sample rate from JACK
        jack_position_ms = int((jack_frame / sample_rate) * 1000)
        
        # Get current video position
        video_position_ms = self.player.position()
        
        # Calculate drift
        drift_ms = jack_position_ms - video_position_ms
        self.sync_stats.drift_ms = drift_ms
        
        # Update max drift
        if abs(drift_ms) > abs(self.sync_stats.max_drift_ms):
            self.sync_stats.max_drift_ms = drift_ms
        
        # Add to circular buffer
        self.sync_buffer.add(drift_ms)
        self.sync_stats.buffer_size = len(self.sync_buffer.buffer)
        
        # Determine sync state
        if abs(drift_ms) > self.drift_threshold_ms * 2:
            self.sync_stats.state = SyncState.LOST
        elif abs(drift_ms) > self.drift_threshold_ms:
            self.sync_stats.state = SyncState.DRIFT
        elif self.sync_buffer.is_stable(threshold=5.0):
            self.sync_stats.state = SyncState.SYNCED
        else:
            self.sync_stats.state = SyncState.SYNCING
        
        # Apply correction if needed
        if abs(drift_ms) > self.drift_threshold_ms:
            # Use buffered average for smooth correction
            correction_ms = self.sync_buffer.median()
            
            # Seek to corrected position
            corrected_position = video_position_ms + int(correction_ms)
            corrected_position = max(0, min(corrected_position, self.duration_ms))
            
            self.player.setPosition(corrected_position)
            self.sync_stats.corrections += 1
            
            logger.debug(
                f"[{self.instance_id}] Sync correction: drift={drift_ms:.1f}ms, "
                f"correction={correction_ms:.1f}ms"
            )
        
        # Emit stats periodically
        self.sync_stats_changed.emit(self.sync_stats)
    
    def cleanup(self):
        """Clean up resources."""
        self.stop()
        if self.sync_timer.isActive():
            self.sync_timer.stop()
        
        if self.video_widget:
            self.video_widget.deleteLater()
            self.video_widget = None
        
        self.player.setVideoOutput(None)
        self.player.deleteLater()
        self.audio_output.deleteLater()


class QtVideoPlayerManager:
    """
    Manages multiple Qt video player instances.
    
    Similar to XjadeoManager but using Qt Multimedia.
    """
    
    def __init__(self, jack_manager: Optional[JackClientManager] = None):
        self.jack_manager = jack_manager
        self.players: Dict[str, QtVideoPlayer] = {}
        self.next_id = 1
    
    def create_player(
        self,
        file_path: Optional[Path] = None,
        instance_id: Optional[str] = None,
        sync_enabled: bool = True
    ) -> tuple[str, QtVideoPlayer]:
        """
        Create a new video player instance.
        
        Args:
            file_path: Optional video file to load
            instance_id: Optional custom instance ID
            sync_enabled: Enable JACK sync
        
        Returns:
            (instance_id, player) tuple
        """
        if not instance_id:
            instance_id = f"video_{self.next_id}"
            self.next_id += 1
        
        player = QtVideoPlayer(
            instance_id=instance_id,
            jack_manager=self.jack_manager
        )
        
        player.set_sync_enabled(sync_enabled)
        
        if file_path:
            player.load(file_path)
        
        self.players[instance_id] = player
        
        logger.info(f"Created video player: {instance_id}")
        return instance_id, player
    
    def get_player(self, instance_id: str) -> Optional[QtVideoPlayer]:
        """Get player by instance ID."""
        return self.players.get(instance_id)
    
    def remove_player(self, instance_id: str):
        """Remove and cleanup a player instance."""
        player = self.players.pop(instance_id, None)
        if player:
            player.cleanup()
            logger.info(f"Removed video player: {instance_id}")
    
    def get_all_players(self) -> Dict[str, QtVideoPlayer]:
        """Get all player instances."""
        return self.players.copy()
    
    def set_jack_manager(self, jack_manager: Optional[JackClientManager]):
        """Update JACK manager for all players."""
        self.jack_manager = jack_manager
        for player in self.players.values():
            player.set_jack_manager(jack_manager)
    
    def cleanup_all(self):
        """Cleanup all players."""
        for instance_id in list(self.players.keys()):
            self.remove_player(instance_id)
