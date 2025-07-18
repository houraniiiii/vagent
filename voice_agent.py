import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from livekit import api
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import openai, silero, deepgram, elevenlabs, google, groq
from livekit.protocol.egress import (
    RoomCompositeEgressRequest,
    EncodedFileOutput,
    S3Upload,
)
import json

load_dotenv()
# Define format and date format
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Create formatter
formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler("voice-agent.log")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


SYSTEM_PROMPT = """
You are Rachel, a charismatic Irish professional human real estate agent working at Continental Real Estate in the UAE. You receive inbound calls from potential clients inquiring about various real estate services.

YOUR PERSONALITY & SPEAKING STYLE:

- Warm, enthusiastic, and genuinely helpful
- Use natural conversational expressions like: "hmm," "cool," "awesome," "let me check that for you," "thank youuu," "hold on a sec," "absolutely," "for sure," "oh that's great," "I see," "gotcha"
- Speak confidently, like a real human with natural pauses and casual interjections
- Show genuine interest in helping clients find solutions
- Use zero to two expression per output as appropriate
- Received input is from STT with possible word errors

SERVICES YOU OFFER:
- Property buying and selling (residential & commercial)
- Property rental (short-term & long-term)
- Golden Visa support and guidance
- Investment consultation
- Property management
- Market analysis and insights

CONVERSATION APPROACH:

- Start answering instantly as fast as possible.
- Listen actively and ask clarifying questions
- Use expressions like "Let me check that for you," "Hold on a sec," "Hmm, that's interesting"
- Always offer to schedule follow-ups or meetings

KEY GUIDELINES:
- Keep responses human-like, professiona, conversational, concise, and natural
- Never output words like "pause", your output will be used for streaming TTS so say expressive phrases instead
- Be patient with questions and explain things clearly
- When asked about properties, stick to the list provided
- provide prices written in words NOT NUMBERS, eg one million and four hundered thousands Derhams
"""


buy_and_rent_properties_data = json.load(
    open("worksheet_data.json", "r", encoding="utf-8")
)
# Adding buy and rent properties to the system prompt
SYSTEM_PROMPT += f"""

- following is BUY AND RENT PROPERTIES data in json format

{buy_and_rent_properties_data}

"""

WELCOME_MESSAGE = """
Welcome to Continental Real Estate. Rachel here. How can I help?
"""

stt, tts, llm = None, None, None

GROQ_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
GROQ_TEMPERATURE = 0.4
OPENAI_MODEL = "gpt-4o"


## STT Models ##
DEEPGRAM_MODEL = "nova-2"
DEEPGRAM_LANGUAGE = "en-US"


GROQ_STT_MODEL = "whisper-large-v3-turbo"
GROQ_STT_LANGUAGE = "en"
GROQ_STT_BASE_URL = "https://api.groq.com/openai/v1"


## TTS Models ##
ELEVENLABS_MODEL = "eleven_flash_v2_5"
ELEVENLABS_VOICE_ID = "h8eW5xfRUGVJrZhAFxqK"
ELEVENLABS_VOICE_NAME = "Isla"
ELEVENLABS_VOICE_CATEGORY = "female"
ELEVENLABS_LANGUAGE = "en-US"

GOOGLE_TTS_LANGUAGE = "en-US"
GOOGLE_TTS_GENDER = "female"
GOOGLE_TTS_CREDENTIALS_FILE = os.getenv("GOOGLE_STT_CREDENTIALS_FILE")
GOOGLE_TTS_SPEAKING_RATE = 1.5

GROQ_TTS_MODEL = "playai-tts-arabic"
GROQ_TTS_VOICE = "Khalid-PlayAI"
GROQ_TTS_BASE_URL = "https://api.groq.com/openai/v1"


OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_TTS_VOICE = "shimmer"
OPENAI_TTS_INSTRUCTIONS = (
    "You are a helpful assistant. When the user speaks, you listen and respond."
)

#LLM_CHOICE = "openai"
# LLM_CHOICE = "google"
LLM_CHOICE = "groq"
# LLM_CHOICE = "grok"  # Implementation issue: makes it stop in middle of welcome message

# STT_CHOICE = "openai"
STT_CHOICE = "groq"
# STT_CHOICE = "google"
#STT_CHOICE = "deepgram"

# TTS_CHOICE = "openai"
# TTS_CHOICE = "google"
# TTS_CHOICE = "groq"
TTS_CHOICE = "elevenlabs"


if LLM_CHOICE == "groq":
    llm = groq.LLM(
        model=GROQ_MODEL,
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=GROQ_TEMPERATURE,
    )
