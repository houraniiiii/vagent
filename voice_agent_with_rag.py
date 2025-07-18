import logging
import os
import random
from dotenv import load_dotenv
from livekit import api
from livekit.agents import (
    JobContext,
    WorkerOptions,
    cli,
    function_tool,
    RunContext,
)
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import openai, silero, deepgram, elevenlabs, google, groq
from livekit.protocol.egress import (
    RoomCompositeEgressRequest,
    EncodedFileOutput,
    S3Upload,
)
from pinecone_query import PineconeHelper

load_dotenv()

logger = logging.getLogger("voice-agent")
logger.setLevel(logging.INFO)

SYSTEM_PROMPT = """You are a professional and friendly voice assistant for Continental Real Estate, a real estate services company in the UAE.

Your job is to assist callers by providing information about:
- Property Management Services
- Real Estate Brokerage Services
- Properties available for rent or sale

Keep all replies short, conversational, and suitable for phone calls — no more than 2 sentences. Speak clearly, warmly, and never sound robotic. Do not guess or invent information. If you're unsure or something is out of scope, let the caller know that **an agent will call them back** to assist.

---

### BEHAVIOR GUIDELINES

1. **For property inquiries**, always collect preferences first:
   - Ask for **location** → then **property type** → then **budget** (in this order).
   - Ask one question at a time and **acknowledge the answer**.
   - If caller gives all the info at once, skip questions.
   - Do **not repeat questions** already answered.

2. Once preferences are known:
   - Check if any listings from the provided list match.
   - If yes: share a **short description** of the closest match and ask if they’d like a callback.
   - If no close match: say an agent will call them back with more suitable options.

3. If the caller asks about company services:
   - Give a short explanation (1–2 sentences max) using info from the services section.

4. If asked to book a viewing or meeting:
   - Say: “Sure, I’ll arrange that. One of our team members will call you soon.”

5. If the caller asks about legal, pricing, negotiation, or detailed documents:
   - Say: “That’s handled by our team. They’ll give you a call shortly to assist.”

6. **Never engage in small talk, personal questions, or jokes**.

---

### COMPANY SERVICES

**Property Management Services**
Continental Real Estate manages residential, commercial, retail, hospitality, industrial, and healthcare properties.
Main services include:
- Tenant Management
- Financial Management (rent, VAT, reporting)
- Maintenance & Repairs
- Legal Compliance
- Asset Enhancement
- Owner/Tenant Portal Access
- 24/7 Emergency Response

**Real Estate Brokerage**
- Leasing vacant properties
- Selling high-return investments
- Acquisition & Disposition support
- Property marketing
- Snagging (defect inspection post-construction)

---"""

WELCOME_MESSAGE = "Welcome to Continental Real Estate. How can I help you today?"
stt, tts, llm = None, None, None


OPENAI_MODEL = "gpt-4o"
OPENAI_TEMPERATURE = 0.8

GEMINI_MODEL = "gemini-2.0-flash-exp"
GEMINI_TEMPERATURE = 0.8

GROQ_MODEL = "llama3-8b-8192"
GROQ_TEMPERATURE = 0.8

GROK_MODEL = "grok-2-public"
GROK_TEMPERATURE = 0.8


DEEPGRAM_MODEL = "nova-2-general"
DEEPGRAM_LANGUAGE = "en-US"

# stt_choice = "openai"
OPENAI_STT_MODEL = "gpt-4o-transcribe"  # other-models: "whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"
OPENAI_STT_LANGUAGE = "en"
OPENAI_STT_PROMPT = (
    "You are a helpful assistant. When the user speaks, you listen and respond."
)


# stt_choice = "groq"
GROQ_STT_MODEL = "whisper-large-v3-turbo"
GROQ_STT_LANGUAGE = "en"

# stt_choice = "google"
GOOGLE_STT_MODEL = "chirp"


# TTS_CHOICE = "elevenlabs"
ELEVENLABS_MODEL = "eleven_turbo_v2_5"
ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_VOICE_NAME = "Rachel"
ELEVENLABS_VOICE_CATEGORY = "female"
ELEVENLABS_LANGUAGE = "en-US"

# TTS_CHOICE = "google"
GOOGLE_LANGUAGE = "en-US"
GOOGLE_GENDER = "female"
GOOGLE_VOICE_NAME = "en-US-Standard-A"
GOOGLE_CREDENTIALS_FILE = "credentials.json"

# TTS_CHOICE = "groq"
GROQ_MODEL = "playai-tts"
GROQ_VOICE = "Arista-PlayAI"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

TTS_CHOICE = "openai"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_TTS_VOICE = "ash"
OPENAI_TTS_INSTRUCTIONS = (
    "You are a helpful assistant. When the user speaks, you listen and respond."
)

