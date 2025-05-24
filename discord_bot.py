import discord
from discord.ext import commands
import asyncio
import discord.sinks # For advanced audio recording sinks
import speech_recognition as sr # For Speech-to-Text
from pycharacterai import PyCharacterAI # For Character AI interaction
from io import BytesIO # For handling byte streams (audio data)

# --- Configuration Placeholders ---
# These MUST be filled in for the bot to work.
CAI_TOKEN = "8041baf6512c863ffe65eea49a071e4f0287f149"  # Your Character AI client token
CAI_CHARACTER_ID = "vOPdHXLGkA_7tamhZGhijCC29nk8W1xphYbm81qfSH4" # The ID of the Character AI character you want to interact with
CAI_VOICE_ID = "453c0918-82d5-40ab-b42c-517a322ee5e5" # The specific voice ID for the Character AI character's speech
BOT_TOKEN = "YOUR_DISCORD_BOT_TOKEN" # Your Discord bot token

# --- Global Variables ---
cai_client = None # Global client for PyCharacterAI, initialized in on_ready()
conversation_mode_status = {} # Dictionary to manage conversation mode state per guild
                              # Key: guild_id (int), Value: boolean (True if active, False if inactive)

# --- Bot Setup ---
# Define intents required by the bot
intents = discord.Intents.default()
intents.voice_states = True # Required for voice channel operations (joining, speaking, listening)
intents.message_content = True # Required for reading message content for commands (e.g., "!join")

# Create bot instance with command prefix "!" and defined intents
bot = commands.Bot(command_prefix="!", intents=intents)


# --- Core Conversation Logic Functions ---

async def after_playback(error, guild_id: int, original_author_id: int, text_channel_id: int):
    """
    Async callback function executed after the bot finishes playing audio in a voice channel.
    This function is crucial for continuing the conversation loop.
    Args:
        error: Any error that occurred during playback (None if successful).
        guild_id: The ID of the guild where playback occurred.
        original_author_id: The ID of the user who initiated the current conversation turn.
        text_channel_id: The ID of the text channel used for bot responses.
    """
    if error:
        print(f"Error during playback for guild {guild_id}: {error}")
        # Optionally, send a message to the text channel about the playback error.
        # text_channel = bot.get_channel(text_channel_id)
        # if text_channel:
        #     await text_channel.send("An error occurred during audio playback.")

    # Retrieve Discord objects from IDs for further operations
    guild = bot.get_guild(guild_id)
    if not guild:
        print(f"after_playback: Guild {guild_id} not found.")
        return

    text_channel = guild.get_channel(text_channel_id)
    if not text_channel:
        print(f"after_playback: Text channel {text_channel_id} not found in guild {guild_id}.")
        return
        
    original_author = guild.get_member(original_author_id) # Get the member object for the user
    if not original_author:
        print(f"after_playback: Original author {original_author_id} not found in guild {guild_id}.")
        return

    # Check if conversation mode is still active for this guild
    if conversation_mode_status.get(guild.id):
        await text_channel.send(f"My turn is over, {original_author.mention}, now listening for your response for 10 seconds...")
        # Schedule the start_recording function to listen to the user again, continuing the loop.
        # asyncio.create_task is used because start_recording is an async function.
        asyncio.create_task(start_recording(guild, original_author, text_channel))
    # If conversation_mode_status is False or not set for the guild, the loop naturally stops.


