import logging
import asyncio

logger = logging.getLogger(__name__)

async def safe_edit_message(client, chat_id, message_id, text, **kwargs):
    """
    Safely edit a message, handling MessageNotModifiedError
    """
    if message_id <= 0:
        return False
    
    # Ensure text is not None
    if text is None:
        text = "Error: Empty message"
        
    try:
        await client.edit_message(chat_id, message_id, text, **kwargs)
        return True
    except Exception as e:
        # Don't log MessageNotModifiedError as it's expected sometimes
        if "MessageNotModifiedError" not in str(e):
            logger.warning(f"Error editing message {message_id}: {str(e)}")
        return False

async def safe_send_message(client, chat_id, text, **kwargs):
    """
    Safely send a message, handling errors
    """
    try:
        message = await client.send_message(chat_id, text, **kwargs)
        return message
    except Exception as e:
        logger.error(f"Error sending message to chat {chat_id}: {str(e)}")
        return None

class ProgressUpdater:
    """Class for safely updating progress messages with debouncing"""
    
    def __init__(self, client, chat_id, message_id, min_interval=1.0, min_change=1.0):
        self.client = client
        self.chat_id = chat_id
        self.message_id = message_id
        self.min_interval = min_interval  # Minimum time between updates
        self.min_change = min_change  # Minimum percentage change to update
        self.last_update_time = 0
        self.last_percentage = -1
        self.task = None
        self.running = False
        self.update_queued = False
        self.current_text = ""
        
    async def start(self, initial_text=""):
        """Start the progress updater task"""
        self.running = True
        self.current_text = initial_text
        self.task = asyncio.create_task(self._update_task())
        
    async def update(self, text, percentage=None):
        """Queue an update to the progress message"""
        self.current_text = text
        if percentage is not None:
            self.last_percentage = percentage
        self.update_queued = True
        
    async def stop(self):
        """Stop the progress updater task"""
        self.running = False
        if self.task:
            try:
                # Do final update if needed
                if self.update_queued and self.message_id > 0:
                    await safe_edit_message(self.client, self.chat_id, self.message_id, self.current_text)
                # Cancel the task
                self.task.cancel()
                await self.task
            except asyncio.CancelledError:
                pass
            
    async def _update_task(self):
        """Task that handles debounced updates"""
        while self.running:
            try:
                if self.update_queued and self.message_id > 0:
                    now = asyncio.get_event_loop().time()
                    if (now - self.last_update_time >= self.min_interval):
                        await safe_edit_message(self.client, self.chat_id, self.message_id, self.current_text)
                        self.last_update_time = now
                        self.update_queued = False
            except Exception as e:
                logger.error(f"Error in progress updater: {str(e)}")
            await asyncio.sleep(0.5)
