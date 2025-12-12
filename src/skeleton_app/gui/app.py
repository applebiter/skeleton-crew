#!/usr/bin/env python3
"""
Main GUI application entry point.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from skeleton_app.gui.main_window import MainWindow
from skeleton_app.config import Config


def main():
    """Run the skeleton-app GUI."""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Skeleton Crew")
    app.setOrganizationName("SkeletonCrew")
    app.setOrganizationDomain("skeleton-crew.local")
    
    # Load configuration
    config_path = Path("config.yaml")
    if config_path.exists():
        config = Config.from_yaml(config_path)
    else:
        config = Config()
    
    # Create and show main window
    window = MainWindow(config)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
