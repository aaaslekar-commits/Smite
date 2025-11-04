"""Gost-based forwarding service for stable TCP/UDP/WS/gRPC tunnels"""
import subprocess
import time
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class GostForwarder:
    """Manages TCP/UDP/WS/gRPC forwarding using gost"""
    
    def __init__(self):
        self.config_dir = Path("/app/data/gost")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.active_forwards: Dict[str, subprocess.Popen] = {}  # tunnel_id -> process
        self.forward_configs: Dict[str, dict] = {}  # tunnel_id -> config
    
    def start_forward(self, tunnel_id: str, local_port: int, node_address: str, remote_port: int, tunnel_type: str = "tcp") -> bool:
        """
        Start forwarding using gost

        Args:
            tunnel_id: Unique tunnel identifier
            local_port: Port on panel to listen on
            node_address: Node IP address (host only, no port)
            remote_port: Port on node to forward to
            tunnel_type: Type of forwarding (tcp, udp, ws, grpc)

        Returns:
            True if started successfully
        """
        import sys
        debug_print = lambda msg: print(f"GOST_FORWARDER: {msg}", file=sys.stderr, flush=True)
        debug_print(f"start_forward called: tunnel_id={tunnel_id}, local_port={local_port}, node_address={node_address}, remote_port={remote_port}, tunnel_type={tunnel_type}")
        try:
            # Stop existing forward if any
            if tunnel_id in self.active_forwards:
                logger.warning(f"Forward for tunnel {tunnel_id} already exists, stopping it first")
                self.stop_forward(tunnel_id)
            
            # Build gost command based on tunnel type
            if tunnel_type == "tcp":
                # TCP forwarding: gost -L=tcp://:local_port -F=tcp://node:remote_port
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=tcp://:{local_port}",
                    f"-F=tcp://{node_address}:{remote_port}"
                ]
            elif tunnel_type == "udp":
                # UDP forwarding: gost -L=udp://:local_port -F=udp://node:remote_port
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=udp://:{local_port}",
                    f"-F=udp://{node_address}:{remote_port}"
                ]
            elif tunnel_type == "ws":
                # WebSocket forwarding (no TLS): gost -L=ws://:local_port -F=tcp://node:remote_port
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=ws://:{local_port}",
                    f"-F=tcp://{node_address}:{remote_port}"
                ]
            elif tunnel_type == "grpc":
                # gRPC forwarding (no TLS): gost -L=grpc://:local_port -F=tcp://node:remote_port
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=grpc://:{local_port}",
                    f"-F=tcp://{node_address}:{remote_port}"
                ]
            else:
                raise ValueError(f"Unsupported tunnel type: {tunnel_type}")
            
            # Check if gost binary exists
            gost_binary = "/usr/local/bin/gost"
            import os
            if not os.path.exists(gost_binary):
                # Try system gost
                import shutil
                gost_binary = shutil.which("gost")
                if not gost_binary:
                    raise RuntimeError("gost binary not found at /usr/local/bin/gost or in PATH")
            
            cmd[0] = gost_binary
            debug_print(f"Command to execute: {' '.join(cmd)}")
            logger.info(f"Starting gost with command: {' '.join(cmd)}")
            
            # Start gost process
            try:
                debug_print(f"About to start subprocess.Popen with cmd={cmd}")
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(self.config_dir)
                )
                debug_print(f"subprocess.Popen returned, PID={proc.pid}")
            except Exception as e:
                error_msg = f"Failed to start gost process: {e}"
                debug_print(f"ERROR in subprocess.Popen: {error_msg}")
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # Wait a moment to check if process started successfully
            debug_print(f"Waiting 0.5s to check if process is still alive...")
            time.sleep(0.5)
            poll_result = proc.poll()
            debug_print(f"Process poll result: {poll_result} (None means still running)")
            if poll_result is not None:
                # Process died immediately
                debug_print(f"Process died immediately, exit code: {poll_result}")
                try:
                    stderr = proc.stderr.read().decode() if proc.stderr else "Unknown error"
                    stdout = proc.stdout.read().decode() if proc.stdout else ""
                    debug_print(f"stderr: {stderr}")
                    debug_print(f"stdout: {stdout}")
                except Exception as e:
                    stderr = f"Could not read error output: {e}"
                    stdout = ""
                    debug_print(f"Exception reading process output: {e}")
                error_msg = f"gost failed to start (exit code: {proc.returncode}): {stderr or stdout}"
                debug_print(f"ERROR: {error_msg}")
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            self.active_forwards[tunnel_id] = proc
            self.forward_configs[tunnel_id] = {
                "local_port": local_port,
                "node_address": node_address,
                "remote_port": remote_port,
                "tunnel_type": tunnel_type
            }
            
            debug_print(f"✅ Successfully started gost forwarding, PID={proc.pid}")
            logger.info(f"✅ Started gost forwarding for tunnel {tunnel_id}: {tunnel_type}://:{local_port} -> {node_address}:{remote_port}")
            logger.info(f"Gost process PID: {proc.pid}")
            return True
            
        except Exception as e:
            import traceback
            debug_print(f"EXCEPTION in start_forward: {e}")
            debug_print(f"Traceback: {traceback.format_exc()}")
            logger.error(f"Failed to start gost forwarding for tunnel {tunnel_id}: {e}")
            raise
    
    def stop_forward(self, tunnel_id: str):
        """Stop forwarding for a tunnel"""
        if tunnel_id in self.active_forwards:
            proc = self.active_forwards[tunnel_id]
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            except Exception as e:
                logger.warning(f"Error stopping gost forward for tunnel {tunnel_id}: {e}")
            finally:
                del self.active_forwards[tunnel_id]
                logger.info(f"Stopped gost forwarding for tunnel {tunnel_id}")
        
        if tunnel_id in self.forward_configs:
            del self.forward_configs[tunnel_id]
    
    def is_forwarding(self, tunnel_id: str) -> bool:
        """Check if forwarding is active for a tunnel"""
        if tunnel_id not in self.active_forwards:
            return False
        proc = self.active_forwards[tunnel_id]
        return proc.poll() is None
    
    def get_forwarding_tunnels(self) -> list:
        """Get list of tunnel IDs with active forwarding"""
        # Filter out dead processes
        active = []
        for tunnel_id, proc in list(self.active_forwards.items()):
            if proc.poll() is None:
                active.append(tunnel_id)
            else:
                # Clean up dead process
                del self.active_forwards[tunnel_id]
                if tunnel_id in self.forward_configs:
                    del self.forward_configs[tunnel_id]
        return active
    
    def cleanup_all(self):
        """Stop all forwarding"""
        tunnel_ids = list(self.active_forwards.keys())
        for tunnel_id in tunnel_ids:
            self.stop_forward(tunnel_id)


# Global forwarder instance
gost_forwarder = GostForwarder()

