import os
import re
import time
import shutil
import asyncio
import logging

logger = logging.getLogger(__name__)

# Global state for multipart operations
pending_multipart_checks = {}  # Mapping of base_name to last check time

def get_multipart_info(file_path, multipart_patterns):
    """
    Analyzes a file path to determine if it's part of a multipart archive
    Returns None if not a multipart file, or a dict with info if it is
    """
    if not file_path or not os.path.exists(file_path):
        logger.warning(f"File path does not exist: {file_path}")
        return None
        
    filename = os.path.basename(file_path)
    logger.debug(f"Checking if file is multipart: {filename}")
    
    # Check against each pattern
    for pattern in multipart_patterns:
        match = pattern.match(filename)
        if match:
            base_name = match.group(1)
            
            # Determine part number
            if ".part" in filename.lower():
                # Extract number from patterns like .part1.rar
                part_match = re.search(r'\.part(\d+)', filename.lower())
                part_num = int(part_match.group(1)) if part_match else 1
            elif ".z" in filename.lower() and re.search(r'\.z\d+$', filename.lower()):
                # Extract number from patterns like .z01
                part_match = re.search(r'\.z(\d+)$', filename.lower())
                part_num = int(part_match.group(1)) if part_match else 1
            else:
                # Extract number from patterns like .001 or .zip.001
                part_match = re.search(r'\.(\d+)$', filename)
                part_num = int(part_match.group(1)) if part_match else 1
            
            # Determine file format
            if ".rar" in filename.lower():
                format_type = "rar"
            elif ".zip" in filename.lower():
                format_type = "zip"
            elif ".7z" in filename.lower():
                format_type = "7z"
            elif ".z" in filename.lower():
                format_type = "z"
            else:
                # Try to guess from the part number format
                if re.search(r'\.\d{3}$', filename):
                    format_type = "numbered"
                else:
                    format_type = "unknown"
            
            logger.info(f"Identified multipart file: {filename}, base_name: {base_name}, part_num: {part_num}, format: {format_type}")
            
            return {
                "base_name": base_name,
                "part_num": part_num,
                "format": format_type,
                "is_first_part": is_first_part(filename, format_type, part_num),
                "full_path": file_path,
                "filename": filename
            }
    
    return None

def is_first_part(filename, format_type, part_num):
    """
    Determine if this is likely the first part of a multipart archive
    """
    if format_type in ["rar", "zip"] and ".part" in filename.lower():
        return part_num == 1
    elif format_type == "z":
        return '.z01' in filename.lower()
    else:  # Numbered parts like .001
        return part_num == 1 or filename.endswith('.001')

