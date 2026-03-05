"""
DSSA Pipeline Orchestrator — manages video chunking, parallel agent execution,
race condition handling, and embedding generation.

Core flow per uploaded video:
1. ffmpeg chunks video into 2-min segments
2. For each chunk, extract key frames via Gemini
3. Launch Narrative Builder + Reasoner in parallel
4. Handle race conditions when processing exceeds chunk duration
5. Store reconstructions + embeddings in DB
"""
import os
import asyncio
import json
import subprocess
import time
import uuid
import traceback
from datetime import datetime, timezone

from config import (
    CHUNK_DURATION_SECONDS, MAX_PENDING_CHUNKS, RISK_THRESHOLD,
    UPLOAD_DIR, FRAMES_DIR, GEMINI_API_KEY, GENERATION_MODEL
)
import database as db
from agents import (
    run_narrative_builder, run_reasoner,
    generate_embedding, _extract_frames_for_range, get_key_timestamps, client
)


# ════════════════════════════════════════════════════════════
#  VIDEO CHUNKING
# ════════════════════════════════════════════════════════════

def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json", video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except Exception as e:
        print(f"[ffprobe] Error getting duration: {e}")
        return 0.0


def split_video_into_chunks(video_path: str, video_id: str) -> list[dict]:
    """Split video into 2-minute chunks using ffmpeg. Returns list of chunk info dicts."""
    duration = get_video_duration(video_path)
    if duration <= 0:
        return []

    chunks_dir = os.path.join(UPLOAD_DIR, video_id, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)

    chunks = []
    chunk_index = 0
    start = 0.0

    while start < duration:
        end = min(start + CHUNK_DURATION_SECONDS, duration)
        chunk_filename = f"chunk_{chunk_index:04d}.mp4"
        chunk_path = os.path.join(chunks_dir, chunk_filename)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(end - start),
            "-i", video_path,
            "-c", "copy",
            "-avoid_negative_ts", "1",
            chunk_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        except Exception as e:
            print(f"[ffmpeg] Chunk split warning: {e}")

        chunks.append({
            "index": chunk_index,
            "path": chunk_path,
            "start_ts": start,
            "end_ts": end,
        })
        start = end
        chunk_index += 1

    return chunks


def extract_key_frames_basic(video_path: str, chunk_index: int, start_ts: float, end_ts: float) -> list[str]:
    """Extract evenly-spaced key frames from a chunk (fallback for race conditions)."""
    out_dir = os.path.join(FRAMES_DIR, f"initial_{chunk_index}")
    os.makedirs(out_dir, exist_ok=True)

    duration = end_ts - start_ts
    if duration <= 0:
        return []

    fps_val = 8.0 / max(duration, 1.0)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"fps={fps_val:.4f}",
        "-frames:v", "8",
        "-q:v", "2",
        os.path.join(out_dir, "kf_%03d.jpg"),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=30, check=True)
    except Exception as e:
        print(f"[ffmpeg] Key frame extraction warning: {e}")

    frames = sorted([
        os.path.join(out_dir, f)
        for f in os.listdir(out_dir) if f.endswith(".jpg")
    ])
    return frames


