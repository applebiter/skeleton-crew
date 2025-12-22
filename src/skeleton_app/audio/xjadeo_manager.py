"""
xjadeo video player manager.

Manages xjadeo processes for JACK transport-synced video playback.

When sync_to_jack=True (default), xjadeo automatically follows JACK transport.
This means when you use TransportAgent/TransportCoordinator to control JACK
transport across multiple machines, all xjadeo instances will stay in sync.

Example workflow for distributed recording:
    1. Each musician launches xjadeo with the same video file
    2. Each musician's TransportAgent is running
    3. Director's TransportCoordinator sends locate_and_start command
    4. All JACK transports start in sync
    5. All xjadeo instances show the same frame simultaneously
    
See TRANSPORT_COORDINATION.md for details.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class XjadeoInstance:
    """Represents a running xjadeo instance."""
    process: subprocess.Popen
    file_path: Path
    instance_id: str
    fullscreen: bool = False
    window_position: Optional[str] = None


class XjadeoManager:
    """
    Manages xjadeo video player instances.
    
    Can launch multiple xjadeo windows for multi-monitor setups,
    all synchronized to JACK transport.
    """
    
    def __init__(self, xjadeo_path: str = "xjadeo"):
        """
        Initialize xjadeo manager.
        
        Args:
            xjadeo_path: Path to xjadeo executable
        """
        self.xjadeo_path = xjadeo_path
        self.instances: Dict[str, XjadeoInstance] = {}
        
        # Check if xjadeo is available
        if not self._check_available():
            logger.warning("xjadeo not found in PATH")
    
    def _check_available(self) -> bool:
        """Check if xjadeo is available."""
        try:
            result = subprocess.run(
                [self.xjadeo_path, "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def is_available(self) -> bool:
        """Check if xjadeo is available."""
        return self._check_available()
    
    def launch(self,
               file_path: Path,
               instance_id: Optional[str] = None,
               fullscreen: bool = False,
               window_position: Optional[str] = None,
               window_size: Optional[str] = None,
               sync_to_jack: bool = True,
               show_osd: bool = True,
               show_timecode: bool = True,
               offset_ms: int = 0) -> str:
        """
        Launch xjadeo video player.
        
        Args:
            file_path: Path to video file
            instance_id: Unique identifier for this instance
            fullscreen: Start in fullscreen mode
            window_position: Window position (e.g., "+100+100")
            window_size: Window size (e.g., "1920x1080")
            sync_to_jack: Sync to JACK transport
            show_osd: Show on-screen display
            show_timecode: Show timecode overlay
            offset_ms: A/V offset in milliseconds
        
        Returns:
            Instance ID
        
        Raises:
            RuntimeError: If xjadeo fails to start
            FileNotFoundError: If video file doesn't exist
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Video file not found: {file_path}")
        
        # Generate instance ID if not provided
        if instance_id is None:
            instance_id = f"xjadeo_{len(self.instances)}"
        
        # Check if instance already exists
        if instance_id in self.instances:
            logger.warning(f"Instance {instance_id} already running, stopping first")
            self.stop(instance_id)
        
        # Build command
        cmd = [self.xjadeo_path]
        
        # Audio via JACK
        cmd.extend(["-A", "jack"])
        
        # Sync to JACK transport
        if sync_to_jack:
            cmd.append("-S")
        
        # Fullscreen
        if fullscreen:
            cmd.append("-f")
        
        # Window position
        if window_position:
            cmd.extend(["-g", window_position])
        
        # Window size
        if window_size:
            cmd.extend(["-s", window_size])
        
        # OSD
        if show_osd:
            cmd.append("-O")
            if show_timecode:
                cmd.extend(["-m", "smpte"])
        
        # A/V offset
        if offset_ms != 0:
            cmd.extend(["-o", str(offset_ms)])
        
        # File to play
        cmd.append(str(file_path))
        
        logger.info(f"Launching xjadeo [{instance_id}]: {' '.join(cmd)}")
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            instance = XjadeoInstance(
                process=process,
                file_path=file_path,
                instance_id=instance_id,
                fullscreen=fullscreen,
                window_position=window_position,
            )
            
            self.instances[instance_id] = instance
            logger.info(f"xjadeo started [{instance_id}] (PID: {process.pid})")
            
            return instance_id
            
        except Exception as e:
            logger.error(f"Failed to start xjadeo: {e}")
            raise RuntimeError(f"Failed to start xjadeo: {e}") from e
    
    def stop(self, instance_id: str):
        """
        Stop a specific xjadeo instance.
        
        Args:
            instance_id: Instance to stop
        """
        if instance_id not in self.instances:
            logger.warning(f"Instance {instance_id} not found")
            return
        
        instance = self.instances[instance_id]
        
        if instance.process.poll() is None:
            logger.info(f"Stopping xjadeo [{instance_id}] (PID: {instance.process.pid})")
            instance.process.terminate()
            
            try:
                instance.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"xjadeo [{instance_id}] did not terminate, killing")
                instance.process.kill()
        
        del self.instances[instance_id]
    
    def stop_all(self):
        """Stop all xjadeo instances."""
        instance_ids = list(self.instances.keys())
        for instance_id in instance_ids:
            self.stop(instance_id)
    
    def is_running(self, instance_id: str) -> bool:
        """
        Check if an instance is running.
        
        Args:
            instance_id: Instance to check
        
        Returns:
            True if running, False otherwise
        """
        if instance_id not in self.instances:
            return False
        
        instance = self.instances[instance_id]
        return instance.process.poll() is None
    
    def get_instances(self) -> List[str]:
        """
        Get list of running instance IDs.
        
        Returns:
            List of instance IDs
        """
        return list(self.instances.keys())
    
    def get_instance_info(self, instance_id: str) -> Optional[Dict]:
        """
        Get information about an instance.
        
        Args:
            instance_id: Instance ID
        
        Returns:
            Dictionary with instance info, or None if not found
        """
        if instance_id not in self.instances:
            return None
        
        instance = self.instances[instance_id]
        return {
            "instance_id": instance.instance_id,
            "file_path": str(instance.file_path),
            "pid": instance.process.pid,
            "running": instance.process.poll() is None,
            "fullscreen": instance.fullscreen,
            "window_position": instance.window_position,
        }
    
    def __del__(self):
        """Cleanup: stop all xjadeo instances."""
        self.stop_all()
