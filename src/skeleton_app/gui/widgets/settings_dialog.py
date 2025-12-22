"""
Settings dialog for configuring node and database settings.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QGroupBox, QPushButton,
    QLabel, QCheckBox, QTabWidget, QWidget,
    QMessageBox, QDialogButtonBox
)
from PySide6.QtCore import Qt

from skeleton_app.config import Config


class SettingsDialog(QDialog):
    """
    Settings dialog for node and database configuration.
    
    Allows user to configure:
    - Node identity (name, host, port)
    - Database connection
    - Service discovery ports
    """
    
    def __init__(self, config: Config, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self.original_config = config.model_copy(deep=True)
        
        self.setWindowTitle("Settings")
        self.setMinimumWidth(600)
        self.setModal(True)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        
        # Tabs for different setting categories
        tabs = QTabWidget()
        
        # Node settings tab
        node_tab = QWidget()
        node_layout = QVBoxLayout(node_tab)
        node_layout.addWidget(self._create_node_settings())
        node_layout.addStretch()
        tabs.addTab(node_tab, "Node Settings")
        
        # Database settings tab
        db_tab = QWidget()
        db_layout = QVBoxLayout(db_tab)
        db_layout.addWidget(self._create_database_settings())
        db_layout.addStretch()
        tabs.addTab(db_tab, "Database")
        
        # Network settings tab
        network_tab = QWidget()
        network_layout = QVBoxLayout(network_tab)
        network_layout.addWidget(self._create_network_settings())
        network_layout.addStretch()
        tabs.addTab(network_tab, "Network")
        
        layout.addWidget(tabs)
        
        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.Apply).clicked.connect(self._apply_settings)
        layout.addWidget(button_box)
    
    def _create_node_settings(self) -> QGroupBox:
        """Create node settings group."""
        group = QGroupBox("Node Identity")
        form = QFormLayout(group)
        
        # Node ID (read-only)
        self.node_id_label = QLabel(self.config.node.id)
        self.node_id_label.setStyleSheet("color: gray;")
        form.addRow("Node ID:", self.node_id_label)
        
        # Node name
        self.node_name_edit = QLineEdit(self.config.node.name)
        self.node_name_edit.setPlaceholderText("e.g., indigo, green, karate")
        form.addRow("Node Name:", self.node_name_edit)
        
        # Node host (IP address)
        self.node_host_edit = QLineEdit(self.config.node.host)
        self.node_host_edit.setPlaceholderText("e.g., 192.168.32.7")
        form.addRow("IP Address:", self.node_host_edit)
        
        # Node port
        self.node_port_spin = QSpinBox()
        self.node_port_spin.setRange(1024, 65535)
        self.node_port_spin.setValue(self.config.node.port)
        form.addRow("Port:", self.node_port_spin)
        
        # Info label
        info = QLabel(
            "The node name and IP address are used for network discovery.\n"
            "Changes take effect after restarting the application."
        )
        info.setStyleSheet("color: gray; font-size: 10px;")
        info.setWordWrap(True)
        form.addRow(info)
        
        return group
    
    def _create_database_settings(self) -> QGroupBox:
        """Create database settings group."""
        group = QGroupBox("PostgreSQL Database")
        layout = QVBoxLayout(group)
        
        # Enable/disable database
        self.db_enabled_check = QCheckBox("Enable database connection")
        self.db_enabled_check.setChecked(self.config.database is not None)
        self.db_enabled_check.toggled.connect(self._toggle_database_fields)
        layout.addWidget(self.db_enabled_check)
        
        # Database connection form
        form = QFormLayout()
        
        # Database URL
        db_url = ""
        if self.config.database:
            db_url = self.config.database.url
        
        self.db_url_edit = QLineEdit(db_url)
        self.db_url_edit.setPlaceholderText(
            "postgresql://user:password@host:5432/skeleton_crew"
        )
        form.addRow("Database URL:", self.db_url_edit)
        
        # Test connection button
        self.test_db_button = QPushButton("Test Connection")
        self.test_db_button.clicked.connect(self._test_database_connection)
        form.addRow("", self.test_db_button)
        
        layout.addLayout(form)
        
        # Info labels
        info = QLabel(
            "Database is optional. Without it, nodes will use UDP broadcast\n"
            "for discovery and keep services in memory only.\n\n"
            "With a database, service history and node registry are persistent\n"
            "across restarts."
        )
        info.setStyleSheet("color: gray; font-size: 10px;")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Set initial state
        self._toggle_database_fields(self.db_enabled_check.isChecked())
        
        return group
    
    def _create_network_settings(self) -> QGroupBox:
        """Create network settings group."""
        group = QGroupBox("Service Discovery Ports")
        form = QFormLayout(group)
        
        # ZeroMQ pub port
        self.pub_port_spin = QSpinBox()
        self.pub_port_spin.setRange(1024, 65535)
        self.pub_port_spin.setValue(5555)
        form.addRow("ZeroMQ Pub Port:", self.pub_port_spin)
        
        # ZeroMQ sub port
        self.sub_port_spin = QSpinBox()
        self.sub_port_spin.setRange(1024, 65535)
        self.sub_port_spin.setValue(5556)
        form.addRow("ZeroMQ Sub Port:", self.sub_port_spin)
        
        # UDP broadcast port
        self.broadcast_port_spin = QSpinBox()
        self.broadcast_port_spin.setRange(1024, 65535)
        self.broadcast_port_spin.setValue(5557)
        form.addRow("UDP Broadcast Port:", self.broadcast_port_spin)
        
        # Info label
        info = QLabel(
            "These ports are used for node discovery and service announcements.\n"
            "Make sure they are allowed through your firewall.\n"
            "Default values should work for most setups."
        )
        info.setStyleSheet("color: gray; font-size: 10px;")
        info.setWordWrap(True)
        form.addRow(info)
        
        return group
    
    def _toggle_database_fields(self, enabled: bool):
        """Enable/disable database fields."""
        self.db_url_edit.setEnabled(enabled)
        self.test_db_button.setEnabled(enabled)
    
    def _test_database_connection(self):
        """Test database connection."""
        db_url = self.db_url_edit.text().strip()
        
        if not db_url:
            QMessageBox.warning(
                self,
                "Database URL Required",
                "Please enter a database URL to test."
            )
            return
        
        # TODO: Implement actual database connection test
        QMessageBox.information(
            self,
            "Connection Test",
            "Database connection test not yet implemented.\n\n"
            f"Would attempt to connect to:\n{db_url}"
        )
    
    def _apply_settings(self):
        """Apply settings without closing dialog."""
        self._save_config()
        
        QMessageBox.information(
            self,
            "Settings Applied",
            "Settings have been updated in memory.\n\n"
            "Note: Some changes (like network settings) require\n"
            "restarting the application to take effect."
        )
    
    def _save_config(self):
        """Save settings to config object."""
        # Update node settings
        self.config.node.name = self.node_name_edit.text().strip()
        self.config.node.host = self.node_host_edit.text().strip()
        self.config.node.port = self.node_port_spin.value()
        
        # Update database settings
        if self.db_enabled_check.isChecked():
            db_url = self.db_url_edit.text().strip()
            if db_url:
                # Update or create database config
                if self.config.database:
                    self.config.database.url = db_url
                else:
                    from skeleton_app.config import DatabaseConfig
                    self.config.database = DatabaseConfig(url=db_url)
        else:
            self.config.database = None
    
    def accept(self):
        """Accept and save settings."""
        self._save_config()
        
        # TODO: Save to config.yaml file
        QMessageBox.information(
            self,
            "Settings Saved",
            "Settings have been updated.\n\n"
            "Note: Changes are in memory only and will be lost on restart.\n"
            "To persist changes, manually edit config.yaml."
        )
        
        super().accept()
    
    def reject(self):
        """Cancel and restore original settings."""
        # Restore original config
        self.config.node = self.original_config.node
        self.config.database = self.original_config.database
        super().reject()
