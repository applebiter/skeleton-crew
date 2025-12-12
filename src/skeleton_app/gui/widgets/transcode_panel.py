"""
Video transcoding panel for creating xjadeo-optimized versions.

Provides single-file and batch transcoding with progress tracking.
"""

import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QProgressBar, QFileDialog, QMessageBox,
    QGroupBox, QSpinBox, QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer

from skeleton_app.utils.video_transcoder import VideoTranscoder, MediaInfo

logger = logging.getLogger(__name__)


class TranscodeThread(QThread):
    """Background thread for transcoding."""
    
    progress = Signal(float, str)  # percent, message
    finished = Signal(Path, Path)  # video_path, audio_path
    error = Signal(str)
    
    def __init__(self, source_path: Path, output_dir: Path, quality: int = 23):
        super().__init__()
        self.source_path = source_path
        self.output_dir = output_dir
        self.quality = quality
        self.transcoder = VideoTranscoder()
    
    def run(self):
        """Run transcode in background."""
        try:
            video_path, audio_path = self.transcoder.transcode_video(
                self.source_path,
                self.output_dir,
                video_quality=self.quality,
                progress_callback=lambda p, m: self.progress.emit(p, m)
            )
            self.finished.emit(video_path, audio_path)
        except Exception as e:
            logger.error(f"Transcode failed: {e}", exc_info=True)
            self.error.emit(str(e))