class MultipartManager:
    """Manager for multipart file operations"""
    
    def __init__(self, config, download_manager):
        self.config = config
        self.download_manager = download_manager
        self.completed_joins = set()  # Track which joins have been completed
        
    async def process_multipart_files(self, client, chat_id, files):
        """
        Process a list of files to check for and join multipart archives
        """
        for file_path in files:
            file_info = get_multipart_info(file_path, self.config.MULTIPART_PATTERNS)
            if file_info:
                await self.check_and_process_multipart_files(client, chat_id, file_path, file_info)
                # Schedule a retry after a delay to catch all parts that might have finished downloading
                asyncio.create_task(self.retry_multipart_check(client, chat_id, file_info["base_name"]))

    async def retry_multipart_check(self, client, chat_id, base_name):
        """Schedule a retry check after a delay to ensure we join files after all downloads complete"""
        # Wait a bit to allow all downloads to complete
        await asyncio.sleep(5)
        logger.info(f"Performing retry check for multipart files with base_name: {base_name}")
        
        # Look for any file with this base_name to use for the check
        for filename in os.listdir(self.config.DOWNLOAD_DIR):
            file_path = os.path.join(self.config.DOWNLOAD_DIR, filename)
            if not os.path.isfile(file_path):
                continue
                
            part_info = get_multipart_info(file_path, self.config.MULTIPART_PATTERNS)
            if part_info and part_info["base_name"] == base_name:
                # Found a file with matching base_name, trigger check again
                await self.check_and_process_multipart_files(client, chat_id, file_path, part_info)
                break

    async def check_and_process_multipart_files(self, client, chat_id, new_file_path, file_info):
        """
        Check if we have all parts of a multipart archive and join them if we do
        """
        base_name = file_info["base_name"]
        format_type = file_info["format"]
        
        # Skip if this base_name was already successfully joined
        if base_name in self.completed_joins:
            logger.info(f"Skipping check for {base_name}, already joined successfully")
            return
            
        # Prevent checking the same base_name too frequently
        current_time = time.time()
        if base_name in pending_multipart_checks:
            last_check_time = pending_multipart_checks[base_name]
            if current_time - last_check_time < 3:  # Further reduced from 5s to 3s
                logger.debug(f"Skipping check for {base_name}, too soon since last check")
                return
        
        pending_multipart_checks[base_name] = current_time
        
        logger.info(f"Checking for multipart files for base_name: {base_name}")
        
        # Look for all parts in the download directory
        all_parts = []
        
        for filename in os.listdir(self.config.DOWNLOAD_DIR):
            file_path = os.path.join(self.config.DOWNLOAD_DIR, filename)
            if not os.path.isfile(file_path):
                continue
                
            part_info = get_multipart_info(file_path, self.config.MULTIPART_PATTERNS)
            if part_info and part_info["base_name"] == base_name:
                all_parts.append((part_info["part_num"], file_path))
                logger.info(f"Found part {part_info['part_num']} for {base_name}: {filename}")
        
        # Check for any active downloads that might be parts of this archive
        has_pending_parts = False
        active_downloads = []
        
        # Fixed: Get accurate picture of active downloads with correct attributes
        for file_id, progress in list(self.download_manager.downloads.items()):
            # Check if file exists before continuing
            download_path = os.path.join(self.config.DOWNLOAD_DIR, progress.file_name)
            if not os.path.exists(download_path):
                continue  # Skip if file doesn't exist on disk yet
            
            # Check if download is complete based on progress attributes
            # Check for complete flag directly if available, otherwise assume incomplete
            is_complete = getattr(progress, 'complete', False)
            
            if not is_complete:
                # This download is not complete
                active_downloads.append(progress.file_name)
                part_info = get_multipart_info(download_path, self.config.MULTIPART_PATTERNS)
                if part_info and part_info["base_name"] == base_name:
                    has_pending_parts = True
                    logger.info(f"Found active download for part of {base_name}: {progress.file_name}")
        
        if has_pending_parts:
            logger.info(f"Not joining {base_name} yet because there are pending downloads: {active_downloads}")
            return
        
        # If we have no pending downloads for this base_name, try to join the files
        if all_parts:
            # Sort parts by part number
            all_parts.sort(key=lambda x: x[0])
            logger.info(f"Found {len(all_parts)} parts for {base_name}, proceeding with join")
            success = await self.join_multipart_files(client, chat_id, base_name, all_parts, format_type)
            if success:
                # Mark this base_name as successfully joined
                self.completed_joins.add(base_name)
        else:
            logger.warning(f"No parts found for {base_name}")

    async def join_multipart_files(self, client, chat_id, base_name, parts, format_type):
        """Enhanced function to join multipart files based on format"""
        if len(parts) <= 1:
            logger.info(f"Only found {len(parts)} part(s) for {base_name}, not joining yet")
            return False
        
        # Log the parts we're about to join
        logger.info(f"Starting join of {len(parts)} parts for {base_name}:")
        for i, (part_num, part_path) in enumerate(parts):
            logger.info(f"  {i+1}. Part {part_num}: {os.path.basename(part_path)}")
        
        # Inform user
        try:
            status_msg = await client.send_message(
                chat_id,
                f"🔄 Joining multipart files: {base_name} ({len(parts)} parts)"
            )
        except Exception as e:
            logger.error(f"Error sending initial status message: {str(e)}")
            # Create a placeholder message object with an id that won't be used
            class PlaceholderMessage:
                id = -1
            status_msg = PlaceholderMessage()
        
        try:
            # Determine output file name based on format
            if format_type == "rar":
                output_path = os.path.join(self.config.DOWNLOAD_DIR, f"{base_name}.rar")
            elif format_type == "zip":
                output_path = os.path.join(self.config.DOWNLOAD_DIR, f"{base_name}.zip")
            elif format_type == "7z":
                output_path = os.path.join(self.config.DOWNLOAD_DIR, f"{base_name}.7z")
            else:
                # Default to using the base name with the appropriate extension
                if parts[0][1].lower().endswith(('.001', '.01', '.1')):
                    # For numbered parts, try to determine the extension from the base name
                    if '.7z.' in parts[0][1].lower():
                        output_path = os.path.join(self.config.DOWNLOAD_DIR, f"{base_name}.7z")
                    elif '.zip.' in parts[0][1].lower():
                        output_path = os.path.join(self.config.DOWNLOAD_DIR, f"{base_name}.zip")
                    elif '.rar.' in parts[0][1].lower():
                        output_path = os.path.join(self.config.DOWNLOAD_DIR, f"{base_name}.rar")
                    else:
                        # Default with no specific extension
                        output_path = os.path.join(self.config.DOWNLOAD_DIR, f"{base_name}")
                else:
                    # Default with no specific extension
                    output_path = os.path.join(self.config.DOWNLOAD_DIR, f"{base_name}")
            
            logger.info(f"Output path for joined file: {output_path}")
            
            # Report progress periodically
            progress_updater_task = None
            
            # Track join progress
            total_size = sum(os.path.getsize(part_path) for _, part_path in parts)
            bytes_written = 0
            start_time = time.time()
            last_progress_percent = -1  # Track last progress percentage to avoid redundant updates
            
            # Create progress updater task
            async def update_join_progress():
                nonlocal last_progress_percent
                while True:
                    # Only update if message has a valid ID and progress changed significantly
                    if status_msg.id > 0:
                        current_progress = bytes_written / total_size * 100 if total_size > 0 else 0
                        
                        # Only update if progress changed by at least 1%
                        if abs(current_progress - last_progress_percent) >= 1:
                            try:
                                await client.edit_message(
                                    chat_id,
                                    status_msg.id,
                                    f"🔄 Joining multipart files: {base_name}\n"
                                    f"Progress: {current_progress:.1f}%\n"
                                    f"Parts: {len(parts)}\n"
                                    f"Time elapsed: {int((time.time() - start_time) // 60)}m {int((time.time() - start_time) % 60)}s"
                                )
                                last_progress_percent = current_progress
                            except Exception as e:
                                if "MessageNotModifiedError" not in str(e):
                                    logger.warning(f"Error updating progress message: {str(e)}")
                    await asyncio.sleep(2)  # Update every 2 seconds
            
            # Start progress updater in background
            progress_updater_task = asyncio.create_task(update_join_progress())
            
            try:
                # Special handling for RAR files with .partX.rar format
                if format_type == "rar" and any(part_path.lower().endswith(".part1.rar") for _, part_path in parts):
                    first_part_path = next((part_path for _, part_path in parts if part_path.lower().endswith(".part1.rar")), None)
                    if first_part_path:
                        logger.info(f"Handling RAR multi-volume archive with {first_part_path}")
                        shutil.copy2(first_part_path, output_path)
                        bytes_written = total_size  # Consider it done
                        
                        await client.edit_message(
                            chat_id,
                            status_msg.id,
                            f"ℹ️ For RAR multipart files, only the first part has been copied. "
                            f"When extracting, your extraction software will automatically find the other parts."
                        )
                        await asyncio.sleep(3)  # Give user time to read the message
                    else:
                        logger.warning(f"Could not find part1.rar for {base_name}")
                        raise Exception("First part of RAR archive not found")
                # FIXED: Modified condition for 7z archives - we want to concatenate numbered .7z.NNN parts
                # Only use the "copy first part" approach for volumed 7z archives with specific patterns
                elif format_type == "7z" and any(part_path.lower().endswith(".part1.7z") for _, part_path in parts):
                    # This is a volume-style 7z archive like .part1.7z, .part2.7z
                    first_part_path = next((part_path for _, part_path in parts if part_path.lower().endswith(".part1.7z")), None)
                    if first_part_path:
                        logger.info(f"Handling 7z volume archive with {first_part_path}")
                        shutil.copy2(first_part_path, output_path)
                        bytes_written = total_size  # Consider it done
                        
                        await client.edit_message(
                            chat_id,
                            status_msg.id,
                            f"ℹ️ For 7z multipart files, only the first part has been copied. "
                            f"When extracting, your extraction software will automatically find the other parts."
                        )
                        await asyncio.sleep(3)
                    else:
                        logger.warning(f"Could not find part1.7z for {base_name}")
                        raise Exception("First part of 7z archive not found")
                else:
                    # For other formats, join the parts by binary concatenation
                    # This includes .7z.001, .7z.002, etc formats and all other formats
                    logger.info(f"Joining parts through binary concatenation")
                    with open(output_path, 'wb') as output_file:
                        for part_num, part_path in parts:
                            logger.info(f"Processing part {part_num}: {os.path.basename(part_path)}")
                            part_size = os.path.getsize(part_path)
                            
                            with open(part_path, 'rb') as part_file:
                                # Read and write in chunks to avoid memory issues with large files
                                chunk_size = 8 * 1024 * 1024  # 8MB chunks
                                bytes_read_from_part = 0
                                
                                while True:
                                    chunk = part_file.read(chunk_size)
                                    if not chunk:
                                        break
                                    output_file.write(chunk)
                                    bytes_written += len(chunk)
                                    bytes_read_from_part += len(chunk)
                                    await asyncio.sleep(0.01)  # Small yield to prevent blocking
                                
                                logger.info(f"Completed part {part_num}, read {bytes_read_from_part} bytes")
                    
                    # Verify the output file size matches the expected total size
                    actual_output_size = os.path.getsize(output_path)
                    if actual_output_size != total_size:
                        logger.warning(f"Output file size mismatch! Expected: {total_size}, Actual: {actual_output_size}")
                        
                        # Add this information to the user message
                        size_warning = f"\n⚠️ The resulting file size ({actual_output_size}) doesn't match the sum of parts ({total_size})."
                    else:
                        size_warning = ""
                        logger.info(f"Output file size verified: {actual_output_size} bytes")

            finally:
                # Stop progress updater
                if progress_updater_task:
                    progress_updater_task.cancel()
                    try:
                        await progress_updater_task
                    except asyncio.CancelledError:
                        pass
            
            # Calculate total join time
            total_time = time.time() - start_time
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            expected_size_mb = total_size / (1024 * 1024)
            
            # Inform user of success
            if status_msg.id > 0:
                try:
                    message = (
                        f"✅ Multipart file joined: {os.path.basename(output_path)}\n"
                        f"Total size: {file_size_mb:.2f} MB\n"
                        f"Expected size: {expected_size_mb:.2f} MB\n" 
                        f"Parts combined: {len(parts)}\n"
                        f"Total time: {int(total_time // 60)}m {int(total_time % 60)}s"
                    )
                    
                    # Add warning if sizes don't match
                    if 'size_warning' in locals() and size_warning:
                        message += size_warning
                        
                    await client.edit_message(
                        chat_id,
                        status_msg.id,
                        message
                    )
                except Exception as e:
                    logger.error(f"Error updating final status message: {str(e)}")
            
            return True  # Return success status
            
        except Exception as e:
            logger.error(f"Error joining multipart files {base_name}: {str(e)}", exc_info=True)
            if status_msg.id > 0:
                try:
                    await client.edit_message(
                        chat_id,
                        status_msg.id,
                        f"❌ Error joining multipart files {base_name}: {str(e)}"
                    )
                except Exception as msg_error:
                    logger.error(f"Error updating error status message: {str(msg_error)}")
            return False  # Return failure status