async def finished_recording_callback(
    sink: discord.sinks.WaveSink, 
    guild: discord.Guild, 
    user_recorded: discord.Member, 
    text_channel_for_responses: discord.TextChannel
):
    """
    Async callback executed when the WaveSink finishes recording audio (i.e., vc.stop_listening() is called).
    This function processes the recorded audio: performs STT, interacts with Character AI,
    gets a voice response, and plays it back. This forms a single turn in the conversation.
    Args:
        sink: The WaveSink object containing the recorded audio data.
        guild: The guild where the recording took place.
        user_recorded: The user whose audio was intended to be recorded.
        text_channel_for_responses: The text channel for sending bot messages.
    """
    # The sink can record multiple users if they speak at once.
    # We filter to get audio specifically from the `user_recorded`.
    user_audio_data = None
    for user_id, audio in sink.audio_data.items():
        if user_id == user_recorded.id:
            user_audio_data = audio # This is a discord.sinks.core.AudioData object
            break
    
    if not user_audio_data:
        await text_channel_for_responses.send(f"Sorry {user_recorded.mention}, I couldn't record your audio this time. Make sure you're speaking.")
        # If in conversation mode, try to re-listen to keep the loop active.
        if conversation_mode_status.get(guild.id):
            await text_channel_for_responses.send(f"Trying to listen again for {user_recorded.mention} for 10 seconds...")
            asyncio.create_task(start_recording(guild, user_recorded, text_channel_for_responses))
        return

    # Save the user's audio data to a temporary .wav file for STT processing.
    filename = f"{user_recorded.id}_{guild.id}_recording.wav"
    with open(filename, "wb") as f:
        f.write(user_audio_data.file.read()) # user_audio_data.file is an io.BytesIO object
    
    await text_channel_for_responses.send(f"Finished recording for {user_recorded.mention}. Processing audio...")

    # 1. Perform Speech-to-Text (STT)
    recognizer = sr.Recognizer()
    with sr.AudioFile(filename) as source: # Use the saved .wav file as the audio source
        audio_data_for_stt = recognizer.record(source) # Load audio data from file
        try:
            # Use Google Web Speech API for STT. Requires internet.
            text = recognizer.recognize_google(audio_data_for_stt) 
            await text_channel_for_responses.send(f"You ({user_recorded.mention}) said: \"{text}\"")

            # 2. Interact with PyCharacterAI
            global cai_client # Access the globally initialized CAI client
            if not cai_client:
                await text_channel_for_responses.send(f"Sorry {user_recorded.mention}, PyCharacterAI client is not initialized.")
                return 

            try:
                # Create a new chat session with the Character AI for this interaction.
                # This ensures conversation history is managed per interaction if needed,
                # though here each turn is treated somewhat independently for simplicity.
                chat_response_tuple = await cai_client.chat.create_chat(CAI_CHARACTER_ID, greeting=False)
                current_chat_object = chat_response_tuple[0]
                current_chat_id = current_chat_object.chat_id
                if not current_chat_id:
                    await text_channel_for_responses.send("Failed to create CAI chat session.")
                    return

                # Send the transcribed text from the user to Character AI.
                answer = await cai_client.chat.send_message(CAI_CHARACTER_ID, current_chat_id, text)
                primary_candidate = answer.get_primary_candidate() # Get the main response from CAI
                if not primary_candidate:
                    await text_channel_for_responses.send("CAI did not return a valid response.")
                    return
                
                cai_text_response = primary_candidate.text
                await text_channel_for_responses.send(f"Character AI: {cai_text_response}") # Send AI's text reply

                # 3. Generate Speech from Character AI's response
                audio_bytes = await cai_client.utils.generate_speech(
                    chat_id=answer.chat_id,
                    turn_id=answer.turn_id,
                    candidate_id=primary_candidate.candidate_id,
                    voice_id=CAI_VOICE_ID # Use the configured voice ID for TTS
                )

                if audio_bytes:
                    # 4. Play Character AI's audio response in the voice channel
                    voice_client = discord.utils.get(bot.voice_clients, guild=guild)
                    if voice_client and voice_client.is_connected():
                        # Create a discord.AudioSource object from the audio bytes.
                        # FFmpeg must be installed and in PATH for FFmpegPCMAudio to work.
                        audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(
                            BytesIO(audio_bytes), pipe=True, executable="ffmpeg"
                        ))
                        if not voice_client.is_playing(): # Play only if not already playing something
                            # The `after` argument schedules `after_playback` to run once this audio finishes.
                            # This is key to the conversation loop.
                            # IDs are passed to `after_playback` to avoid issues with Discord objects in async callbacks.
                            voice_client.play(audio_source, after=lambda e: bot.loop.create_task(
                                after_playback(e, guild.id, user_recorded.id, text_channel_for_responses.id)
                            ))
                            await text_channel_for_responses.send("Playing Character AI's response...")
                        else:
                            await text_channel_for_responses.send("Already playing audio. CAI response will not be played now.")
                            # If in conversation mode and can't play, still trigger re-listening via after_playback.
                            if conversation_mode_status.get(guild.id):
                                 bot.loop.create_task(after_playback(None, guild.id, user_recorded.id, text_channel_for_responses.id))
                    else: 
                        await text_channel_for_responses.send("Bot is not connected to VC. Cannot play CAI audio.")
                        if conversation_mode_status.get(guild.id): # If bot got disconnected during convo
                            conversation_mode_status[guild.id] = False # Stop conversation mode
                            await text_channel_for_responses.send("Conversation mode stopped as bot is not in a voice channel.")
                else: 
                    await text_channel_for_responses.send("Failed to generate speech from CAI.")
                    # If speech generation fails but in convo mode, try to re-listen.
                    if conversation_mode_status.get(guild.id):
                        bot.loop.create_task(after_playback(None, guild.id, user_recorded.id, text_channel_for_responses.id))

            except PyCharacterAI.exceptions.PyCAIError as e: # Handle errors from PyCharacterAI library
                await text_channel_for_responses.send(f"Error with PyCharacterAI: {e}")
            except Exception as e: # Handle other unexpected errors during CAI interaction
                await text_channel_for_responses.send(f"Unexpected error during CAI interaction: {e}")

        except sr.UnknownValueError: # STT could not understand the audio
            await text_channel_for_responses.send(f"Sorry {user_recorded.mention}, I could not understand your audio.")
            if conversation_mode_status.get(guild.id): # If in convo mode, try re-listening
                await text_channel_for_responses.send(f"Trying to listen again for {user_recorded.mention} for 10 seconds...")
                asyncio.create_task(start_recording(guild, user_recorded, text_channel_for_responses))
        except sr.RequestError as e: # STT service (e.g., Google) had an issue
            await text_channel_for_responses.send(f"Could not request STT results; {e}")
            if conversation_mode_status.get(guild.id): # If in convo mode, try re-listening
                 bot.loop.create_task(after_playback(None, guild.id, user_recorded.id, text_channel_for_responses.id))


