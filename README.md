# TDownloader - Telegram Download Bot

TDownloader is a Telegram bot that allows downloading large files directly from Telegram. Using a local implementation of the Telegram API, this bot can handle files of virtually any size without the usual Telegram limitations.

<p><img src="https://github.com/JOSEW383/tdownloader/blob/main/TDownlaoderDemo.gif" alt="Demo" /></p>

## Features

- **Unlimited size downloads**: Using the local Telegram API server, it can download files of any size.
- **Real-time progress tracking**: Shows progress, speed, and estimated download time.
- **Multipart file management**: Automatically detects and joins split files in various formats:
  - `.zip.001`, `.zip.002`, etc.
  - `.part1.rar`, `.part2.rar`, etc.
  - `.7z.001`, `.7z.002`, etc.
  - Files ending with `.001`, `.002`, etc.
- **File management**:
  - List downloaded files with sizes
  - Cancel ongoing downloads
  - Delete downloaded files

## Requirements

- Docker and Docker Compose
- Internet connection
- At least 1 GB of available RAM
- Disk space for the files you download

## Configuration

### Environment Variables

Configure these variables in the `docker-compose.yml` file:

- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token (obtained from @BotFather)
- `BOT_OWNER_ID`: Telegram user ID of the bot owner (only allowed user)
- `BOT_DOWNLOAD_DIR`: Directory where files will be saved (default: `/app/downloads`)
- `API_ID` and `API_HASH`: Telegram API credentials (obtained from https://my.telegram.org)

## Installation

1. Clone this repository:

   ```bash
   git clone https://github.com/yourusername/tdownloader.git
   cd tdownloader
   ```

2. Edit `docker-compose.yml` to configure your credentials

3. Build and start the containers:
   ```bash
   docker-compose up -d
   ```

## Usage

Once the bot is running, start a conversation with it on Telegram.

### Commands

- `/start`: Start the bot and show available commands
- `/files`: Show the list of downloaded files
- `/cancel`: Cancel an ongoing download (shows interactive buttons)
- `/delete`: Delete a downloaded file (shows interactive buttons)

### Downloading Files

Simply send any file to the bot via Telegram and it will start downloading it. The bot will display:

- Download progress as a percentage
- Downloaded size vs. total size
- Download speed
- Estimated time remaining

### Multipart Files

The bot automatically detects and handles multipart files in various formats:

- For RAR files (like `.part1.rar`, `.part2.rar`), the bot copies the first part and keeps the extension, as extraction tools automatically find other parts.
- For 7z files (like `.7z.001`, `.7z.002`), the bot copies the first part and keeps the extension.
- For other formats, the bot concatenates all parts in order to create a complete file.

## Project Structure

```
tdownloader/
├── src/                      # Application code
│   ├── main.py               # Main entry point
│   ├── config_manager.py     # Configuration management
│   ├── download_manager.py   # Download handling
│   ├── multipart_manager.py  # Multipart file handling
│   ├── bot_commands.py       # Bot command handlers
│   ├── requirements.txt      # Python dependencies
│   └── dockerfile            # Configuration to build the image
├── docker-compose.yml        # Docker Compose configuration
├── downloads/                # Directory where downloaded files are saved
└── README.md                 # This file
```

## Dependencies

- Python 3.9
- Telethon 1.27.0 (library for Telegram API)
- python-telegram-bot
- python-dotenv
- httpx

## Security

- The bot only responds to the owner specified in `BOT_OWNER_ID`
- API credentials are stored as environment variables
- Tokens are limited to the Docker container

## Troubleshooting

### Bot Not Responding

1. Verify that the containers are running:

   ```bash
   docker-compose ps
   ```

2. Check the bot logs:

   ```bash
   docker-compose logs tdownloader
   ```

3. Make sure the API credentials are correct

### Connection Errors

If you have connection issues, check:

1. API server logs:

   ```bash
   docker-compose logs telegram_api
   ```

2. Connectivity between containers (they must be on the same network)

### Multipart File Issues

If multipart files aren't being joined correctly:

1. Check that all parts are fully downloaded
2. Ensure all parts follow the same naming convention
3. Check for sufficient disk space
4. Review the logs for any join errors:
   ```bash
   docker-compose logs tdownloader | grep "multipart"
   ```

## License

This project is free software and has no usage restrictions.

## Contributing

Contributions welcome! To contribute:

1. Fork the repository
2. Create a branch for your feature
3. Submit a pull request

---

Developed to facilitate downloading large files from Telegram.
