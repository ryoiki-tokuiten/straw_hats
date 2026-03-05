"""
DSSA Backend — FastAPI Application
Real-time video surveillance AI with WebSocket streaming.
"""
import os
import uuid
import asyncio
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import database as db
from config import UPLOAD_DIR, FACE_DATA_DIR, DANGER_ZONE_DIR, GEMINI_API_KEY
from pipeline import process_video, get_video_duration
from face_recognition import face_engine


# ════════════════════════════════════════════════════════════
#  WEBSOCKET MANAGER
# ════════════════════════════════════════════════════════════

class ConnectionManager:
    """Manages WebSocket connections for real-time event broadcasting."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, event_type: str, data: dict):
        message = json.dumps({"type": event_type, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()})
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.active_connections.remove(conn)


manager = ConnectionManager()


# ════════════════════════════════════════════════════════════
#  APP LIFECYCLE
# ════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(
    title="DSSA — Dual-Stream Surveillance AI",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files statically for frontend video playback
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/face_data", StaticFiles(directory=FACE_DATA_DIR), name="face_data")
app.mount("/danger_zone_images", StaticFiles(directory=DANGER_ZONE_DIR), name="danger_zone_images")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ════════════════════════════════════════════════════════════
#  REST ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {"status": "ok", "api_key_set": bool(GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here")}


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file and start processing pipeline."""
    video_id = str(uuid.uuid4())
    video_dir = os.path.join(UPLOAD_DIR, video_id)
    os.makedirs(video_dir, exist_ok=True)

    # Save file
    file_path = os.path.join(video_dir, file.filename)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Get duration
    duration = get_video_duration(file_path)
    total_chunks = max(1, int(duration / 120) + (1 if duration % 120 > 0 else 0))

    # Insert video record
    now = datetime.now(timezone.utc).isoformat()
    await db.insert_video(video_id, file.filename, now, duration, total_chunks)

    # Start pipeline in background
    async def run_pipeline():
        try:
            await process_video(video_id, file_path, broadcast_fn=manager.broadcast)
        except Exception as e:
            print(f"[Pipeline Error] {e}")
            import traceback
            traceback.print_exc()
            await db.update_video_status(video_id, "error")
            await manager.broadcast("pipeline_error", {"video_id": video_id, "error": str(e)})

    asyncio.create_task(run_pipeline())

    return JSONResponse({
        "video_id": video_id,
        "filename": file.filename,
        "duration": duration,
        "total_chunks": total_chunks,
        "status": "processing",
        "video_url": f"/uploads/{video_id}/{file.filename}",
    })


@app.get("/api/status/{video_id}")
async def get_status(video_id: str):
    """Get current processing status for a video."""
    video = await db.get_video(video_id)
    if not video:
        return JSONResponse({"error": "Video not found"}, status_code=404)

    reconstructions = await db.get_reconstructions(video_id)
    risk_scores = await db.get_risk_scores(video_id)

    return {
        "video": video,
        "completed_chunks": len(reconstructions),
        "risk_scores_count": len(risk_scores),
    }


@app.get("/api/reconstructions/recent")
async def get_recent_reconstructions(limit: int = Query(default=10, le=50)):
    """Get the most recent atomic reconstructions for display on the search page."""
    all_recs = await db.get_all_reconstructions_with_embeddings()
    # Already ordered by created_at DESC from the query
    recent = all_recs[:limit]
    for r in recent:
        r.pop("embedding", None)
        r["has_embedding"] = True
        r["chunk_video_url"] = f"/uploads/{r['video_id']}/chunks/chunk_{r['chunk_index']:04d}.mp4"
    return {"reconstructions": recent}


@app.get("/api/reconstructions/{video_id}")
async def get_reconstructions(video_id: str):
    """Get all atomic reconstructions for a video."""
    reconstructions = await db.get_reconstructions(video_id)
    # Strip embedding vectors from response (too large)
    for r in reconstructions:
        r.pop("embedding", None)
    return {"video_id": video_id, "reconstructions": reconstructions}


@app.get("/api/risk-scores/{video_id}")
async def get_risk_scores(video_id: str):
    """Get all risk scores for a video."""
    scores = await db.get_risk_scores(video_id)
    return {"video_id": video_id, "risk_scores": scores}



@app.get("/api/search")
async def search(q: str = Query(..., description="Search query")):
    """Semantic search across all atomic reconstructions using embeddings."""
    from agents import generate_embedding_for_search
    from database import semantic_search

    query_embedding = await asyncio.to_thread(generate_embedding_for_search, q)
    if not query_embedding:
        return {"results": [], "query": q}

    results = await semantic_search(query_embedding, top_k=10)
    # Clean up results
    for r in results:
        r.pop("embedding", None)
        r["chunk_video_url"] = f"/uploads/{r['video_id']}/chunks/chunk_{r['chunk_index']:04d}.mp4"
    return {"results": results, "query": q}


