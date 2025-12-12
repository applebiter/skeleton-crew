"""
Main application window for skeleton-app.
"""

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QStatusBar, QMenuBar, QMenu, QToolBar,
    QLabel, QPushButton, QMessageBox, QDockWidget
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence

from skeleton_app.config import Config
from skeleton_app.database import Database
from skeleton_app.service_discovery import ServiceDiscovery
from skeleton_app.gui.widgets.transport_panel import TransportPanel
from skeleton_app.gui.widgets.cluster_panel import ClusterPanel
from skeleton_app.gui.widgets.patchbay_widget import PatchbayWidget
from skeleton_app.gui.widgets.node_canvas import NodeCanvasWidget
from skeleton_app.gui.widgets.video_panel import VideoPanel
from skeleton_app.gui.widgets.transcode_panel import TranscodePanel
from skeleton_app.audio.jack_client import JackClientManager
from skeleton_app.audio.qt_video_player import QtVideoPlayerManager


class MainWindow(QMainWindow):
    """
    Main application window.
    
    Provides:
    - JACK transport controls
    - Visual patchbay
    - Cluster status
    - xjadeo video player controls
    - Command log
    """
    
    # Signals
    jack_status_changed = Signal(bool)  # Connected/disconnected
    
    def __init__(self, config: Config, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        
        # JACK client manager
        self.jack_manager: Optional[JackClientManager] = None
        
        # Qt video player manager
        self.video_manager = QtVideoPlayerManager()
        
        # Database and service discovery
        self.database: Optional[Database] = None
        self.service_discovery: Optional[ServiceDiscovery] = None
        
        # Setup UI
        self.setWindowTitle("Skeleton Crew - JACK Control Hub")
        self.setMinimumSize(1200, 800)
        
        self._create_actions()
        self._create_menus()
        self._create_toolbars()
        self._create_central_widget()
        self._create_dock_widgets()
        self._create_status_bar()
        
        # Initialize JACK connection
        self._init_jack()
        
        # Initialize service discovery (async)
        self._init_service_discovery()
        
        # Status update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(1000)  # Update every second
        
        # Restore window geometry
        self._restore_geometry()
    
    def _create_actions(self):
        """Create menu and toolbar actions."""
        # File menu actions
        self.open_video_action = QAction("Open &Video...", self)
        self.open_video_action.setShortcut("Ctrl+O")
        self.open_video_action.triggered.connect(self._open_video)
        
        self.quit_action = QAction("&Quit", self)
        self.quit_action.setShortcut(QKeySequence.Quit)
        self.quit_action.triggered.connect(self.close)
        
        # JACK menu actions
        self.connect_jack_action = QAction("&Connect to JACK", self)
        self.connect_jack_action.setShortcut("Ctrl+J")
        self.connect_jack_action.triggered.connect(self._connect_jack)
        
        self.disconnect_jack_action = QAction("&Disconnect from JACK", self)
        self.disconnect_jack_action.triggered.connect(self._disconnect_jack)
        self.disconnect_jack_action.setEnabled(False)
        
        # View menu actions
        self.view_patchbay_action = QAction("&Patchbay", self)
        self.view_patchbay_action.setCheckable(True)
        self.view_patchbay_action.setChecked(True)
        
        self.view_cluster_action = QAction("&Cluster Status", self)
        self.view_cluster_action.setCheckable(True)
        self.view_cluster_action.setChecked(True)
        
        self.view_video_action = QAction("&Video Players", self)
        self.view_video_action.setCheckable(True)
        self.view_video_action.setChecked(True)
        
        self.view_transcode_action = QAction("&Transcode Videos", self)
        self.view_transcode_action.setCheckable(True)
        self.view_transcode_action.setChecked(False)
        
        # Help menu actions
        self.about_action = QAction("&About", self)
        self.about_action.triggered.connect(self._show_about)
    
    def _create_menus(self):
        """Create menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.open_video_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)
        
        # JACK menu
        jack_menu = menubar.addMenu("&JACK")
        jack_menu.addAction(self.connect_jack_action)
        jack_menu.addAction(self.disconnect_jack_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.view_patchbay_action)
        view_menu.addAction(self.view_cluster_action)
        view_menu.addAction(self.view_video_action)
        view_menu.addAction(self.view_transcode_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self.about_action)
    
    def _create_toolbars(self):
        """Create toolbars."""
        # Main toolbar
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # Add transport controls to toolbar will be done by TransportPanel
    
    def _create_central_widget(self):
        """Create central widget with tabs."""
        central = QWidget()
        layout = QVBoxLayout(central)
        
        # Transport panel (always visible at top)
        self.transport_panel = TransportPanel(self)
        layout.addWidget(self.transport_panel)
        
        # Tab widget for main content
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        
        # Node Canvas tab (visual graph)
        self.node_canvas = NodeCanvasWidget(self)
        self.tabs.addTab(self.node_canvas, "Node Canvas")
        
        # Patchbay tab (list view)
        self.patchbay = PatchbayWidget(self)
        self.tabs.addTab(self.patchbay, "Patchbay List")
        
        # Prevent closing of system tabs (Node Canvas, Patchbay)
        from PySide6.QtWidgets import QTabBar
        self.tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        self.tabs.tabBar().setTabButton(1, QTabBar.ButtonPosition.RightSide, None)
        
        # TODO: Add more tabs (Media Library, Playlist, etc.)
        
        layout.addWidget(self.tabs)
        
        self.setCentralWidget(central)
    
    def _create_dock_widgets(self):
        """Create dock widgets."""
        # Cluster status dock
        self.cluster_dock = QDockWidget("Cluster Status", self)
        self.cluster_panel = ClusterPanel(self)
        self.cluster_dock.setWidget(self.cluster_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.cluster_dock)
        
        # Video players dock (pass main tab widget)
        self.video_dock = QDockWidget("Video Players", self)
        self.video_panel = VideoPanel(self.video_manager, self.tabs, self)
        self.video_dock.setWidget(self.video_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.video_dock)
        
        # Transcode dock (initially hidden)
        self.transcode_dock = QDockWidget("Transcode Videos", self)
        self.transcode_panel = TranscodePanel(self)
        self.transcode_dock.setWidget(self.transcode_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.transcode_dock)
        self.transcode_dock.setVisible(False)
        
        # Connect view actions
        self.view_cluster_action.toggled.connect(self.cluster_dock.setVisible)
        self.cluster_dock.visibilityChanged.connect(self.view_cluster_action.setChecked)
        self.view_video_action.toggled.connect(self.video_dock.setVisible)
        self.video_dock.visibilityChanged.connect(self.view_video_action.setChecked)
        self.view_transcode_action.toggled.connect(self.transcode_dock.setVisible)
        self.transcode_dock.visibilityChanged.connect(self.view_transcode_action.setChecked)
    
    def _open_video(self):
        """Handle open video action (delegates to video panel)."""
        self.video_panel._on_open_video()
    
    def _on_tab_close_requested(self, index: int):
        """Handle tab close request."""
        # Don't allow closing system tabs (first two: Node Canvas, Patchbay)
        if index < 2:
            return
        
        # Get the widget at this index
        widget = self.tabs.widget(index)
        
        # If it's a video player widget, trigger its close
        from skeleton_app.gui.widgets.video_player_widget import VideoPlayerWidget
        if isinstance(widget, VideoPlayerWidget):
            widget.closed.emit(widget.player.instance_id)
        else:
            # For other tabs, just remove
            self.tabs.removeTab(index)
    
    def _create_status_bar(self):
        """Create status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # JACK status indicator
        self.jack_status_label = QLabel("JACK: Disconnected")
        self.status_bar.addPermanentWidget(self.jack_status_label)
        
        # Transport status
        self.transport_status_label = QLabel("Transport: Stopped")
        self.status_bar.addPermanentWidget(self.transport_status_label)
    
    def _init_jack(self):
        """Initialize JACK connection."""
        try:
            self.jack_manager = JackClientManager(
                client_name=self.config.node.name
            )
            self.jack_manager.connect()
            self._on_jack_connected()
        except Exception as e:
            self.status_bar.showMessage(f"Failed to connect to JACK: {e}", 5000)
            print(f"JACK connection failed: {e}")
    
    def _connect_jack(self):
        """Connect to JACK server."""
        try:
            if not self.jack_manager:
                self.jack_manager = JackClientManager(
                    client_name=self.config.node.name
                )
            self.jack_manager.connect()
            self._on_jack_connected()
        except Exception as e:
            QMessageBox.critical(
                self,
                "JACK Connection Failed",
                f"Could not connect to JACK server:\n{e}"
            )
    
    def _disconnect_jack(self):
        """Disconnect from JACK server."""
        if self.jack_manager:
            self.jack_manager.disconnect()
            self._on_jack_disconnected()
    
    def _on_jack_connected(self):
        """Handle JACK connection."""
        self.jack_status_label.setText("JACK: Connected")
        self.connect_jack_action.setEnabled(False)
        self.disconnect_jack_action.setEnabled(True)
        self.jack_status_changed.emit(True)
        
        # Update widgets
        self.node_canvas.set_jack_manager(self.jack_manager)
        self.patchbay.set_jack_manager(self.jack_manager)
        
        # Update transport panel
        self.transport_panel.set_jack_manager(self.jack_manager)
        
        # Update video player manager
        self.video_manager.set_jack_manager(self.jack_manager)
    
    def _on_jack_disconnected(self):
        """Handle JACK disconnection."""
        self.jack_status_label.setText("JACK: Disconnected")
        self.connect_jack_action.setEnabled(True)
        self.disconnect_jack_action.setEnabled(False)
        self.jack_status_changed.emit(False)
        
        # Update widgets
        self.node_canvas.set_jack_manager(None)
        self.patchbay.set_jack_manager(None)
        self.transport_panel.set_jack_manager(None)
    
    def _update_status(self):
        """Update status bar periodically."""
        if self.jack_manager and self.jack_manager.is_connected():
            # Update transport status
            state = self.jack_manager.get_transport_state()
            self.transport_status_label.setText(f"Transport: {state}")
        else:
            self.transport_status_label.setText("Transport: N/A")
    
    def _init_service_discovery(self):
        """Initialize service discovery asynchronously."""
        import asyncio
        
        # Create event loop in separate thread if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        async def _async_init():
            # Initialize database
            if self.config.database:
                self.database = Database(self.config.database.url)
                await self.database.connect()
                await self.database.initialize_schema()
            
            # Initialize service discovery
            self.service_discovery = ServiceDiscovery(
                node_id=self.config.node.id,
                database=self.database,
                heartbeat_interval=10
            )
            await self.service_discovery.start()
            
            # Update cluster panel
            self.cluster_panel.set_service_discovery(self.service_discovery)
        
        # Run async initialization
        asyncio.ensure_future(_async_init())
    
    def _open_video(self):
        """Open video file via File menu."""
        # Delegate to video panel
        self.video_panel._on_open_video()
    
    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About Skeleton Crew",
            "<h3>Skeleton Crew</h3>"
            "<p>Distributed JACK-centric control hub</p>"
            "<p>Film scoring, composition, and live performance platform</p>"
            "<p>Your crew of nodes working together</p>"
            "<p>Version 0.1.0</p>"
        )
    
    def _restore_geometry(self):
        """Restore window geometry from settings."""
        # TODO: Implement settings persistence
        pass
    
    def _save_geometry(self):
        """Save window geometry to settings."""
        # TODO: Implement settings persistence
        pass
    
    def closeEvent(self, event):
        """Handle window close event."""
        self._save_geometry()
        
        # Stop service discovery
        if self.service_discovery:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.service_discovery.stop())
            except Exception:
                pass
        
        # Disconnect database
        if self.database:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.database.disconnect())
            except Exception:
                pass
        
        # Stop all video players
        if self.video_manager:
            self.video_manager.cleanup_all()
        
        # Disconnect from JACK
        if self.jack_manager:
            self.jack_manager.disconnect()
        
        event.accept()
