"""Gost-based forwarding service for stable tunnel protocols."""
import subprocess
import time
import logging
from pathlib import Path
from typing import Dict, Optional

from app.utils import parse_address_port, format_address_port

logger = logging.getLogger(__name__)


class GostForwarder:
    """Manages forwarding using gost."""
    
    def __init__(self):
        self.config_dir = Path("/app/data/gost")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.active_forwards: Dict[str, subprocess.Popen] = {}
        self.forward_configs: Dict[str, dict] = {}
    
    def start_forward(self, tunnel_id: str, local_port: int, forward_to: str, tunnel_type: str = "tcp", path: str = None, use_ipv6: bool = False) -> bool:
        """
        Start forwarding using gost - forwards directly to target (no node)

        Args:
            tunnel_id: Unique tunnel identifier
            local_port: Port on panel to listen on
            forward_to: Target address:port (e.g., "127.0.0.1:9999" or "[2001:db8::1]:443")
            tunnel_type: Type of forwarding (tcp, udp, ws, grpc, tcpmux, dns, icmp, tls, kcp)
            path: Optional path for WS tunnels (ignored, kept for compatibility)
            use_ipv6: Whether to use IPv6 for listening (default: False for IPv4)

        Returns:
            True if started successfully
        """
        try:
            if tunnel_id in self.active_forwards:
                logger.warning(f"Forward for tunnel {tunnel_id} already exists, stopping it first")
                self.stop_forward(tunnel_id)
                time.sleep(0.5)
            
            forward_host, forward_port, forward_is_ipv6 = parse_address_port(forward_to)
            if forward_port is None:
                forward_port = 8080
            
            target_addr = format_address_port(forward_host, forward_port)
            
            if use_ipv6:
                listen_addr = f"[::]:{local_port}"
            else:
                listen_addr = f"0.0.0.0:{local_port}"
            
            if tunnel_type == "tcp":
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=tcp://{listen_addr}/{target_addr}"
                ]
            elif tunnel_type == "udp":
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=udp://{listen_addr}/{target_addr}"
                ]
            elif tunnel_type == "ws":
                import socket
                try:
                    if use_ipv6:
                        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
                        s.connect(("2001:4860:4860::8888", 80))
                        bind_ip = s.getsockname()[0]
                    else:
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s.connect(("8.8.8.8", 80))
                        bind_ip = s.getsockname()[0]
                    s.close()
                except Exception:
                    bind_ip = "[::]" if use_ipv6 else "0.0.0.0"
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=ws://{bind_ip}:{local_port}/tcp://{target_addr}"
                ]
            elif tunnel_type == "grpc":
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=grpc://{listen_addr}/{target_addr}"
                ]
            elif tunnel_type == "tcpmux":
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=tcpmux://{listen_addr}/{target_addr}"
                ]
            elif tunnel_type == "dns":
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=dns://{listen_addr}/{target_addr}"
                ]
            elif tunnel_type == "icmp":
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=icmp://{listen_addr}/{target_addr}"
                ]
            elif tunnel_type == "tls":
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=tls://{listen_addr}/{target_addr}"
                ]
            elif tunnel_type == "kcp":
                cmd = [
                    "/usr/local/bin/gost",
                    f"-L=kcp://{listen_addr}/{target_addr}"
                ]
            else:
                raise ValueError(f"Unsupported tunnel type: {tunnel_type}")
            
            gost_binary = "/usr/local/bin/gost"
            import os
            if not os.path.exists(gost_binary):
                import shutil
                gost_binary = shutil.which("gost")
                if not gost_binary:
                    error_msg = "gost binary not found at /usr/local/bin/gost or in PATH"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
            else:
                if not os.access(gost_binary, os.X_OK):
                    error_msg = f"gost binary at {gost_binary} is not executable"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
            
            cmd[0] = gost_binary
            logger.info(f"Starting gost: {' '.join(cmd)}")
            
            try:
                log_file = self.config_dir / f"gost_{tunnel_id}.log"
                log_file.parent.mkdir(parents=True, exist_ok=True)
                log_f = open(log_file, 'w', buffering=1)
                log_f.write(f"Starting gost with command: {' '.join(cmd)}\n")
                log_f.write(f"Tunnel ID: {tunnel_id}\n")
                log_f.write(f"Local port: {local_port}, Forward to: {forward_to}\n")
                log_f.flush()
                proc = subprocess.Popen(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    cwd=str(self.config_dir),
                    start_new_session=True,
                    close_fds=False
                )
                log_f.write(f"Process started with PID: {proc.pid}\n")
                log_f.flush()
                self.active_forwards[f"{tunnel_id}_log"] = log_f
                logger.info(f"Started gost process for tunnel {tunnel_id}, PID={proc.pid}")
            except Exception as e:
                error_msg = f"Failed to start gost process: {e}"
                logger.error(error_msg, exc_info=True)
                raise RuntimeError(error_msg)
            
            time.sleep(1.5)
            poll_result = proc.poll()
            if poll_result is not None:
                try:
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
            
            if tunnel_type != "udp":
                time.sleep(0.5)
                poll_result = proc.poll()
                if poll_result is not None:
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
                
                if tunnel_type != "ws":
                    import socket
                    port_listening = False
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(1)
                        result = sock.connect_ex(('127.0.0.1', local_port))
                        sock.close()
                        port_listening = (result == 0)
                        if not port_listening:
                            try:
                                sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                                sock.settimeout(1)
                                result = sock.connect_ex(('::1', local_port))
                                sock.close()
                                port_listening = (result == 0)
                            except:
                                pass
                        if not port_listening:
                            time.sleep(0.5)
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(1)
                            result = sock.connect_ex(('127.0.0.1', local_port))
                            sock.close()
                            if result == 0:
                                port_listening = True
                            else:
                                try:
                                    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                                    sock.settimeout(1)
                                    result = sock.connect_ex(('::1', local_port))
                                    sock.close()
                                    port_listening = (result == 0)
                                except:
                                    pass
                        
                        poll_result = proc.poll()
                        if poll_result is not None:
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
                            logger.warning(f"Port {local_port} not listening after gost start (checked IPv4 and IPv6), but process is running. PID: {proc.pid}")
                    except Exception as e:
                        logger.warning(f"Could not verify port {local_port} is listening: {e}")
                        poll_result = proc.poll()
                        if poll_result is not None:
                            error_msg = f"gost process died during port check (exit code: {poll_result})"
                            logger.error(error_msg)
                            raise RuntimeError(error_msg)
                else:
                    logger.info(f"WS tunnel on port {local_port}: skipping port verification (WebSocket requires handshake)")
            else:
                time.sleep(0.5)
                poll_result = proc.poll()
                if poll_result is not None:
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
                log_key = f"{tunnel_id}_log"
                if log_key in self.active_forwards:
                    try:
                        self.active_forwards[log_key].close()
                    except:
                        pass
                    del self.active_forwards[log_key]
                logger.info(f"Stopped gost forwarding for tunnel {tunnel_id}")
        
        if tunnel_id in self.forward_configs:
            config = self.forward_configs[tunnel_id]
            local_port = config.get("local_port")
            if local_port:
                try:
                    subprocess.run(['pkill', '-f', f'gost.*{local_port}'], timeout=3, check=False, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                except Exception as e:
                    pass
        
        if tunnel_id in self.forward_configs:
            del self.forward_configs[tunnel_id]
    
    def is_forwarding(self, tunnel_id: str) -> bool:
        """Check if forwarding is active for a tunnel"""
        if tunnel_id not in self.active_forwards:
            return False
        proc = self.active_forwards[tunnel_id]
        is_alive = proc.poll() is None
        if not is_alive and tunnel_id in self.forward_configs:
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
        active = []
        for tunnel_id, proc in list(self.active_forwards.items()):
            if proc.poll() is None:
                active.append(tunnel_id)
            else:
                del self.active_forwards[tunnel_id]
                if tunnel_id in self.forward_configs:
                    del self.forward_configs[tunnel_id]
        return active
    
    def cleanup_all(self):
        """Stop all forwarding"""
        tunnel_ids = list(self.active_forwards.keys())
        for tunnel_id in tunnel_ids:
            self.stop_forward(tunnel_id)


gost_forwarder = GostForwarder()

