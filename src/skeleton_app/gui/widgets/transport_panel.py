"""
JACK transport control panel widget.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QSlider, QLCDNumber, QFrame
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

from skeleton_app.audio.jack_client import JackClientManager


class TransportPanel(QWidget):
    """
    JACK transport control panel.
    
    Provides:
    - Play/pause/stop buttons
    - Timecode display (SMPTE)
    - Frame position slider
    - Transport state indicator
    """
    
    # Signals
    play_clicked = Signal()
    stop_clicked = Signal()
    locate_requested = Signal(int)  # frame number
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.jack_manager: Optional[JackClientManager] = None
        
        self._setup_ui()
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_display)
        self.update_timer.start(50)  # Update every 50ms for smooth display
        
        # Track if we're dragging the slider
        self._slider_dragging = False
    
    def _setup_ui(self):
        """Setup the UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Transport controls
        controls_layout = QHBoxLayout()
        
        self.play_button = QPushButton("▶ Play")
        self.play_button.setMinimumWidth(80)
        self.play_button.clicked.connect(self._on_play_clicked)
        self.play_button.setEnabled(False)
        controls_layout.addWidget(self.play_button)
        
        self.stop_button = QPushButton("⏹ Stop")
        self.stop_button.setMinimumWidth(80)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.stop_button.setEnabled(False)
        controls_layout.addWidget(self.stop_button)
        
        layout.addLayout(controls_layout)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Timecode display
        timecode_layout = QVBoxLayout()
        timecode_layout.setSpacing(2)
        
        timecode_label = QLabel("Timecode:")
        timecode_label.setAlignment(Qt.AlignCenter)
        timecode_layout.addWidget(timecode_label)
        
        self.timecode_display = QLabel("00:00:00:00")
        font = QFont("Monospace", 16, QFont.Bold)
        self.timecode_display.setFont(font)
        self.timecode_display.setAlignment(Qt.AlignCenter)
        self.timecode_display.setMinimumWidth(150)
        self.timecode_display.setStyleSheet("""
            QLabel {
                background-color: #000;
                color: #0f0;
                padding: 5px;
                border: 1px solid #333;
                border-radius: 3px;
            }
        """)
        timecode_layout.addWidget(self.timecode_display)
        
        layout.addLayout(timecode_layout)
        
        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.VLine)
        separator2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator2)
        
        # Frame position
        position_layout = QVBoxLayout()
        position_layout.setSpacing(2)
        
        frame_label = QLabel("Frame:")
        frame_label.setAlignment(Qt.AlignCenter)
        position_layout.addWidget(frame_label)
        
        self.frame_display = QLabel("0")
        frame_font = QFont("Monospace", 12)
        self.frame_display.setFont(frame_font)
        self.frame_display.setAlignment(Qt.AlignCenter)
        position_layout.addWidget(self.frame_display)
        
        layout.addLayout(position_layout)
        
        # Position slider (for seeking)
        slider_layout = QVBoxLayout()
        slider_layout.setSpacing(2)
        
        slider_label = QLabel("Position:")
        slider_label.setAlignment(Qt.AlignCenter)
        slider_layout.addWidget(slider_label)
        
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setMinimum(0)
        self.position_slider.setMaximum(0)
        self.position_slider.setValue(0)
        self.position_slider.setEnabled(False)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.sliderMoved.connect(self._on_slider_moved)
        self.position_slider.setMinimumWidth(300)
        slider_layout.addWidget(self.position_slider)
        
        layout.addLayout(slider_layout)
        
        # Stretch to push everything left
        layout.addStretch()
    
    def set_jack_manager(self, jack_manager: Optional[JackClientManager]):
        """
        Set the JACK client manager.
        
        Args:
            jack_manager: JACK client manager instance
        """
        self.jack_manager = jack_manager
        
        # Enable/disable controls
        enabled = jack_manager is not None and jack_manager.is_connected()
        self.play_button.setEnabled(enabled)
        self.stop_button.setEnabled(enabled)
        self.position_slider.setEnabled(enabled)
        
        if not enabled:
            self.timecode_display.setText("00:00:00:00")
            self.frame_display.setText("0")
            self.position_slider.setValue(0)
    
    def _on_play_clicked(self):
        """Handle play button click."""
        if self.jack_manager:
            state = self.jack_manager.get_transport_state()
            if state == "Stopped":
                self.jack_manager.transport_start()
                self.play_button.setText("⏸ Pause")
            elif state == "Rolling":
                self.jack_manager.transport_stop()
                self.play_button.setText("▶ Play")
        
        self.play_clicked.emit()
    
    def _on_stop_clicked(self):
        """Handle stop button click."""
        if self.jack_manager:
            self.jack_manager.transport_stop()
            self.jack_manager.transport_locate(0)
            self.play_button.setText("▶ Play")
        
        self.stop_clicked.emit()
    
    def _on_slider_pressed(self):
        """Handle slider press."""
        self._slider_dragging = True
    
    def _on_slider_released(self):
        """Handle slider release."""
        self._slider_dragging = False
        
        # Seek to the slider position
        if self.jack_manager:
            frame = self.position_slider.value()
            self.jack_manager.transport_locate(frame)
            self.locate_requested.emit(frame)
    
    def _on_slider_moved(self, value: int):
        """Handle slider movement."""
        # Update frame display while dragging
        self.frame_display.setText(str(value))
    
    def _update_display(self):
        """Update the transport display."""
        if not self.jack_manager or not self.jack_manager.is_connected():
            return
        
        # Get current state
        state = self.jack_manager.get_transport_state()
        
        # Update play button text based on state
        if state == "Rolling":
            self.play_button.setText("⏸ Pause")
        else:
            self.play_button.setText("▶ Play")
        
        # Get current frame and time
        frame = self.jack_manager.get_transport_frame()
        hours, minutes, seconds, frames = self.jack_manager.get_transport_time()
        
        # Update timecode display
        timecode = f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"
        self.timecode_display.setText(timecode)
        
        # Update frame display
        self.frame_display.setText(str(frame))
        
        # Update slider (only if not dragging)
        if not self._slider_dragging:
            # Set maximum to current frame + some buffer (for seeking ahead)
            # In practice, you might want to set this based on video length
            max_frame = max(frame + 1000, self.position_slider.maximum())
            self.position_slider.setMaximum(max_frame)
            self.position_slider.setValue(frame)
