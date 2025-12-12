"""Remote execution via SSH for deep node integration."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SSHExecutor:
    """Execute commands on remote nodes via SSH."""
    
    def __init__(self, user: str = None, key_file: str = None):
        self.user = user or "sysadmin"  # Default user
        self.key_file = key_file  # Optional explicit key
    
    async def execute(
        self,
        host: str,
        command: str,
        timeout: float = 30.0,
        cwd: Optional[str] = None
    ) -> Tuple[int, str, str]:
        """
        Execute a command on a remote host via SSH.
        
        Returns:
            (exit_code, stdout, stderr)
        """
        # Build SSH command
        ssh_cmd = ["ssh", "-o", "ConnectTimeout=5"]
        
        if self.key_file:
            ssh_cmd.extend(["-i", self.key_file])
        
        ssh_cmd.append(f"{self.user}@{host}")
        
        # Add directory change if specified
        if cwd:
            command = f"cd {cwd} && {command}"
        
        ssh_cmd.append(command)
        
        try:
            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            return (
                process.returncode,
                stdout.decode('utf-8', errors='replace'),
                stderr.decode('utf-8', errors='replace')
            )
            
        except asyncio.TimeoutError:
            logger.error(f"SSH command timed out on {host}: {command}")
            return (-1, "", "Command timed out")
        except Exception as e:
            logger.error(f"SSH execution failed on {host}: {e}")
            return (-1, "", str(e))
    
    async def execute_background(
        self,
        host: str,
        command: str,
        cwd: Optional[str] = None
    ) -> bool:
        """
        Execute a command in the background (doesn't wait for completion).
        Useful for starting daemons.
        """
        # Use nohup to keep process running after SSH disconnects
        bg_command = f"nohup {command} > /dev/null 2>&1 &"
        
        exit_code, stdout, stderr = await self.execute(
            host, bg_command, timeout=5.0, cwd=cwd
        )
        
        return exit_code == 0
    
    async def copy_file(
        self,
        host: str,
        local_path: str,
        remote_path: str,
        direction: str = "to"
    ) -> bool:
        """
        Copy file to/from remote host using scp.
        
        Args:
            direction: "to" (local -> remote) or "from" (remote -> local)
        """
        scp_cmd = ["scp", "-o", "ConnectTimeout=5"]
        
        if self.key_file:
            scp_cmd.extend(["-i", self.key_file])
        
        if direction == "to":
            scp_cmd.extend([local_path, f"{self.user}@{host}:{remote_path}"])
        else:
            scp_cmd.extend([f"{self.user}@{host}:{remote_path}", local_path])
        
        try:
            process = await asyncio.create_subprocess_exec(
                *scp_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            return process.returncode == 0
            
        except Exception as e:
            logger.error(f"SCP failed: {e}")
            return False
    
    async def check_process(self, host: str, process_name: str) -> bool:
        """Check if a process is running on remote host."""
        exit_code, stdout, stderr = await self.execute(
            host,
            f"pgrep -f {process_name}",
            timeout=5.0
        )
        return exit_code == 0 and stdout.strip() != ""
    
    async def get_system_info(self, host: str) -> Dict[str, str]:
        """Gather system information from remote host."""
        info = {}
        
        # Get CPU info
        exit_code, stdout, _ = await self.execute(
            host,
            "nproc",
            timeout=5.0
        )
        if exit_code == 0:
            info['cpu_cores'] = stdout.strip()
        
        # Get memory
        exit_code, stdout, _ = await self.execute(
            host,
            "free -h | grep Mem | awk '{print $2}'",
            timeout=5.0
        )
        if exit_code == 0:
            info['total_memory'] = stdout.strip()
        
        # Get GPU info (if available)
        exit_code, stdout, _ = await self.execute(
            host,
            "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'none'",
            timeout=5.0
        )
        if exit_code == 0:
            info['gpu'] = stdout.strip()
        
        # Get disk space
        exit_code, stdout, _ = await self.execute(
            host,
            "df -h / | tail -1 | awk '{print $4}'",
            timeout=5.0
        )
        if exit_code == 0:
            info['disk_available'] = stdout.strip()
        
        # Get load average
        exit_code, stdout, _ = await self.execute(
            host,
            "uptime | awk -F'load average:' '{print $2}' | awk '{print $1}'",
            timeout=5.0
        )
        if exit_code == 0:
            info['load_avg'] = stdout.strip().rstrip(',')
        
        return info
    
    async def rsync_directory(
        self,
        host: str,
        local_path: str,
        remote_path: str,
        direction: str = "to",
        exclude: Optional[List[str]] = None
    ) -> bool:
        """
        Sync directory to/from remote host using rsync.
        Much more efficient than copying individual files.
        """
        rsync_cmd = [
            "rsync",
            "-avz",  # archive, verbose, compress
            "--progress",
            "-e", "ssh -o ConnectTimeout=5"
        ]
        
        if self.key_file:
            rsync_cmd[-1] += f" -i {self.key_file}"
        
        # Add exclusions
        if exclude:
            for pattern in exclude:
                rsync_cmd.extend(["--exclude", pattern])
        
        if direction == "to":
            rsync_cmd.extend([local_path, f"{self.user}@{host}:{remote_path}"])
        else:
            rsync_cmd.extend([f"{self.user}@{host}:{remote_path}", local_path])
        
        try:
            process = await asyncio.create_subprocess_exec(
                *rsync_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            return process.returncode == 0
            
        except Exception as e:
            logger.error(f"Rsync failed: {e}")
            return False


class ClusterManager:
    """Manage a cluster of nodes via SSH."""
    
    def __init__(self, executor: SSHExecutor):
        self.executor = executor
    
    async def execute_on_all(
        self,
        hosts: List[str],
        command: str,
        parallel: bool = True,
        cwd: Optional[str] = None
    ) -> Dict[str, Tuple[int, str, str]]:
        """
        Execute command on multiple hosts.
        
        Returns:
            Dict mapping host to (exit_code, stdout, stderr)
        """
        if parallel:
            tasks = [
                self.executor.execute(host, command, cwd=cwd)
                for host in hosts
            ]
            results = await asyncio.gather(*tasks)
            return dict(zip(hosts, results))
        else:
            results = {}
            for host in hosts:
                results[host] = await self.executor.execute(host, command, cwd=cwd)
            return results
    
    async def deploy_code(
        self,
        hosts: List[str],
        local_path: str,
        remote_path: str
    ) -> Dict[str, bool]:
        """
        Deploy code to multiple nodes using rsync.
        """
        tasks = [
            self.executor.rsync_directory(
                host,
                local_path,
                remote_path,
                direction="to",
                exclude=[".venv", "__pycache__", "*.pyc", ".git", "logs"]
            )
            for host in hosts
        ]
        
        results = await asyncio.gather(*tasks)
        return dict(zip(hosts, results))
    
    async def start_daemon(
        self,
        host: str,
        app_path: str,
        config_file: str = "config.yaml"
    ) -> bool:
        """Start skeleton-daemon on a remote node."""
        command = (
            f"cd {app_path} && "
            f"source .venv/bin/activate && "
            f"skeleton-daemon --config {config_file}"
        )
        return await self.executor.execute_background(host, command, cwd=app_path)
    
    async def stop_daemon(self, host: str) -> bool:
        """Stop skeleton-daemon on a remote node."""
        exit_code, stdout, stderr = await self.executor.execute(
            host,
            "pkill -f skeleton-daemon"
        )
        return exit_code == 0
    
    async def restart_daemon(
        self,
        host: str,
        app_path: str,
        config_file: str = "config.yaml"
    ) -> bool:
        """Restart daemon on a remote node."""
        await self.stop_daemon(host)
        await asyncio.sleep(2)  # Give it time to stop
        return await self.start_daemon(host, app_path, config_file)
    
    async def check_daemon_status(self, hosts: List[str]) -> Dict[str, bool]:
        """Check if daemon is running on multiple hosts."""
        tasks = [
            self.executor.check_process(host, "skeleton-daemon")
            for host in hosts
        ]
        results = await asyncio.gather(*tasks)
        return dict(zip(hosts, results))
    
    async def collect_logs(
        self,
        host: str,
        log_path: str,
        local_dest: str,
        lines: int = 100
    ) -> bool:
        """Collect recent logs from remote node."""
        # Get last N lines from remote log
        exit_code, stdout, stderr = await self.executor.execute(
            host,
            f"tail -n {lines} {log_path}",
            timeout=10.0
        )
        
        if exit_code == 0:
            # Write to local file
            Path(local_dest).parent.mkdir(parents=True, exist_ok=True)
            with open(local_dest, 'w') as f:
                f.write(stdout)
            return True
        
        return False
    
    async def sync_models(
        self,
        source_host: str,
        target_hosts: List[str],
        models_path: str
    ) -> Dict[str, bool]:
        """
        Synchronize models from one node to others.
        Useful for distributing Vosk/Whisper/Piper models.
        """
        results = {}
        
        for target in target_hosts:
            if target == source_host:
                continue
            
            # Use SSH to rsync between remote hosts
            command = (
                f"rsync -avz --progress "
                f"{self.executor.user}@{source_host}:{models_path}/ "
                f"{models_path}/"
            )
            
            exit_code, stdout, stderr = await self.executor.execute(
                target,
                command,
                timeout=300.0  # Models can be large
            )
            
            results[target] = (exit_code == 0)
        
        return results
    
    async def execute_python_script(
        self,
        host: str,
        script_path: str,
        app_path: str,
        args: str = ""
    ) -> Tuple[int, str, str]:
        """
        Execute a Python script on remote node using the venv.
        """
        command = (
            f"cd {app_path} && "
            f"source .venv/bin/activate && "
            f"python {script_path} {args}"
        )
        return await self.executor.execute(host, command, timeout=300.0)
    
    async def health_check_all(self, hosts: List[str]) -> Dict[str, Dict[str, any]]:
        """
        Perform health check on all nodes.
        Returns system info and daemon status for each.
        """
        results = {}
        
        for host in hosts:
            info = await self.executor.get_system_info(host)
            daemon_running = await self.executor.check_process(host, "skeleton-daemon")
            
            results[host] = {
                **info,
                'daemon_running': daemon_running
            }
        
        return results
