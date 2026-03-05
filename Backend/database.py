"""
DSSA Database Layer — async SQLite with embedding storage
"""
import json
import aiosqlite
import numpy as np
from config import DB_PATH


async def init_db():
    """Create tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                upload_time TEXT NOT NULL,
                duration REAL DEFAULT 0,
                status TEXT DEFAULT 'uploaded',
                total_chunks INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reconstructions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                start_ts REAL NOT NULL,
                end_ts REAL NOT NULL,
                text TEXT NOT NULL,
                embedding TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (video_id) REFERENCES videos(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS risk_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                start_ts REAL NOT NULL,
                end_ts REAL NOT NULL,
                score REAL NOT NULL,
                classification TEXT,
                reasoning TEXT,
                action_required INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (video_id) REFERENCES videos(id)
            )
        """)
        await db.commit()


# ── Videos ──────────────────────────────────────────────────

async def insert_video(video_id: str, filename: str, upload_time: str, duration: float, total_chunks: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO videos (id, filename, upload_time, duration, status, total_chunks) VALUES (?, ?, ?, ?, 'processing', ?)",
            (video_id, filename, upload_time, duration, total_chunks),
        )
        await db.commit()


async def update_video_status(video_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE videos SET status = ? WHERE id = ?", (status, video_id))
        await db.commit()


async def get_video(video_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


# ── Reconstructions ─────────────────────────────────────────

async def insert_reconstruction(video_id: str, chunk_index: int, start_ts: float, end_ts: float, text: str, embedding: list, created_at: str):
    embedding_json = json.dumps(embedding) if embedding else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO reconstructions (video_id, chunk_index, start_ts, end_ts, text, embedding, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (video_id, chunk_index, start_ts, end_ts, text, embedding_json, created_at),
        )
        await db.commit()


async def get_reconstructions(video_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM reconstructions WHERE video_id = ? ORDER BY chunk_index ASC", (video_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_reconstructions_with_embeddings():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM reconstructions WHERE embedding IS NOT NULL ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ── Risk Scores ─────────────────────────────────────────────

async def insert_risk_score(video_id: str, chunk_index: int, start_ts: float, end_ts: float,
                            score: float, classification: str, reasoning: str, action_required: bool, created_at: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO risk_scores (video_id, chunk_index, start_ts, end_ts, score, classification, reasoning, action_required, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (video_id, chunk_index, start_ts, end_ts, score, classification, reasoning, int(action_required), created_at),
        )
        await db.commit()


async def get_risk_scores(video_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM risk_scores WHERE video_id = ? ORDER BY chunk_index ASC", (video_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ── Semantic Search ─────────────────────────────────────────

def cosine_similarity(a: list, b: list) -> float:
    a_np = np.array(a, dtype=np.float32)
    b_np = np.array(b, dtype=np.float32)
    dot = np.dot(a_np, b_np)
    norm = np.linalg.norm(a_np) * np.linalg.norm(b_np)
    if norm == 0:
        return 0.0
    return float(dot / norm)


async def semantic_search(query_embedding: list, top_k: int = 10):
    """Search reconstructions by cosine similarity against stored embeddings."""
    all_recs = await get_all_reconstructions_with_embeddings()
    scored = []
    for rec in all_recs:
        emb = json.loads(rec["embedding"]) if rec["embedding"] else None
        if emb is None:
            continue
        sim = cosine_similarity(query_embedding, emb)
        scored.append({**rec, "similarity": sim})
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_k]
