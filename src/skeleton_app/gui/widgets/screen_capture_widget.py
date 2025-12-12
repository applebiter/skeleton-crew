"""
Screen capture widget for live display and recording.

Supports capturing entire screens, specific windows, or screen regions.
Integrates with video player infrastructure for display in tabs.
"""

import logging
import time
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal, Qt, QRect, QSize
from PySide6.QtGui import QImage, QPixmap, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QFileDialog
)

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


class ScreenCaptureSource(QObject):
    """
    Screen capture source that grabs frames at specified FPS.
    
    Can capture:
    - Entire screens (monitor 1, 2, etc.)
    - Specific windows by title
    - Custom regions
    """
    
    # Signals
    frame_ready = Signal(QImage)  # New frame available
    error_occurred = Signal(str)
    
    def __init__(
        self,
        source_type: str = "screen",  # "screen", "window", "region"
        source_id: int = 0,  # Monitor number or window ID
        fps: int = 30,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        
        self.source_type = source_type
        self.source_id = source_id
        self.fps = fps
        self.is_capturing = False
        
        # MSS for fast screen capture
        self.sct = mss.mss() if HAS_MSS else None
        
        # Timer for frame capture
        self.capture_timer = QTimer()
        self.capture_timer.timeout.connect(self._capture_frame)
        
        # Recording state
        self.is_recording = False
        self.video_writer: Optional['cv2.VideoWriter'] = None
        self.record_path: Optional[Path] = None
        
        # Stats
        self.frames_captured = 0
        self.frames_recorded = 0
        self.start_time = 0
    
    def start_capture(self):
        """Start capturing frames."""
        if not HAS_MSS:
            self.error_occurred.emit("python-mss not installed. Install with: pip install mss")
            return
        
        self.is_capturing = True
        self.frames_captured = 0
        self.start_time = time.time()
        
        interval_ms = int(1000 / self.fps)
        self.capture_timer.start(interval_ms)
        logger.info(f"Started screen capture at {self.fps} FPS")
    
    def stop_capture(self):
        """Stop capturing frames."""
        self.is_capturing = False
        self.capture_timer.stop()
        
        if self.is_recording:
            self.stop_recording()
        
        elapsed = time.time() - self.start_time
        logger.info(f"Stopped capture. Captured {self.frames_captured} frames in {elapsed:.1f}s")
    
    def start_recording(self, output_path: Path, codec: str = "mp4v"):
        """Start recording frames to video file."""
        if not HAS_OPENCV:
            self.error_occurred.emit("opencv-python not installed. Install with: pip install opencv-python")
            return
        
        if not self.is_capturing:
            self.error_occurred.emit("Must start capture before recording")
            return
        
        # Get monitor info for resolution
        monitor = self.sct.monitors[self.source_id + 1]  # 0 is all monitors
        width = monitor["width"]
        height = monitor["height"]
        
        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*codec)
        self.video_writer = cv2.VideoWriter(
            str(output_path),
            fourcc,
            self.fps,
            (width, height)
        )
        
        self.is_recording = True
        self.frames_recorded = 0
        self.record_path = output_path
        logger.info(f"Started recording to {output_path}")
    
    def stop_recording(self):
        """Stop recording."""
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        
        self.is_recording = False
        logger.info(f"Stopped recording. Wrote {self.frames_recorded} frames to {self.record_path}")
    
    def _capture_frame(self):
        """Capture a single frame."""
        try:
            # Capture screen using MSS
            monitor = self.sct.monitors[self.source_id + 1]  # 0 is all monitors
            sct_img = self.sct.grab(monitor)
            
            # Convert to QImage
            img = QImage(
                sct_img.rgb,
                sct_img.width,
                sct_img.height,
                QImage.Format_RGB888
            )
            
            self.frames_captured += 1
            self.frame_ready.emit(img)
            
            # Record if enabled
            if self.is_recording and self.video_writer and HAS_OPENCV:
                # Convert to numpy array for OpenCV
                ptr = img.bits()
                arr = np.array(ptr).reshape((img.height(), img.width(), 3))
                # BGR for OpenCV
                bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                self.video_writer.write(bgr)
                self.frames_recorded += 1
        
        except Exception as e:
            logger.error(f"Capture error: {e}")
            self.error_occurred.emit(str(e))
    
    def get_available_monitors(self) -> list[dict]:
        """Get list of available monitors."""
        if not self.sct:
            return []
        return [
            {
                "id": i,
                "width": mon["width"],
                "height": mon["height"],
                "left": mon["left"],
                "top": mon["top"]
            }
            for i, mon in enumerate(self.sct.monitors[1:])  # Skip "all monitors"
        ]


