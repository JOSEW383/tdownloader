import os
import logging
from telethon import events, Button

logger = logging.getLogger(__name__)

def setup_bot_commands(client, download_manager, multipart_manager):
    """Register all command handlers for the bot"""

    @client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        if event.sender_id != download_manager.config.OWNER_ID:
            return
        await event.respond(
            "Hello! Send me files to download. Using local API, I can download files of any size.\n\n"
            "Available commands:\n"
            "/files - Show downloaded files\n"
            "/cancel - Cancel active download\n"
            "/delete - Delete downloaded file"
        )
    
    @client.on(events.NewMessage(pattern='/cancel'))
    async def cancel_handler(event):
        if event.sender_id != download_manager.config.OWNER_ID:
            return
        
        # Check active downloads
        active_downloads = []
        for file_id, progress in list(download_manager.downloads.items()):
            if not progress.complete:
                active_downloads.append((file_id, progress.file_name))
        
        if not active_downloads:
            await event.respond("💤 No active downloads at the moment.")
            return
            
        # Create buttons for each active download
        buttons = []
        for file_id, file_name in active_downloads:
            buttons.append([Button.inline(
                f"❌ {file_name[:40]}{'...' if len(file_name) > 40 else ''}", 
                data=f"cancel_{file_id}"
            )])
        
        # Add a cancel button
        buttons.append([Button.inline("🔙 Cancel", data="cancel_none")])
        
        await event.respond(
            "📝 Select the download you want to cancel:",
            buttons=buttons
        )
    
    @client.on(events.NewMessage(pattern='/files'))
    async def list_files_handler(event):
        if event.sender_id != download_manager.config.OWNER_ID:
            return
        
        files = []
        try:
            for item in os.listdir(download_manager.config.DOWNLOAD_DIR):
                item_path = os.path.join(download_manager.config.DOWNLOAD_DIR, item)
                if os.path.isfile(item_path):
                    size_mb = os.path.getsize(item_path) / (1024 * 1024)
                    files.append(f"• {item} ({size_mb:.2f} MB)")
        except Exception as e:
            await event.respond(f"❌ Error listing files: {str(e)}")
            return
            
        if files:
            # Split into multiple messages if needed (Telegram limit is 4096 chars)
            files_text = "📁 Downloaded files:\n" + "\n".join(files)
            
            if len(files_text) <= 4000:
                await event.respond(files_text)
            else:
                # Split into chunks
                chunks = []
                current_chunk = "📁 Downloaded files:\n"
                
                for file_line in files:
                    if len(current_chunk) + len(file_line) + 1 > 4000:
                        chunks.append(current_chunk)
                        current_chunk = "📁 Downloaded files (continued):\n"
                    
                    current_chunk += file_line + "\n"
                
                if current_chunk:
                    chunks.append(current_chunk)
                
                for chunk in chunks:
                    await event.respond(chunk)
        else:
            await event.respond("📂 No downloaded files.")

    @client.on(events.NewMessage(pattern='/delete'))
    async def delete_file_handler(event):
        if event.sender_id != download_manager.config.OWNER_ID:
            return
        
        try:
            # Get list of files in download directory
            files = []
            for item in os.listdir(download_manager.config.DOWNLOAD_DIR):
                item_path = os.path.join(download_manager.config.DOWNLOAD_DIR, item)
                if os.path.isfile(item_path):
                    size_mb = os.path.getsize(item_path) / (1024 * 1024)
                    files.append((item, f"{item} ({size_mb:.2f} MB)"))
            
            if not files:
                await event.respond("📂 No downloaded files.")
                return
                
            # Create buttons for each file
            buttons = []
            # Group files into rows of 1 button each
            for filename, display_name in files:
                buttons.append([Button.inline(
                    f"🗑️ {display_name[:40]}{'...' if len(display_name) > 40 else ''}", 
                    data=f"delete_{filename}"
                )])
            
            # Add a cancel button
            buttons.append([Button.inline("🔙 Cancel", data="delete_none")])
            
            await event.respond(
                "🗑️ Select the file you want to delete:",
                buttons=buttons
            )
        except Exception as e:
            await event.respond(f"❌ Error listing files: {str(e)}")

    @client.on(events.CallbackQuery(pattern=r'^cancel_'))
    async def on_cancel_callback(event):
        if event.sender_id != download_manager.config.OWNER_ID:
            await event.answer("You don't have permission to use this function", alert=True)
            return
            
        # Extract file_id from button data
        file_id = event.data.decode('utf-8').split('_', 1)[1]
        
        if file_id == 'none':
            await event.delete()
            await event.respond("Operation cancelled.")
            return
        
        if file_id in download_manager.downloads and file_id in download_manager.active_tasks:
            progress = download_manager.downloads[file_id]
            
            # Set cancel flag
            download_manager.cancel_flags[file_id] = True
            
            # Cancel the task
            if not download_manager.active_tasks[file_id].done():
                download_manager.active_tasks[file_id].cancel()
            
            # Update message
            await client.edit_message(
                progress.chat_id,
                progress.message_id,
                f"❌ Download cancelled: {progress.file_name}"
            )
            
            # Clean up
            if file_id in download_manager.downloads:
                del download_manager.downloads[file_id]
            if file_id in download_manager.active_tasks:
                del download_manager.active_tasks[file_id]
            if file_id in download_manager.cancel_flags:
                del download_manager.cancel_flags[file_id]
                
            # Delete the buttons message and send confirmation
            await event.delete()
            await event.respond(f"✅ Download cancelled: {progress.file_name}")
        else:
            await event.answer("This download is no longer active", alert=True)

    @client.on(events.CallbackQuery(pattern=r'^delete_'))
    async def on_delete_callback(event):
        if event.sender_id != download_manager.config.OWNER_ID:
            await event.answer("You don't have permission to use this function", alert=True)
            return
            
        # Extract filename from button data
        filename = event.data.decode('utf-8').split('_', 1)[1]
        
        if filename == 'none':
            await event.delete()
            await event.respond("Operation cancelled.")
            return
        
        file_path = os.path.join(download_manager.config.DOWNLOAD_DIR, filename)
        
        try:
            if os.path.exists(file_path):
                # Get file size before deleting
                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                
                # Delete the file
                os.remove(file_path)
                
                # Delete the buttons message and send confirmation
                await event.delete()
                await event.respond(f"🗑️ File deleted: {filename} ({size_mb:.2f} MB)")
            else:
                await event.answer(f"The file no longer exists", alert=True)
        except Exception as e:
            await event.answer(f"Error: {str(e)}", alert=True)

    @client.on(events.NewMessage)
    async def message_handler(event):
        if event.sender_id != download_manager.config.OWNER_ID:
            return
        
        # Check if the message has a document
        if event.document:
            await download_manager.process_document(client, event)