def extract_stamped_key_frames(
    video_path: str,
    chunk_index: int,
    key_ranges: list[dict],
    chunk_start_ts: float,
) -> list[str]:
    """Extract frames at Gemini-identified timestamp ranges and burn timestamp text onto them.

    key_ranges: list of {"start": float, "end": float} — timestamps relative to the chunk (0-based).
    chunk_start_ts: absolute start timestamp of this chunk in the full video (for display).

    For each range, extracts ~3 frames and overlays the absolute timestamp on each.
    Returns sorted list of all stamped frame paths.
    """
    out_dir = os.path.join(FRAMES_DIR, f"stamped_{chunk_index}")
    os.makedirs(out_dir, exist_ok=True)

    all_frames = []

    for range_idx, ts_range in enumerate(key_ranges):
        rs = ts_range["start"]
        re = ts_range["end"]
        duration = re - rs
        if duration <= 0:
            continue

        # Extract ~3 frames per range
        n_frames = min(3, max(1, int(duration / 2)))
        fps_val = n_frames / max(duration, 0.5)

        # Compute the absolute timestamp for display:
        # chunk_start_ts + range midpoint
        abs_start = chunk_start_ts + rs
        abs_end = chunk_start_ts + re

        def _fmt(t):
            m = int(t) // 60
            s = int(t) % 60
            return f"{m}:{s:02d}"

        timestamp_text = f"{_fmt(abs_start)} - {_fmt(abs_end)}"

        # ffmpeg: extract frames at this range, burn timestamp text
        prefix = f"r{range_idx:02d}"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(rs),
            "-t", str(duration),
            "-i", video_path,
            "-vf", (
                f"fps={fps_val:.4f},"
                f"drawtext=text='{timestamp_text}':"
                f"fontsize=24:fontcolor=white:"
                f"borderw=2:bordercolor=black:"
                f"x=10:y=h-40"
            ),
            "-frames:v", str(n_frames),
            "-q:v", "2",
            os.path.join(out_dir, f"{prefix}_%03d.jpg"),
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=15, check=True)
        except Exception as e:
            print(f"[ffmpeg] Stamped frame extraction warning (range {range_idx}): {e}")

    # Collect all extracted frames in order
    if os.path.exists(out_dir):
        all_frames = sorted([
            os.path.join(out_dir, f)
            for f in os.listdir(out_dir) if f.endswith(".jpg")
        ])

    print(f"[StampedFrames] Chunk {chunk_index}: extracted {len(all_frames)} stamped frames from {len(key_ranges)} ranges")
    return all_frames