async def start_recording(
    guild: discord.Guild, 
    user_to_record: discord.Member, 
    text_channel_for_responses: discord.TextChannel
):
    """
    Initiates the audio recording process for a specific user in their voice channel.
    This is called at the beginning of each user's "turn" in the conversation.
    Args:
        guild: The guild (server) where the recording should happen.
        user_to_record: The specific member whose audio should be captured.
        text_channel_for_responses: The text channel for sending bot status messages.
    """
    voice_client = discord.utils.get(bot.voice_clients, guild=guild) # Get the bot's current voice client for this guild
    if not voice_client or not voice_client.is_connected():
        await text_channel_for_responses.send("Bot is not connected to a voice channel. Cannot start recording.")
        conversation_mode_status[guild.id] = False # Ensure conversation mode is off if bot is not in VC
        return

    # Verify the target user is in the same voice channel as the bot.
    if not user_to_record.voice or user_to_record.voice.channel != voice_client.channel:
        await text_channel_for_responses.send(f"{user_to_record.mention} is not in the bot's voice channel. Cannot record.")
        # This might pause the conversation loop if the user has left the channel.
        return

    # Create a new WaveSink for each recording session. This sink collects audio in WAV format.
    sink_instance = discord.sinks.WaveSink()

    try:
        # Start listening for audio.
        # `voice_client.listen()` takes the sink and an `after` callback.
        # The `after` callback (`finished_recording_callback`) is triggered when `voice_client.stop_listening()` is called.
        # We pass `guild`, `user_to_record`, and `text_channel_for_responses` as `*cb_args` (callback arguments)
        # so that `finished_recording_callback` receives the necessary context for its operations.
        voice_client.listen(sink_instance, 
                            after=lambda sink_obj, *cb_args: bot.loop.create_task(finished_recording_callback(sink_obj, *cb_args)), 
                            guild, user_to_record, text_channel_for_responses)
        
        await text_channel_for_responses.send(f"Listening to {user_to_record.mention} for 10 seconds...")
        await asyncio.sleep(10) # Record audio for a fixed duration of 10 seconds.
    except Exception as e:
        print(f"Error starting listener: {e}")
        await text_channel_for_responses.send(f"Error starting recording: {e}")
        return 
        
    # After the 10-second recording duration, stop listening.
    # This action will trigger the `after` callback specified in `voice_client.listen()`,
    # which in turn calls `finished_recording_callback` to process the audio.
    if voice_client.is_listening():
        voice_client.stop_listening() 
    else:
        # This case might occur if the bot was disconnected or `stop_listening` was called by another process.
        print("Was not listening when trying to stop. Callback might not be called as expected.")


