import os
import re
import logging
from dataclasses import dataclass

@dataclass
class Config:
    OWNER_ID: int
    DOWNLOAD_DIR: str
    API_ID: int
    API_HASH: str
    BOT_TOKEN: str
    SERVER_URL: str
    CHUNK_SIZE: int
    MULTIPART_PATTERNS: list

def setup_logging():
    """Configure and return logger"""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    return logger

def get_config():
    """Load configuration from environment variables"""
    # Configuration
    config = Config(
        OWNER_ID = int(os.getenv("BOT_OWNER_ID")),
        DOWNLOAD_DIR = os.getenv("BOT_DOWNLOAD_DIR", "./downloads"),
        API_ID = int(os.getenv("API_ID")),
        API_HASH = os.getenv("API_HASH"),
        BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN"),
        SERVER_URL = os.getenv("TELEGRAM_BOT_API_URL", "http://telegram_api:8081"),
        CHUNK_SIZE = 8 * 1024 * 1024,  # 8MB chunks for downloads
        
        # Updated multipart file patterns
        MULTIPART_PATTERNS = [
            re.compile(r"^(.+)\.(?:zip|rar|7z|tar|gz|bz2)\.\d+$"),  # file.zip.001
            re.compile(r"^(.+)\.part\d+\.(?:rar|zip)$"),            # file.part1.rar
            re.compile(r"^(.+)\.z\d+$"),                            # file.z01
            re.compile(r"^(.+)\.\d{3}$")                            # file.001
        ]
    )
    return config
