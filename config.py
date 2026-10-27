"""Runtime settings.

Real credentials live in `example.env` (gitignored). `.env` is the committed
template with placeholders only, so it is loaded second and never overrides.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent

load_dotenv(ROOT / "example.env")
load_dotenv(ROOT / ".env")  # fills only keys still missing


def _real(value: str | None) -> str:
    """Treat template placeholders like `nvapi-...` as unset."""
    if not value or value.endswith("..."):
        return ""
    return value


NVIDIA_API_KEY = _real(os.getenv("NVIDIA_API_KEY"))
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

# Primary NVIDIA model — override via NVIDIA_MODEL env var.
# Must be a model ID from the NVIDIA NIM catalog (build.nvidia.com/models).
# The list below is the fallback chain tried in order when one model fails permanently.
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")

# Ordered fallback chain for NVIDIA models.
# Tried left-to-right if a model is permanently dead (404/401/410).
# All have free endpoints as of Oct 2026.  GLM-5-3 is excluded (deprecating).
NVIDIA_MODEL_FALLBACKS: list[str] = [
    "nvidia/nemotron-3.5-lightning-30b-a3b",        # 30B MoE, fastest, agentic — primary
    "nvidia/nemotron-3.5-super-vl-120b-a12b",       # 120B, best tool-calling, a bit slower
    "nvidia/nemotron-3.5-bolt-e4b",                 # compact reasoning/agentic, very fast
    "nvidia/deepseek-r1-67b-instruct",              # 552B MoE / 8B active, free tier
    "zhipuai/glm-5-3-flash",                        # 320B / 18B active, multimodal
    "openai/gpt-oss-20b",                           # OpenAI OSS 20B MoE on NVIDIA, reasoning
]

NVIDIA_THINKING = os.getenv("NVIDIA_THINKING", "false").lower() == "true"

OPENAI_API_KEY = _real(os.getenv("OPENAI_API_KEY"))
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")

METERLESS_API_KEY = _real(os.getenv("METERLESS_API_KEY"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = ROOT / os.getenv("LOG_DIR", "logs")
MAX_RETRY_COUNT = int(os.getenv("MAX_RETRY_COUNT", "2"))
QUERY_TIMEOUT_SECONDS = int(os.getenv("QUERY_TIMEOUT_SECONDS", "10"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

# true → always use mock data; false → use Sai Teja's data/sources, falling back to mocks if missing
USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
# true → skip all LLM calls and use deterministic heuristics (tests, offline demo)
OFFLINE = os.getenv("CLINICALTRAIL_OFFLINE", "false").lower() == "true"
