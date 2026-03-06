"""
DSSA Configuration Constants
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── AI Provider ─────────────────────────────────────────────
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()  # "gemini" or "local"

# ── Gemini API ──────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GENERATION_MODEL = "gemini-3-flash-preview"
EMBEDDING_MODEL = "gemini-embedding-001"

# ── Local Model (LM Studio endpoint) ──────────────────────
LOCAL_ENDPOINT_URL = os.getenv("LOCAL_ENDPOINT_URL", "http://localhost:1234")
LOCAL_MODEL_ID = os.getenv("LOCAL_MODEL_ID", "")
LOCAL_MAX_FRAMES = int(os.getenv("LOCAL_MAX_FRAMES", "8"))

# ── Pipeline ────────────────────────────────────────────────
CHUNK_DURATION_SECONDS = 120          # 2 minutes per chunk
MAX_PENDING_CHUNKS = 3                # After 3 pending (6 min), go tool-less
RISK_THRESHOLD = 0.7                  # Score above this triggers alert
MAX_TOOL_CALLS = 5                    # Max tool calls per agent invocation
MAX_HISTORY_ITEMS = 30                # Keep last 30 atomic reconstructions in context
SKIP_KEY_TIMESTAMPS_RANGE = os.getenv("SKIP_KEY_TIMESTAMPS_RANGE", "FALSE").upper() == "TRUE"

# ── Storage ─────────────────────────────────────────────────
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
FRAMES_DIR = os.path.join(os.path.dirname(__file__), "frames")
FACE_DATA_DIR = os.path.join(os.path.dirname(__file__), "face_data")
DANGER_ZONE_DIR = os.path.join(os.path.dirname(__file__), "danger_zone_images")
DB_PATH = os.path.join(os.path.dirname(__file__), "dssa.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(FACE_DATA_DIR, exist_ok=True)
os.makedirs(DANGER_ZONE_DIR, exist_ok=True)

# ── Face Recognition ───────────────────────────────────────
FACE_DETECTION_THRESHOLD = 0.5       # Min det_score to consider a face
FACE_MATCH_THRESHOLD = 0.4           # Min cosine similarity for face match
