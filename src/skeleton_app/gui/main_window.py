"""
Main application window for skeleton-app.
"""

import logging
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
from skeleton_app.gui.discovery_bridge import ServiceDiscoveryBridge
from skeleton_app.gui.widgets.transport_panel import TransportPanel
from skeleton_app.gui.widgets.cluster_panel import ClusterPanel
from skeleton_app.gui.widgets.patchbay_widget import PatchbayWidget
from skeleton_app.gui.widgets.node_canvas_v3 import NodeCanvasWidget
from skeleton_app.gui.widgets.transport_nodes import TransportAgentNodeWidget, TransportCoordinatorNodeWidget
from skeleton_app.gui.widgets.settings_dialog import SettingsDialog
from skeleton_app.audio.jack_client import JackClientManager
from skeleton_app.audio.transport_services import TransportAgentService, TransportCoordinatorService

logger = logging.getLogger(__name__)
class MainWindow(QMainWindow):
    """
    Main application window.
    
    Provides:
    - JACK transport controls and orchestration
    - Visual patchbay for JACK graph management
    - Cluster status and node discovery
    - Multi-node JACK graph selection and control
    """
    
    # Signals
    jack_status_changed = Signal(bool)  # Connected/disconnected
    service_discovery_ready = Signal()  # Service discovery initialized
    
    def __init__(self, config: Config, config_path: Optional[Path] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self.config_path = config_path or Path("config.yaml")
        
        # Create discovery bridge for thread-safe signals
        self.discovery_bridge = ServiceDiscoveryBridge(self)
        
        # Connect service discovery signal
        self.service_discovery_ready.connect(self._set_service_discovery)
        
        # JACK client manager
        self.jack_manager: Optional[JackClientManager] = None
        
        # Database and service discovery
        self.database: Optional[Database] = None
        self.service_discovery: Optional[ServiceDiscovery] = None
        
        # Transport coordination services
        self.transport_agent: Optional[TransportAgentService] = None
        self.transport_coordinator: Optional[TransportCoordinatorService] = None
        
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
        self.view_video_action.setChecked(False)
        
        self.view_transcode_action = QAction("&Transcode Videos", self)
        self.view_transcode_action.setCheckable(True)
        self.view_transcode_action.setChecked(False)
        
        self.view_transport_action = QAction("Transport &Coordination", self)
        self.view_transport_action.setCheckable(True)
        self.view_transport_action.setChecked(True)
        
        # Tools menu actions
        self.settings_action = QAction("&Settings...", self)
        self.settings_action.setShortcut("Ctrl+,")
        self.settings_action.triggered.connect(self._show_settings)
        
        # Help menu actions
        self.about_action = QAction("&About", self)
        self.about_action.triggered.connect(self._show_about)
    
    def _create_menus(self):
        """Create menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.quit_action)
        
        # JACK menu
        jack_menu = menubar.addMenu("&JACK")
        jack_menu.addAction(self.connect_jack_action)
        jack_menu.addAction(self.disconnect_jack_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.view_patchbay_action)
        view_menu.addAction(self.view_cluster_action)
        view_menu.addAction(self.view_transport_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction(self.settings_action)
        
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
        self.node_canvas = NodeCanvasWidget(parent=self)
        self.tabs.addTab(self.node_canvas, "Node Canvas")
        
        # Patchbay tab (list view)
        self.patchbay = PatchbayWidget(self)
        self.tabs.addTab(self.patchbay, "Patchbay List")
        
        # Prevent closing of system tabs (Node Canvas, Patchbay)
        from PySide6.QtWidgets import QTabBar
        self.tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        self.tabs.tabBar().setTabButton(1, QTabBar.ButtonPosition.RightSide, None)
        
        layout.addWidget(self.tabs)
        
        self.setCentralWidget(central)
    
    def _create_dock_widgets(self):
        """Create dock widgets."""
        # Cluster status dock
        self.cluster_dock = QDockWidget("Cluster Status", self)
        self.cluster_panel = ClusterPanel(self)
        self.cluster_dock.setWidget(self.cluster_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.cluster_dock)
        
        # Transport coordination dock
        self.transport_dock = QDockWidget("Transport Coordination", self)
        self._init_transport_panel()
        self.addDockWidget(Qt.RightDockWidgetArea, self.transport_dock)
        
        # Connect view actions
        self.view_cluster_action.toggled.connect(self.cluster_dock.setVisible)
        self.cluster_dock.visibilityChanged.connect(self.view_cluster_action.setChecked)
        self.view_transport_action.toggled.connect(self.transport_dock.setVisible)
        self.transport_dock.visibilityChanged.connect(self.view_transport_action.setChecked)
    
    def _on_tab_close_requested(self, index: int):
        """Handle tab close request."""
        # Don't allow closing system tabs (first two: Node Canvas, Patchbay)
        if index < 2:
            return
        
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
    
    def _init_transport_panel(self):
        """Initialize transport coordination panel."""
        # Create container widget with tabs for agent and coordinator
        transport_container = QWidget()
        transport_layout = QVBoxLayout(transport_container)
        transport_layout.setContentsMargins(0, 0, 0, 0)
        
        transport_tabs = QTabWidget()
        
        # Agent tab
        try:
            self.transport_agent = TransportAgentService(
                node_id=self.config.node.id,
                jack_client_name=f"transport_{self.config.node.name}",
                osc_port=5555
            )
            agent_widget = TransportAgentNodeWidget(self.transport_agent)
            transport_tabs.addTab(agent_widget, "Agent (This Node)")
            
            # Start agent
            QTimer.singleShot(500, self.transport_agent.start)
        except Exception as e:
            error_label = QLabel(f"Agent unavailable: {e}")
            transport_tabs.addTab(error_label, "Agent (Error)")
        
        # Coordinator tab
        try:
            self.transport_coordinator = TransportCoordinatorService(
                node_id=self.config.node.id,
                listen_port=5556
            )
            coordinator_widget = TransportCoordinatorNodeWidget(self.transport_coordinator)
            transport_tabs.addTab(coordinator_widget, "Coordinator")
        except Exception as e:
            error_label = QLabel(f"Coordinator unavailable: {e}")
            transport_tabs.addTab(error_label, "Coordinator (Error)")
        
        transport_layout.addWidget(transport_tabs)
        self.transport_dock.setWidget(transport_container)
    
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
        import threading
        
        logger.info(f"Starting service discovery initialization for {self.config.node.name}")
        
        def run_async_init():
            """Run async init in a separate thread with its own event loop."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def _async_init():
                try:
                    logger.info("Initializing service discovery...")
                    
                    # Initialize database
                    if self.config.database:
                        logger.info("Connecting to database...")
                        self.database = Database(self.config.database.url)
                        await self.database.connect()
                        await self.database.initialize_schema()
                        logger.info("Database connected")
                    
                    # Initialize service discovery
                    logger.info(f"Creating ServiceDiscovery: {self.config.node.name} @ {self.config.node.host}")
                    self.service_discovery = ServiceDiscovery(
                        node_id=self.config.node.id,
                        node_name=self.config.node.name,
                        node_host=self.config.node.host,
                        database=self.database,
                        heartbeat_interval=10,
                        discovery_bridge=self.discovery_bridge
                    )
                    
                    logger.info("Starting service discovery...")
                    await self.service_discovery.start()
                    logger.info("Service discovery started")
                    
                    # Emit signal to update cluster panel
                    self.service_discovery_ready.emit()
                    
                    logger.info(f"Service discovery initialized: {self.config.node.name}")
                    
                except Exception as e:
                    logger.error(f"Error initializing service discovery: {e}", exc_info=True)
            
            try:
                loop.run_until_complete(_async_init())
                # Keep loop running for async tasks
                loop.run_forever()
            except Exception as e:
                logger.error(f"Service discovery thread error: {e}", exc_info=True)
            finally:
                loop.close()
        
        # Start in daemon thread
        thread = threading.Thread(target=run_async_init, daemon=True)
        thread.start()
        logger.info("Service discovery thread started")
    
    def _set_service_discovery(self):
        """Set service discovery on cluster panel (must be called from main thread)."""
        if self.service_discovery:
            logger.info("Setting service discovery on cluster panel")
            self.cluster_panel.set_service_discovery(self.service_discovery, self.discovery_bridge)
        else:
            logger.warning("Service discovery not available when trying to set on cluster panel")
    
    def _open_video(self):
        """Open video file via File menu."""
        # Delegate to video panel
        self.video_panel._on_open_video()
    
    def _show_settings(self):
        """Show settings dialog."""
        dialog = SettingsDialog(self.config, self.config_path, self)
        dialog.exec()
    
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
        
        # Stop transport services
        if self.transport_agent:
            self.transport_agent.stop()
        
        # Disconnect from JACK
        if self.jack_manager:
            self.jack_manager.disconnect()
        
        event.accept()
