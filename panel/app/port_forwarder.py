"""Port forwarding service for panel to forward connections to nodes"""
import asyncio
import socket
from typing import Dict, Optional
from asyncio import StreamReader, StreamWriter
import logging

logger = logging.getLogger(__name__)


class PortForwarder:
    """Manages TCP port forwarding from panel to nodes"""
    
    def __init__(self):
        self.active_forwards: Dict[int, asyncio.Task] = {}
        self.forward_configs: Dict[int, dict] = {}  # port -> {node_address, remote_port}
        
    async def start_forward(self, local_port: int, node_address: str, remote_port: int) -> bool:
        """Start forwarding from local_port to node_address:remote_port"""
        try:
            # Check if already forwarding on this port
            if local_port in self.active_forwards:
                logger.warning(f"Port {local_port} already being forwarded, stopping old forward")
                await self.stop_forward(local_port)
            
            # Store config
            self.forward_configs[local_port] = {
                "node_address": node_address,
                "remote_port": remote_port
            }
            
            # Start forwarding task
            task = asyncio.create_task(self._forward_loop(local_port, node_address, remote_port))
            self.active_forwards[local_port] = task
            
            logger.info(f"Started forwarding {local_port} -> {node_address}:{remote_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start forwarding on port {local_port}: {e}")
            return False
    
    async def stop_forward(self, local_port: int):
        """Stop forwarding on local_port"""
        if local_port in self.active_forwards:
            task = self.active_forwards[local_port]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.active_forwards[local_port]
            
        if local_port in self.forward_configs:
            del self.forward_configs[local_port]
            
        logger.info(f"Stopped forwarding on port {local_port}")
    
    async def _forward_loop(self, local_port: int, node_address: str, remote_port: int):
        """Main forwarding loop - accepts connections and forwards them"""
        try:
            # Parse node address
            if "://" in node_address:
                node_address = node_address.split("://")[-1]
            node_host = node_address.split(":")[0] if ":" in node_address else node_address
            
            try:
                server = await asyncio.start_server(
                    lambda r, w: self._handle_client(r, w, node_host, remote_port),
                    host='0.0.0.0',
                    port=local_port,
                    reuse_address=True,
                    reuse_port=False
                )
                logger.info(f"✅ Forwarding server started on 0.0.0.0:{local_port} -> {node_host}:{remote_port}")
            except OSError as e:
                if "Address already in use" in str(e) or e.errno == 98:
                    logger.error(f"❌ Port {local_port} is already in use. Please ensure:")
                    logger.error(f"   1. The panel container is in host network mode, OR")
                    logger.error(f"   2. Port {local_port} is exposed in docker-compose.yml, OR")
                    logger.error(f"   3. No other service is using port {local_port}")
                    raise RuntimeError(f"Port {local_port} already in use. Check docker-compose.yml network configuration.")
                raise
            
            async with server:
                await server.serve_forever()
        except asyncio.CancelledError:
            logger.info(f"Forwarding on port {local_port} cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in forwarding loop for port {local_port}: {e}")
            raise
    
    async def _handle_client(self, reader: StreamReader, writer: StreamWriter, target_host: str, target_port: int):
        """Handle a client connection by forwarding to target"""
        remote_reader = None
        remote_writer = None
        
        try:
            # Connect to target node with longer timeout and keep-alive
            try:
                # Create socket with keep-alive
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                
                # Connect socket first, then use it for asyncio
                sock.connect((target_host, target_port))
                remote_reader, remote_writer = await asyncio.wait_for(
                    asyncio.open_connection(sock=sock),
                    timeout=10.0  # Increased timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Timeout connecting to {target_host}:{target_port}")
                try:
                    writer.close()
                    await writer.wait_closed()
                except:
                    pass
                return
            except Exception as e:
                logger.warning(f"Failed to connect to {target_host}:{target_port}: {e}")
                try:
                    writer.close()
                    await writer.wait_closed()
                except:
                    pass
                return
            
            # Create bidirectional forwarding with better error handling
            async def forward(src_reader: StreamReader, dst_writer: StreamWriter, direction: str):
                try:
                    while True:
                        try:
                            # Use read with timeout to detect dead connections
                            data = await asyncio.wait_for(src_reader.read(8192), timeout=300.0)
                            if not data:
                                break
                            dst_writer.write(data)
                            await dst_writer.drain()
                        except asyncio.TimeoutError:
                            # Send keep-alive or check if connection is alive
                            try:
                                dst_writer.write(b'')
                                await dst_writer.drain()
                            except:
                                break
                        except (ConnectionResetError, BrokenPipeError, OSError) as e:
                            logger.debug(f"Connection {direction} reset: {e}")
                            break
                except Exception as e:
                    logger.debug(f"Forwarding {direction} closed: {e}")
                finally:
                    try:
                        if not dst_writer.is_closing():
                            dst_writer.close()
                            await dst_writer.wait_closed()
                    except:
                        pass
            
            # Start bidirectional forwarding
            await asyncio.gather(
                forward(reader, remote_writer, "client->node"),
                forward(remote_reader, writer, "node->client"),
                return_exceptions=True
            )
            
        except Exception as e:
            logger.debug(f"Error handling client connection: {e}")
        finally:
            # Cleanup
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass
            try:
                if remote_writer:
                    remote_writer.close()
                    await remote_writer.wait_closed()
            except:
                pass
    
    def is_forwarding(self, local_port: int) -> bool:
        """Check if port is being forwarded"""
        return local_port in self.active_forwards
    
    def get_forwarding_ports(self) -> list:
        """Get list of all forwarding ports"""
        return list(self.active_forwards.keys())
    
    async def cleanup_all(self):
        """Stop all forwarding"""
        ports = list(self.active_forwards.keys())
        for port in ports:
            await self.stop_forward(port)


# Global forwarder instance
port_forwarder = PortForwarder()

