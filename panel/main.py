"""
Smite Panel - Central Controller
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Tunnel, Node

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import nodes, tunnels, panel, usage, status, logs, auth
from app.hysteria2_server import Hysteria2Server
from app.gost_forwarder import gost_forwarder
from app.rathole_server import rathole_server_manager
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Initialize database
    await init_db()
    
    # Start Hysteria2 server (for cert generation - always needed for CA cert)
    h2_server = Hysteria2Server()
    await h2_server.start()
    app.state.h2_server = h2_server
    
    # Ensure CA certificate is generated on startup
    try:
        cert_path = Path(settings.hysteria2_cert_path)
        if not cert_path.is_absolute():
            cert_path = Path(os.getcwd()) / cert_path
        
        if not cert_path.exists() or cert_path.stat().st_size == 0:
            logger.info("Generating CA certificate on startup...")
            h2_server.cert_path = str(cert_path)
            h2_server.key_path = str(cert_path.parent / "ca.key")
            await h2_server._generate_certs()
            logger.info(f"CA certificate generated at {cert_path}")
    except Exception as e:
        logger.warning(f"Failed to generate CA certificate on startup: {e}")
        # Don't fail startup if cert generation fails
    
    # Initialize gost forwarder
    app.state.gost_forwarder = gost_forwarder
    
    # Initialize Rathole server manager
    app.state.rathole_server_manager = rathole_server_manager
    
    # Restore active tunnels' forwarding on startup
    await _restore_forwards()
    
    # Restore active Rathole servers on startup
    await _restore_rathole_servers()
    
    yield
    
    # Shutdown
    if hasattr(app.state, 'h2_server'):
        await app.state.h2_server.stop()
    
    # Stop all gost forwarding
    gost_forwarder.cleanup_all()
    
    # Stop all Rathole servers
    rathole_server_manager.cleanup_all()


async def _restore_forwards():
    """Restore forwarding for active tunnels on startup"""
    try:
        logger.info("Starting to restore forwarding for active tunnels...")
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tunnel).where(Tunnel.status == "active"))
            tunnels = result.scalars().all()
            logger.info(f"Found {len(tunnels)} active tunnels to restore")
            
            for tunnel in tunnels:
                logger.info(f"Checking tunnel {tunnel.id}: type={tunnel.type}, core={tunnel.core}")
                # Only restore xray tunnels (tcp, udp, ws, grpc)
                needs_gost_forwarding = tunnel.type in ["tcp", "udp", "ws", "grpc"] and tunnel.core == "xray"
                if not needs_gost_forwarding:
                    continue
                
                # panel_port: port on panel where gost listens (remote_port from spec = 8080)
                # node_port: port on node where xray listens (listen_port from spec = 10000)
                panel_port = tunnel.spec.get("remote_port") or tunnel.spec.get("listen_port")
                node_port = tunnel.spec.get("listen_port") or tunnel.spec.get("remote_port")
                if not panel_port or not node_port:
                    continue
                
                # Get node
                node_result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
                node = node_result.scalar_one_or_none()
                if not node:
                    continue
                
                # Get node address
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
                
                if not node_address:
                    continue
                
                # Start gost forwarding
                try:
                    logger.info(f"Restoring gost forwarding for tunnel {tunnel.id}: {tunnel.type}://:{panel_port} -> {node_address}:{node_port}")
                    gost_forwarder.start_forward(
                        tunnel_id=tunnel.id,
                        local_port=int(panel_port),
                        node_address=node_address,
                        remote_port=int(node_port),
                        tunnel_type=tunnel.type
                    )
                    logger.info(f"Successfully restored gost forwarding for tunnel {tunnel.id}")
                except Exception as e:
                    logger.error(f"Failed to restore forwarding for tunnel {tunnel.id}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error restoring forwards: {e}")


async def _restore_rathole_servers():
    """Restore Rathole servers for active tunnels on startup"""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tunnel).where(Tunnel.status == "active"))
            tunnels = result.scalars().all()
            
            for tunnel in tunnels:
                # Only restore Rathole tunnels
                if tunnel.core != "rathole":
                    continue
                
                remote_addr = tunnel.spec.get("remote_addr")
                token = tunnel.spec.get("token")
                proxy_port = tunnel.spec.get("remote_port") or tunnel.spec.get("listen_port")
                
                if not remote_addr or not token or not proxy_port:
                    continue
                
                # Start Rathole server
                rathole_server_manager.start_server(
                    tunnel_id=tunnel.id,
                    remote_addr=remote_addr,
                    token=token,
                    proxy_port=int(proxy_port)
                )
    except Exception as e:
        logger.error(f"Error restoring Rathole servers: {e}")


app = FastAPI(
    title="Smite Panel",
    description="Tunneling Control Panel",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(panel.router, prefix="/api/panel", tags=["panel"])
app.include_router(nodes.router, prefix="/api/nodes", tags=["nodes"])
app.include_router(tunnels.router, prefix="/api/tunnels", tags=["tunnels"])
app.include_router(usage.router, prefix="/api/usage", tags=["usage"])
app.include_router(status.router, prefix="/api/status", tags=["status"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])

# Serve frontend static files if available
static_dir = os.path.join(os.path.dirname(__file__), "static")
static_path = Path(static_dir)

if static_path.exists() and (static_path / "index.html").exists():
    # Mount static files
    app.mount("/static", StaticFiles(directory=static_path), name="static-assets")
    
    # Serve index.html for all non-API routes (SPA routing)
    from fastapi.responses import FileResponse
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend for all non-API routes"""
        # Don't interfere with API routes
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("redoc") or full_path.startswith("openapi.json"):
            raise HTTPException(status_code=404)
        
        # Check if it's a static file request
        file_path = static_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        
        # Otherwise serve index.html for SPA routing
        index_path = static_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        raise HTTPException(status_code=404)

@app.get("/")
async def root():
    """Root redirect"""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    index_path = Path(static_dir) / "index.html"
    if index_path.exists():
        from fastapi.responses import FileResponse
        return FileResponse(index_path)
    return {"message": "Smite Panel API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    
    if settings.https_enabled:
        import ssl
        cert_path = Path(settings.https_cert_path).resolve()
        key_path = Path(settings.https_key_path).resolve()
        
        if not cert_path.exists() or not key_path.exists():
            logger.warning(f"HTTPS enabled but certificate files not found. Using HTTP.")
            uvicorn.run(app, host=settings.panel_host, port=settings.panel_port)
        else:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(str(cert_path), str(key_path))
            uvicorn.run(
                app,
                host=settings.panel_host,
                port=settings.panel_port,
                ssl_keyfile=str(key_path),
                ssl_certfile=str(cert_path)
            )
    else:
        uvicorn.run(app, host=settings.panel_host, port=settings.panel_port)
