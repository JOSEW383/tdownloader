import os
import logging
import shutil
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)

async def binary_concat_files(parts, output_path, chunk_size=8*1024*1024):
    """
    Concatenate multiple file parts into a single file.
    
    Args:
        parts: List of (part_num, file_path) tuples
        output_path: Path for the output file
        chunk_size: Size of chunks to read/write
        
    Returns:
        Tuple of (success, bytes_written)
    """
    try:
        # Sort parts by part number to ensure correct order
        parts.sort(key=lambda x: x[0])
        
        # Get total expected size
        total_size = sum(os.path.getsize(part_path) for _, part_path in parts)
        logger.info(f"Starting binary concatenation, expected size: {total_size} bytes")
        
        bytes_written = 0
        with open(output_path, 'wb') as output_file:
            for part_num, part_path in parts:
                logger.info(f"Processing part {part_num}: {os.path.basename(part_path)}")
                
                try:
                    part_size = os.path.getsize(part_path)
                    
                    with open(part_path, 'rb') as part_file:
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
                except FileNotFoundError:
                    logger.error(f"File not found: {part_path}")
                    return False, bytes_written
                except Exception as e:
                    logger.error(f"Error processing part {part_num}: {str(e)}")
                    return False, bytes_written
        
        # Verify the output file size
        actual_size = os.path.getsize(output_path)
        if actual_size != total_size:
            logger.warning(f"Output size mismatch! Expected: {total_size}, got: {actual_size}")
            return False, bytes_written
        
        logger.info(f"Successfully concatenated {len(parts)} parts, total size: {bytes_written} bytes")
        return True, bytes_written
    
    except Exception as e:
        logger.error(f"Error in binary_concat_files: {str(e)}", exc_info=True)
        return False, 0

def is_self_extracting_archive(file_path):
    """Determine if a file is likely a self-extracting archive format"""
    if not os.path.exists(file_path):
        return False
    
    # Check file extension
    ext = Path(file_path).suffix.lower()
    if ext in ['.exe', '.sfx']:
        return True
    
    # Read file header to check for signatures
    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)
            # Check for executable header (MZ for Windows EXE)
            if header.startswith(b'MZ'):
                return True
    except Exception:
        pass
        
    return False

def get_multipart_type(parts):
    """
    Determine the type of multipart archive based on file patterns
    
    Returns: One of ["standard", "volumed", "split"]
    """
    if not parts:
        return "unknown"
    
    # Sample a few filenames
    filenames = [os.path.basename(p[1]).lower() for p in parts[:min(3, len(parts))]]
    
    # Check for volumed patterns (.part1.rar, .part2.rar)
    if any('.part' in name for name in filenames):
        return "volumed"
    
    # Check for split patterns (.7z.001, .7z.002, .r01, .r02)
    if any(name.endswith(('.001', '.002', '.r01', '.r02')) for name in filenames):
        return "split"
    
    # Default to standard
    return "standard"
