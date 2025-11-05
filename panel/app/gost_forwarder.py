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
    
    def start_forward(self, tunnel_id: str, local_port: int, forward_to: str, tunnel_type: str = "tcp") -> bool:
        """
        Start forwarding using gost - forwards directly to target (no node)

        Args:
            tunnel_id: Unique tunnel identifier
            local_port: Port on panel to listen on
            forward_to: Target address:port (e.g., "127.0.0.1:9999" or "1.2.3.4:443")
            tunnel_type: Type of forwarding (tcp, udp, ws, grpc)

        Returns:
            True if started successfully
        """
        try:
            # Stop existing forward if any
            if tunnel_id in self.active_forwards:
                logger.warning(f"Forward for tunnel {tunnel_id} already exists, stopping it first")
                self.stop_forward(tunnel_id)
                # Wait a moment for port to be released
                time.sleep(0.5)
            
            # Build gost command based on tunnel type
            # Forward directly to target (forward_to format: "host:port")
            if tunnel_type == "tcp":
                # TCP forwarding using gost chain syntax (like Shifter): -L=tcp://:port/host:port
                # This syntax is more reliable for transparent TCP forwarding (e.g., VLESS)
                # Parse forward_to to get host and port
                if ":" in forward_to:
                    forward_host, forward_port = forward_to.rsplit(":", 1)
                else:
                    forward_host = forward_to
                    forward_port = "8080"
                # Use chain syntax: listen on local_port, forward to forward_host:forward_port
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=tcp://0.0.0.0:{local_port}/{forward_host}:{forward_port}"
                ]
            elif tunnel_type == "udp":
                # UDP forwarding using gost chain syntax: -L=udp://:port/host:port
                if ":" in forward_to:
                    forward_host, forward_port = forward_to.rsplit(":", 1)
                else:
                    forward_host = forward_to
                    forward_port = "8080"
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=udp://0.0.0.0:{local_port}/{forward_host}:{forward_port}"
                ]
            elif tunnel_type == "ws":
                # WebSocket forwarding: listen as WS, forward to TCP
                # For VLESS over WS, the client connects via WebSocket, but target is TCP
                # Use chain syntax: -L=ws://host:port/tcp://host:port
                if ":" in forward_to:
                    forward_host, forward_port = forward_to.rsplit(":", 1)
                else:
                    forward_host = forward_to
                    forward_port = "8080"
                # WebSocket on listen side, TCP on forward side
                # Simple chain syntax without path parameter
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=ws://0.0.0.0:{local_port}/tcp://{forward_host}:{forward_port}"
                ]
            elif tunnel_type == "grpc":
                # gRPC forwarding using chain syntax: -L=grpc://:port/host:port
                if ":" in forward_to:
                    forward_host, forward_port = forward_to.rsplit(":", 1)
                else:
                    forward_host = forward_to
                    forward_port = "8080"
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=grpc://0.0.0.0:{local_port}/{forward_host}:{forward_port}"
                ]
            elif tunnel_type == "tcpmux":
                # TCPMux forwarding using chain syntax: -L=tcpmux://:port/host:port
                # Note: tcpmux:// is plain TCP, no TLS. Use tcpmux+tls:// for TLS.
                if ":" in forward_to:
                    forward_host, forward_port = forward_to.rsplit(":", 1)
                else:
                    forward_host = forward_to
                    forward_port = "8080"
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=tcpmux://0.0.0.0:{local_port}/{forward_host}:{forward_port}"
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
                    error_msg = "gost binary not found at /usr/local/bin/gost or in PATH"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
            else:
                # Check if executable
                if not os.access(gost_binary, os.X_OK):
                    error_msg = f"gost binary at {gost_binary} is not executable"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
            
            cmd[0] = gost_binary
            logger.info(f"Starting gost: {' '.join(cmd)}")
            
            # Start gost process
            try:
                # Use log file for debugging (keep file open for subprocess)
                log_file = self.config_dir / f"gost_{tunnel_id}.log"
                # Ensure directory exists
                log_file.parent.mkdir(parents=True, exist_ok=True)
                log_f = open(log_file, 'w', buffering=1)  # Line buffered
                log_f.write(f"Starting gost with command: {' '.join(cmd)}\n")
                log_f.write(f"Tunnel ID: {tunnel_id}\n")
                log_f.write(f"Local port: {local_port}, Forward to: {forward_to}\n")
                log_f.flush()
                proc = subprocess.Popen(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,  # Combine stderr with stdout
                    cwd=str(self.config_dir),
                    start_new_session=True,  # Detach from parent process group
                    close_fds=False  # Don't close file descriptors
                )
                log_f.write(f"Process started with PID: {proc.pid}\n")
                log_f.flush()
                # Store file handle so we can close it later
                self.active_forwards[f"{tunnel_id}_log"] = log_f
                logger.info(f"Started gost process for tunnel {tunnel_id}, PID={proc.pid}")
            except Exception as e:
                error_msg = f"Failed to start gost process: {e}"
                logger.error(error_msg, exc_info=True)
                raise RuntimeError(error_msg)
            
            # Wait a moment to check if process started successfully
            time.sleep(1.5)  # Increased wait time
            poll_result = proc.poll()
            if poll_result is not None:
                # Process died immediately
                try:
                    # Read from log file
                    if log_file.exists():
                        with open(log_file, 'r') as f:
                            stderr = f.read()
                    else:
                        stderr = "Log file not found"
                    stdout = ""
                except Exception as e:
                    stderr = f"Could not read log file: {e}"
                    stdout = ""
                error_msg = f"gost failed to start (exit code: {poll_result}): {stderr[-500:] if len(stderr) > 500 else stderr or 'Unknown error'}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # Verify port is actually listening (check after a short delay)
            # Skip port check for UDP (uses SOCK_DGRAM, not SOCK_STREAM)
            if tunnel_type != "udp":
                time.sleep(0.5)
                import socket
                port_listening = False
                try:
                    # Try IPv4 first
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex(('127.0.0.1', local_port))
                    sock.close()
                    port_listening = (result == 0)
                    if not port_listening:
                        # Try IPv6 (gost might bind to IPv6)
                        try:
                            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                            sock.settimeout(1)
                            result = sock.connect_ex(('::1', local_port))
                            sock.close()
                            port_listening = (result == 0)
                        except:
                            pass
                    if not port_listening:
                        # Check again - sometimes it takes a moment
                        time.sleep(0.5)
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(1)
                        result = sock.connect_ex(('127.0.0.1', local_port))
                        sock.close()
                        if result == 0:
                            port_listening = True
                        else:
                            # Try IPv6 again
                            try:
                                sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                                sock.settimeout(1)
                                result = sock.connect_ex(('::1', local_port))
                                sock.close()
                                port_listening = (result == 0)
                            except:
                                pass
                        
                    # Check if process is still alive (most important check)
                    poll_result = proc.poll()
                    if poll_result is not None:
                        # Process died - try to read error from log
                        try:
                            if log_file.exists():
                                with open(log_file, 'r') as f:
                                    error_output = f.read()
                                error_msg = f"gost process died after startup (exit code: {poll_result}): {error_output[-500:] if len(error_output) > 500 else error_output}"
                            else:
                                error_msg = f"gost process died after startup (exit code: {poll_result}), log file not found"
                            logger.error(error_msg)
                            raise RuntimeError(error_msg)
                        except Exception as e:
                            error_msg = f"gost process died after startup (exit code: {poll_result}), could not read error: {e}"
                            logger.error(error_msg)
                            raise RuntimeError(error_msg)
                    elif not port_listening:
                        # Process is alive but port check failed - just warn, don't fail
                        logger.warning(f"Port {local_port} not listening after gost start (checked IPv4 and IPv6), but process is running. PID: {proc.pid}")
                except Exception as e:
                    logger.warning(f"Could not verify port {local_port} is listening: {e}")
                    # Still check if process is alive (most important)
                    poll_result = proc.poll()
                    if poll_result is not None:
                        error_msg = f"gost process died during port check (exit code: {poll_result})"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
            else:
                # For UDP, just verify process is running
                time.sleep(0.5)
                poll_result = proc.poll()
                if poll_result is not None:
                    # Try to read error from log
                    try:
                        if log_file.exists():
                            with open(log_file, 'r') as f:
                                error_output = f.read()
                            error_msg = f"gost UDP process died after startup (exit code: {poll_result}): {error_output[-500:] if len(error_output) > 500 else error_output}"
                        else:
                            error_msg = f"gost UDP process died after startup (exit code: {poll_result}), log file not found"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
                    except Exception as e:
                        error_msg = f"gost UDP process died after startup (exit code: {poll_result}), could not read error: {e}"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
            
            self.active_forwards[tunnel_id] = proc
            self.forward_configs[tunnel_id] = {
                "local_port": local_port,
                "forward_to": forward_to,
                "tunnel_type": tunnel_type
            }
            
            logger.info(f"Started gost forwarding for tunnel {tunnel_id}: {tunnel_type}://:{local_port} -> {forward_to}, PID={proc.pid}")
            return True
            
        except Exception as e:
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
                # Close log file if it exists
                log_key = f"{tunnel_id}_log"
                if log_key in self.active_forwards:
                    try:
                        self.active_forwards[log_key].close()
                    except:
                        pass
                    del self.active_forwards[log_key]
                logger.info(f"Stopped gost forwarding for tunnel {tunnel_id}")
        
        # Also kill any gost processes that might be using the port (safety cleanup)
        if tunnel_id in self.forward_configs:
            config = self.forward_configs[tunnel_id]
            local_port = config.get("local_port")
            if local_port:
                try:
                    # Try to kill any gost processes that might be using this port
                    # Use pkill to find and kill processes matching the pattern
                    subprocess.run(['pkill', '-f', f'gost.*{local_port}'], timeout=3, check=False, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                except Exception as e:
                    logger.debug(f"Could not cleanup port {local_port} (non-critical): {e}")
        
        if tunnel_id in self.forward_configs:
            del self.forward_configs[tunnel_id]
    
    def is_forwarding(self, tunnel_id: str) -> bool:
        """Check if forwarding is active for a tunnel"""
        if tunnel_id not in self.active_forwards:
            return False
        proc = self.active_forwards[tunnel_id]
        is_alive = proc.poll() is None
        if not is_alive and tunnel_id in self.forward_configs:
            # Process died, try to restart it
            logger.warning(f"Gost process for tunnel {tunnel_id} died, attempting restart...")
            try:
                config = self.forward_configs[tunnel_id]
                self.start_forward(
                    tunnel_id=tunnel_id,
                    local_port=config["local_port"],
                    forward_to=config["forward_to"],
                    tunnel_type=config["tunnel_type"]
                )
                return True
            except Exception as e:
                logger.error(f"Failed to restart gost for tunnel {tunnel_id}: {e}")
                return False
        return is_alive
    
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