class TranscodePanel(QWidget):
    """
    Panel for transcoding videos to xjadeo-optimized format.
    
    Features:
    - Browse source videos
    - Show transcode status (transcoded/not transcoded)
    - Single-file transcode
    - Batch transcode selected files
    - Progress tracking
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.source_base = Path.home() / "Backups/Videos"
        self.output_base = Path.home() / "Videos"
        
        self.transcode_thread: Optional[TranscodeThread] = None
        self.transcode_queue: List[Path] = []
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("<b>Video Transcoding</b>")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        # Refresh button
        self.refresh_button = QPushButton("🔄 Refresh")
        self.refresh_button.clicked.connect(self._refresh_list)
        header_layout.addWidget(self.refresh_button)
        
        layout.addLayout(header_layout)
        
        # Video list
        self.video_tree = QTreeWidget()
        self.video_tree.setHeaderLabels(["Video", "Status", "Size"])
        self.video_tree.setColumnWidth(0, 300)
        self.video_tree.setColumnWidth(1, 100)
        self.video_tree.setSelectionMode(QTreeWidget.MultiSelection)
        layout.addWidget(self.video_tree)
        
        # Settings
        settings_group = QGroupBox("Settings")
        settings_layout = QHBoxLayout(settings_group)
        
        settings_layout.addWidget(QLabel("Quality (CRF):"))
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(0, 51)
        self.quality_spin.setValue(23)
        self.quality_spin.setToolTip("Lower = better quality (0-51, 23 = high quality)")
        settings_layout.addWidget(self.quality_spin)
        
        settings_layout.addStretch()
        layout.addWidget(settings_group)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.transcode_selected_button = QPushButton("Transcode Selected")
        self.transcode_selected_button.clicked.connect(self._on_transcode_selected)
        button_layout.addWidget(self.transcode_selected_button)
        
        self.browse_button = QPushButton("Browse & Transcode...")
        self.browse_button.clicked.connect(self._on_browse_transcode)
        button_layout.addWidget(self.browse_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        # Info
        info_label = QLabel(
            "<small>Transcodes videos from ~/Backups/Videos to ~/Videos<br>"
            "Creates GPU-accelerated H.264 with keyframes every second for xjadeo</small>"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Auto-refresh on show
        QTimer.singleShot(500, self._refresh_list)
    
    def _refresh_list(self):
        """Refresh video list."""
        self.video_tree.clear()
        
        if not self.source_base.exists():
            self.status_label.setText("Source directory not found")
            return
        
        # Scan for video files
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.m4v', '.wmv'}
        video_files = []
        
        for ext in video_extensions:
            video_files.extend(self.source_base.rglob(f"*{ext}"))
        
        # Add to tree
        for video_file in sorted(video_files):
            relative_path = video_file.relative_to(self.source_base)
            
            # Check if transcoded version exists
            transcoded = self._get_transcoded_path(video_file)
            status = "✓ Transcoded" if transcoded and transcoded.exists() else "Not transcoded"
            
            # File size
            size_mb = video_file.stat().st_size / (1024 * 1024)
            size_str = f"{size_mb:.1f} MB" if size_mb < 1024 else f"{size_mb/1024:.2f} GB"
            
            item = QTreeWidgetItem([str(relative_path), status, size_str])
            item.setData(0, Qt.UserRole, video_file)
            self.video_tree.addTopLevelItem(item)
        
        self.status_label.setText(f"Found {len(video_files)} videos")
    
    def _get_transcoded_path(self, source_path: Path) -> Path:
        """Get transcoded video path for source."""
        relative = source_path.relative_to(self.source_base)
        return self.output_base / relative.parent / f"{relative.stem}_video.mp4"
    
    def _on_browse_transcode(self):
        """Browse for a video file and transcode it."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video to Transcode",
            str(self.source_base),
            "Video Files (*.mp4 *.mkv *.avi *.mov *.m4v *.wmv);;All Files (*)"
        )
        
        if not file_path:
            return
        
        source_path = Path(file_path)
        self._transcode_single(source_path)
    
    def _on_transcode_selected(self):
        """Transcode selected videos."""
        selected_items = self.video_tree.selectedItems()
        
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select videos to transcode")
            return
        
        # Get source paths
        source_paths = [item.data(0, Qt.UserRole) for item in selected_items]
        
        # Filter out already transcoded
        to_transcode = []
        for path in source_paths:
            transcoded = self._get_transcoded_path(path)
            if not transcoded.exists():
                to_transcode.append(path)
        
        if not to_transcode:
            QMessageBox.information(
                self,
                "Already Transcoded",
                "All selected videos are already transcoded"
            )
            return
        
        # Confirm batch
        total_size = sum(p.stat().st_size for p in to_transcode) / (1024 ** 3)
        reply = QMessageBox.question(
            self,
            "Confirm Batch Transcode",
            f"Transcode {len(to_transcode)} videos?\n"
            f"Total size: {total_size:.2f} GB\n"
            f"This may take a while.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Start batch
        self.transcode_queue = to_transcode.copy()
        self._process_queue()
    
    def _transcode_single(self, source_path: Path):
        """Transcode a single video."""
        # Determine output directory
        if source_path.is_relative_to(self.source_base):
            relative = source_path.relative_to(self.source_base)
            output_dir = self.output_base / relative.parent
        else:
            # File outside standard location - ask user
            output_dir = Path(QFileDialog.getExistingDirectory(
                self,
                "Select Output Directory",
                str(self.output_base)
            ))
            if not output_dir:
                return
        
        self._start_transcode(source_path, output_dir)
    
    def _process_queue(self):
        """Process next item in transcode queue."""
        if not self.transcode_queue:
            self.status_label.setText("Batch transcode complete!")
            self.progress_bar.setVisible(False)
            self._refresh_list()
            return
        
        # Get next file
        source_path = self.transcode_queue.pop(0)
        relative = source_path.relative_to(self.source_base)
        output_dir = self.output_base / relative.parent
        
        remaining = len(self.transcode_queue)
        self.status_label.setText(f"Transcoding {source_path.name} ({remaining} remaining)")
        
        self._start_transcode(source_path, output_dir)
    
    def _start_transcode(self, source_path: Path, output_dir: Path):
        """Start transcoding a file."""
        if self.transcode_thread and self.transcode_thread.isRunning():
            QMessageBox.warning(self, "Busy", "A transcode is already in progress")
            return
        
        self.transcode_thread = TranscodeThread(
            source_path,
            output_dir,
            self.quality_spin.value()
        )
        
        self.transcode_thread.progress.connect(self._on_progress)
        self.transcode_thread.finished.connect(self._on_finished)
        self.transcode_thread.error.connect(self._on_error)
        
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.transcode_selected_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        
        self.transcode_thread.start()
        self.status_label.setText(f"Transcoding {source_path.name}...")
    
    def _on_progress(self, percent: float, message: str):
        """Handle progress update."""
        self.progress_bar.setValue(int(percent))
        self.status_label.setText(message)
    
    def _on_finished(self, video_path: Path, audio_path: Path):
        """Handle transcode completion."""
        logger.info(f"Transcode complete: {video_path}")
        
        # Check if batch queue has more
        if self.transcode_queue:
            self._process_queue()
        else:
            self.progress_bar.setVisible(False)
            self.cancel_button.setEnabled(False)
            self.transcode_selected_button.setEnabled(True)
            self.browse_button.setEnabled(True)
            self.status_label.setText(f"Complete! Video: {video_path.name}")
            self._refresh_list()
    
    def _on_error(self, error_msg: str):
        """Handle transcode error."""
        logger.error(f"Transcode error: {error_msg}")
        
        self.progress_bar.setVisible(False)
        self.cancel_button.setEnabled(False)
        self.transcode_selected_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.status_label.setText(f"Error: {error_msg[:100]}")
        
        QMessageBox.critical(self, "Transcode Error", f"Failed to transcode:\n{error_msg}")
        
        # Continue with queue if in batch mode
        if self.transcode_queue:
            reply = QMessageBox.question(
                self,
                "Continue?",
                "Continue with remaining videos?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._process_queue()
            else:
                self.transcode_queue.clear()
    
    def _on_cancel(self):
        """Cancel current transcode."""
        if self.transcode_thread and self.transcode_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel Transcode",
                "Cancel current transcode?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.transcode_thread.terminate()
                self.transcode_thread.wait()
                self.transcode_queue.clear()
                
                self.progress_bar.setVisible(False)
                self.cancel_button.setEnabled(False)
                self.transcode_selected_button.setEnabled(True)
                self.browse_button.setEnabled(True)
                self.status_label.setText("Cancelled")
