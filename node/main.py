"""
Smite Node - Lightweight Agent
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import agent
from app.hysteria2_client import Hysteria2Client
from app.core_adapters import AdapterManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def usage_reporting_task(app: FastAPI):
    """Periodic task to collect and report usage"""
    import asyncio
    while True:
        try:
            await asyncio.sleep(60)  # Report every 60 seconds
            
            adapter_manager = app.state.adapter_manager
            h2_client = app.state.h2_client
            
            if not adapter_manager or not h2_client or not h2_client.node_id:
                continue
            
            # Collect usage for all active tunnels
            for tunnel_id, adapter in adapter_manager.active_tunnels.items():
                try:
                    usage_mb = adapter.get_usage_mb(tunnel_id)
                    
                    # Calculate incremental usage
                    # adapter_manager.usage_tracking stores MB as float
                    previous_mb = adapter_manager.usage_tracking.get(tunnel_id, 0.0)
                    
                    # Both are in MB now, so compare directly
                    if usage_mb > previous_mb:
                        incremental_mb = usage_mb - previous_mb
                        # Store in MB
                        adapter_manager.usage_tracking[tunnel_id] = usage_mb
                        
                        # Convert to bytes for reporting
                        incremental_bytes = int(incremental_mb * 1024 * 1024)
                        
                        if incremental_bytes > 0:
                            await h2_client.push_usage_to_panel(
                                tunnel_id=tunnel_id,
                                node_id=h2_client.node_id,
                                bytes_used=incremental_bytes
                            )
                    elif previous_mb == 0.0 and usage_mb > 0:
                        # First time tracking, store but don't report
                        adapter_manager.usage_tracking[tunnel_id] = usage_mb
                except Exception as e:
                    print(f"Warning: Failed to report usage for tunnel {tunnel_id}: {e}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error in usage reporting task: {e}")
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Start Hysteria2 client and connect to panel
    h2_client = Hysteria2Client()
    await h2_client.start()
    app.state.h2_client = h2_client
    
    # Initialize adapter manager
    adapter_manager = AdapterManager()
    app.state.adapter_manager = adapter_manager
    
    # Auto-register with panel
    try:
        await h2_client.register_with_panel()
    except Exception as e:
        print(f"Warning: Could not register with panel: {e}")
        print("Node will continue running but manual registration may be needed")
    
    # Start usage reporting task
    usage_task = asyncio.create_task(usage_reporting_task(app))
    app.state.usage_task = usage_task
    
    yield
    
    # Shutdown
    if hasattr(app.state, 'usage_task'):
        app.state.usage_task.cancel()
        try:
            await app.state.usage_task
        except asyncio.CancelledError:
            pass
    if hasattr(app.state, 'h2_client'):
        await app.state.h2_client.stop()
    if hasattr(app.state, 'adapter_manager'):
        await app.state.adapter_manager.cleanup()


app = FastAPI(
    title="Smite Node",
    description="Lightweight Tunnel Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add logging middleware
from app.routers.agent import LoggingMiddleware
app.add_middleware(LoggingMiddleware)

app.include_router(agent.router, prefix="/api/agent", tags=["agent"])


@app.get("/")
async def root():
    return {"status": "ok", "service": "smite-node"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)

