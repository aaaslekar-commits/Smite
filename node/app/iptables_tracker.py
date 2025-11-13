"""iptables-based traffic tracking for tunnels"""
import subprocess
import logging
import re
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Chain name for Smite traffic tracking
CHAIN_NAME = "SMITE_TRACK"


def _run_iptables(args: list, check: bool = True) -> subprocess.CompletedProcess:
    """Run iptables command"""
    cmd = ["iptables"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            timeout=5
        )
        return result
    except subprocess.TimeoutExpired:
        logger.error(f"iptables command timed out: {' '.join(cmd)}")
        raise
    except subprocess.CalledProcessError as e:
        logger.warning(f"iptables command failed: {' '.join(cmd)}: {e.stderr}")
        raise


def _run_ip6tables(args: list, check: bool = True) -> subprocess.CompletedProcess:
    """Run ip6tables command for IPv6"""
    cmd = ["ip6tables"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            timeout=5
        )
        return result
    except subprocess.TimeoutExpired:
        logger.error(f"ip6tables command timed out: {' '.join(cmd)}")
        raise
    except subprocess.CalledProcessError as e:
        logger.warning(f"ip6tables command failed: {' '.join(cmd)}: {e.stderr}")
        raise


def ensure_chain_exists():
    """Ensure the tracking chain exists"""
    try:
        # Check if chain exists
        _run_iptables(["-L", CHAIN_NAME], check=False)
    except subprocess.CalledProcessError:
        # Chain doesn't exist, create it
        try:
            _run_iptables(["-N", CHAIN_NAME])
            # Insert rule to jump to chain from INPUT and OUTPUT
            _run_iptables(["-I", "INPUT", "-j", CHAIN_NAME], check=False)
            _run_iptables(["-I", "OUTPUT", "-j", CHAIN_NAME], check=False)
            logger.info(f"Created iptables chain {CHAIN_NAME}")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to create iptables chain: {e}")
    
    try:
        # Same for IPv6
        _run_ip6tables(["-L", CHAIN_NAME], check=False)
    except subprocess.CalledProcessError:
        try:
            _run_ip6tables(["-N", CHAIN_NAME])
            _run_ip6tables(["-I", "INPUT", "-j", CHAIN_NAME], check=False)
            _run_ip6tables(["-I", "OUTPUT", "-j", CHAIN_NAME], check=False)
            logger.info(f"Created ip6tables chain {CHAIN_NAME}")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to create ip6tables chain: {e}")


def parse_address_port(addr: str) -> Tuple[Optional[str], Optional[int], bool]:
    """
    Parse address:port string
    Returns: (host, port, is_ipv6)
    """
    if not addr:
        return None, None, False
    
    # Handle IPv6 with brackets [::1]:8080
    if addr.startswith('['):
        match = re.match(r'\[([^\]]+)\]:(\d+)', addr)
        if match:
            host = match.group(1)
            port = int(match.group(2))
            return host, port, True
    elif ':' in addr:
        parts = addr.rsplit(':', 1)
        if len(parts) == 2 and parts[1].isdigit():
            host = parts[0] if parts[0] else None
            port = int(parts[1])
            # Check if it's IPv6 (contains ::)
            is_ipv6 = '::' in host or (host and ':' in host and not host.startswith('['))
            return host, port, is_ipv6
    
    return None, None, False


def add_tracking_rule(tunnel_id: str, port: int, is_ipv6: bool = False):
    """
    Add iptables rule to track traffic on a port
    The rule only COUNTS traffic, doesn't block or modify it
    Tracks both INPUT (incoming) and OUTPUT (outgoing) traffic
    """
    ensure_chain_exists()
    
    rule_comment = f"smite-{tunnel_id}"
    cmd = is_ipv6 and _run_ip6tables or _run_iptables
    
    try:
        # Check if rule already exists
        result = cmd(["-L", CHAIN_NAME, "-n", "-v", "--line-numbers"], check=False)
        if rule_comment in result.stdout:
            logger.debug(f"Tracking rule for tunnel {tunnel_id} port {port} already exists")
            return
        
        # Add TCP INPUT rule (traffic coming TO this port)
        cmd([
            "-A", CHAIN_NAME,
            "-p", "tcp",
            "--dport", str(port),
            "-m", "comment", "--comment", f"{rule_comment}-tcp-in",
            "-j", "ACCEPT"
        ])
        
        # Add TCP OUTPUT rule (traffic going FROM this port)
        cmd([
            "-A", CHAIN_NAME,
            "-p", "tcp",
            "--sport", str(port),
            "-m", "comment", "--comment", f"{rule_comment}-tcp-out",
            "-j", "ACCEPT"
        ])
        
        # Add UDP INPUT rule
        cmd([
            "-A", CHAIN_NAME,
            "-p", "udp",
            "--dport", str(port),
            "-m", "comment", "--comment", f"{rule_comment}-udp-in",
            "-j", "ACCEPT"
        ])
        
        # Add UDP OUTPUT rule
        cmd([
            "-A", CHAIN_NAME,
            "-p", "udp",
            "--sport", str(port),
            "-m", "comment", "--comment", f"{rule_comment}-udp-out",
            "-j", "ACCEPT"
        ])
        
        logger.info(f"Added iptables tracking rules for tunnel {tunnel_id} on port {port} (IPv6={is_ipv6})")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to add tracking rule for tunnel {tunnel_id}: {e}")


def remove_tracking_rule(tunnel_id: str, port: int, is_ipv6: bool = False):
    """Remove iptables tracking rule"""
    rule_comment = f"smite-{tunnel_id}"
    cmd = is_ipv6 and _run_ip6tables or _run_iptables
    
    try:
        # Find and delete rules by comment
        result = cmd(["-L", CHAIN_NAME, "-n", "-v", "--line-numbers"], check=False)
        lines = result.stdout.split('\n')
        
        # Get line numbers of rules with this comment
        line_nums = []
        for i, line in enumerate(lines, 1):
            if rule_comment in line:
                # Extract line number (first field)
                match = re.match(r'^\s*(\d+)', line)
                if match:
                    line_nums.append(int(match.group(1)))
        
        # Delete in reverse order to maintain line numbers
        for line_num in sorted(line_nums, reverse=True):
            cmd(["-D", CHAIN_NAME, str(line_num)], check=False)
        
        if line_nums:
            logger.info(f"Removed iptables tracking rule for tunnel {tunnel_id} on port {port} (IPv6={is_ipv6})")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to remove tracking rule for tunnel {tunnel_id}: {e}")


def get_traffic_bytes(tunnel_id: str, port: int, is_ipv6: bool = False) -> int:
    """
    Get total bytes (sent + received) for a tunnel from iptables counters
    Returns bytes, or 0 if not found
    
    iptables -L -n -v -x output format:
    pkts      bytes target     prot opt in     out     source               destination
    12345  1234567 ACCEPT     tcp  --  *      *       0.0.0.0/0            0.0.0.0/0
    """
    rule_comment = f"smite-{tunnel_id}"
    cmd = is_ipv6 and _run_ip6tables or _run_iptables
    
    try:
        result = cmd(["-L", CHAIN_NAME, "-n", "-v", "-x"], check=False)
        total_bytes = 0
        
        # Sum bytes from all rules matching our comment (both input and output)
        for line in result.stdout.split('\n'):
            if rule_comment in line:
                # Extract bytes (second field in -x format)
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        # In -x format, bytes is the second field (after pkts)
                        bytes_val = int(parts[1])
                        total_bytes += bytes_val
                    except (ValueError, IndexError):
                        pass
        
        return total_bytes
    except subprocess.CalledProcessError:
        return 0

