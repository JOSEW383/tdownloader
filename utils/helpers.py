import os
import logging
import asyncio

logger = logging.getLogger(__name__)

async def check_file_locked(filepath, timeout=0.5):
    """
    Check if a file is locked (being written to) by trying to open it
    in exclusive mode. Returns True if file is locked, False otherwise.
    """
    try:
        # Try to open the file in exclusive mode with a timeout
        check_task = asyncio.create_task(_try_open_exclusive(filepath))
        result = await asyncio.wait_for(check_task, timeout=timeout)
        return not result
    except asyncio.TimeoutError:
        logger.debug(f"File appears to be locked (timeout): {filepath}")
        return True
    except Exception as e:
        logger.debug(f"Error checking if file is locked: {filepath}, {str(e)}")
        return True

async def _try_open_exclusive(filepath):
    """Try to open a file in exclusive mode"""
    try:
        with open(filepath, 'rb+') as f:
            # Just opening it is enough to check
            return True
    except (IOError, PermissionError):
        # File is locked or doesn't exist
        return False
    
def is_file_complete(filepath, expected_size=None):
    """
    Check if a file is likely complete by verifying:
    1. It exists
    2. It's not being written to (optional)
    3. It matches expected size if provided
    """
    if not os.path.exists(filepath):
        return False
    
    if expected_size is not None:
        actual_size = os.path.getsize(filepath)
        if actual_size != expected_size:
            return False
    
    # File exists and matches size if expected size was provided
    return True
