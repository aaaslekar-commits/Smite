"""Core adapters for different tunnel types"""
from typing import Protocol, Dict, Any, Optional
from abc import ABC, abstractmethod
import subprocess
import json
import os
import psutil
import time
from pathlib import Path


class CoreAdapter(Protocol):
    """Protocol for core adapters"""
    name: str
    
    def apply(self, tunnel_id: str, spec: Dict[str, Any]) -> None:
        """Apply tunnel configuration"""
        ...
    
    def remove(self, tunnel_id: str) -> None:
        """Remove tunnel"""
        ...
    
    def status(self, tunnel_id: str) -> Dict[str, Any]:
        """Get tunnel status"""
        ...
    
    def get_usage_mb(self, tunnel_id: str) -> float:
        """Get usage in MB"""
        ...


class WireGuardAdapter:
    """WireGuard tunnel adapter"""
    name = "wireguard"
    
    def __init__(self):
        self.config_dir = Path("/etc/wireguard")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.active_interfaces = set()
    
    def apply(self, tunnel_id: str, spec: Dict[str, Any]):
        """Apply WireGuard tunnel"""
        config = f"""[Interface]
PrivateKey = {spec.get('private_key', '')}
Address = {spec.get('address', '10.0.0.1/24')}
ListenPort = {spec.get('listen_port', 51820)}

[Peer]
PublicKey = {spec.get('peer_public_key', '')}
AllowedIPs = {spec.get('allowed_ips', '0.0.0.0/0')}
Endpoint = {spec.get('endpoint', '')}
"""
        
        config_path = self.config_dir / f"{tunnel_id}.conf"
        with open(config_path, "w") as f:
            f.write(config)
        
        # Start wireguard
        try:
            result = subprocess.run(
                ["wg-quick", "up", str(config_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            self.active_interfaces.add(tunnel_id)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"WireGuard failed to start: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("WireGuard start timed out")
    
    def remove(self, tunnel_id: str):
        """Remove WireGuard tunnel"""
        config_path = self.config_dir / f"{tunnel_id}.conf"
        if config_path.exists():
            try:
                subprocess.run(
                    ["wg-quick", "down", str(config_path)],
                    check=False,
                    timeout=10,
                    capture_output=True
                )
            except:
                pass
            config_path.unlink()
            self.active_interfaces.discard(tunnel_id)
    
    def status(self, tunnel_id: str) -> Dict[str, Any]:
        """Get status"""
        config_path = self.config_dir / f"{tunnel_id}.conf"
        interface_name = f"wg-{tunnel_id}"[:15]  # wg-quick creates interfaces
        
        # Check if interface exists
        try:
            result = subprocess.run(
                ["ip", "link", "show", interface_name],
                capture_output=True,
                timeout=2
            )
            is_active = result.returncode == 0
        except:
            is_active = False
        
        return {
            "active": config_path.exists() and is_active,
            "type": "wireguard",
            "interface": interface_name if is_active else None
        }
    
    def get_usage_mb(self, tunnel_id: str) -> float:
        """Get usage in MB"""
        # TODO: Implement WireGuard usage tracking
        return 0.0


class RatholeAdapter:
    """Rathole reverse tunnel adapter"""
    name = "rathole"
    
    def __init__(self):
        self.config_dir = Path("/etc/smite-node/rathole")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.processes = {}  # Track running processes
        self.usage_tracking = {}  # Track cumulative usage per tunnel
    
    def apply(self, tunnel_id: str, spec: Dict[str, Any]):
        """Apply Rathole tunnel"""
        remote_addr = spec.get('remote_addr', '').strip()
        token = spec.get('token', '').strip()
        local_addr = spec.get('local_addr', '127.0.0.1:8080')
        
        # Validate required fields
        if not remote_addr:
            raise ValueError("Rathole requires 'remote_addr' (panel address) in spec")
        if not token:
            raise ValueError("Rathole requires 'token' in spec")
        
        config = f"""[client]
remote_addr = "{remote_addr}"
default_token = "{token}"

[client.services.{tunnel_id}]
local_addr = "{local_addr}"
"""
        
        config_path = self.config_dir / f"{tunnel_id}.toml"
        with open(config_path, "w") as f:
            f.write(config)
        
        # Start rathole
        try:
            proc = subprocess.Popen(
                ["/usr/local/bin/rathole", "-c", str(config_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.processes[tunnel_id] = proc
            time.sleep(0.5)
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode() if proc.stderr else "Unknown error"
                raise RuntimeError(f"rathole failed to start: {stderr}")
        except FileNotFoundError:
            proc = subprocess.Popen(
                ["rathole", "-c", str(config_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.processes[tunnel_id] = proc
            time.sleep(0.5)
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode() if proc.stderr else "Unknown error"
                raise RuntimeError(f"rathole failed to start: {stderr}")
    
    def remove(self, tunnel_id: str):
        """Remove Rathole tunnel"""
        config_path = self.config_dir / f"{tunnel_id}.toml"
        
        # Stop process if tracked
        if tunnel_id in self.processes:
            proc = self.processes[tunnel_id]
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            except:
                pass
            del self.processes[tunnel_id]
        
        # Also try pkill as fallback
        try:
            subprocess.run(["pkill", "-f", f"rathole.*{tunnel_id}"], check=False, timeout=3)
        except:
            pass
            
        if config_path.exists():
            config_path.unlink()
    
    def status(self, tunnel_id: str) -> Dict[str, Any]:
        """Get status"""
        config_path = self.config_dir / f"{tunnel_id}.toml"
        is_running = False
        
        if tunnel_id in self.processes:
            proc = self.processes[tunnel_id]
            is_running = proc.poll() is None
        
        return {
            "active": config_path.exists() and is_running,
            "type": "rathole",
            "config_exists": config_path.exists(),
            "process_running": is_running
        }
    
    def get_usage_mb(self, tunnel_id: str) -> float:
        """Get usage in MB - tracks cumulative network I/O"""
        if tunnel_id in self.processes:
            proc = self.processes[tunnel_id]
            try:
                proc_info = psutil.Process(proc.pid)
                # Get network connections to estimate traffic
                connections = proc_info.connections()
                
                # Try to get network I/O from connections and process I/O
                try:
                    io_counters = proc_info.io_counters()
                    # For network processes, most I/O is network-related
                    # Estimate network bytes (read_bytes + write_bytes for network process)
                    total_bytes = io_counters.read_bytes + io_counters.write_bytes
                    
                    # Track cumulative usage
                    if tunnel_id not in self.usage_tracking:
                        self.usage_tracking[tunnel_id] = 0.0
                    
                    # Update if we have new data (cumulative)
                    current_mb = total_bytes / (1024 * 1024)
                    if current_mb > self.usage_tracking[tunnel_id]:
                        self.usage_tracking[tunnel_id] = current_mb
                    
                    return self.usage_tracking[tunnel_id]
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, OSError):
                    # Return last known usage if process is gone
                    if tunnel_id in self.usage_tracking:
                        return self.usage_tracking[tunnel_id]
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, OSError):
                # Return last known usage if process is gone
                if tunnel_id in self.usage_tracking:
                    return self.usage_tracking[tunnel_id]
        return 0.0


class AdapterManager:
    """Manager for core adapters"""
    
    def __init__(self):
        self.adapters: Dict[str, CoreAdapter] = {
            "wireguard": WireGuardAdapter(),
            "rathole": RatholeAdapter(),
        }
        self.active_tunnels: Dict[str, CoreAdapter] = {}
        self.usage_tracking: Dict[str, float] = {}  # Track previous usage to calculate increments
    
    def get_adapter(self, tunnel_type: str) -> Optional[CoreAdapter]:
        """Get adapter for tunnel type"""
        return self.adapters.get(tunnel_type)
    
    async def apply_tunnel(self, tunnel_id: str, tunnel_type: str, spec: Dict[str, Any]):
        """Apply tunnel using appropriate adapter"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Applying tunnel {tunnel_id}: type={tunnel_type}")
        
        adapter = self.get_adapter(tunnel_type)
        if not adapter:
            error_msg = f"Unknown tunnel type: {tunnel_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Using adapter: {adapter.name}")
        adapter.apply(tunnel_id, spec)
        self.active_tunnels[tunnel_id] = adapter
        # Initialize usage tracking
        if tunnel_id not in self.usage_tracking:
            self.usage_tracking[tunnel_id] = 0.0
        logger.info(f"Tunnel {tunnel_id} applied successfully")
    
    async def remove_tunnel(self, tunnel_id: str):
        """Remove tunnel"""
        if tunnel_id in self.active_tunnels:
            adapter = self.active_tunnels[tunnel_id]
            adapter.remove(tunnel_id)
            del self.active_tunnels[tunnel_id]
        # Clean up usage tracking
        if tunnel_id in self.usage_tracking:
            del self.usage_tracking[tunnel_id]
    
    async def get_tunnel_status(self, tunnel_id: str) -> Dict[str, Any]:
        """Get tunnel status"""
        if tunnel_id in self.active_tunnels:
            adapter = self.active_tunnels[tunnel_id]
            return adapter.status(tunnel_id)
        return {"active": False}
    
    async def cleanup(self):
        """Cleanup all tunnels"""
        for tunnel_id in list(self.active_tunnels.keys()):
            await self.remove_tunnel(tunnel_id)