# --- Bot Event Handlers ---

@bot.event
async def on_ready():
    """
    Event handler executed when the bot has successfully connected to Discord and is ready.
    This is typically used for initialization tasks, like setting up the PyCharacterAI client.
    """
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    print("PyCharacterAI and other services will be initialized now.")
    
    global cai_client
    try:
        # Initialize the PyCharacterAI client using the token from configuration.
        cai_client = await PyCharacterAI.get_client(token=CAI_TOKEN)
        if cai_client:
            print("PyCharacterAI client initialized successfully.")
            # Optional: Fetch account info to verify successful authentication with Character AI.
            # me = await cai_client.account.fetch_me()
            # print(f"Authenticated to Character AI as: @{me.username}")
        else:
            # This case (get_client returning None without an exception) might be unlikely
            # depending on PyCharacterAI's implementation.
            print("Failed to initialize PyCharacterAI client (get_client returned None).")
    except Exception as e: # Catch any errors during CAI client initialization
        print(f"Failed to initialize PyCharacterAI client: {e}")
        cai_client = None # Ensure cai_client is None if setup fails, preventing further CAI calls.

# --- Bot Commands ---

@bot.command(name='join', help='Makes the bot join your voice channel and starts conversation mode.')
async def join(ctx: commands.Context):
    """
    Command for the bot to join the voice channel of the user who issued the command.
    Upon joining, it automatically starts "conversation mode," where it will listen to the user.
    """
    if not ctx.author.voice: # Check if the command issuer is in a voice channel
        await ctx.send("You are not in a voice channel. Please join a channel first.")
        return

    voice_channel = ctx.author.voice.channel # Get the voice channel of the user
    
    # Check if bot is already in a voice channel in the same guild
    if ctx.voice_client: 
        if ctx.voice_client.channel == voice_channel: # Already in the target channel
            await ctx.send("Already in your voice channel.")
        else: # In a different channel, so move
            await ctx.voice_client.move_to(voice_channel)
            await ctx.send(f"Moved to {voice_channel.name}.")
    else: # Bot is not in any voice channel in this guild, so connect
        try:
            await voice_channel.connect() # Connect to the user's voice channel
            await ctx.send(f"Joined {voice_channel.name}.")
        except Exception as e:
            await ctx.send(f"Could not join voice channel: {e}")
            return

    # Start conversation mode for this guild.
    # The bot will begin by listening to the user who issued the !join command.
    conversation_mode_status[ctx.guild.id] = True 
    await ctx.send("Conversation mode started. I will listen for your first message for 10 seconds...")
    
    # Initiate the recording process for the user who called !join.
    # `ctx.guild` is the server, `ctx.author` is the user, `ctx.channel` is the text channel for messages.
    # `asyncio.create_task` schedules the `start_recording` coroutine to run.
    asyncio.create_task(start_recording(ctx.guild, ctx.author, ctx.channel))


@bot.command(name='leave', help='Makes the bot leave its current voice channel and stops conversation mode.')
async def leave(ctx: commands.Context):
    """
    Command for the bot to leave its current voice channel.
    This also deactivates conversation mode for the guild.
    """
    # Explicitly turn off conversation mode for this guild.
    conversation_mode_status[ctx.guild.id] = False 

    if ctx.voice_client: # Check if the bot is connected to a voice channel in this guild
        if ctx.voice_client.is_playing(): # If playing audio, stop it.
            ctx.voice_client.stop() 
        
        if ctx.voice_client.is_listening(): # If recording audio, stop it.
             ctx.voice_client.stop_listening()

        await ctx.voice_client.disconnect() # Disconnect from the voice channel.
        await ctx.send("Left voice channel and conversation mode stopped.")
    else:
        await ctx.send("I am not in a voice channel.")