elif LLM_CHOICE == "openai":
    llm = openai.LLM(model=OPENAI_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
elif LLM_CHOICE == "grok":
     llm = openai.LLM(
         model=GROK_MODEL,
         base_url="https://api.x.ai/v1",
         api_key=os.getenv("XAI_API_KEY"),
     )

if STT_CHOICE == "deepgram":
    stt = deepgram.STT(
        model=DEEPGRAM_MODEL,
        #        language=DEEPGRAM_LANGUAGE,
        api_key=os.getenv("DEEPGRAM_API_KEY"),
    )
# elif STT_CHOICE == "openai":
#     stt = openai.STT(
#         model=OPENAI_STT_MODEL,
#         language=OPENAI_STT_LANGUAGE,
#         prompt=OPENAI_STT_PROMPT,
#         api_key=os.getenv("OPENAI_API_KEY"),
#     )
elif STT_CHOICE == "groq":
    stt = groq.STT(
        model=GROQ_STT_MODEL,
        language=GROQ_STT_LANGUAGE,
        api_key=os.getenv("GROQ_API_KEY"),
        base_url=GROQ_STT_BASE_URL,
    )
# elif STT_CHOICE == "google":
#     stt = google.STT(
#         credentials_file=os.getenv("GOOGLE_STT_CREDENTIALS_FILE"),
#         languages=GOOGLE_STT_LANGUAGE,
#     )

if TTS_CHOICE == "elevenlabs":

    tts = elevenlabs.TTS(
        voice_id=ELEVENLABS_VOICE_ID,
        model=ELEVENLABS_MODEL,
        streaming_latency=0,
        chunk_length_schedule=[50, 80, 140, 200, 300],
        # language=elevenlabs_language,
        api_key=os.getenv("ELEVENLABS_API_KEY"),
    )
elif TTS_CHOICE == "google":
    tts = google.TTS(
        language=GOOGLE_TTS_LANGUAGE,
        gender=GOOGLE_TTS_GENDER,
        credentials_file=GOOGLE_TTS_CREDENTIALS_FILE,
        speaking_rate=GOOGLE_TTS_SPEAKING_RATE,
    )
elif TTS_CHOICE == "groq":
    tts = groq.TTS(
        base_url=GROQ_TTS_BASE_URL,
        model=GROQ_TTS_MODEL,
        voice=GROQ_TTS_VOICE,
        api_key=os.getenv("GROQ_API_KEY"),
    )
elif TTS_CHOICE == "openai":
    tts = openai.TTS(
        model=OPENAI_TTS_MODEL,
        voice=OPENAI_TTS_VOICE,
        instructions=OPENAI_TTS_INSTRUCTIONS,
        api_key=os.getenv("OPENAI_API_KEY"),
        speed=1.2,
    )


class VoiceAgent(Agent):
    """Voice agent that listens to the user and responds with text."""

    def __init__(self) -> None:

        super().__init__(
            instructions=SYSTEM_PROMPT,
            stt=stt,
            llm=llm,
            tts=tts,
            vad=silero.VAD.load(
                min_speech_duration=0.10,  # ~20 ms before starting a speech chunk
                min_silence_duration=0.40,  # 300 ms of silence to mark end of speech
                prefix_padding_duration=0.40,  # 200 ms of padding at the front of each chunk
                #  sample_rate=8000,               # 8 kHz to reduce per-frame CPU work
                activation_threshold=0.5,  # default sensitivity
            ),
        )

    async def on_enter(self):
        self.session.generate_reply(
            instructions=f"Say the message {WELCOME_MESSAGE}", allow_interruptions=False
        )


async def entrypoint(ctx: JobContext):
    """Entrypoint for the voice agent."""

    await ctx.connect()

    session = AgentSession()

    await session.start(agent=VoiceAgent(), room=ctx.room)
    print("Session started", ctx.room.name)

    egress_req = RoomCompositeEgressRequest(
        room_name=ctx.room.name,
        audio_only=True,
        file_outputs=[
            EncodedFileOutput(
                filepath=f"continental/{ctx.room.name}-output.mp3",  # TODO: change to <from>-<to>-recording.mp3
                disable_manifest=False,
                s3=S3Upload(
                    bucket=os.getenv("S3_BUCKET"),
                    region=os.getenv("AWS_REGION"),
                    access_key=os.getenv("AWS_ACCESS_KEY_ID"),
                    secret=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    force_path_style=True,
                ),
            ),
        ],
    )

    lkapi = api.LiveKitAPI()
    # await lkapi.egress.start_room_composite_egress(egress_req)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
