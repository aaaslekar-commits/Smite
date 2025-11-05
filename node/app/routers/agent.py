"""Agent API endpoints"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import Dict, Any
import logging
import sys

router = APIRouter()
logger = logging.getLogger(__name__)

# Add middleware to log all requests
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/api/agent/tunnels/apply":
            body = await request.body()
            print(f"🔵 MIDDLEWARE: {request.method} {request.url.path}", file=sys.stderr, flush=True)
            print(f"🔵 MIDDLEWARE: Body: {body}", file=sys.stderr, flush=True)
        response = await call_next(request)
        if request.url.path == "/api/agent/tunnels/apply":
            print(f"🔵 MIDDLEWARE: Response status: {response.status_code}", file=sys.stderr, flush=True)
        return response


class TunnelApply(BaseModel):
    tunnel_id: str
    core: str
    type: str
    spec: Dict[str, Any]


class TunnelRemove(BaseModel):
    tunnel_id: str


class UsagePush(BaseModel):
    tunnel_id: str
    bytes_used: int


@router.post("/tunnels/apply")
async def apply_tunnel(data: TunnelApply, request: Request):
    """Apply tunnel configuration"""
    import logging
    import sys
    logger = logging.getLogger(__name__)
    adapter_manager = request.app.state.adapter_manager
    
    # Use print for immediate output (not buffered)
    print(f"🔵 NODE: Received tunnel apply request: tunnel_id={data.tunnel_id}, type={data.type}, spec={data.spec}", file=sys.stderr, flush=True)
    logger.info(f"Received tunnel apply request: tunnel_id={data.tunnel_id}, type={data.type}, spec={data.spec}")
    try:
        print(f"🔵 NODE: Calling adapter_manager.apply_tunnel...", file=sys.stderr, flush=True)
        await adapter_manager.apply_tunnel(
            tunnel_id=data.tunnel_id,
            tunnel_type=data.type,
            spec=data.spec
        )
        print(f"✅ NODE: Tunnel {data.tunnel_id} applied successfully", file=sys.stderr, flush=True)
        logger.info(f"Tunnel {data.tunnel_id} applied successfully")
        return {"status": "success", "message": "Tunnel applied"}
    except Exception as e:
        import traceback
        error_msg = f"❌ NODE: Failed to apply tunnel {data.tunnel_id}: {e}"
        print(error_msg, file=sys.stderr, flush=True)
        print(f"❌ NODE: Traceback: {traceback.format_exc()}", file=sys.stderr, flush=True)
        logger.error(f"Failed to apply tunnel {data.tunnel_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tunnels/remove")
async def remove_tunnel(data: TunnelRemove, request: Request):
    """Remove tunnel"""
    adapter_manager = request.app.state.adapter_manager
    
    try:
        await adapter_manager.remove_tunnel(data.tunnel_id)
        return {"status": "success", "message": "Tunnel removed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tunnels/status")
async def get_tunnel_status(tunnel_id: str, request: Request):
    """Get tunnel status"""
    adapter_manager = request.app.state.adapter_manager
    
    try:
        status = await adapter_manager.get_tunnel_status(tunnel_id)
        return {"status": "success", "data": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/usage/push")
async def push_usage(data: UsagePush, request: Request):
    """Push usage data to panel"""
    adapter_manager = request.app.state.adapter_manager
    
    # Get actual usage from adapter
    try:
        adapter = adapter_manager.active_tunnels.get(data.tunnel_id)
        if adapter:
            usage_mb = adapter.get_usage_mb(data.tunnel_id)
            data.bytes_used = int(usage_mb * 1024 * 1024)
        
        # TODO: Send usage data back to panel via HTTPS
        # For now, just acknowledge
        return {"status": "ok", "bytes_used": data.bytes_used}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/status")
async def get_status(request: Request):
    """Get node status"""
    adapter_manager = request.app.state.adapter_manager
    
    return {
        "status": "ok",
        "active_tunnels": len(adapter_manager.active_tunnels),
        "tunnels": list(adapter_manager.active_tunnels.keys())
    }

