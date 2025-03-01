import os
import logging
import asyncio

from config_manager import setup_logging, get_config
from bot_commands import setup_bot_commands
from download_manager import DownloadManager
from multipart_manager import MultipartManager

# Setup logging
logger = setup_logging()

async def main():
    """Main entry point for the Telegram download bot"""
    
    # Load configuration
    config = get_config()
    
    # Create download directory
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    
    # Initialize managers
    download_manager = DownloadManager(config)
    multipart_manager = MultipartManager(config, download_manager)
    
    # Start the client
    client = await download_manager.initialize_client()
    logger.info("Bot started! Using local bot API for unrestricted file sizes.")
    
    # Register command handlers
    setup_bot_commands(client, download_manager, multipart_manager)
    
    # Keep the client running
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())