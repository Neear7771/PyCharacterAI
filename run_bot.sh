#!/bin/bash
echo "Starting the Discord Character AI Bot..."

# It's good practice to ensure the bot runs from the script's directory
# in case it relies on relative paths for configs or assets in the future.
# SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# cd "$SCRIPT_DIR"

# Assuming discord_bot.py is in the same directory as run_bot.sh
python3 discord_bot.py

echo "Discord Character AI Bot has stopped."
