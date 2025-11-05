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


class TunnelCreate(BaseModel):
    name: str
    core: str
    type: str
    node_id: str | None = None
    spec: dict


class TunnelUpdate(BaseModel):
    name: str | None = None
    spec: dict | None = None


class TunnelResponse(BaseModel):
    id: str
    name: str
    core: str
    type: str
    node_id: str
    spec: dict
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
    
    logger.info(f"Creating tunnel: name={tunnel.name}, type={tunnel.type}, core={tunnel.core}, node_id={tunnel.node_id}")
    
    # For GOST tunnels (xray core), node is optional - they forward directly
    # For Rathole tunnels, node is required
    node = None
    if tunnel.node_id:
        result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
        node = result.scalar_one_or_none()
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
    elif tunnel.core == "rathole":
        raise HTTPException(status_code=400, detail="Node is required for Rathole tunnels")
    
    # Create tunnel - use empty string for node_id if not provided (for GOST tunnels)
    db_tunnel = Tunnel(
        name=tunnel.name,
        core=tunnel.core,
        type=tunnel.type,
        node_id=tunnel.node_id or "",
        spec=tunnel.spec,
        status="pending"
    )
    db.add(db_tunnel)
    await db.commit()
    await db.refresh(db_tunnel)
    
    # Auto-apply tunnel immediately
    # Only send to node for rathole tunnels - gost tunnels forward directly without node
    try:
        # Only apply to node for rathole tunnels
        needs_node_apply = db_tunnel.core == "rathole"
        
        if needs_node_apply:
            client = Hysteria2Client()
            # Update node metadata with API address if not set
            if not node.node_metadata.get("api_address"):
                node.node_metadata["api_address"] = f"http://{node.node_metadata.get('ip_address', node.fingerprint)}:{node.node_metadata.get('api_port', 8888)}"
                await db.commit()
            
            logger.info(f"Applying tunnel {db_tunnel.id} to node {node.id}")
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
            
            # Check if node returned an error
            if response.get("status") == "error":
                db_tunnel.status = "error"
                error_msg = response.get("message", "Unknown error from node")
                db_tunnel.error_message = f"Node error: {error_msg}"
                logger.error(f"Tunnel {db_tunnel.id}: {error_msg}")
                await db.commit()
                await db.refresh(db_tunnel)
                return db_tunnel
            
            if response.get("status") != "success":
                db_tunnel.status = "error"
                db_tunnel.error_message = "Failed to apply tunnel to node. Check node connection."
                logger.error(f"Tunnel {db_tunnel.id}: Failed to apply to node")
                await db.commit()
                await db.refresh(db_tunnel)
                return db_tunnel
        
        # Mark as active (for both gost and rathole)
        db_tunnel.status = "active"
        
        try:
            # Start forwarding on panel using gost (for TCP/UDP/WS/gRPC/tcpmux tunnels)
            # Rathole: reverse tunnel, needs Rathole server on panel
            needs_gost_forwarding = db_tunnel.type in ["tcp", "udp", "ws", "grpc", "tcpmux"] and db_tunnel.core == "xray"
            needs_rathole_server = db_tunnel.core == "rathole"
            
            if needs_gost_forwarding:
                panel_port = db_tunnel.spec.get("remote_port") or db_tunnel.spec.get("listen_port")
                forward_to = db_tunnel.spec.get("forward_to")
                
                if panel_port and forward_to and hasattr(request.app.state, 'gost_forwarder'):
                    try:
                        logger.info(f"Starting gost forwarding for tunnel {db_tunnel.id}: {db_tunnel.type}://:{panel_port} -> {forward_to}")
                        request.app.state.gost_forwarder.start_forward(
                            tunnel_id=db_tunnel.id,
                            local_port=int(panel_port),
                            forward_to=forward_to,
                            tunnel_type=db_tunnel.type
                        )
                        logger.info(f"Successfully started gost forwarding for tunnel {db_tunnel.id}")
                    except Exception as e:
                        error_msg = str(e)
                        logger.error(f"Failed to start gost forwarding for tunnel {db_tunnel.id}: {error_msg}", exc_info=True)
                        db_tunnel.status = "error"
                        db_tunnel.error_message = f"Gost forwarding error: {error_msg}"
                else:
                    missing = []
                    if not panel_port:
                        missing.append("panel_port")
                    if not forward_to:
                        missing.append("forward_to")
                    if not hasattr(request.app.state, 'gost_forwarder'):
                        missing.append("gost_forwarder")
                    logger.warning(f"Tunnel {db_tunnel.id}: Missing required fields: {missing}")
                    if not forward_to:
                        error_msg = "forward_to is required for gost tunnels"
                        db_tunnel.status = "error"
                        db_tunnel.error_message = error_msg
            
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
            logger.error(f"Exception in forwarding setup for tunnel {db_tunnel.id}: {e}", exc_info=True)
        
        await db.commit()
        await db.refresh(db_tunnel)
    except Exception as e:
        # Don't fail tunnel creation if apply fails, just mark as error
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
    
    tunnel.revision += 1
    tunnel.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(tunnel)
    
    # Re-apply tunnel if spec changed
    if spec_changed:
        try:
            # For GOST tunnels, restart gost forwarding
            needs_gost_forwarding = tunnel.type in ["tcp", "udp", "ws", "grpc", "tcpmux"] and tunnel.core == "xray"
            needs_rathole_server = tunnel.core == "rathole"
            needs_node_apply = tunnel.core == "rathole"
            
            if needs_gost_forwarding:
                # Restart gost forwarding with new spec
                panel_port = tunnel.spec.get("remote_port") or tunnel.spec.get("listen_port")
                forward_to = tunnel.spec.get("forward_to")
                
                if panel_port and forward_to and hasattr(request.app.state, 'gost_forwarder'):
                    try:
                        # Stop old forwarding
                        request.app.state.gost_forwarder.stop_forward(tunnel.id)
                        # Start new forwarding
                        logger.info(f"Restarting gost forwarding for tunnel {tunnel.id}: {tunnel.type}://:{panel_port} -> {forward_to}")
                        request.app.state.gost_forwarder.start_forward(
                            tunnel_id=tunnel.id,
                            local_port=int(panel_port),
                            forward_to=forward_to,
                            tunnel_type=tunnel.type
                        )
                        tunnel.status = "active"
                        tunnel.error_message = None
                        logger.info(f"Successfully restarted gost forwarding for tunnel {tunnel.id}")
                    except Exception as e:
                        error_msg = str(e)
                        logger.error(f"Failed to restart gost forwarding for tunnel {tunnel.id}: {error_msg}", exc_info=True)
                        tunnel.status = "error"
                        tunnel.error_message = f"Gost forwarding error: {error_msg}"
                else:
                    if not forward_to:
                        tunnel.status = "error"
                        tunnel.error_message = "forward_to is required for gost tunnels"
            
            elif needs_rathole_server:
                # Restart Rathole server
                if hasattr(request.app.state, 'rathole_server_manager'):
                    remote_addr = tunnel.spec.get("remote_addr")
                    token = tunnel.spec.get("token")
                    proxy_port = tunnel.spec.get("remote_port") or tunnel.spec.get("listen_port")
                    
                    if remote_addr and token and proxy_port:
                        try:
                            # Stop old server
                            request.app.state.rathole_server_manager.stop_server(tunnel.id)
                            # Start new server
                            request.app.state.rathole_server_manager.start_server(
                                tunnel_id=tunnel.id,
                                remote_addr=remote_addr,
                                token=token,
                                proxy_port=int(proxy_port)
                            )
                            tunnel.status = "active"
                            tunnel.error_message = None
                        except Exception as e:
                            logger.error(f"Failed to restart Rathole server: {e}")
                            tunnel.status = "error"
                            tunnel.error_message = f"Rathole server error: {str(e)}"
            
            # For Rathole tunnels, also update node
            if needs_node_apply and tunnel.node_id:
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
                        else:
                            tunnel.status = "error"
                            tunnel.error_message = f"Node error: {response.get('message', 'Unknown error')}"
                    except Exception as e:
                        logger.error(f"Failed to re-apply tunnel to node: {e}")
                        tunnel.status = "error"
                        tunnel.error_message = f"Node error: {str(e)}"
            
            await db.commit()
            await db.refresh(tunnel)
        except Exception as e:
            logger.error(f"Failed to re-apply tunnel: {e}", exc_info=True)
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