LLM_CHOICE = "openai"
# LLM_CHOICE = "google"
# LLM_CHOICE = "groq"
# LLM_CHOICE = "grok"

STT_CHOICE = "openai"
# STT_CHOICE = "groq"
# STT_CHOICE = "google"
# STT_CHOICE = "deepgram"

# TTS_CHOICE = "openai"
# TTS_CHOICE = "google"
# TTS_CHOICE = "groq"
TTS_CHOICE = "elevenlabs"

if LLM_CHOICE == "openai":
    llm = openai.LLM(model=OPENAI_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
elif LLM_CHOICE == "groq":
    llm = groq.LLM(model=GROQ_MODEL, api_key=os.getenv("GROQ_API_KEY"))
elif LLM_CHOICE == "google":
    llm = google.LLM(model=GEMINI_MODEL, api_key=os.getenv("GOOGLE_API_KEY"))
elif LLM_CHOICE == "grok":
    llm = openai.LLM.with_x_ai(
        model=GROK_MODEL,
        temperature=GROK_TEMPERATURE,
        api_key=os.getenv("X_AI_API_KEY"),
    )

if STT_CHOICE == "deepgram":
    stt = deepgram.STT(
        model=DEEPGRAM_MODEL,
        language=DEEPGRAM_LANGUAGE,
        api_key=os.getenv("DEEPGRAM_API_KEY"),
    )
elif STT_CHOICE == "openai":
    stt = openai.STT(
        model=OPENAI_STT_MODEL,
        language=OPENAI_STT_LANGUAGE,
        prompt=OPENAI_STT_PROMPT,
        api_key=os.getenv("OPENAI_API_KEY"),
    )
elif STT_CHOICE == "groq":
    stt = groq.STT(
        model=GROQ_STT_MODEL,
        language=GROQ_STT_LANGUAGE,
        api_key=os.getenv("GROQ_API_KEY"),
    )
elif STT_CHOICE == "google":
    stt = google.STT(
        model=GOOGLE_STT_MODEL,
    )

if TTS_CHOICE == "elevenlabs":

    tts = elevenlabs.TTS(
        voice_id=ELEVENLABS_VOICE_ID,
        model=ELEVENLABS_MODEL,
        streaming_latency=1,
        # language=elevenlabs_language,
        api_key=os.getenv("ELEVENLABS_API_KEY"),
    )
elif TTS_CHOICE == "google":
    tts = google.TTS(
        language=GOOGLE_LANGUAGE,
        gender=GOOGLE_GENDER,
        voice_name=GOOGLE_VOICE_NAME,
        credentials_file=GOOGLE_CREDENTIALS_FILE,
    )
elif TTS_CHOICE == "groq":
    tts = groq.TTS(
        base_url=GROQ_BASE_URL,
        model=GROQ_MODEL,
        voice=GROQ_VOICE,
        api_key=os.getenv("GROQ_API_KEY"),
    )
elif TTS_CHOICE == "openai":
    tts = openai.TTS(
        model=OPENAI_TTS_MODEL,
        voice=OPENAI_TTS_VOICE,
        instructions=OPENAI_TTS_INSTRUCTIONS,
        api_key=os.getenv("OPENAI_API_KEY"),
    )

ph = PineconeHelper()


class VoiceAgent(Agent):
    """Voice agent that listens to the user and responds with text."""

    def __init__(self) -> None:

        super().__init__(
            instructions=SYSTEM_PROMPT,
            stt=stt,
            llm=llm,
            tts=tts,
            vad=silero.VAD.load(),
        )
        self._seen_results = set()

    @function_tool()
    async def get_dubai_properties_info(
        self, context: RunContext, question_for_knowledge_base: str
    ):
        """
        Called when user asks about properties for rent or buy in Dubai.
        Args:
            context: RunContext
            question_for_knowledge_base: Question for the knowledge base which has properties data
        """
        logger.info(
            "get_dubai_properties_info function called with question %s",
            question_for_knowledge_base,
        )

        thinking_messages = [
            "Let me look that up...",
            "One moment while I check...",
            "I'll find that information for you...",
            "Just a second while I search...",
            "Looking into that now...",
        ]
        await self.session.say(random.choice(thinking_messages))
        result = await ph.get_document_from_pinecone(
            question_for_knowledge_base,
        )

        return result

    async def on_enter(self):
        self.session.generate_reply(
            instructions=f"Say the welcome message {WELCOME_MESSAGE}"
        )


async def entrypoint(ctx: JobContext):
    """Entrypoint for the voice agent."""

    await ctx.connect()

    session = AgentSession()
    agent = VoiceAgent()
    await session.start(agent=agent, room=ctx.room)
    await ph.initialize()

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
    await lkapi.egress.start_room_composite_egress(egress_req)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
