"""
Video player management panel.

Shows active xjadeo instances and allows control.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt, QTimer, Signal

from skeleton_app.audio.xjadeo_manager import XjadeoManager

logger = logging.getLogger(__name__)


class VideoPanel(QWidget):
    """
    Video player management panel.
    
    Shows active xjadeo instances and provides controls.
    """
    
    # Signals
    video_opened = Signal(str, str)  # instance_id, file_path
    video_closed = Signal(str)  # instance_id
    
    def __init__(self, xjadeo_manager: XjadeoManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.xjadeo_manager = xjadeo_manager
        self._setup_ui()
        
        # Auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_instances)
        self.refresh_timer.start(2000)  # Update every 2 seconds
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("<b>Video Players</b>")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        # Open video button
        self.open_button = QPushButton("Open Video")
        self.open_button.clicked.connect(self._on_open_video)
        header_layout.addWidget(self.open_button)
        
        layout.addLayout(header_layout)
        
        # Instance tree
        self.instance_tree = QTreeWidget()
        self.instance_tree.setHeaderLabels(["Instance", "File", "Status"])
        self.instance_tree.setColumnWidth(0, 120)
        self.instance_tree.setColumnWidth(1, 300)
        self.instance_tree.setColumnWidth(2, 100)
        layout.addWidget(self.instance_tree)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.stop_button = QPushButton("Stop Selected")
        self.stop_button.clicked.connect(self._on_stop_selected)
        button_layout.addWidget(self.stop_button)
        
        self.stop_all_button = QPushButton("Stop All")
        self.stop_all_button.clicked.connect(self._on_stop_all)
        button_layout.addWidget(self.stop_all_button)
        
        button_layout.addStretch()
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._refresh_instances)
        button_layout.addWidget(self.refresh_button)
        
        layout.addLayout(button_layout)
        
        # Info box
        info_box = QGroupBox("Info")
        info_layout = QVBoxLayout()
        info_label = QLabel(
            "xjadeo video players sync to JACK transport.\n"
            "Open multiple videos for multi-monitor setups.\n"
            "All instances follow the same timeline."
        )
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        info_box.setLayout(info_layout)
        layout.addWidget(info_box)
        
        # Initial refresh
        self._refresh_instances()
    
    def _on_open_video(self):
        """Handle open video button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video File",
            str(Path.home()),
            "Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.ogv);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            # Generate instance ID
            instance_id = f"video_{len(self.xjadeo_manager.instances) + 1}"
            
            # Launch xjadeo
            self.xjadeo_manager.launch(
                file_path=Path(file_path),
                instance_id=instance_id,
                sync_to_jack=True,
                show_osd=True,
                show_timecode=True
            )
            
            logger.info(f"Opened video: {file_path} (instance: {instance_id})")
            self.video_opened.emit(instance_id, file_path)
            self._refresh_instances()
            
        except Exception as e:
            logger.error(f"Failed to open video: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open video:\n{str(e)}"
            )
    
    def _on_stop_selected(self):
        """Stop selected video instance."""
        selected_items = self.instance_tree.selectedItems()
        if not selected_items:
            return
        
        for item in selected_items:
            instance_id = item.text(0)
            try:
                self.xjadeo_manager.stop(instance_id)
                logger.info(f"Stopped video instance: {instance_id}")
                self.video_closed.emit(instance_id)
            except Exception as e:
                logger.error(f"Failed to stop instance {instance_id}: {e}")
        
        self._refresh_instances()
    
    def _on_stop_all(self):
        """Stop all video instances."""
        try:
            self.xjadeo_manager.stop_all()
            logger.info("Stopped all video instances")
            for instance_id in list(self.xjadeo_manager.instances.keys()):
                self.video_closed.emit(instance_id)
            self._refresh_instances()
        except Exception as e:
            logger.error(f"Failed to stop all instances: {e}")
    
    def _refresh_instances(self):
        """Refresh the instance list."""
        self.instance_tree.clear()
        
        instances = self.xjadeo_manager.get_instances()
        for instance_id in instances:
            info = self.xjadeo_manager.get_instance_info(instance_id)
            if info:
                file_path = Path(info["file_path"])
                item = QTreeWidgetItem([
                    instance_id,
                    file_path.name,
                    "Running" if info["running"] else "Stopped"
                ])
                self.instance_tree.addTopLevelItem(item)
        
        # Update button states
        has_instances = len(instances) > 0
        self.stop_button.setEnabled(has_instances)
        self.stop_all_button.setEnabled(has_instances)