class ScreenCaptureWidget(QWidget):
    """
    Widget for displaying live screen capture and controlling recording.
    
    Integrates with video player infrastructure - can be displayed in tabs
    alongside regular video files.
    """
    
    closed = Signal(str)  # instance_id when closed
    
    def __init__(
        self,
        instance_id: str,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self.instance_id = instance_id
        self.capture_source: Optional[ScreenCaptureSource] = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        
        # Display area for live preview
        self.preview_label = QLabel("No capture active")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 480)
        self.preview_label.setStyleSheet("QLabel { background-color: black; color: white; }")
        layout.addWidget(self.preview_label)
        
        # Control panel
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        
        # Source selection
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Monitor:"))
        
        self.monitor_combo = QComboBox()
        self._populate_monitors()
        source_layout.addWidget(self.monitor_combo)
        
        source_layout.addWidget(QLabel("FPS:"))
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setValue(30)
        source_layout.addWidget(self.fps_spin)
        
        source_layout.addStretch()
        control_layout.addLayout(source_layout)
        
        # Capture controls
        capture_layout = QHBoxLayout()
        
        self.start_button = QPushButton("Start Capture")
        self.start_button.clicked.connect(self._on_start_capture)
        capture_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop Capture")
        self.stop_button.clicked.connect(self._on_stop_capture)
        self.stop_button.setEnabled(False)
        capture_layout.addWidget(self.stop_button)
        
        self.record_button = QPushButton("⏺ Start Recording")
        self.record_button.clicked.connect(self._on_toggle_recording)
        self.record_button.setEnabled(False)
        capture_layout.addWidget(self.record_button)
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self._on_close)
        capture_layout.addWidget(self.close_button)
        
        control_layout.addLayout(capture_layout)
        
        # Stats
        self.stats_label = QLabel("Ready")
        control_layout.addWidget(self.stats_label)
        
        layout.addWidget(control_widget)
    
    def _populate_monitors(self):
        """Populate monitor dropdown."""
        if not HAS_MSS:
            self.monitor_combo.addItem("MSS not installed")
            return
        
        with mss.mss() as sct:
            for i, mon in enumerate(sct.monitors[1:]):  # Skip "all monitors"
                self.monitor_combo.addItem(
                    f"Monitor {i+1} ({mon['width']}x{mon['height']})",
                    i
                )
    
    def _on_start_capture(self):
        """Start screen capture."""
        monitor_id = self.monitor_combo.currentData()
        if monitor_id is None:
            return
        
        fps = self.fps_spin.value()
        
        self.capture_source = ScreenCaptureSource(
            source_type="screen",
            source_id=monitor_id,
            fps=fps,
            parent=self
        )
        self.capture_source.frame_ready.connect(self._on_frame_ready)
        self.capture_source.error_occurred.connect(self._on_error)
        
        self.capture_source.start_capture()
        
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.record_button.setEnabled(True)
        self.monitor_combo.setEnabled(False)
        self.fps_spin.setEnabled(False)
    
    def _on_stop_capture(self):
        """Stop screen capture."""
        if self.capture_source:
            self.capture_source.stop_capture()
            self.capture_source = None
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.record_button.setEnabled(False)
        self.monitor_combo.setEnabled(True)
        self.fps_spin.setEnabled(True)
        self.preview_label.setText("Capture stopped")
    
    def _on_toggle_recording(self):
        """Toggle recording on/off."""
        if not self.capture_source:
            return
        
        if not self.capture_source.is_recording:
            # Start recording - prompt for file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"screen_capture_{timestamp}.mp4"
            
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Recording",
                default_name,
                "Video Files (*.mp4 *.avi);;All Files (*)"
            )
            
            if file_path:
                self.capture_source.start_recording(Path(file_path))
                self.record_button.setText("⏹ Stop Recording")
                self.record_button.setStyleSheet("QPushButton { background-color: red; }")
        else:
            # Stop recording
            self.capture_source.stop_recording()
            self.record_button.setText("⏺ Start Recording")
            self.record_button.setStyleSheet("")
    
    def _on_frame_ready(self, image: QImage):
        """Handle new frame from capture."""
        # Scale to fit preview while maintaining aspect ratio
        scaled = image.scaled(
            self.preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.preview_label.setPixmap(QPixmap.fromImage(scaled))
        
        # Update stats
        if self.capture_source:
            elapsed = time.time() - self.capture_source.start_time
            fps_actual = self.capture_source.frames_captured / elapsed if elapsed > 0 else 0
            
            stats = f"Captured: {self.capture_source.frames_captured} frames ({fps_actual:.1f} FPS)"
            if self.capture_source.is_recording:
                stats += f" | Recording: {self.capture_source.frames_recorded} frames"
            
            self.stats_label.setText(stats)
    
    def _on_error(self, error_msg: str):
        """Handle capture error."""
        logger.error(f"[{self.instance_id}] {error_msg}")
        self.preview_label.setText(f"Error: {error_msg}")
    
    def _on_close(self):
        """Close this capture."""
        if self.capture_source:
            self.capture_source.stop_capture()
        
        self.closed.emit(self.instance_id)
    
    def cleanup(self):
        """Cleanup resources."""
        if self.capture_source:
            self.capture_source.stop_capture()
            self.capture_source = None
