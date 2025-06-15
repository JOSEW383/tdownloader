import os
import time
import asyncio
import logging
from collections import defaultdict

from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeFilename
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged

logger = logging.getLogger(__name__)

class DownloadProgress:
    """Class to track download progress"""
    def __init__(self, chat_id, message_id, file_name, total_size):
        self.chat_id = chat_id
        self.message_id = message_id
        self.file_name = file_name
        self.total_size = total_size
        self.start_time = time.time()
        self.downloaded = 0
        self.progress_message = None
        self.last_update_time = 0
        self.complete = False

class DownloadManager:
    """Manager for download operations"""
    def __init__(self, config):
        self.config = config
        self.downloads = {}  # Mapping of file_id to progress information
        self.media_groups = defaultdict(list)
        self.active_tasks = {}  # Mapping of file_id to asyncio tasks
        self.cancel_flags = {}  # Mapping of file_id to cancel status
        self.client = None
        
    async def initialize_client(self):
        """Initialize and return the TelegramClient"""
        # Initialize client with larger upload/download limits and proper connection type
        self.client = TelegramClient(
            'bot_session',
            self.config.API_ID,
            self.config.API_HASH,
            base_logger=logger,
            connection=ConnectionTcpAbridged,
            connection_retries=None,
            flood_sleep_threshold=60,  # More tolerant to flood wait
        )
        
        # Configure to use local bot API server - don't use session.set_dc for bot API
        if self.config.SERVER_URL:
            try:
                logger.info(f"Using bot API server at {self.config.SERVER_URL}")
                # For bot API servers, we don't need to manually configure the session
                # The bot token login will handle this automatically
            except Exception as e:
                logger.error(f"Failed to set custom server: {e}")
        
        # Start the client
        await self.client.start(bot_token=self.config.BOT_TOKEN)
        return self.client
        
    async def process_document(self, client, event):
        """Process a document (file) sent to the bot"""
        file_name = None
        
        # Get file name from attributes
        for attr in event.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                file_name = attr.file_name
                break
        
        if not file_name:
            file_name = f"file_{event.document.id}"
        
        # Create progress message
        progress_msg = await event.respond(f"📥 Starting download of {file_name}...")
        
        # Setup progress tracking
        progress = DownloadProgress(
            event.chat_id,
            progress_msg.id,
            file_name,
            event.document.size
        )
        progress.progress_message = progress_msg
        
        file_id = f"{event.document.id}"
        self.downloads[file_id] = progress
        self.cancel_flags[file_id] = False
        
        # Get the download destination path
        download_path = os.path.join(self.config.DOWNLOAD_DIR, file_name)
        
        # Create a task for the download so it can be canceled
        download_task = asyncio.create_task(
            self.download_file_with_progress(client, event, download_path, progress, file_id)
        )
        self.active_tasks[file_id] = download_task
        
        try:
            await download_task
        except asyncio.CancelledError:
            logger.info(f"Download of {file_name} was cancelled")
            # The cancellation is already handled in the download function
        except Exception as e:
            logger.error(f"Error in download task for {file_name}: {str(e)}", exc_info=True)
            if not self.cancel_flags.get(file_id, False):  # Don't show error for intentional cancellations
                await client.edit_message(
                    progress.chat_id,
                    progress.message_id,
                    f"❌ Error downloading {file_name}: {str(e)}"
                )
        
        finally:
            # Clean up 
            if file_id in self.active_tasks:
                del self.active_tasks[file_id]
            if file_id in self.cancel_flags:
                del self.cancel_flags[file_id]

    async def update_progress_message(self, client, progress, force=False):
        """Update progress message with throttling to avoid flood limits"""
        current_time = time.time()
        # Update at most once per second unless force=True
        if force or current_time - progress.last_update_time >= 1:
            progress.last_update_time = current_time
            
            # Calculate metrics
            percent = (progress.downloaded / progress.total_size) * 100 if progress.total_size > 0 else 0
            elapsed = current_time - progress.start_time
            speed = progress.downloaded / elapsed if elapsed > 0 else 0
            speed_mb = speed / (1024 * 1024)
            remaining = (progress.total_size - progress.downloaded) / speed if speed > 0 else 0
            
            # Format download size
            downloaded_mb = progress.downloaded / (1024 * 1024)
            total_mb = progress.total_size / (1024 * 1024)
            
            await client.edit_message(
                progress.chat_id,
                progress.message_id,
                f"📥 Downloading {progress.file_name}...\n"
                f"Progress: {percent:.1f}% ({downloaded_mb:.2f} MB / {total_mb:.2f} MB)\n"
                f"Speed: {speed_mb:.2f} MB/s\n"
                f"Remaining time: {int(remaining // 60)}m {int(remaining % 60)}s"
            )
        
    async def download_file_with_progress(self, client, event, download_path, progress, file_id):
        """Download a file with progress updates"""
        from multipart_manager import get_multipart_info  # Import here to avoid circular imports
        
        try:
            # Tell user we're starting the download
            await client.edit_message(
                progress.chat_id,
                progress.message_id,
                f"📥 Preparing download of {progress.file_name}... (Size: {event.document.size / (1024 * 1024):.2f} MB)"
            )
            
            # First, initialize the progress
            progress.total_size = event.document.size
            
            # Define callback function for our custom download
            async def progress_callback(received_bytes):
                progress.downloaded = received_bytes
                # Check if download should be cancelled
                if self.cancel_flags.get(file_id, False):
                    raise asyncio.CancelledError("Download cancelled by user")
                await self.update_progress_message(client, progress)
            
            # Download the file
            if event.document.size > 20 * 1024 * 1024:  # For files larger than 20MB
                logger.info(f"Large file detected: {progress.file_name} ({event.document.size / (1024 * 1024):.2f} MB)")
                await self.download_large_file(client, event.document, download_path, progress, progress_callback)
            else:
                # For smaller files, use the standard download method
                await client.download_media(
                    event.document,
                    file=download_path,
                    progress_callback=lambda received, total: asyncio.create_task(
                        progress_callback(received)
                    )
                )
            
            # If we get here, the download completed successfully
            # Calculate total download time and size in MB
            total_time = time.time() - progress.start_time
            file_size_mb = progress.total_size / (1024 * 1024)
            avg_speed = file_size_mb / total_time if total_time > 0 else 0
            
            # Mark as complete
            progress.complete = True
            
            # Update message after successful download
            await client.edit_message(
                progress.chat_id,
                progress.message_id,
                f"✅ Download completed: {progress.file_name}\n"
                f"Size: {file_size_mb:.2f} MB\n"
                f"Total time: {int(total_time // 60)}m {int(total_time % 60)}s\n"
                f"Average speed: {avg_speed:.2f} MB/s"
            )
            
            # Check if this is a multipart file and process it after a short delay
            # This ensures that the file is fully written to disk
            from multipart_manager import MultipartManager  # Import here to avoid circular imports
            multipart_manager = MultipartManager(self.config, self)
            
            file_info = get_multipart_info(download_path, self.config.MULTIPART_PATTERNS)
            if file_info:
                logger.info(f"Downloaded file is part of a multipart archive: {progress.file_name}")
                # Schedule the check with a small delay to make sure file is fully saved
                await asyncio.sleep(1)
                await multipart_manager.check_and_process_multipart_files(client, progress.chat_id, download_path, file_info)
                
        except asyncio.CancelledError:
            logger.info(f"Download of {progress.file_name} was cancelled")
            # Delete the partial file
            try:
                if os.path.exists(download_path):
                    os.remove(download_path)
                    logger.info(f"Removed partial download file: {download_path}")
            except Exception as e:
                logger.error(f"Error removing partial file: {str(e)}")
            
            # Update status message
            await client.edit_message(
                progress.chat_id,
                progress.message_id,
                f"❌ Download cancelled: {progress.file_name}"
            )
            raise  # Re-raise to signal cancellation
            
        except Exception as e:
            logger.error(f"Error downloading {progress.file_name}: {str(e)}", exc_info=True)
            await client.edit_message(
                progress.chat_id,
                progress.message_id,
                f"❌ Error downloading {progress.file_name}: {str(e)}"
            )
            raise  # Re-raise to propagate the error

    async def download_large_file(self, client, document, destination, progress, progress_callback):
        """Custom implementation for downloading large files with better error handling"""
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
        
        try:
            # For Telethon 1.27.0, we'll use the get_file method with proper parameters
            logger.info(f"Starting download of large file: {os.path.basename(destination)}")
            
            # First approach: standard download_media with progress tracking
            await client.download_media(
                document,
                file=destination,
                progress_callback=lambda received, total: asyncio.create_task(
                    progress_callback(received)
                )
            )
            
        except Exception as e:
            logger.error(f"Error during download: {str(e)}", exc_info=True)
            raise
                
        return destination
