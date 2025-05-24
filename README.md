# Discord Character AI Voice Bot

## Description
This Discord bot engages in voice conversations with users. It joins a voice channel, listens to a user's speech, converts it to text using Speech-to-Text (STT), sends the text to a Character AI persona, receives a text response, converts that response to speech using Character AI's voice generation, and plays it back in the voice channel. The bot supports a continuous conversation mode.

## Features
- **Voice Conversations:** Enables spoken dialogue with a Character AI persona.
- **Configurable Character:** Users can specify the Character AI token, character ID, and voice ID.
- **Turn-Based Interaction:** The bot listens for a user's speech, responds, and then listens again.
- **Conversation Management:** Commands to start, stop, and manage the conversation flow.
- **Manual Recording:** Option for one-off voice recordings (when not in conversation mode).

## Setup Instructions

### Prerequisites
- **Python:** Python 3.8+ is recommended.
- **FFmpeg:** FFmpeg must be installed and accessible in your system's PATH. FFmpeg is used for audio processing by `discord.py`. You can download it from [ffmpeg.org](https://ffmpeg.org/download.html).

### Installation
1.  **Clone the repository** (or download the files).
2.  **Install Python dependencies:**
    Create a `requirements.txt` file (or use the one provided) with the following content:
    ```txt
    discord.py
    SpeechRecognition
    # PyCharacterAI is assumed to be a local module present in the same directory.
    # Pocketsphinx was installed as a dependency of SpeechRecognition for offline STT capabilities,
    # but the bot primarily uses online STT (Google Web Speech API).
    # curl-cffi was installed as a dependency of PyCharacterAI.
    ```
    Open your terminal or command prompt in the project directory and run:
    ```bash
    pip install -r requirements.txt
    ```
    If `PyCharacterAI` is not provided as a local module, you would typically install it via pip if it were available on PyPI (e.g., `pip install PyCharacterAI`). For this project, ensure the `pycharacterai` library/module is correctly placed if it's a local dependency.

3.  **Configuration:**
    Open the `discord_bot.py` file in a text editor. At the top of the file, you will find placeholder values for your tokens and IDs. **You MUST replace these with your actual credentials:**
    ```python
    CAI_TOKEN = "YOUR_CAI_TOKEN"  # Your Character AI client token
    CAI_CHARACTER_ID = "YOUR_CAI_CHARACTER_ID" # The ID of the Character AI you want to use
    CAI_VOICE_ID = "YOUR_CAI_VOICE_ID" # The voice ID for the character's speech
    BOT_TOKEN = "YOUR_DISCORD_BOT_TOKEN" # Your Discord bot token
    ```

## Running the Bot

There are two main ways to run the bot:

**1. Using the startup script (recommended for Linux/macOS):**

   Make the script executable (only needs to be done once):
   ```bash
   chmod +x run_bot.sh
   ```
   Then run the script:
   ```bash
   ./run_bot.sh
   ```
   Alternatively, you can run it directly with bash:
   ```bash
   bash run_bot.sh
   ```

**2. Directly with Python:**

   You can also run the bot directly using Python (ensure you are in the project's root directory and use `python3` as specified in the `run_bot.sh` script):
   ```bash
   python3 discord_bot.py
   ```

## Usage / Commands
-   **`!join`**: The bot will join the voice channel you are currently in and initiate "conversation mode." It will listen for your speech for 10 seconds, process it, get a response from Character AI, speak it back, and then listen to you again.
-   **`!stopconvo`**: This command stops the active "conversation mode." The bot will stop listening, clear any ongoing processes, and leave the voice channel.
-   **`!leave`**: Similar to `!stopconvo`, this command makes the bot leave the voice channel and ends any active conversation mode.
-   **`!record`**: If conversation mode is *not* active, you can use this command to make a manual 10-second recording of your voice. The bot will process this single recording (STT and Character AI response if configured, though playback might only be the text part depending on implementation details outside conversation mode).

---

*This bot relies on external services (SpeechRecognition for STT, Character AI for persona and TTS). Ensure you have stable internet access and that these services are operational.*
*Ensure FFmpeg is correctly installed and added to your system's PATH.*
