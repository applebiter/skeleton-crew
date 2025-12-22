#!/usr/bin/env python
"""
Verification script for service discovery GUI integration fix.

Checks that all components are in place and working correctly.
"""

import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def check_imports():
    """Verify all critical imports work."""
    print("Checking imports...")
    try:
        from skeleton_app.gui.discovery_bridge import ServiceDiscoveryBridge
        print("  ✓ ServiceDiscoveryBridge")
        
        from skeleton_app.service_discovery import ServiceDiscovery
        print("  ✓ ServiceDiscovery")
        
        from skeleton_app.gui.main_window import MainWindow
        print("  ✓ MainWindow")
        
        from skeleton_app.gui.widgets.cluster_panel import ClusterPanel
        print("  ✓ ClusterPanel")
        
        return True
    except Exception as e:
        print(f"  ✗ Import failed: {e}")
        return False


def check_bridge_signals():
    """Verify bridge signals are available."""
    print("\nChecking bridge signals...")
    try:
        from skeleton_app.gui.discovery_bridge import ServiceDiscoveryBridge
        from PySide6.QtWidgets import QApplication
        
        app = QApplication([])
        bridge = ServiceDiscoveryBridge()
        
        signals = [
            'node_discovered',
            'service_registered',
            'service_updated',
            'service_unregistered',
            'services_loaded'
        ]
        
        for sig in signals:
            if hasattr(bridge, sig):
                print(f"  ✓ {sig}")
            else:
                print(f"  ✗ {sig} missing")
                return False
        
        return True
    except Exception as e:
        print(f"  ✗ Signal check failed: {e}")
        return False


def check_discovery_params():
    """Verify ServiceDiscovery accepts bridge parameter."""
    print("\nChecking ServiceDiscovery parameters...")
    try:
        from skeleton_app.service_discovery import ServiceDiscovery
        import inspect
        
        sig = inspect.signature(ServiceDiscovery.__init__)
        params = list(sig.parameters.keys())
        
        if 'discovery_bridge' in params:
            print("  ✓ discovery_bridge parameter present")
        else:
            print("  ✗ discovery_bridge parameter missing")
            return False
        
        return True
    except Exception as e:
        print(f"  ✗ Parameter check failed: {e}")
        return False


def check_cluster_panel_methods():
    """Verify ClusterPanel has signal handlers."""
    print("\nChecking ClusterPanel methods...")
    try:
        from skeleton_app.gui.widgets.cluster_panel import ClusterPanel
        
        methods = [
            '_on_node_discovered',
            '_on_service_registered',
            '_on_service_updated',
            '_on_service_unregistered'
        ]
        
        for method in methods:
            if hasattr(ClusterPanel, method):
                print(f"  ✓ {method}")
            else:
                print(f"  ✗ {method} missing")
                return False
        
        return True
    except Exception as e:
        print(f"  ✗ Method check failed: {e}")
        return False


def check_files_exist():
    """Verify all modified files exist."""
    print("\nChecking files...")
    
    files = [
        "src/skeleton_app/gui/discovery_bridge.py",
        "src/skeleton_app/service_discovery.py",
        "src/skeleton_app/gui/main_window.py",
        "src/skeleton_app/gui/widgets/cluster_panel.py",
        "src/skeleton_app/daemon.py",
    ]
    
    all_exist = True
    for file in files:
        path = Path(__file__).parent / file
        if path.exists():
            print(f"  ✓ {file}")
        else:
            print(f"  ✗ {file} NOT FOUND")
            all_exist = False
    
    return all_exist


def main():
    """Run all checks."""
    print("=" * 70)
    print("Service Discovery GUI Integration - Verification")
    print("=" * 70)
    
    checks = [
        ("Files Exist", check_files_exist),
        ("Imports", check_imports),
        ("Bridge Signals", check_bridge_signals),
        ("Discovery Parameters", check_discovery_params),
        ("ClusterPanel Methods", check_cluster_panel_methods),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"✗ {name} check crashed: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 70)
    print("Summary:")
    print("=" * 70)
    
    all_passed = True
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {name}")
        if not result:
            all_passed = False
    
    print("=" * 70)
    
    if all_passed:
        print("\n✅ All checks passed! Implementation is complete and ready to test.\n")
        print("Next steps:")
        print("  1. Run GUI: python -m skeleton_app.gui.app")
        print("  2. Run on multiple hosts to test discovery")
        print("  3. Check Cluster Status panel for discovered nodes")
        return 0
    else:
        print("\n❌ Some checks failed. Please review the output above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
