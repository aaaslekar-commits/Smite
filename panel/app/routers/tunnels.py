"""Tunnels API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime
from pydantic import BaseModel
import logging
import sys

from app.database import get_db
from app.models import Tunnel, Node
from app.hysteria2_client import Hysteria2Client


router = APIRouter()
logger = logging.getLogger(__name__)

# Use stderr for immediate output (not buffered)
def debug_print(msg):
    print(msg, file=sys.stderr, flush=True)
    logger.info(msg)


class TunnelCreate(BaseModel):
    name: str
    core: str
    type: str
    node_id: str
    spec: dict
    quota_mb: float = 0
    expires_at: datetime | None = None


class TunnelUpdate(BaseModel):
    name: str | None = None
    spec: dict | None = None
    quota_mb: float | None = None
    expires_at: datetime | None = None


class TunnelResponse(BaseModel):
    id: str
    name: str
    core: str
    type: str
    node_id: str
    spec: dict
    quota_mb: float
    used_mb: float
    expires_at: datetime | None
    status: str
    error_message: str | None = None
    revision: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


@router.post("", response_model=TunnelResponse)
async def create_tunnel(tunnel: TunnelCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a new tunnel and auto-apply it"""
    from app.hysteria2_client import Hysteria2Client
    
    debug_print(f"DEBUG: create_tunnel called - name={tunnel.name}, type={tunnel.type}, core={tunnel.core}, node_id={tunnel.node_id}")
    
    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    debug_print(f"DEBUG: Node found: {node.id}, metadata: {node.node_metadata}")
    
    # Create tunnel
    db_tunnel = Tunnel(
        name=tunnel.name,
        core=tunnel.core,
        type=tunnel.type,
        node_id=tunnel.node_id,
        spec=tunnel.spec,
        quota_mb=tunnel.quota_mb,
        expires_at=tunnel.expires_at,
        status="pending"
    )
    db.add(db_tunnel)
    await db.commit()
    await db.refresh(db_tunnel)
    
    # Auto-apply tunnel immediately
    try:
        debug_print(f"DEBUG: Starting tunnel apply for tunnel {db_tunnel.id}")
        
        client = Hysteria2Client()
        # Update node metadata with API address if not set
        if not node.node_metadata.get("api_address"):
            node.node_metadata["api_address"] = f"http://{node.node_metadata.get('ip_address', node.fingerprint)}:{node.node_metadata.get('api_port', 8888)}"
            await db.commit()
        
        debug_print(f"DEBUG: Sending tunnel apply to node {node.id}")
        response = await client.send_to_node(
            node_id=node.id,
            endpoint="/api/agent/tunnels/apply",
            data={
                "tunnel_id": db_tunnel.id,
                "core": db_tunnel.core,
                "type": db_tunnel.type,
                "spec": db_tunnel.spec
            }
        )
        
        # Debug: Print response
        debug_print(f"DEBUG: Node response for tunnel {db_tunnel.id}: {response}")
        
        # Check if node returned an error
        if response.get("status") == "error":
            db_tunnel.status = "error"
            error_msg = response.get("message", "Unknown error from node")
            db_tunnel.error_message = f"Node error: {error_msg}"
            await db.commit()
            await db.refresh(db_tunnel)
            return db_tunnel
        
        if response.get("status") == "success":
            debug_print(f"DEBUG: Tunnel {db_tunnel.id} applied successfully, status={response.get('status')}")
            db_tunnel.status = "active"
            
            debug_print("DEBUG: About to enter try block for forwarding setup")
            try:
                debug_print("DEBUG: Inside try block for forwarding setup")
                # Start forwarding on panel using gost (for TCP/UDP/WS/gRPC tunnels)
                # Rathole: reverse tunnel, needs Rathole server on panel
                needs_gost_forwarding = db_tunnel.type in ["tcp", "udp", "ws", "grpc"] and db_tunnel.core == "xray"
                needs_rathole_server = db_tunnel.core == "rathole"
                
                debug_print(f"DEBUG: Calculated needs_gost_forwarding={needs_gost_forwarding}, needs_rathole_server={needs_rathole_server}")
                
                # Force log output - use print as well to ensure we see it
                log_msg = f"Tunnel {db_tunnel.id}: needs_gost_forwarding={needs_gost_forwarding}, needs_rathole_server={needs_rathole_server}, type={db_tunnel.type}, core={db_tunnel.core}"
                debug_print(log_msg)
                debug_print(f"DEBUG: About to check if needs_gost_forwarding (value: {needs_gost_forwarding}, type: {type(needs_gost_forwarding)})")
                debug_print(f"DEBUG: needs_gost_forwarding == True? {needs_gost_forwarding == True}")
                debug_print(f"DEBUG: needs_gost_forwarding is True? {needs_gost_forwarding is True}")
                debug_print(f"DEBUG: bool(needs_gost_forwarding)? {bool(needs_gost_forwarding)}")
                
                if needs_gost_forwarding:
                    debug_print(f"DEBUG: INSIDE if needs_gost_forwarding block!")
                    debug_print(f"DEBUG: Entering gost forwarding block for tunnel {db_tunnel.id}")
                    remote_port = db_tunnel.spec.get("remote_port") or db_tunnel.spec.get("listen_port")
                    debug_print(f"DEBUG: Tunnel {db_tunnel.id}: remote_port={remote_port}, spec={db_tunnel.spec}")
                    debug_print(f"DEBUG: Tunnel {db_tunnel.id}: has gost_forwarder={hasattr(request.app.state, 'gost_forwarder')}")
                    if remote_port and hasattr(request.app.state, 'gost_forwarder'):
                        debug_print(f"DEBUG: Conditions met - will start gost forwarding")
                        debug_print(f"DEBUG: IMMEDIATELY AFTER Conditions met - checking node metadata")
                        # Get node IP address from metadata
                        debug_print(f"DEBUG: Getting node_address from metadata, node.node_metadata={node.node_metadata}")
                        node_address = node.node_metadata.get("ip_address") if node.node_metadata else None
                        debug_print(f"DEBUG: node_address from ip_address field: {node_address}")
                        if not node_address:
                            # Try to extract from api_address
                            api_address = node.node_metadata.get("api_address", "") if node.node_metadata else ""
                            debug_print(f"DEBUG: api_address={api_address}")
                            if api_address:
                                # Extract host from http://host:port or host:port
                                if "://" in api_address:
                                    api_address = api_address.split("://")[-1]
                                if ":" in api_address:
                                    node_address = api_address.split(":")[0]
                                else:
                                    node_address = api_address
                                debug_print(f"DEBUG: Extracted node_address from api_address: {node_address}")
                        
                        debug_print(f"DEBUG: Final node_address={node_address}")
                        logger.info(f"Tunnel {db_tunnel.id}: node_address={node_address}")
                        if node_address:
                            debug_print(f"DEBUG: node_address is truthy, about to call start_forward()")
                            try:
                                # Use gost for forwarding
                                debug_print(f"DEBUG: About to call start_forward() with: tunnel_id={db_tunnel.id}, local_port={remote_port}, node_address={node_address}, remote_port={remote_port}, tunnel_type={db_tunnel.type}")
                                logger.info(f"Starting gost forwarding for tunnel {db_tunnel.id}: {db_tunnel.type}://:{remote_port} -> {node_address}:{remote_port}")
                                request.app.state.gost_forwarder.start_forward(
                                    tunnel_id=db_tunnel.id,
                                    local_port=int(remote_port),
                                    node_address=node_address,
                                    remote_port=int(remote_port),
                                    tunnel_type=db_tunnel.type
                                )
                                debug_print(f"DEBUG: start_forward() returned successfully")
                                logger.info(f"Successfully started gost forwarding for tunnel {db_tunnel.id}")
                            except Exception as e:
                                debug_print(f"DEBUG: Exception in start_forward(): {e}")
                                import traceback
                                debug_print(f"DEBUG: Traceback: {traceback.format_exc()}")
                                # Log but don't fail tunnel creation
                                error_msg = str(e)
                                logger.error(f"Failed to start gost forwarding for tunnel {db_tunnel.id}: {error_msg}", exc_info=True)
                                db_tunnel.status = "error"
                                db_tunnel.error_message = f"Gost forwarding error: {error_msg}"
                        else:
                            logger.warning(f"Tunnel {db_tunnel.id}: Node IP address not found in metadata")
                            db_tunnel.status = "error"
                            db_tunnel.error_message = "Node IP address not found in metadata"
                    else:
                        logger.warning(f"Tunnel {db_tunnel.id}: Missing remote_port or gost_forwarder not available")
                
                elif needs_rathole_server:
                    # Start Rathole server on panel
                    remote_addr = db_tunnel.spec.get("remote_addr")
                    token = db_tunnel.spec.get("token")
                    proxy_port = db_tunnel.spec.get("remote_port") or db_tunnel.spec.get("listen_port")
                    
                    # Validate remote_addr format
                    if remote_addr and ":" in remote_addr:
                        rathole_port = remote_addr.split(":")[1]
                        # Check if using panel API port (8000) - this will conflict
                        try:
                            if int(rathole_port) == 8000:
                                db_tunnel.status = "error"
                                db_tunnel.error_message = "Rathole server cannot use port 8000 (panel API port). Use a different port like 23333."
                                await db.commit()
                                await db.refresh(db_tunnel)
                                return db_tunnel
                        except ValueError:
                            pass
                    
                    if remote_addr and token and proxy_port and hasattr(request.app.state, 'rathole_server_manager'):
                        try:
                            request.app.state.rathole_server_manager.start_server(
                                tunnel_id=db_tunnel.id,
                                remote_addr=remote_addr,
                                token=token,
                                proxy_port=int(proxy_port)
                            )
                        except Exception as e:
                            # Log but don't fail tunnel creation
                            import logging
                            error_msg = str(e)
                            logging.error(f"Failed to start Rathole server: {error_msg}")
                            db_tunnel.status = "error"
                            db_tunnel.error_message = f"Rathole server error: {error_msg}"
            except Exception as e:
                # Catch any exception in the forwarding setup
                debug_print(f"ERROR: Exception in forwarding setup: {e}")
                logger.error(f"Exception in forwarding setup for tunnel {db_tunnel.id}: {e}", exc_info=True)
        else:
            db_tunnel.status = "error"
            db_tunnel.error_message = "Failed to apply tunnel to node. Check node connection."
        await db.commit()
        await db.refresh(db_tunnel)
    except Exception as e:
        # Don't fail tunnel creation if apply fails, just mark as error
        debug_print(f"ERROR: Exception in tunnel creation: {e}")
        logger.error(f"Exception in tunnel creation for {db_tunnel.id}: {e}", exc_info=True)
        error_msg = str(e)
        db_tunnel.status = "error"
        db_tunnel.error_message = f"Tunnel creation error: {error_msg}"
        await db.commit()
        await db.refresh(db_tunnel)
    
    return db_tunnel


