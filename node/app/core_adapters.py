"""Core adapters for different tunnel types"""
from typing import Protocol, Dict, Any, Optional, List
import subprocess
import os
import psutil
import time
from pathlib import Path
import shutil
def parse_address_port(address_str: str):
    """Parse address:port string, returns (host, port, is_ipv6)"""
    import re
    import ipaddress
    
    if not address_str:
        return ("", None, False)
    
    address_str = address_str.strip()
    
    # Check for IPv6 address in brackets: [2001:db8::1]:8080
    ipv6_bracket_match = re.match(r'^\[([^\]]+)\](?::(\d+))?$', address_str)
    if ipv6_bracket_match:
        host = ipv6_bracket_match.group(1)
        port_str = ipv6_bracket_match.group(2)
        port = int(port_str) if port_str else None
        return (host, port, True)
    
    # Check if it's a bare IPv6 address
    try:
        ipaddress.IPv6Address(address_str)
        return (address_str, None, True)
    except (ValueError, ipaddress.AddressValueError):
        pass
    
    # For IPv4 or hostname with port, split on last colon
    if ":" in address_str:
        parts = address_str.rsplit(":", 1)
        if len(parts) == 2:
            host_part = parts[0]
            port_str = parts[1]
            
            # Check if host_part is actually an IPv6 address
            try:
                ipaddress.IPv6Address(host_part)
                return (host_part, int(port_str), True)
            except (ValueError, ipaddress.AddressValueError):
                try:
                    port = int(port_str)
                    return (host_part, port, False)
                except ValueError:
                    return (address_str, None, False)
    
    # No port specified
    return (address_str, None, False)


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


class RatholeAdapter:
    """Rathole reverse tunnel adapter"""
    name = "rathole"
    
    def __init__(self):
        self.config_dir = Path("/etc/smite-node/rathole")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.processes = {}
    
    def apply(self, tunnel_id: str, spec: Dict[str, Any]):
        """Apply Rathole tunnel"""
        remote_addr = spec.get('remote_addr', '').strip()
        token = spec.get('token', '').strip()
        local_addr = spec.get('local_addr', '127.0.0.1:8080')
        
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


class BackhaulAdapter:
    """Backhaul reverse tunnel adapter"""
    name = "backhaul"

    CLIENT_OPTION_KEYS = [
        "connection_pool",
        "retry_interval",
        "nodelay",
        "keepalive_period",
        "log_level",
        "pprof",
        "mux_session",
        "mux_version",
        "mux_framesize",
        "mux_recievebuffer",
        "mux_streambuffer",
        "sniffer",
        "web_port",
        "sniffer_log",
        "dial_timeout",
        "aggressive_pool",
        "edge_ip",
        "skip_optz",
        "mss",
        "so_rcvbuf",
        "so_sndbuf",
        "accept_udp",
    ]

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        binary_path: Optional[Path] = None,
    ):
        resolved_config = config_dir or Path(
            os.environ.get("SMITE_BACKHAUL_CLIENT_DIR", "/etc/smite-node/backhaul")
        )
        self.config_dir = Path(resolved_config)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.processes: Dict[str, subprocess.Popen] = {}
        self.log_handles: Dict[str, Any] = {}
        default_binary = binary_path or Path(
            os.environ.get("BACKHAUL_CLIENT_BINARY", "/usr/local/bin/backhaul")
        )
        self.binary_candidates = [
            Path(default_binary),
            Path("backhaul"),
        ]

    def apply(self, tunnel_id: str, spec: Dict[str, Any]):
        remote_addr = spec.get("remote_addr") or spec.get("control_addr") or spec.get("bind_addr")
        if not remote_addr:
            raise ValueError("Backhaul requires 'remote_addr' in spec")

        transport = (spec.get("transport") or spec.get("type") or "tcp").lower()
        if transport not in {"tcp", "udp", "ws", "wsmux", "tcpmux"}:
            raise ValueError(f"Unsupported Backhaul transport '{transport}'")
        client_options = dict(spec.get("client_options") or {})

        config_dict: Dict[str, Any] = {
            "remote_addr": remote_addr,
            "transport": transport,
        }

        token = spec.get("token") or client_options.get("token")
        if token:
            config_dict["token"] = token

        for key in self.CLIENT_OPTION_KEYS:
            value = client_options.get(key)
            if value is None or value == "":
                value = spec.get(key)
            if value is None or value == "":
                continue
            config_dict[key] = value

        if "connection_pool" not in config_dict:
            config_dict["connection_pool"] = 4
        if "retry_interval" not in config_dict:
            config_dict["retry_interval"] = 3
        if "dial_timeout" not in config_dict:
            config_dict["dial_timeout"] = 10

        if spec.get("accept_udp") and transport in {"tcp", "tcpmux"}:
            config_dict["accept_udp"] = True

        config_path = self.config_dir / f"{tunnel_id}.toml"
        config_path.write_text(self._render_toml({"client": config_dict}), encoding="utf-8")

        binary_path = self._resolve_binary_path()

        log_path = self.config_dir / f"backhaul_{tunnel_id}.log"
        log_fh = log_path.open("w", buffering=1)
        log_fh.write(f"Starting Backhaul client for tunnel {tunnel_id}\n")
        log_fh.write(self._render_toml({"client": config_dict}))
        log_fh.flush()

        try:
            proc = subprocess.Popen(
                [str(binary_path), "-c", str(config_path)],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
        except Exception:
            log_fh.close()
            raise

        time.sleep(0.5)
        if proc.poll() is not None:
            error_output = ""
            try:
                error_output = log_path.read_text(encoding="utf-8")[-1000:]
            except Exception:
                pass
            log_fh.close()
            raise RuntimeError(f"backhaul failed to start: {error_output}")

        self.processes[tunnel_id] = proc
        self.log_handles[tunnel_id] = log_fh

    def remove(self, tunnel_id: str):
        config_path = self.config_dir / f"{tunnel_id}.toml"
        
        if tunnel_id in self.processes:
            proc = self.processes[tunnel_id]
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            except Exception:
                pass
            del self.processes[tunnel_id]
        if tunnel_id in self.log_handles:
            try:
                self.log_handles[tunnel_id].close()
            except Exception:
                pass
            del self.log_handles[tunnel_id]

        if config_path.exists():
            try:
                config_path.unlink()
            except Exception:
                pass

    def status(self, tunnel_id: str) -> Dict[str, Any]:
        config_path = self.config_dir / f"{tunnel_id}.toml"
        proc = self.processes.get(tunnel_id)
        is_running = proc is not None and proc.poll() is None
        return {
            "active": config_path.exists() and is_running,
            "type": "backhaul",
            "config_exists": config_path.exists(),
            "process_running": is_running,
        }

    def _render_toml(self, data: Dict[str, Dict[str, Any]]) -> str:
        def format_value(value: Any) -> str:
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (int, float)):
                return str(value)
            if isinstance(value, list):
                if not value:
                    return "[]"
                rendered = ",\n  ".join(f"\"{str(item)}\"" for item in value)
                return "[\n  " + rendered + "\n]"
            value_str = str(value).replace("\\", "\\\\").replace('"', '\\"')
            return f"\"{value_str}\""

        lines: List[str] = []
        for section, values in data.items():
            lines.append(f"[{section}]")
            for key, val in values.items():
                if val is None:
                    continue
                lines.append(f"{key} = {format_value(val)}")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _resolve_binary_path(self) -> Path:
        for candidate in self.binary_candidates:
            if candidate.exists():
                return candidate

        resolved = shutil.which("backhaul")
        if resolved:
            return Path(resolved)

        raise FileNotFoundError(
            "Backhaul binary not found. Expected at BACKHAUL_CLIENT_BINARY, '/usr/local/bin/backhaul', or in PATH."
        )