@bot.command(name='stopconvo', help='Stops conversation mode and makes the bot leave the voice channel.')
async def stopconvo(ctx: commands.Context):
    """
    Command to explicitly stop the conversation mode.
    The bot will also leave the voice channel. This is functionally similar to `!leave`
    but provides a more semantically clear way to end the active conversation.
    """
    # Set conversation mode to false for the guild.
    conversation_mode_status[ctx.guild.id] = False
    await ctx.send("Conversation mode stopped.")

    if ctx.voice_client: # If connected to a voice channel
        if ctx.voice_client.is_playing(): # Stop any audio playback
            ctx.voice_client.stop()
        
        if ctx.voice_client.is_listening(): # Stop any audio recording
            ctx.voice_client.stop_listening()

        if ctx.voice_client.is_connected(): # Disconnect from the voice channel
            await ctx.voice_client.disconnect()
            await ctx.send("Disconnected from voice channel.")
    else:
        await ctx.send("Was not in a voice channel.")


@bot.command(name='record', help='Manually records 10s of audio if not in conversation mode.')
async def record(ctx: commands.Context):
    """
    Command to manually trigger a 10-second audio recording from the command issuer.
    This command only functions if "conversation mode" is NOT active for the guild.
    It's intended for one-off recordings rather than continuous conversation.
    """
    # Check if conversation mode is currently active for this guild.
    if conversation_mode_status.get(ctx.guild.id):
        await ctx.send("Conversation mode is active. Please use `!stopconvo` first if you want to make a manual recording.")
        return

    # Standard checks for bot and user voice state for any voice command.
    if not ctx.voice_client:
        await ctx.send("I am not in a voice channel. Use `!join` first to bring me in (this will start conversation mode).")
        return

    if not ctx.author.voice or ctx.author.voice.channel != ctx.voice_client.channel:
        await ctx.send("You need to be in the same voice channel as the bot to record.")
        return

    # Manual recording logic.
    # This uses the same `finished_recording_callback` as the conversation loop,
    # but it won't trigger a subsequent re-listening because `conversation_mode_status`
    # is False (or not set) for this guild during a manual record.
    await ctx.send(f"Manual recording for {ctx.author.mention} for 10 seconds...")
    
    sink_instance = discord.sinks.WaveSink() # Create a new sink for this recording session.
    try:
        # Pass guild, author, and channel to the callback via listen's *args for context.
        ctx.voice_client.listen(sink_instance, 
                                after=lambda sink, *args: bot.loop.create_task(finished_recording_callback(sink, *args)),
                                ctx.guild, ctx.author, ctx.channel)
        await asyncio.sleep(10) # Record for 10 seconds.
    except Exception as e:
        print(f"Error starting manual recording listener: {e}")
        await ctx.send(f"Error starting manual recording: {e}")
        return

    if ctx.voice_client.is_listening(): # Stop the recording after 10 seconds.
        ctx.voice_client.stop_listening()
    else:
        await ctx.send("Recording was already stopped or failed to start for manual record.")


# --- Run the Bot ---
if __name__ == "__main__":
    # This check ensures the bot runs only when the script is executed directly.
    # The BOT_TOKEN must be configured at the top of the file.
    if BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN" or not BOT_TOKEN:
        print("ERROR: Please fill in your BOT_TOKEN in the discord_bot.py file.")
    elif CAI_TOKEN == "YOUR_CAI_TOKEN" or not CAI_TOKEN:
        print("ERROR: Please fill in your CAI_TOKEN in the discord_bot.py file.")
    elif CAI_CHARACTER_ID == "YOUR_CAI_CHARACTER_ID" or not CAI_CHARACTER_ID:
        print("ERROR: Please fill in your CAI_CHARACTER_ID in the discord_bot.py file.")
    elif CAI_VOICE_ID == "YOUR_CAI_VOICE_ID" or not CAI_VOICE_ID:
        print("ERROR: Please fill in your CAI_VOICE_ID in the discord_bot.py file.")
    else:
        bot.run(BOT_TOKEN)