def upload_chunk_to_gemini(chunk_path: str):
    """Upload a video chunk to Gemini Files API for the Reasoner agent.
    Polls until the file reaches ACTIVE state (required before use).
    Includes 1 retry on upload failure before returning None."""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            uploaded = client.files.upload(file=chunk_path)
            print(f"[Gemini Files] Uploaded {chunk_path} (attempt {attempt + 1}), waiting for ACTIVE state...")
            # Poll until file is ACTIVE (max 60s)
            for _ in range(30):
                file_info = client.files.get(name=uploaded.name)
                if file_info.state.name == "ACTIVE":
                    print(f"[Gemini Files] File {uploaded.name} is ACTIVE")
                    return file_info
                import time as _time
                _time.sleep(2)
            print(f"[Gemini Files] File {uploaded.name} did not reach ACTIVE state in time")
            # Don't retry for ACTIVE state timeout — file is uploaded but stuck
            return None
        except Exception as e:
            print(f"[Gemini Files] Upload error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import time as _time
                _time.sleep(3)
    return None


# ════════════════════════════════════════════════════════════
#  PIPELINE STATE
# ════════════════════════════════════════════════════════════

class PipelineState:
    """Track the state of pipeline processing for race condition handling."""

    def __init__(self, video_id: str, total_chunks: int):
        self.video_id = video_id
        self.total_chunks = total_chunks
        self.completed_reconstructions: dict[int, dict] = {}   # chunk_index -> {"text": ..., "start_ts": ..., "end_ts": ...}
        self.completed_risk_scores: dict[int, dict] = {}       # chunk_index -> risk result
        self.pending_chunks: set[int] = set()                  # Currently being processed
        self.failed_chunks: set[int] = set()
        self.started_at: dict[int, float] = {}                 # chunk_index -> timestamp started
        self.events: list[dict] = []                           # Full event log
        self.lock = asyncio.Lock()

    def get_pending_count(self) -> int:
        return len(self.pending_chunks)

    def get_history(self) -> list[dict]:
        """Get ordered list of completed reconstructions for agent context."""
        items = sorted(self.completed_reconstructions.values(), key=lambda x: x["start_ts"])
        return items

    def is_chunk_complete(self, idx: int) -> bool:
        return idx in self.completed_reconstructions

    def should_use_tool_less(self) -> bool:
        """Returns True if we have >= MAX_PENDING_CHUNKS pending (6 min behind)."""
        return self.get_pending_count() >= MAX_PENDING_CHUNKS


# ════════════════════════════════════════════════════════════
#  PIPELINE EXECUTION
# ════════════════════════════════════════════════════════════

async def process_video(video_id: str, video_path: str, broadcast_fn=None):
    """
    Main pipeline entry point. Processes an uploaded video end-to-end.

    Uses timer-driven dispatching: a new chunk task is launched every
    CHUNK_DURATION_SECONDS regardless of whether the previous chunk has
    finished.  This accurately simulates a live CCTV feed and makes the
    race-condition / tool-less logic activate for real.

    broadcast_fn: async callable(event_type, data) to push real-time updates to WebSocket clients.
    """
    async def broadcast(event_type, data):
        if broadcast_fn:
            await broadcast_fn(event_type, {**data, "video_id": video_id})

    print(f"\n{'='*60}")
    print(f"[PIPELINE] Starting processing for video {video_id}")
    print(f"[PIPELINE] Video path: {video_path}")
    print(f"{'='*60}")

    await broadcast("pipeline_started", {"message": "Starting video processing pipeline"})

    # 1. Get duration and split into chunks
    duration = get_video_duration(video_path)
    print(f"[PIPELINE] Video duration: {duration:.1f}s")
    if duration <= 0:
        print(f"[PIPELINE ERROR] Could not determine video duration!")
        await broadcast("pipeline_error", {"message": "Could not determine video duration. Is ffmpeg installed?"})
        await db.update_video_status(video_id, "error")
        return

    chunks = split_video_into_chunks(video_path, video_id)
    total_chunks = len(chunks)
    print(f"[PIPELINE] Split into {total_chunks} chunks")

    await db.update_video_status(video_id, "processing")
    await broadcast("pipeline_info", {
        "message": f"Video split into {total_chunks} chunks ({duration:.0f}s total)",
        "total_chunks": total_chunks,
        "duration": duration,
    })

    state = PipelineState(video_id, total_chunks)

    # ── Per-chunk processor ────────────────────────────────
    # This runs as a floating async task.  Multiple instances can be
    # in-flight simultaneously, which is what creates real race conditions.

    async def process_single_chunk(chunk: dict):
        """Process a single 2-min chunk: run both agents in parallel."""
        idx = chunk["index"]
        chunk_path = chunk["path"]
        start_ts = chunk["start_ts"]
        end_ts = chunk["end_ts"]

        async with state.lock:
            state.pending_chunks.add(idx)
            state.started_at[idx] = time.time()

        # Evaluate tool_less at invocation time — pending set is live
        tool_less = state.should_use_tool_less()

        await broadcast("chunk_started", {
            "chunk_index": idx,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "tool_less": tool_less,
            "pending_count": state.get_pending_count(),
        })

        # ── Step 1: Upload chunk to Gemini (shared by key-timestamp extraction + Reasoner) ──
        uploaded_file = await asyncio.to_thread(upload_chunk_to_gemini, chunk_path)
        if uploaded_file is None:
            await broadcast("agent_status", {
                "agent": "pipeline",
                "status": "file_upload_fallback",
                "chunk": idx,
                "message": "Gemini file upload failed — using basic frame extraction fallback",
            })

        # ── Step 2: Get key timestamp ranges from Gemini ──
        if uploaded_file and not tool_less:
            await broadcast("agent_status", {
                "agent": "pipeline",
                "status": "extracting_key_timestamps",
                "chunk": idx,
                "message": "Asking Gemini for key timestamp ranges...",
            })
            key_ranges = await asyncio.to_thread(
                get_key_timestamps, uploaded_file, start_ts, end_ts
            )
            await broadcast("tool_call", {
                "agent": "pipeline",
                "tool": "get_key_timestamps",
                "args": {"ranges": key_ranges},
                "chunk": idx,
                "iteration": 0,
            })
            # Extract frames at those timestamps with burned-in timestamp text
            key_frames = await asyncio.to_thread(
                extract_stamped_key_frames, chunk_path, idx, key_ranges, start_ts
            )
        else:
            # Fallback: basic even-spaced extraction (tool-less or upload failed)
            key_frames = extract_key_frames_basic(chunk_path, idx, 0, end_ts - start_ts)

        # Build history — snapshot of completed reconstructions at this moment
        history = state.get_history()

        # ── Race-condition context optimisation ──
        # If the immediately previous chunk is still pending, we can't include
        # its atomic reconstruction.  Instead, include its key frames so the
        # agents still have *some* visual context of that interval.
        prev_idx = idx - 1
        prev_key_frames: list[str] = []
        race_context_note = None
        if prev_idx >= 0 and not state.is_chunk_complete(prev_idx):
            prev_chunk = chunks[prev_idx] if prev_idx < len(chunks) else None
            if prev_chunk:
                race_context_note = (
                    f"Note: The previous segment ({prev_chunk['start_ts']:.0f}s-"
                    f"{prev_chunk['end_ts']:.0f}s) is still being processed. "
                    f"Its atomic reconstruction is not yet available."
                )
                # Extract basic key frames from the previous chunk for fallback context
                prev_key_frames = extract_key_frames_basic(
                    prev_chunk["path"], prev_idx,
                    0, prev_chunk["end_ts"] - prev_chunk["start_ts"],
                )
            await broadcast("race_condition", {
                "chunk_index": idx,
                "pending_chunk": prev_idx,
                "pending_count": state.get_pending_count(),
                "tool_less": tool_less,
                "message": f"Race condition: chunk {prev_idx} not ready while processing chunk {idx}",
            })

        # Merge any previous-chunk fallback frames into the current key frames
        combined_key_frames = prev_key_frames + key_frames

        # Create event callback for real-time UI
        async def on_agent_event(event_type, data):
            state.events.append({"type": event_type, "data": data, "ts": time.time()})
            await broadcast(event_type, data)

        # Launch both agents in parallel — ALWAYS
        agent_tasks = []

        # Narrative Builder
        agent_tasks.append(asyncio.create_task(
            run_narrative_builder(
                video_path=chunk_path,
                chunk_index=idx,
                start_ts=start_ts,
                end_ts=end_ts,
                history=history,
                key_frame_paths=combined_key_frames,
                tool_less=tool_less,
                on_event=on_agent_event,
            )
        ))

        # Reasoner
        agent_tasks.append(asyncio.create_task(
            run_reasoner(
                video_path=chunk_path,
                chunk_index=idx,
                start_ts=start_ts,
                end_ts=end_ts,
                history=history,
                uploaded_file=uploaded_file,
                key_frame_paths=combined_key_frames,
                tool_less=tool_less,
                on_event=on_agent_event,
            )
        ))

        # Wait for both agents to finish
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)

        # Process Narrative Builder result
        nb_result = results[0] if not isinstance(results[0], Exception) else None
        if isinstance(results[0], Exception):
            print(f"[NB Error] Chunk {idx}: {results[0]}")
            await broadcast("agent_error", {"agent": "narrative_builder", "chunk": idx, "error": str(results[0])})

        # Process Reasoner result
        rs_result = results[1] if len(results) > 1 and not isinstance(results[1], Exception) else None
        if len(results) > 1 and isinstance(results[1], Exception):
            print(f"[RS Error] Chunk {idx}: {results[1]}")
            await broadcast("agent_error", {"agent": "reasoner", "chunk": idx, "error": str(results[1])})

        if nb_result:
            reconstruction_text = nb_result["text"]
            # Generate embedding
            try:
                embedding = await asyncio.to_thread(generate_embedding, reconstruction_text)
            except Exception as e:
                print(f"[Embedding Error] {e}")
                embedding = []

            # Save to DB
            now = datetime.now(timezone.utc).isoformat()
            await db.insert_reconstruction(
                video_id=video_id,
                chunk_index=idx,
                start_ts=start_ts,
                end_ts=end_ts,
                text=reconstruction_text,
                embedding=embedding,
                created_at=now,
            )

            async with state.lock:
                state.completed_reconstructions[idx] = {
                    "text": reconstruction_text,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                }
                state.pending_chunks.discard(idx)
        else:
            # Narrative builder failed — still remove from pending
            async with state.lock:
                state.pending_chunks.discard(idx)
                state.failed_chunks.add(idx)

        # Process Reasoner result
        if rs_result:
            now = datetime.now(timezone.utc).isoformat()
            await db.insert_risk_score(
                video_id=video_id,
                chunk_index=idx,
                start_ts=start_ts,
                end_ts=end_ts,
                score=rs_result["score"],
                classification=rs_result["classification"],
                reasoning=rs_result["reasoning"],
                action_required=rs_result["action_required"],
                created_at=now,
            )

            async with state.lock:
                state.completed_risk_scores[idx] = rs_result

            # Raise alert immediately if high risk
            if rs_result["score"] >= RISK_THRESHOLD:
                await broadcast("alert", {
                    "chunk_index": idx,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                    "score": rs_result["score"],
                    "classification": rs_result["classification"],
                    "reasoning": rs_result["reasoning"],
                    "action_required": rs_result["action_required"],
                })

        elapsed = time.time() - state.started_at.get(idx, time.time())
        await broadcast("chunk_completed", {
            "chunk_index": idx,
            "elapsed_seconds": elapsed,
            "pending_count": state.get_pending_count(),
            "completed_count": len(state.completed_reconstructions),
            "total_chunks": total_chunks,
        })

    # ── Timer-driven dispatch ──────────────────────────────
    # Launch a new chunk task every CHUNK_DURATION_SECONDS, simulating
    # a live CCTV feed.  If a previous chunk is still running, it stays
    # in-flight — that's what creates real race conditions.

    in_flight_tasks: list[asyncio.Task] = []

    for i, chunk in enumerate(chunks):
        dispatch_wall = time.time()
        print(f"\n[PIPELINE] --- Dispatching chunk {chunk['index']} "
              f"({chunk['start_ts']:.0f}s - {chunk['end_ts']:.0f}s) --- "
              f"[pending={state.get_pending_count()}]")

        task = asyncio.create_task(
            process_single_chunk(chunk),
            name=f"chunk-{chunk['index']}",
        )
        in_flight_tasks.append(task)

        # Wait CHUNK_DURATION_SECONDS before dispatching the next chunk
        # (simulates waiting for next 2 min of footage to "arrive")
        if i < len(chunks) - 1:
            elapsed_dispatch = time.time() - dispatch_wall
            wait_remaining = max(0, CHUNK_DURATION_SECONDS - elapsed_dispatch)
            if wait_remaining > 0:
                print(f"[PIPELINE] Next chunk dispatches in {wait_remaining:.1f}s (live feed simulation)")
                await broadcast("pipeline_waiting", {
                    "chunk_index": chunk["index"],
                    "wait_seconds": wait_remaining,
                    "message": f"Waiting {wait_remaining:.0f}s for next 2-min chunk to arrive...",
                })
                await asyncio.sleep(wait_remaining)

    # All chunks dispatched — wait for any still in-flight to finish
    if in_flight_tasks:
        print(f"\n[PIPELINE] All chunks dispatched. Waiting for {sum(1 for t in in_flight_tasks if not t.done())} remaining tasks...")
        results = await asyncio.gather(*in_flight_tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"[PIPELINE ERROR] Chunk {i} task failed: {result}")
                traceback.print_exc()

    # Pipeline complete
    print(f"\n{'='*60}")
    print(f"[PIPELINE] All chunks processed! Reconstructions: {len(state.completed_reconstructions)}, Risk Scores: {len(state.completed_risk_scores)}")
    print(f"{'='*60}")
    await db.update_video_status(video_id, "completed")
    await broadcast("pipeline_completed", {
        "total_chunks": total_chunks,
        "completed_reconstructions": len(state.completed_reconstructions),
        "completed_risk_scores": len(state.completed_risk_scores),
    })