@router.get("", response_model=List[TunnelResponse])
async def list_tunnels(db: AsyncSession = Depends(get_db)):
    """List all tunnels"""
    result = await db.execute(select(Tunnel))
    tunnels = result.scalars().all()
    return tunnels


@router.get("/{tunnel_id}", response_model=TunnelResponse)
async def get_tunnel(tunnel_id: str, db: AsyncSession = Depends(get_db)):
    """Get tunnel by ID"""
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    return tunnel


@router.put("/{tunnel_id}", response_model=TunnelResponse)
async def update_tunnel(
    tunnel_id: str,
    tunnel_update: TunnelUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Update a tunnel and re-apply if spec changed"""
    from app.hysteria2_client import Hysteria2Client
    
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    
    spec_changed = tunnel_update.spec is not None and tunnel_update.spec != tunnel.spec
    
    # Update fields
    if tunnel_update.name is not None:
        tunnel.name = tunnel_update.name
    if tunnel_update.spec is not None:
        tunnel.spec = tunnel_update.spec
    if tunnel_update.quota_mb is not None:
        tunnel.quota_mb = tunnel_update.quota_mb
    if tunnel_update.expires_at is not None:
        tunnel.expires_at = tunnel_update.expires_at
    
    tunnel.revision += 1
    tunnel.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(tunnel)
    
    # Re-apply tunnel if spec changed
    if spec_changed:
        result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
        node = result.scalar_one_or_none()
        if node:
            client = Hysteria2Client()
            try:
                response = await client.send_to_node(
                    node_id=node.id,
                    endpoint="/api/agent/tunnels/apply",
                    data={
                        "tunnel_id": tunnel.id,
                        "core": tunnel.core,
                        "type": tunnel.type,
                        "spec": tunnel.spec
                    }
                )
                
                if response.get("status") == "success":
                    tunnel.status = "active"
                    tunnel.error_message = None
                    
                    # Update rathole server if needed
                    if tunnel.core == "rathole" and hasattr(request.app.state, 'rathole_server_manager'):
                        remote_addr = tunnel.spec.get("remote_addr")
                        token = tunnel.spec.get("token")
                        proxy_port = tunnel.spec.get("remote_port") or tunnel.spec.get("listen_port")
                        
                        if remote_addr and token and proxy_port:
                            try:
                                request.app.state.rathole_server_manager.start_server(
                                    tunnel_id=tunnel.id,
                                    remote_addr=remote_addr,
                                    token=token,
                                    proxy_port=int(proxy_port)
                                )
                            except Exception as e:
                                import logging
                                logging.error(f"Failed to restart Rathole server: {e}")
                                tunnel.status = "error"
                                tunnel.error_message = f"Rathole server error: {str(e)}"
                else:
                    tunnel.status = "error"
                    tunnel.error_message = f"Node error: {response.get('message', 'Unknown error')}"
                    
                await db.commit()
                await db.refresh(tunnel)
            except Exception as e:
                import logging
                logging.error(f"Failed to re-apply tunnel: {e}")
                tunnel.status = "error"
                tunnel.error_message = f"Re-apply error: {str(e)}"
                await db.commit()
                await db.refresh(tunnel)
    
    return tunnel


@router.post("/{tunnel_id}/apply")
async def apply_tunnel(tunnel_id: str, db: AsyncSession = Depends(get_db)):
    """Apply tunnel configuration to node"""
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    
    # Get node
    result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # Send to node via HTTPS
    client = Hysteria2Client()
    try:
        # Update node metadata with API address if not set
        if not node.node_metadata.get("api_address"):
            node.node_metadata["api_address"] = f"http://{node.fingerprint}:8888"  # Fallback
            await db.commit()
        
        response = await client.send_to_node(
            node_id=node.id,
            endpoint="/api/agent/tunnels/apply",
            data={
                "tunnel_id": tunnel.id,
                "core": tunnel.core,
                "type": tunnel.type,
                "spec": tunnel.spec
            }
        )
        
        if response.get("status") == "success":
            tunnel.status = "active"
            await db.commit()
            return {"status": "applied", "message": "Tunnel applied successfully"}
        else:
            error_msg = response.get("message", "Failed to apply tunnel")
            tunnel.status = "error"
            await db.commit()
            raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        tunnel.status = "error"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to apply tunnel: {str(e)}")


@router.delete("/{tunnel_id}")
async def delete_tunnel(tunnel_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Delete a tunnel"""
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    
    # Stop forwarding on panel (for TCP/UDP/WS/gRPC tunnels)
    needs_gost_forwarding = tunnel.type in ["tcp", "udp", "ws", "grpc"] and tunnel.core == "xray"
    needs_rathole_server = tunnel.core == "rathole"
    
    if needs_gost_forwarding:
        if hasattr(request.app.state, 'gost_forwarder'):
            try:
                request.app.state.gost_forwarder.stop_forward(tunnel.id)
            except Exception as e:
                import logging
                logging.error(f"Failed to stop gost forwarding: {e}")
    
    elif needs_rathole_server:
        # Stop Rathole server on panel
        if hasattr(request.app.state, 'rathole_server_manager'):
            try:
                request.app.state.rathole_server_manager.stop_server(tunnel.id)
            except Exception as e:
                import logging
                logging.error(f"Failed to stop Rathole server: {e}")
    
    # Remove from node if active
    if tunnel.status == "active":
        result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
        node = result.scalar_one_or_none()
        if node:
            client = Hysteria2Client()
            try:
                await client.send_to_node(
                    node_id=node.id,
                    endpoint="/api/agent/tunnels/remove",
                    data={"tunnel_id": tunnel.id}
                )
            except:
                pass  # Continue deletion even if node is unreachable
    
    await db.delete(tunnel)
    await db.commit()
    return {"status": "deleted"}


@router.put("/{tunnel_id}", response_model=TunnelResponse)
async def update_tunnel(tunnel_id: str, tunnel: TunnelUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    """Update a tunnel"""
    from app.hysteria2_client import Hysteria2Client
    
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    db_tunnel = result.scalar_one_or_none()
    if not db_tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    
    # Update fields
    if tunnel.name is not None:
        db_tunnel.name = tunnel.name
    if tunnel.spec is not None:
        db_tunnel.spec = tunnel.spec
    if tunnel.quota_mb is not None:
        db_tunnel.quota_mb = tunnel.quota_mb
    if tunnel.expires_at is not None:
        db_tunnel.expires_at = tunnel.expires_at
    
    db_tunnel.revision += 1
    db_tunnel.updated_at = datetime.utcnow()
    
    # If spec changed, reapply tunnel
    if tunnel.spec is not None:
        result = await db.execute(select(Node).where(Node.id == db_tunnel.node_id))
        node = result.scalar_one_or_none()
        if node:
            client = Hysteria2Client()
            try:
                # Stop old forwarding or Rathole server
                old_needs_gost_forwarding = db_tunnel.type in ["tcp", "udp", "ws", "grpc"] and db_tunnel.core == "xray"
                old_needs_rathole_server = db_tunnel.core == "rathole"
                
                if old_needs_gost_forwarding:
                    if hasattr(request.app.state, 'gost_forwarder'):
                        try:
                            request.app.state.gost_forwarder.stop_forward(db_tunnel.id)
                        except:
                            pass
                elif old_needs_rathole_server:
                    if hasattr(request.app.state, 'rathole_server_manager'):
                        try:
                            request.app.state.rathole_server_manager.stop_server(db_tunnel.id)
                        except:
                            pass
                
                # Apply new tunnel config
                response = await client.send_to_node(
                    node_id=node.id,
                    endpoint="/api/agent/tunnels/apply",
                    data={
                        "tunnel_id": db_tunnel.id,
                        "core": db_tunnel.core,
                        "type": db_tunnel.type,
                        "spec": db_tunnel.spec
                    }
                )
                
                if response.get("status") == "success":
                    db_tunnel.status = "active"
                    # Start new forwarding or Rathole server if needed
                    needs_gost_forwarding = db_tunnel.type in ["tcp", "udp", "ws", "grpc"] and db_tunnel.core == "xray"
                    needs_rathole_server = db_tunnel.core == "rathole"
                    
                    if needs_gost_forwarding:
                        remote_port = db_tunnel.spec.get("remote_port") or db_tunnel.spec.get("listen_port")
                        if remote_port and hasattr(request.app.state, 'gost_forwarder'):
                            node_address = node.node_metadata.get("ip_address") if node.node_metadata else None
                            if not node_address:
                                # Try to extract from api_address
                                api_address = node.node_metadata.get("api_address", "") if node.node_metadata else ""
                                if api_address:
                                    if "://" in api_address:
                                        api_address = api_address.split("://")[-1]
                                    if ":" in api_address:
                                        node_address = api_address.split(":")[0]
                                    else:
                                        node_address = api_address
                            
                            if node_address:
                                try:
                                    request.app.state.gost_forwarder.start_forward(
                                        tunnel_id=db_tunnel.id,
                                        local_port=int(remote_port),
                                        node_address=node_address,
                                        remote_port=int(remote_port),
                                        tunnel_type=db_tunnel.type
                                    )
                                except Exception as e:
                                    import logging
                                    logging.error(f"Failed to start gost forwarding: {e}")
                    
                    elif needs_rathole_server:
                        remote_addr = db_tunnel.spec.get("remote_addr")
                        token = db_tunnel.spec.get("token")
                        proxy_port = db_tunnel.spec.get("remote_port") or db_tunnel.spec.get("listen_port")
                        
                        if remote_addr and token and proxy_port and hasattr(request.app.state, 'rathole_server_manager'):
                            try:
                                success = request.app.state.rathole_server_manager.start_server(
                                    tunnel_id=db_tunnel.id,
                                    remote_addr=remote_addr,
                                    token=token,
                                    proxy_port=int(proxy_port)
                                )
                                if not success:
                                    db_tunnel.status = "error"
                            except Exception as e:
                                import logging
                                logging.error(f"Failed to start Rathole server: {e}")
                                db_tunnel.status = "error"
                else:
                    db_tunnel.status = "error"
            except Exception as e:
                db_tunnel.status = "error"
                import logging
                logging.error(f"Failed to reapply tunnel: {e}")
    
    await db.commit()
    await db.refresh(db_tunnel)
    return db_tunnel

