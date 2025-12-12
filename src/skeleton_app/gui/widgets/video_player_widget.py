"""
Flexible video player widget with multiple display modes.
"""

import logging
from pathlib import Path
from typing import Optional, Literal

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, 
    QLabel, QStyle, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QEvent
from PySide6.QtMultimedia import QMediaPlayer

from skeleton_app.audio.qt_video_player import QtVideoPlayer

logger = logging.getLogger(__name__)

VideoMode = Literal["thumbnail", "embedded", "detached"]


class VideoPlayerWidget(QWidget):
    """
    Flexible video player with configurable display modes.
    
    Modes:
    - thumbnail: Small preview, no controls, plays on hover, click to promote
    - embedded: Full controls, embedded in panel, can detach
    - detached: Separate maximized window, fullscreen capable
    
    Configuration:
    - show_controls: Show playback controls
    - enable_audio: Enable audio output (default muted for JACK)
    - play_on_hover: Auto-play preview on mouse hover
    """
    
    # Signals
    detached = Signal(str)  # instance_id
    closed = Signal(str)  # instance_id
    clicked = Signal(str)  # instance_id (for thumbnail mode)
    
    def __init__(
        self, 
        player: QtVideoPlayer, 
        parent: Optional[QWidget] = None,
        mode: VideoMode = "embedded",
        show_controls: bool = True,
        enable_audio: bool = False,
        play_on_hover: bool = False
    ):
        super().__init__(parent)
        self.player = player
        self.mode = mode
        self.show_controls = show_controls
        self.enable_audio = enable_audio
        self.play_on_hover = play_on_hover
        self.is_detached = False
        self.detached_window: Optional[QWidget] = None
        self._was_playing_before_hover = False
        
        self._setup_ui()
        self._connect_signals()
        self._apply_mode_settings()
        
        # Update timer for position slider
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_position)
        self.update_timer.start(100)  # Update 10 times per second
        
        # Install event filter for hover if needed
        if self.play_on_hover:
            self.installEventFilter(self)
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Video display area
        self.video_widget = self.player.create_video_widget(self)
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.video_widget)
        
        # Control bar (in a container widget for visibility control)
        self.control_widget = QWidget()
        control_layout = QHBoxLayout(self.control_widget)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        # JACK Sync checkbox
        from PySide6.QtWidgets import QCheckBox
        self.jack_sync_checkbox = QCheckBox("JACK Sync")
        self.jack_sync_checkbox.setToolTip("Follow JACK transport (play/stop/seek)")
        self.jack_sync_checkbox.stateChanged.connect(self._on_jack_sync_toggled)
        control_layout.addWidget(self.jack_sync_checkbox)
        
        # Play/Pause button
        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_button.clicked.connect(self._toggle_play_pause)
        self.play_button.setMaximumWidth(40)
        control_layout.addWidget(self.play_button)
        
        # Stop button
        self.stop_button = QPushButton()
        self.stop_button.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.stop_button.clicked.connect(self._on_stop)
        self.stop_button.setMaximumWidth(40)
        control_layout.addWidget(self.stop_button)
        
        # Position slider
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self._on_slider_moved)
        control_layout.addWidget(self.position_slider)
        
        # Time labels
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setMinimumWidth(100)
        control_layout.addWidget(self.time_label)
        
        # Volume slider
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(0)  # Start at 0 since muted
        self.volume_slider.setMaximumWidth(100)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.setToolTip("Volume (muted by default)")
        control_layout.addWidget(self.volume_slider)
        
        # Mute button
        self.mute_button = QPushButton()
        self.mute_button.setIcon(self.style().standardIcon(QStyle.SP_MediaVolumeMuted))
        self.mute_button.clicked.connect(self._toggle_mute)
        self.mute_button.setMaximumWidth(40)
        self.mute_button.setToolTip("Audio muted (JACK handles audio)")
        control_layout.addWidget(self.mute_button)
        
        # Fullscreen button
        self.fullscreen_button = QPushButton("⛶")
        self.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        self.fullscreen_button.setMaximumWidth(40)
        self.fullscreen_button.setToolTip("Toggle fullscreen")
        control_layout.addWidget(self.fullscreen_button)
        
        # Detach button
        self.detach_button = QPushButton("Detach")
        self.detach_button.clicked.connect(self._toggle_detach)
        self.detach_button.setMaximumWidth(80)
        control_layout.addWidget(self.detach_button)
        
        # Close button
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self._on_close)
        self.close_button.setMaximumWidth(60)
        control_layout.addWidget(self.close_button)
        
        layout.addWidget(self.control_widget)
        
        # Info bar (in a container widget for visibility control)
        self.info_widget = QWidget()
        info_layout = QHBoxLayout(self.info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        # File name
        file_name = self.player.file_path.name if self.player.file_path else "No file"
        self.file_label = QLabel(f"<b>{file_name}</b>")
        info_layout.addWidget(self.file_label)
        
        info_layout.addStretch()
        
        # Sync status
        self.sync_label = QLabel("Sync: --")
        info_layout.addWidget(self.sync_label)
        
        layout.addWidget(self.info_widget)
    
    def _apply_mode_settings(self):
        """Apply settings based on current mode."""
        if self.mode == "thumbnail":
            # Thumbnail mode: minimal UI
            self.control_widget.setVisible(False)
            self.info_widget.setVisible(False)
            self.player.audio_output.setMuted(True)
            self.setCursor(Qt.PointingHandCursor)
            
            # Set size constraints for thumbnail
            self.setMaximumHeight(200)
            self.video_widget.setMaximumHeight(200)
            
        elif self.mode == "embedded":
            # Embedded mode: full controls
            self.control_widget.setVisible(self.show_controls)
            self.info_widget.setVisible(self.show_controls)
            self.player.audio_output.setMuted(not self.enable_audio)
            
        elif self.mode == "detached":
            # Detached mode: handled separately in detach window
            pass
        
        # Apply audio setting
        if not self.enable_audio:
            self.player.audio_output.setMuted(True)
    
    def _connect_signals(self):
        """Connect player signals."""
        self.player.position_changed.connect(self._on_position_changed)
        self.player.duration_changed.connect(self._on_duration_changed)
        self.player.state_changed.connect(self._on_state_changed)
        self.player.sync_stats_changed.connect(self._on_sync_stats_changed)
    
    def _on_jack_sync_toggled(self, state):
        """Handle JACK sync checkbox toggle."""
        from PySide6.QtCore import Qt
        enabled = (state == Qt.CheckState.Checked.value)
        self.player.set_sync_enabled(enabled)
        
        if enabled:
            logger.info(f"[{self.player.instance_id}] JACK sync enabled")
            # Disable local play/pause buttons when JACK controls
            self.play_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.position_slider.setEnabled(False)
        else:
            logger.info(f"[{self.player.instance_id}] JACK sync disabled")
            # Re-enable local controls
            self.play_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.position_slider.setEnabled(True)
    
    def eventFilter(self, obj, event):
        """Handle hover events for thumbnail mode."""
        if self.mode == "thumbnail" and self.play_on_hover:
            if event.type() == QEvent.Enter:
                # Mouse entered - start playing preview
                self._was_playing_before_hover = (
                    self.player.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
                )
                if not self._was_playing_before_hover:
                    self.player.play()
                    logger.debug(f"[{self.player.instance_id}] Started hover preview")
                    
            elif event.type() == QEvent.Leave:
                # Mouse left - pause if we started it
                if not self._was_playing_before_hover:
                    self.player.pause()
                    logger.debug(f"[{self.player.instance_id}] Stopped hover preview")
        
        return super().eventFilter(obj, event)
    
    def mousePressEvent(self, event):
        """Handle mouse click in thumbnail mode."""
        if self.mode == "thumbnail" and event.button() == Qt.LeftButton:
            self.clicked.emit(self.player.instance_id)
            logger.info(f"[{self.player.instance_id}] Thumbnail clicked")
        super().mousePressEvent(event)
    
    def _toggle_play_pause(self):
        """Toggle play/pause."""
        if self.player.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
    
    def _on_stop(self):
        """Stop playback."""
        self.player.stop()
    
    def _on_volume_changed(self, value: int):
        """Handle volume slider change."""
        volume = value / 100.0
        self.player.audio_output.setVolume(volume)
        
        # Auto-unmute if volume raised above 0
        if value > 0 and self.player.audio_output.isMuted():
            self.player.audio_output.setMuted(False)
            self.mute_button.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))
    
    def _toggle_mute(self):
        """Toggle mute state."""
        is_muted = self.player.audio_output.isMuted()
        self.player.audio_output.setMuted(not is_muted)
        
        if is_muted:
            self.mute_button.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))
            self.mute_button.setToolTip("Audio enabled (not recommended with JACK)")
            # Set volume slider to a reasonable level if it was 0
            if self.volume_slider.value() == 0:
                self.volume_slider.setValue(50)
        else:
            self.mute_button.setIcon(self.style().standardIcon(QStyle.SP_MediaVolumeMuted))
            self.mute_button.setToolTip("Audio muted (JACK handles audio)")
    
    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.is_detached and self.detached_window:
            # Toggle fullscreen on detached window
            if self.detached_window.isFullScreen():
                self.detached_window.showNormal()
                self.fullscreen_button.setText("⛶")
            else:
                self.detached_window.showFullScreen()
                self.fullscreen_button.setText("⛉")
        else:
            # Create detached window in fullscreen
            self._toggle_detach()
            if self.detached_window:
                self.detached_window.showFullScreen()
                self.fullscreen_button.setText("⛉")
    
    def _toggle_detach(self):
        """Toggle detached window."""
        if self.is_detached:
            # Re-attach
            if self.detached_window:
                # Exit fullscreen first if needed
                if self.detached_window.isFullScreen():
                    self.detached_window.showNormal()
                    self.fullscreen_button.setText("⛶")
                
                # Move video widget back to this widget
                self.video_widget.setParent(self)
                self.layout().insertWidget(0, self.video_widget)
                self.detached_window.close()
                self.detached_window = None
            
            self.is_detached = False
            self.detach_button.setText("Detach")
        else:
            # Detach
            from PySide6.QtWidgets import QDialog
            from PySide6.QtCore import Qt
            
            self.detached_window = QDialog(self)
            file_name = self.player.file_path.name if self.player.file_path else "Video"
            self.detached_window.setWindowTitle(f"{file_name} - {self.player.instance_id}")
            
            # Set reasonable default size (can be resized by user)
            self.detached_window.resize(1280, 720)
            
            # Allow fullscreen, maximize, minimize
            self.detached_window.setWindowFlags(
                Qt.Window | 
                Qt.WindowMaximizeButtonHint | 
                Qt.WindowMinimizeButtonHint | 
                Qt.WindowCloseButtonHint
            )
            
            layout = QVBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            
            # Move video widget to detached window
            self.video_widget.setParent(self.detached_window)
            layout.addWidget(self.video_widget)
            
            self.detached_window.setLayout(layout)
            self.detached_window.show()
            
            self.is_detached = True
            self.detach_button.setText("Attach")
            
            # Connect window close to re-attach
            self.detached_window.finished.connect(self._on_detached_closed)
            
            # Add keyboard shortcut for fullscreen (F11)
            from PySide6.QtGui import QShortcut, QKeySequence
            fullscreen_shortcut = QShortcut(QKeySequence(Qt.Key_F11), self.detached_window)
            fullscreen_shortcut.activated.connect(self._toggle_fullscreen)
    
    def _on_detached_closed(self):
        """Handle detached window close."""
        if self.is_detached:
            # Reset fullscreen button
            self.fullscreen_button.setText("⛶")
            
            # Re-attach video widget
            self.video_widget.setParent(self)
            self.layout().insertWidget(0, self.video_widget)
            self.detached_window = None
            self.is_detached = False
            self.detach_button.setText("Detach")
    
    def _on_close(self):
        """Close this video player."""
        self.closed.emit(self.player.instance_id)
    
    def _on_slider_moved(self, position: int):
        """Handle slider movement."""
        self.player.seek(position)
    
    def _update_position(self):
        """Update position slider from player."""
        try:
            if not self.player or not self.player.player:
                return
            
            if self.player.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                position = self.player.get_position_ms()
                
                # Don't update if user is dragging
                if not self.position_slider.isSliderDown():
                    self.position_slider.setValue(position)
        except RuntimeError:
            # Player was deleted, stop timer
            self.update_timer.stop()
    
    @Slot(int)
    def _on_position_changed(self, position_ms: int):
        """Handle position change from player."""
        # Update time label
        duration_ms = self.player.get_duration_ms()
        
        position_str = self._format_time(position_ms)
        duration_str = self._format_time(duration_ms)
        
        self.time_label.setText(f"{position_str} / {duration_str}")
    
    @Slot(int)
    def _on_duration_changed(self, duration_ms: int):
        """Handle duration change."""
        self.position_slider.setRange(0, duration_ms)
    
    @Slot(str)
    def _on_state_changed(self, state: str):
        """Handle state change."""
        if state == "playing":
            self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        else:
            self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
    
    @Slot(object)
    def _on_sync_stats_changed(self, stats):
        """Handle sync stats update."""
        # Update sync label with color coding
        sync_text = f"Sync: {stats.state.value} ({stats.drift_ms:.1f}ms)"
        
        if stats.state.value == "synced":
            color = "green"
        elif stats.state.value in ["syncing", "drift"]:
            color = "orange"
        else:
            color = "red"
        
        self.sync_label.setText(f'<span style="color: {color};">{sync_text}</span>')
    
    def _format_time(self, ms: int) -> str:
        """Format milliseconds as MM:SS."""
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
    
    def set_mode(self, mode: VideoMode):
        """Change the display mode dynamically."""
        self.mode = mode
        self._apply_mode_settings()
        
        if mode == "thumbnail" and self.play_on_hover:
            self.installEventFilter(self)
        else:
            self.removeEventFilter(self)
    
    def cleanup(self):
        """Cleanup resources."""
        # Stop timer first
        if self.update_timer:
            self.update_timer.stop()
            self.update_timer.deleteLater()
            self.update_timer = None
        
        # Close detached window
        if self.detached_window:
            self.detached_window.close()
            self.detached_window = None
        
        # Clear player reference
        self.player = None