class ChiselAdapter:
    """Chisel reverse tunnel adapter"""
    name = "chisel"
    
    def __init__(self):
        self.config_dir = Path("/etc/smite-node/chisel")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.processes = {}
        self.log_handles = {}  # Store log file handles to keep them open
    
    def _resolve_binary_path(self) -> Path:
        """Resolve chisel binary path"""
        # Check environment variable first
        env_path = os.environ.get("CHISEL_BINARY")
        if env_path:
            resolved = Path(env_path)
            if resolved.exists() and resolved.is_file():
                return resolved
        
        # Check common locations
        common_paths = [
            Path("/usr/local/bin/chisel"),
            Path("/usr/bin/chisel"),
            Path("/opt/chisel/chisel"),
        ]
        
        for path in common_paths:
            if path.exists() and path.is_file():
                return path
        
        # Check PATH
        resolved = shutil.which("chisel")
        if resolved:
            return Path(resolved)
        
        raise FileNotFoundError(
            "Chisel binary not found. Expected at CHISEL_BINARY, '/usr/local/bin/chisel', or in PATH."
        )
    
    def apply(self, tunnel_id: str, spec: Dict[str, Any]):
        """Apply Chisel tunnel"""
        server_url = spec.get('server_url', '').strip()
        # reverse_port is where the reverse tunnel endpoint listens on the server
        # This should be different from the server control port in server_url
        reverse_port = spec.get('reverse_port') or spec.get('remote_port') or spec.get('listen_port') or spec.get('server_port')
        local_addr = spec.get('local_addr')
        
        if not server_url:
            raise ValueError("Chisel requires 'server_url' (panel server address) in spec")
        if not reverse_port:
            raise ValueError("Chisel requires 'reverse_port', 'remote_port', or 'listen_port' in spec")
        
        # If local_addr is not provided, default to same port as reverse_port on localhost
        if not local_addr:
            local_addr = f"127.0.0.1:{reverse_port}"
            logger.warning(f"Chisel tunnel {tunnel_id}: local_addr not specified, defaulting to {local_addr}")
        
        # Parse local_addr to get host and port
        host, port, is_ipv6 = parse_address_port(local_addr)
        if not port:
            raise ValueError(f"Invalid local_addr format: {local_addr} (port required)")
        
        # Chisel reverse tunnel format: R:<reverse_port>:<local_host>:<local_port>
        # Example: R:8080:127.0.0.1:8080 or R:8080:[::1]:8080 for IPv6
        # This means: forward connections to reverse_port on server to local_host:local_port on node
        # IMPORTANT: reverse_port should be different from the server control port in server_url
        # But if they're the same, Chisel should handle it (though it may cause conflicts)
        # For IPv6 addresses, Chisel requires brackets around the host
        if is_ipv6:
            reverse_spec = f"R:{reverse_port}:[{host}]:{port}"
        else:
            reverse_spec = f"R:{reverse_port}:{host}:{port}"
        logger.info(f"Chisel tunnel {tunnel_id}: reverse_spec={reverse_spec}, server_url={server_url}")
        
        # Build chisel client command
        # chisel client <server_url> <reverse_spec>
        binary_path = self._resolve_binary_path()
        cmd = [
            str(binary_path),
            "client",
            server_url,
            reverse_spec
        ]
        
        # Optional: Add authentication if provided
        auth = spec.get('auth')
        if auth:
            cmd.extend(["--auth", auth])
        
        # Optional: Add fingerprint if provided
        fingerprint = spec.get('fingerprint')
        if fingerprint:
            cmd.extend(["--fingerprint", fingerprint])
        
        # Start chisel client process
        log_file = self.config_dir / f"{tunnel_id}.log"
        log_f = open(log_file, 'w', buffering=1)
        try:
            log_f.write(f"Starting chisel client for tunnel {tunnel_id}\n")
            log_f.write(f"Command: {' '.join(cmd)}\n")
            log_f.write(f"server_url={server_url}, reverse_spec={reverse_spec}\n")
            log_f.flush()
            proc = subprocess.Popen(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                cwd=str(self.config_dir),
                start_new_session=True
            )
            # Store log file handle to keep it open (prevents subprocess from exiting)
            self.log_handles[tunnel_id] = log_f
            self.processes[tunnel_id] = proc
            time.sleep(1.0)  # Give it more time to start
            if proc.poll() is not None:
                stderr = ""
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        stderr = f.read()
                # Close log handle if process failed
                if tunnel_id in self.log_handles:
                    try:
                        self.log_handles[tunnel_id].close()
                    except:
                        pass
                    del self.log_handles[tunnel_id]
                raise RuntimeError(f"chisel failed to start: {stderr[-500:] if len(stderr) > 500 else stderr}")
        except FileNotFoundError:
            log_f.close()
            raise RuntimeError("chisel binary not found. Please install chisel.")
    
    def remove(self, tunnel_id: str):
        """Remove Chisel tunnel"""
        if tunnel_id in self.processes:
            proc = self.processes[tunnel_id]
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            except:
                pass
            del self.processes[tunnel_id]
        
        # Close log file handle
        if tunnel_id in self.log_handles:
            try:
                self.log_handles[tunnel_id].close()
            except:
                pass
            del self.log_handles[tunnel_id]
        
        try:
            subprocess.run(["pkill", "-f", f"chisel.*{tunnel_id}"], check=False, timeout=3)
        except:
            pass
    
    def status(self, tunnel_id: str) -> Dict[str, Any]:
        """Get status"""
        is_running = False
        
        if tunnel_id in self.processes:
            proc = self.processes[tunnel_id]
            is_running = proc.poll() is None
        
        return {
            "active": is_running,
            "type": "chisel",
            "process_running": is_running
        }


