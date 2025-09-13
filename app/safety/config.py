import os
from dotenv import load_dotenv

# Load .env as soon as this module is imported (safe to call multiple times)
load_dotenv()

SAFETY_LLM: bool = os.getenv("SAFETY_LLM", "1") == "1"
SAFETY_LLM_MODEL: str = os.getenv("SAFETY_LLM_MODEL", "gpt-4o-mini")
SAFETY_LLM_TIMEOUT: float = float(os.getenv("SAFETY_LLM_TIMEOUT", "3.0"))  # seconds
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")