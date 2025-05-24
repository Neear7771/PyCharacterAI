#!/bin/bash

echo "Installing dependencies..."
pip install -r requirements.txt --user

echo "Starting bot..."
python discord_bot.py