class AdapterManager:
    """Manager for core adapters"""
    
    def __init__(self):
        self.adapters: Dict[str, CoreAdapter] = {
            "rathole": RatholeAdapter(),
            "backhaul": BackhaulAdapter(),
            "chisel": ChiselAdapter(),
        }
        self.active_tunnels: Dict[str, CoreAdapter] = {}
    
    def get_adapter(self, tunnel_core: str) -> Optional[CoreAdapter]:
        """Get adapter for tunnel core"""
        return self.adapters.get(tunnel_core)
    
    async def apply_tunnel(self, tunnel_id: str, tunnel_core: str, spec: Dict[str, Any]):
        """Apply tunnel using appropriate adapter"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Applying tunnel {tunnel_id}: core={tunnel_core}")
        
        adapter = self.get_adapter(tunnel_core)
        if not adapter:
            error_msg = f"Unknown tunnel core: {tunnel_core}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Using adapter: {adapter.name}")
        adapter.apply(tunnel_id, spec)
        self.active_tunnels[tunnel_id] = adapter
        logger.info(f"Tunnel {tunnel_id} applied successfully")
    
    async def remove_tunnel(self, tunnel_id: str):
        """Remove tunnel"""
        if tunnel_id in self.active_tunnels:
            adapter = self.active_tunnels[tunnel_id]
            adapter.remove(tunnel_id)
            del self.active_tunnels[tunnel_id]
    
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

