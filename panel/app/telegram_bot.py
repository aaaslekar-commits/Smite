"""Telegram bot for panel management"""
import asyncio
import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Node, Tunnel, Settings

logger = logging.getLogger(__name__)

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not installed. Telegram bot will not work.")


class TelegramBot:
    """Telegram bot for managing panel"""
    
    def __init__(self):
        self.application: Optional[Application] = None
        self.enabled = False
        self.bot_token: Optional[str] = None
        self.admin_ids: List[str] = []
        self.backup_task: Optional[asyncio.Task] = None
        self.backup_enabled = False
        self.backup_interval = 60
        self.backup_interval_unit = "minutes"
    
    async def load_settings(self):
        """Load settings from database"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Settings).where(Settings.key == "telegram"))
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                self.enabled = setting.value.get("enabled", False)
                self.bot_token = setting.value.get("bot_token")
                self.admin_ids = setting.value.get("admin_ids", [])
                self.backup_enabled = setting.value.get("backup_enabled", False)
                self.backup_interval = setting.value.get("backup_interval", 60)
                self.backup_interval_unit = setting.value.get("backup_interval_unit", "minutes")
            else:
                self.enabled = False
                self.bot_token = None
                self.admin_ids = []
                self.backup_enabled = False
                self.backup_interval = 60
                self.backup_interval_unit = "minutes"
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return str(user_id) in self.admin_ids
    
    async def start(self):
        """Start Telegram bot"""
        if not TELEGRAM_AVAILABLE:
            logger.error("python-telegram-bot not available. Cannot start bot.")
            return False
        
        await self.load_settings()
        
        if not self.enabled or not self.bot_token:
            logger.info("Telegram bot not enabled or token not set")
            return False
        
        # Stop existing instance if running
        await self.stop()
        
        try:
            self.application = Application.builder().token(self.bot_token).build()
            
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("help", self.cmd_help))
            self.application.add_handler(CommandHandler("nodes", self.cmd_nodes))
            self.application.add_handler(CommandHandler("tunnels", self.cmd_tunnels))
            self.application.add_handler(CommandHandler("status", self.cmd_status))
            self.application.add_handler(CommandHandler("backup", self.cmd_backup))
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))
            
            await self.application.initialize()
            await self.application.start()
            
            # Use drop_pending_updates to avoid conflicts
            await self.application.updater.start_polling(drop_pending_updates=True)
            
            await self.start_backup_task()
            
            logger.info("Telegram bot started successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}", exc_info=True)
            # Clean up on failure
            await self.stop()
            return False
    
    async def stop(self):
        """Stop Telegram bot"""
        await self.stop_backup_task()
        
        if self.application:
            try:
                if self.application.updater and self.application.updater.running:
                    await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            except Exception as e:
                logger.warning(f"Error stopping Telegram bot: {e}")
            finally:
                self.application = None
                logger.info("Telegram bot stopped")
    
    async def start_backup_task(self):
        """Start automatic backup task"""
        await self.stop_backup_task()
        await self.load_settings()
        
        if self.backup_enabled and self.admin_ids:
            self.backup_task = asyncio.create_task(self._backup_loop())
            logger.info(f"Automatic backup task started: interval={self.backup_interval} {self.backup_interval_unit}")
    
    async def stop_backup_task(self):
        """Stop automatic backup task"""
        if self.backup_task:
            self.backup_task.cancel()
            try:
                await self.backup_task
            except asyncio.CancelledError:
                pass
            self.backup_task = None
            logger.info("Automatic backup task stopped")
    
    async def _backup_loop(self):
        """Background task for automatic backups"""
        try:
            while True:
                await self.load_settings()
                
                if not self.backup_enabled or not self.admin_ids:
                    await asyncio.sleep(60)
                    continue
                
                if self.backup_interval_unit == "hours":
                    sleep_seconds = self.backup_interval * 3600
                else:
                    sleep_seconds = self.backup_interval * 60
                
                await asyncio.sleep(sleep_seconds)
                
                if not self.backup_enabled:
                    continue
                
                try:
                    backup_path = await self.create_backup()
                    if backup_path and self.application and self.application.bot:
                        for admin_id_str in self.admin_ids:
                            try:
                                admin_id = int(admin_id_str)
                                with open(backup_path, 'rb') as f:
                                    await self.application.bot.send_document(
                                        chat_id=admin_id,
                                        document=f,
                                        filename=f"smite_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                                        caption=f"🔄 Automatic backup - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                                    )
                            except Exception as e:
                                logger.error(f"Failed to send backup to admin {admin_id_str}: {e}")
                        
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        logger.info("Automatic backup sent successfully")
                except Exception as e:
                    logger.error(f"Error in automatic backup: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("Backup loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Backup loop error: {e}", exc_info=True)
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied. You are not an admin.")
            return
        
        await update.message.reply_text(
            "👋 Welcome to Smite Panel Bot!\n\n"
            "Use /help to see available commands."
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied. You are not an admin.")
            return
        
        help_text = """📋 Available Commands:

/nodes - List all nodes
/tunnels - List all tunnels
/status - Show panel status
/backup - Create and send backup

Use buttons in messages to interact with nodes and tunnels."""
        
        await update.message.reply_text(help_text)
    
    async def cmd_nodes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /nodes command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied. You are not an admin.")
            return
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Node))
            nodes = result.scalars().all()
            
            if not nodes:
                await update.message.reply_text("📭 No nodes found.")
                return
            
            text = "🖥️ Nodes:\n\n"
            for node in nodes:
                status = "🟢" if node.status == "active" else "🔴"
                role = node.node_metadata.get("role", "unknown") if node.node_metadata else "unknown"
                text += f"{status} {node.name} ({role})\n"
                text += f"   ID: {node.id[:8]}...\n\n"
            
            keyboard = []
            for node in nodes:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📊 {node.name}",
                        callback_data=f"node_info_{node.id}"
                    )
                ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup)
    
    async def cmd_tunnels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /tunnels command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied. You are not an admin.")
            return
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Tunnel))
            tunnels = result.scalars().all()
            
            if not tunnels:
                await update.message.reply_text("📭 No tunnels found.")
                return
            
            text = f"🔗 Tunnels ({len(tunnels)}):\n\n"
            for tunnel in tunnels[:10]:
                status = "🟢" if tunnel.status == "active" else "🔴"
                text += f"{status} {tunnel.name} ({tunnel.core})\n"
            
            if len(tunnels) > 10:
                text += f"\n... and {len(tunnels) - 10} more"
            
            keyboard = []
            for tunnel in tunnels[:5]:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🔗 {tunnel.name}",
                        callback_data=f"tunnel_info_{tunnel.id}"
                    )
                ])
            
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await update.message.reply_text(text, reply_markup=reply_markup)
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied. You are not an admin.")
            return
        
        async with AsyncSessionLocal() as session:
            nodes_result = await session.execute(select(Node))
            nodes = nodes_result.scalars().all()
            
            tunnels_result = await session.execute(select(Tunnel))
            tunnels = tunnels_result.scalars().all()
            
            active_nodes = sum(1 for n in nodes if n.status == "active")
            active_tunnels = sum(1 for t in tunnels if t.status == "active")
            
            text = f"""📊 Panel Status:

🖥️ Nodes: {active_nodes}/{len(nodes)} active
🔗 Tunnels: {active_tunnels}/{len(tunnels)} active
"""
            
            keyboard = [
                [
                    InlineKeyboardButton("🖥️ View Nodes", callback_data="cmd_nodes"),
                    InlineKeyboardButton("🔗 View Tunnels", callback_data="cmd_tunnels")
                ],
                [
                    InlineKeyboardButton("📦 Create Backup", callback_data="cmd_backup"),
                    InlineKeyboardButton("🔄 Refresh", callback_data="cmd_status")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup)
    
    async def cmd_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /backup command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied. You are not an admin.")
            return
        
        await update.message.reply_text("📦 Creating backup...")
        
        try:
            backup_path = await self.create_backup()
            if backup_path:
                with open(backup_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=f"smite_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        caption="✅ Backup created successfully"
                    )
                os.remove(backup_path)
            else:
                await update.message.reply_text("❌ Failed to create backup")
        except Exception as e:
            logger.error(f"Error creating backup: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error creating backup: {str(e)}")
    
    async def create_backup(self) -> Optional[str]:
        """Create backup archive"""
        try:
            from app.config import settings
            import os
            
            backup_dir = Path("/tmp/smite_backup")
            backup_dir.mkdir(exist_ok=True)
            
            db_path = Path("./data/smite.db")
            if db_path.exists():
                shutil.copy2(db_path, backup_dir / "smite.db")
            
            env_path = Path(".env")
            if env_path.exists():
                shutil.copy2(env_path, backup_dir / ".env")
            
            docker_compose = Path("docker-compose.yml")
            if docker_compose.exists():
                shutil.copy2(docker_compose, backup_dir / "docker-compose.yml")
            
            certs_dir = Path("./certs")
            if certs_dir.exists():
                shutil.copytree(certs_dir, backup_dir / "certs", dirs_exist_ok=True)
            
            node_cert_path = Path(settings.node_cert_path)
            if not node_cert_path.is_absolute():
                node_cert_path = Path(os.getcwd()) / node_cert_path
            if node_cert_path.exists():
                (backup_dir / "node_certs").mkdir(exist_ok=True)
                shutil.copy2(node_cert_path, backup_dir / "node_certs" / "ca.crt")
            
            node_key_path = Path(settings.node_key_path)
            if not node_key_path.is_absolute():
                node_key_path = Path(os.getcwd()) / node_key_path
            if node_key_path.exists():
                (backup_dir / "node_certs").mkdir(exist_ok=True)
                shutil.copy2(node_key_path, backup_dir / "node_certs" / "ca.key")
            
            server_cert_path = Path(settings.node_server_cert_path)
            if not server_cert_path.is_absolute():
                server_cert_path = Path(os.getcwd()) / server_cert_path
            if server_cert_path.exists():
                (backup_dir / "server_certs").mkdir(exist_ok=True)
                shutil.copy2(server_cert_path, backup_dir / "server_certs" / "ca-server.crt")
            
            server_key_path = Path(settings.node_server_key_path)
            if not server_key_path.is_absolute():
                server_key_path = Path(os.getcwd()) / server_key_path
            if server_key_path.exists():
                (backup_dir / "server_certs").mkdir(exist_ok=True)
                shutil.copy2(server_key_path, backup_dir / "server_certs" / "ca-server.key")
            
            data_dir = Path("./data")
            if data_dir.exists():
                (backup_dir / "data").mkdir(exist_ok=True)
                for item in data_dir.iterdir():
                    if item.is_file() and item.suffix in ['.json', '.yaml', '.toml']:
                        shutil.copy2(item, backup_dir / "data" / item.name)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"/tmp/smite_backup_{timestamp}.zip"
            
            with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(backup_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(backup_dir)
                        zipf.write(file_path, arcname)
            
            shutil.rmtree(backup_dir)
            
            return backup_file
        except Exception as e:
            logger.error(f"Error creating backup: {e}", exc_info=True)
            return None
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        if not self.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Access denied. You are not an admin.")
            return
        
        data = query.data
        
        if data.startswith("node_info_"):
            node_id = data.replace("node_info_", "")
            await self.show_node_info(query, node_id)
        elif data.startswith("tunnel_info_"):
            tunnel_id = data.replace("tunnel_info_", "")
            await self.show_tunnel_info(query, tunnel_id)
        elif data == "cmd_nodes":
            await self.cmd_nodes_callback(query)
        elif data == "cmd_tunnels":
            await self.cmd_tunnels_callback(query)
        elif data == "cmd_backup":
            await self.cmd_backup_callback(query)
        elif data == "cmd_status":
            await self.cmd_status_callback(query)
    
    async def show_node_info(self, query, node_id: str):
        """Show node information"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Node).where(Node.id == node_id))
            node = result.scalar_one_or_none()
            
            if not node:
                await query.edit_message_text("❌ Node not found.")
                return
            
            role = node.node_metadata.get("role", "unknown") if node.node_metadata else "unknown"
            ip = node.node_metadata.get("ip_address", "N/A") if node.node_metadata else "N/A"
            
            text = f"""🖥️ Node: {node.name}

📋 ID: {node.id}
🌐 Role: {role}
📍 IP: {ip}
📊 Status: {node.status}
"""
            
            keyboard = [
                [InlineKeyboardButton("🔙 Back to Nodes", callback_data="cmd_nodes")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def show_tunnel_info(self, query, tunnel_id: str):
        """Show tunnel information"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
            tunnel = result.scalar_one_or_none()
            
            if not tunnel:
                await query.edit_message_text("❌ Tunnel not found.")
                return
            
            text = f"""🔗 Tunnel: {tunnel.name}

📋 ID: {tunnel.id}
🔧 Core: {tunnel.core}
📊 Status: {tunnel.status}
"""
            
            keyboard = [
                [InlineKeyboardButton("🔙 Back to Tunnels", callback_data="cmd_tunnels")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def cmd_nodes_callback(self, query):
        """Handle nodes command from callback"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Node))
            nodes = result.scalars().all()
            
            if not nodes:
                await query.edit_message_text("📭 No nodes found.")
                return
            
            text = "🖥️ Nodes:\n\n"
            for node in nodes:
                status = "🟢" if node.status == "active" else "🔴"
                role = node.node_metadata.get("role", "unknown") if node.node_metadata else "unknown"
                text += f"{status} {node.name} ({role})\n"
                text += f"   ID: {node.id[:8]}...\n\n"
            
            keyboard = []
            for node in nodes:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📊 {node.name}",
                        callback_data=f"node_info_{node.id}"
                    )
                ])
            keyboard.append([InlineKeyboardButton("🔙 Back to Status", callback_data="cmd_status")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def cmd_tunnels_callback(self, query):
        """Handle tunnels command from callback"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Tunnel))
            tunnels = result.scalars().all()
            
            if not tunnels:
                await query.edit_message_text("📭 No tunnels found.")
                return
            
            text = f"🔗 Tunnels ({len(tunnels)}):\n\n"
            for tunnel in tunnels[:10]:
                status = "🟢" if tunnel.status == "active" else "🔴"
                text += f"{status} {tunnel.name} ({tunnel.core})\n"
            
            if len(tunnels) > 10:
                text += f"\n... and {len(tunnels) - 10} more"
            
            keyboard = []
            for tunnel in tunnels[:5]:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🔗 {tunnel.name}",
                        callback_data=f"tunnel_info_{tunnel.id}"
                    )
                ])
            keyboard.append([InlineKeyboardButton("🔙 Back to Status", callback_data="cmd_status")])
            
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def cmd_backup_callback(self, query):
        """Handle backup command from callback"""
        await query.edit_message_text("📦 Creating backup...")
        
        try:
            backup_path = await self.create_backup()
            if backup_path:
                with open(backup_path, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=f"smite_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        caption="✅ Backup created successfully"
                    )
                os.remove(backup_path)
                await query.edit_message_text("✅ Backup created and sent successfully!")
            else:
                await query.edit_message_text("❌ Failed to create backup")
        except Exception as e:
            logger.error(f"Error creating backup: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error creating backup: {str(e)}")
    
    async def cmd_status_callback(self, query):
        """Handle status command from callback"""
        async with AsyncSessionLocal() as session:
            nodes_result = await session.execute(select(Node))
            nodes = nodes_result.scalars().all()
            
            tunnels_result = await session.execute(select(Tunnel))
            tunnels = tunnels_result.scalars().all()
            
            active_nodes = sum(1 for n in nodes if n.status == "active")
            active_tunnels = sum(1 for t in tunnels if t.status == "active")
            
            text = f"""📊 Panel Status:

🖥️ Nodes: {active_nodes}/{len(nodes)} active
🔗 Tunnels: {active_tunnels}/{len(tunnels)} active
"""
            
            keyboard = [
                [
                    InlineKeyboardButton("🖥️ View Nodes", callback_data="cmd_nodes"),
                    InlineKeyboardButton("🔗 View Tunnels", callback_data="cmd_tunnels")
                ],
                [
                    InlineKeyboardButton("📦 Create Backup", callback_data="cmd_backup"),
                    InlineKeyboardButton("🔄 Refresh", callback_data="cmd_status")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)


telegram_bot = TelegramBot()