# ════════════════════════════════════════════════════════════
#  FAMILIAR FACES ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.post("/api/faces")
async def register_face(name: str = Query(...), file: UploadFile = File(...)):
    """Upload a face image and register it with a name.
    The image is processed by InsightFace to extract the ArcFace embedding."""
    # Save the image
    face_filename = f"{uuid.uuid4().hex}_{file.filename}"
    face_path = os.path.join(FACE_DATA_DIR, face_filename)
    content = await file.read()
    with open(face_path, "wb") as f:
        f.write(content)

    # Extract face embedding via InsightFace
    try:
        embedding = await asyncio.to_thread(face_engine.get_primary_embedding, face_path)
    except Exception as e:
        # Clean up saved file on failure
        if os.path.exists(face_path):
            os.remove(face_path)
        return JSONResponse({"error": f"Face detection failed: {str(e)}"}, status_code=400)

    if embedding is None:
        if os.path.exists(face_path):
            os.remove(face_path)
        return JSONResponse({"error": "No face detected in the uploaded image. Please upload a clear photo with a visible face."}, status_code=400)

    # Store in database
    now = datetime.now(timezone.utc).isoformat()
    face_id = await db.insert_familiar_face(name, face_path, embedding, now)

    return JSONResponse({
        "id": face_id,
        "name": name,
        "image_url": f"/face_data/{face_filename}",
        "created_at": now,
    })


@app.get("/api/faces")
async def list_faces():
    """List all registered familiar faces."""
    faces = await db.get_all_familiar_faces()
    results = []
    for f in faces:
        image_filename = os.path.basename(f["image_path"]) if f["image_path"] else ""
        results.append({
            "id": f["id"],
            "name": f["name"],
            "image_url": f"/face_data/{image_filename}" if image_filename else None,
            "created_at": f["created_at"],
        })
    return {"faces": results}


@app.delete("/api/faces/{face_id}")
async def remove_face(face_id: int):
    """Delete a registered face."""
    image_path = await db.delete_familiar_face(face_id)
    # Clean up the image file
    if image_path and os.path.exists(image_path):
        os.remove(image_path)
    return {"deleted": True, "id": face_id}


# ════════════════════════════════════════════════════════════
#  DANGER ZONE ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.post("/api/danger-zone")
async def save_danger_zone(
    description: str = Query(default=""),
    files: list[UploadFile] = File(default=[]),
):
    """Save danger zone config: text description + up to 3 reference images."""
    # Limit to 3 images
    if len(files) > 3:
        return JSONResponse({"error": "Maximum 3 danger zone images allowed."}, status_code=400)

    # Get existing config to clean up old images
    existing = await db.get_danger_zone()
    if existing and existing.get("image_paths"):
        for old_path in existing["image_paths"]:
            if os.path.exists(old_path):
                os.remove(old_path)

    # Save new images
    saved_paths = []
    for f in files:
        if f.filename:  # Skip empty file fields
            img_filename = f"{uuid.uuid4().hex}_{f.filename}"
            img_path = os.path.join(DANGER_ZONE_DIR, img_filename)
            content = await f.read()
            with open(img_path, "wb") as fh:
                fh.write(content)
            saved_paths.append(img_path)

    now = datetime.now(timezone.utc).isoformat()
    await db.upsert_danger_zone(description if description else None, saved_paths, now)

    return JSONResponse({
        "description": description,
        "image_urls": [f"/danger_zone_images/{os.path.basename(p)}" for p in saved_paths],
        "updated_at": now,
    })


@app.get("/api/danger-zone")
async def get_danger_zone():
    """Get current danger zone configuration."""
    config = await db.get_danger_zone()
    if config is None:
        return {"config": None}
    # Convert image_paths to URLs
    image_urls = []
    for p in config.get("image_paths", []):
        if os.path.exists(p):
            image_urls.append(f"/danger_zone_images/{os.path.basename(p)}")
    return {
        "config": {
            "description": config.get("description", ""),
            "image_urls": image_urls,
            "updated_at": config.get("updated_at", ""),
        }
    }


@app.delete("/api/danger-zone")
async def clear_danger_zone():
    """Clear danger zone configuration."""
    image_paths = await db.delete_danger_zone()
    for p in image_paths:
        if os.path.exists(p):
            os.remove(p)
    return {"deleted": True}


# ════════════════════════════════════════════════════════════
#  WEBSOCKET ENDPOINT
# ════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, receive any client messages
            data = await websocket.receive_text()
            # Client can send queries or commands via WebSocket too
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
