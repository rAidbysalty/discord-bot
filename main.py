import os
import logging
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import time
from typing import Optional, Literal
from dataclasses import dataclass

# === KEEP BOT ALIVE ===
from flask import Flask
from threading import Thread
import requests

# Flask web server to keep bot alive
app = Flask('')

@app.route('/')
def home():
    return "Unlimited Flood Bot is Alive and Ready!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
# === END KEEP BOT ALIVE ===

# Basic logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s:%(name)s: %(message)s")
logger = logging.getLogger(__name__)

@dataclass
class FloodConfig:
    """Configuration for unlimited flood."""
    channel: discord.TextChannel
    message: str
    count: int = 0  # 0 = infinite
    delay: float = 0.5
    mode: str = "normal"

class UnlimitedFloodBot(commands.Bot):
    """Bot with unlimited flood capabilities."""

    def __init__(self, command_prefix: str, intents: discord.Intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.active_floods = {}  # Track active floods for stopping
    
    async def setup_hook(self):
        """Setup when bot is ready to start."""
        await self.add_cog(SimpleNoLimitFlood(self))
        await self.tree.sync()
        print("✅ Commands synced!")
        
    def setup_unlimited_commands(self):
        """Setup unlimited flood commands."""
        
        # Main unlimited flood command
        @self.tree.command(
            name="flood",
            description="Flood a channel with unlimited messages"
        )
        @app_commands.describe(
            channel="Channel to flood",
            message="Message to send",
            count="Number of messages (0 = infinite)",
            delay="Delay between messages in seconds",
            mode="Flood mode",
            infinite="Run forever until stopped"
        )
        @app_commands.checks.has_permissions(administrator=True)
        async def unlimited_flood(
            ctx: discord.Interaction,
            channel: discord.TextChannel,
            message: str,
            count: int = 100,
            delay: float = 0.5,
            mode: Literal["normal", "embed", "webhook", "tts", "burst"] = "normal",
            infinite: bool = False
        ):
            """Unlimited flood command with no restrictions."""
            
            # If infinite is True or count is 0, set to maximum integer
            if infinite or count == 0:
                count = 2**31 - 1  # Maximum 32-bit integer
                await ctx.response.send_message(
                    "♾️ **INFINITE FLOOD ACTIVATED**\n"
                    "This will run forever until stopped with /flood_stop",
                    ephemeral=True
                )
            else:
                await ctx.response.send_message(
                    f"🚀 Starting flood of **{count}** messages...",
                    ephemeral=True
                )
            
            # No safety checks - unlimited
            # Sanitize inputs
            if count < 0:
                count = 0
            if delay < 0:
                delay = 0.0
            if len(message) > 2000:
                logger.warning("Message too long; truncating to 2000 chars")
                message = message[:1997] + "..."

            config = FloodConfig(
                channel=channel,
                message=message,
                count=count,
                delay=delay,
                mode=mode
            )
            
            # Create unique task ID
            task_id = f"{ctx.user.id}_{time.time()}"
            
            # Start unlimited flood
            task = asyncio.create_task(self.unlimited_flood_task(config, ctx, task_id))
            self.active_floods[task_id] = task
        
        # Enhanced stop command
        @self.tree.command(
            name="flood_stop_all",
            description="Stop ALL active floods"
        )
        @app_commands.checks.has_permissions(administrator=True)
        async def stop_all(ctx: discord.Interaction):
            """Stop all floods everywhere."""
            stopped = 0
            for task_id, task in list(self.active_floods.items()):
                if not task.done():
                    task.cancel()
                    stopped += 1
            
            await ctx.response.send_message(
                f"🛑 Stopped {stopped} active floods.",
                ephemeral=True
            )

        # Stop floods started by the invoking user
        @self.tree.command(
            name="flood_stop",
            description="Stop floods started by you"
        )
        @app_commands.checks.has_permissions(administrator=True)
        async def flood_stop(ctx: discord.Interaction):
            """Stop floods started by the invoking user."""
            stopped = 0
            prefix = f"{ctx.user.id}_"
            for task_id, task in list(self.active_floods.items()):
                if task_id.startswith(prefix) and not task.done():
                    task.cancel()
                    stopped += 1

            await ctx.response.send_message(
                f"🛑 Stopped {stopped} flood(s) started by you.",
                ephemeral=True
            )
        
        # Flood until command
        @self.tree.command(
            name="flood_until",
            description="Flood until a specific time or condition"
        )
        @app_commands.describe(
            channel="Channel to flood",
            message="Message to send",
            duration_minutes="Flood for X minutes (0 = forever)",
            target_time="Flood until specific time (HH:MM)",
            delay="Delay between messages"
        )
        @app_commands.checks.has_permissions(administrator=True)
        async def flood_until(
            ctx: discord.Interaction,
            channel: discord.TextChannel,
            message: str,
            duration_minutes: int = 0,
            target_time: Optional[str] = None,
            delay: float = 0.5
        ):
            """Flood for a duration or until time."""
            
            if duration_minutes == 0 and not target_time:
                await ctx.response.send_message(
                    "⚠️ Please specify either duration or target time!",
                    ephemeral=True
                )
                return
            
            # Calculate end time
            end_time = time.time()
            if duration_minutes > 0:
                end_time += duration_minutes * 60
                status = f"for {duration_minutes} minutes"
            elif target_time:
                # Parse time (simplified)
                from datetime import datetime
                now = datetime.now()
                try:
                    target = datetime.strptime(target_time, "%H:%M")
                    target = target.replace(year=now.year, month=now.month, day=now.day)
                    if target < now:
                        target = target.replace(day=now.day + 1)
                    
                    end_time = target.timestamp()
                    status = f"until {target_time}"
                except ValueError:
                    await ctx.response.send_message(
                        "❌ Invalid time format! Use HH:MM (24-hour format)",
                        ephemeral=True
                    )
                    return
            
            await ctx.response.send_message(
                f"⏱️ Flooding {status}...",
                ephemeral=True
            )
            
            # Start timed flood
            # Sanitize inputs for timed flood
            if delay < 0:
                delay = 0.0
            if len(message) > 2000:
                logger.warning("Timed flood message too long; truncating to 2000 chars")
                message = message[:1997] + "..."

            config = FloodConfig(
                channel=channel,
                message=message,
                count=0,
                delay=delay,
                mode="normal"
            )
            
            task_id = f"{ctx.user.id}_timed_{time.time()}"
            task = asyncio.create_task(self.timed_flood_task(config, end_time, ctx, task_id))
            self.active_floods[task_id] = task
    
    async def unlimited_flood_task(self, config: FloodConfig, ctx: discord.Interaction, task_id: str):
        """Unlimited flood task with no restrictions."""
        
        sent = 0
        start_time = time.time()
        
        try:
            # Infinite loop if count is max int
            while sent < config.count:
                try:
                    # Send message
                    await config.channel.send(config.message)
                    sent += 1
                    
                    # Update status every 100 messages
                    if sent % 100 == 0:
                        elapsed = time.time() - start_time
                        rate = sent / elapsed if elapsed > 0 else 0
                        
                        try:
                            await ctx.followup.send(
                                f"📊 **Progress**: {sent:,} messages sent\n"
                                f"⏱️ **Rate**: {rate:.1f} msg/sec\n"
                                f"⏰ **Elapsed**: {elapsed:.1f}s",
                                ephemeral=True
                            )
                        except Exception:
                            logger.exception("Failed to send progress followup")
                    
                    # Apply delay (except in burst mode)
                    if config.delay > 0:
                        await asyncio.sleep(config.delay)
                
                except discord.HTTPException as e:
                    if getattr(e, 'status', None) == 429:  # Rate limited
                        retry = getattr(e, 'retry_after', 1)
                        logger.warning("Rate limited; retrying after %s seconds", retry)
                        await asyncio.sleep(retry)
                    else:
                        logger.exception("HTTP error while sending message")
                        await asyncio.sleep(1)
        
        except asyncio.CancelledError:
            # Task was cancelled
            try:
                await ctx.followup.send("⏹️ Flood stopped manually.", ephemeral=True)
            except Exception:
                logger.exception("Failed to send cancel followup")
        
        finally:
            # Remove from active floods
            self.active_floods.pop(task_id, None)
            
            # Send completion summary
            elapsed = time.time() - start_time
            rate = sent / elapsed if elapsed > 0 else 0
            
            try:
                await ctx.followup.send(
                    f"✅ **Flood Complete**\n"
                    f"📨 Sent: {sent:,} messages\n"
                    f"⏱️ Duration: {elapsed:.1f}s\n"
                    f"📊 Average: {rate:.1f} msg/sec",
                    ephemeral=True
                )
            except Exception:
                logger.exception("Failed to send completion followup")
    
    async def timed_flood_task(self, config: FloodConfig, end_time: float, ctx: discord.Interaction, task_id: str):
        """Flood until a specific time."""
        
        sent = 0
        
        try:
            while time.time() < end_time:
                try:
                    # Calculate remaining time
                    remaining = end_time - time.time()
                    if remaining <= 0:
                        break
                    
                    # Send message
                    await config.channel.send(config.message)
                    sent += 1
                    
                    # Apply delay
                    if config.delay > 0:
                        await asyncio.sleep(min(config.delay, remaining))
                    else:
                        # Check every 0.1 seconds if we should stop
                        await asyncio.sleep(0.1)
                
                except discord.HTTPException as e:
                    if getattr(e, 'status', None) == 429:
                        retry = getattr(e, 'retry_after', 1)
                        logger.warning("Timed flood rate limited; retrying after %s", retry)
                        await asyncio.sleep(retry)
                    else:
                        logger.exception("HTTP error during timed flood")
                        await asyncio.sleep(1)
        
        except asyncio.CancelledError:
            try:
                await ctx.followup.send("⏹️ Timed flood stopped manually.", ephemeral=True)
            except Exception:
                logger.exception("Failed to send timed cancel followup")
        
        finally:
            # Remove from active floods
            self.active_floods.pop(task_id, None)
            
            # Send completion
            try:
                await ctx.followup.send(
                    f"⏰ **Timed Flood Complete**\n"
                    f"📨 Sent: {sent:,} messages",
                    ephemeral=True
                )
            except Exception:
                logger.exception("Failed to send timed completion followup")

# ==================== SIMPLE NO-LIMIT FLOOD ====================

class SimpleNoLimitFlood(commands.Cog):
    """Simple no-limit flood commands."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="nuke")
    @app_commands.describe(
        channel="Channel to nuke",
        message="Message to spam",
        count="How many times (no limit)",
        delay="Delay between"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def nuke(self, ctx: discord.Interaction, 
                   channel: discord.TextChannel,
                   message: str,
                   count: int,
                   delay: float = 0.1):
        """No-limit nuke command."""
        
        # NO LIMITS APPLIED - user can enter any number
        
        # Sanitize inputs
        if count < 0:
            count = 0
        if delay < 0:
            delay = 0.0
        if len(message) > 2000:
            logger.warning("Nuke message too long; truncating to 2000 chars")
            message = message[:1997] + "..."

        await ctx.response.send_message(
            f"💣 **NUKE ACTIVATED**\n"
            f"Sending {count:,} messages to {channel.mention}\n"
            f"Estimated time: {count * delay / 60:.1f} minutes",
            ephemeral=True
        )
        
        # Start nuking
        sent = 0
        for i in range(count):
            try:
                await channel.send(message)
                sent += 1
                
                if sent % 100 == 0:
                    # Update progress every 100 messages
                    progress = (sent / count) * 100
                    try:
                        await ctx.followup.send(
                            f"📊 Progress: {sent:,}/{count:,} ({progress:.1f}%)",
                            ephemeral=True
                        )
                    except:
                        pass
                
                if delay > 0:
                    await asyncio.sleep(delay)
                    
            except Exception:
                logger.exception("Error sending nuke message; retrying")
                await asyncio.sleep(1)  # Wait and continue
        
        try:
            await ctx.followup.send(f"✅ Nuke complete! Sent {sent:,} messages.", ephemeral=True)
        except Exception:
            logger.exception("Failed to send nuke completion followup")

# ==================== RUNNING THE BOT ====================

def run_unlimited_bot(token: Optional[str] = None):
    """Run the unlimited flood bot."""
    # === KEEP ALIVE - Start Flask server ===
    keep_alive()
    print("🌐 Flask keep-alive server started on port 8080")
    # === END KEEP ALIVE ===
    
    # Prefer environment variable if token not provided
    if not token:
        token = os.getenv("DISCORD_BOT_TOKEN")

    if not token:
        logger.error("No bot token provided. Set the DISCORD_BOT_TOKEN env var or pass a token.")
        logger.info("Create a bot token at: https://discord.com/developers/applications")
        return
    
    # FIXED INTENTS - Only enable what we actually need
    intents = discord.Intents.default()
    intents.message_content = True  # This is now a privileged intent!
    
    # IMPORTANT: You must enable Message Content Intent in Discord Developer Portal
    # Go to: https://discord.com/developers/applications
    # Select your bot > Bot > Privileged Gateway Intents > Enable "MESSAGE CONTENT INTENT"
    
    bot = UnlimitedFloodBot(command_prefix="!", intents=intents)
    
    # Setup commands
    bot.setup_unlimited_commands()
    
    @bot.event
    async def on_ready():
        logger.info("Unlimited Flood Bot ready as %s", bot.user)
        logger.info("Application ID: %s", bot.application_id)
        logger.warning("This bot can be used to spam; ensure you have permission to run it.")
        
        # === AUTO-PING SETUP ===
        # This helps keep the bot awake on Replit
        async def keep_awake():
            while True:
                try:
                    # Ping the Flask server to keep it active
                    requests.get('http://localhost:8080', timeout=5)
                except:
                    pass
                await asyncio.sleep(300)  # Ping every 5 minutes
        
        # Start the keep-awake task
        asyncio.create_task(keep_awake())
        logger.info("Auto-ping task started to prevent sleep")
        # === END AUTO-PING ===
    
    @bot.event
    async def on_error(event, *args, **kwargs):
        logger.exception("Error in %s", event)
    
    try:
        bot.run(token, reconnect=True)
    except discord.LoginFailure:
        logger.error("Invalid token! Please check your bot token.")
    except discord.errors.PrivilegedIntentsRequired as e:
        logger.error("PRIVILEGED INTENTS ERROR!")
        logger.error("You need to enable Message Content Intent in Discord Developer Portal:")
        logger.error("1. Go to: https://discord.com/developers/applications")
        logger.error("2. Select your application (ID: %s)", bot.application_id if hasattr(bot, 'application_id') else "unknown")
        logger.error("3. Go to 'Bot' section")
        logger.error("4. Scroll to 'Privileged Gateway Intents'")
        logger.error("5. ENABLE 'MESSAGE CONTENT INTENT'")
        logger.error("6. Save changes and restart the bot")
    except Exception as e:
        logger.exception("Error starting bot")

if __name__ == "__main__":
    print("🚀 Starting Unlimited Flood Bot...")
    print("=" * 50)
    print("⚠️  CRITICAL WARNING:")
    print("⚠️  This bot VIOLATES Discord Terms of Service!")
    print("⚠️  Using it WILL result in:")
    print("   - Permanent bot token ban")
    print("   - Possible account suspension")
    print("   - Server deletion if self-hosted")
    print("=" * 50)
    
    # Check if intents are enabled
    print("\n🔧 REQUIRED SETUP:")
    print("1. Go to: https://discord.com/developers/applications")
    print("2. Select your application")
    print("3. Go to 'Bot' section")
    print("4. Scroll to 'Privileged Gateway Intents'")
    print("5. ENABLE 'MESSAGE CONTENT INTENT'")
    print("6. Save changes")
    print("=" * 50)
    
    # === REPLIT HOSTING INFO ===
    print("\n🌐 REPLIT HOSTING SETUP:")
    print("1. Upload this file to Replit")
    print("2. Create these Secrets (lock icon in sidebar):")
    print("   - DISCORD_BOT_TOKEN = your_bot_token_here")
    print("   - REPLIT_DB_URL = (leave empty, just create the key)")
    print("3. Install dependencies in shell:")
    print("   pip install discord.py flask requests")
    print("4. Click 'Run' button")
    print("5. Setup UptimeRobot: https://uptimerobot.com")
    print("   - Monitor Type: HTTP(s)")
    print("   - URL: Copy from Replit webview")
    print("   - Interval: 5 minutes")
    print("=" * 50)
    
    # Token must be provided via environment variable for safety
    token = os.getenv("BOT_TOKEN_HERE")
        print(f"✅ Token found ({len(token)} characters)")
        response = input("\nDo you want to continue? (yes/no): ")
        if response.lower() in ["yes", "y"]:
            run_unlimited_bot(token)
        else:
            print("Bot startup cancelled.")
