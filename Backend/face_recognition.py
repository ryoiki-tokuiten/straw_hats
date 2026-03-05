"""
DSSA Face Recognition Engine — ArcFace/InsightFace local inference.

Provides face detection, embedding generation, matching against registered
faces, and aggregation of per-frame detections into compressed text for
LLM context injection.
"""
import os
import cv2
import numpy as np
from collections import defaultdict

from config import FACE_DETECTION_THRESHOLD, FACE_MATCH_THRESHOLD


class FaceRecognitionEngine:
    """Singleton-style engine wrapping InsightFace (ArcFace / buffalo_l)."""

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_model(self):
        """Lazily initialise the InsightFace analysis app."""
        if self._model is not None:
            return
        from insightface.app import FaceAnalysis
        print("[FaceRecognition] Loading InsightFace buffalo_l model...")
        self._model = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
        )
        # det_size controls the input resolution for the detector
        self._model.prepare(ctx_id=-1, det_size=(640, 640))
        print("[FaceRecognition] Model loaded successfully")

    # ── Single-image operations ─────────────────────────────

    def get_faces(self, image_path: str) -> list[dict]:
        """Detect faces in an image.

        Returns list of dicts:
            [{"bbox": [x1,y1,x2,y2], "embedding": np.array(512,), "det_score": float}, ...]
        """
        self.load_model()
        img = cv2.imread(image_path)
        if img is None:
            print(f"[FaceRecognition] Could not read image: {image_path}")
            return []
        faces = self._model.get(img)
        results = []
        for face in faces:
            det_score = float(face.det_score)
            if det_score < FACE_DETECTION_THRESHOLD:
                continue
            results.append({
                "bbox": face.bbox.tolist(),
                "embedding": face.normed_embedding.tolist(),
                "det_score": det_score,
            })
        return results

    def get_primary_embedding(self, image_path: str) -> list[float] | None:
        """Get the embedding of the highest-confidence face in an image.

        Used for registering familiar faces — picks the dominant face.
        Returns None if no face detected above threshold.
        """
        faces = self.get_faces(image_path)
        if not faces:
            return None
        # Pick the face with the highest detection score
        best = max(faces, key=lambda f: f["det_score"])
        return best["embedding"]

    # ── Matching ────────────────────────────────────────────

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        a_np = np.array(a, dtype=np.float32)
        b_np = np.array(b, dtype=np.float32)
        dot = np.dot(a_np, b_np)
        norm = np.linalg.norm(a_np) * np.linalg.norm(b_np)
        if norm == 0:
            return 0.0
        return float(dot / norm)

    def match_face(
        self, embedding: list[float], registered_faces: list[dict]
    ) -> tuple[str | None, float]:
        """Match a face embedding against registered faces.

        registered_faces: [{"name": str, "embedding": list[float]}, ...]
        Returns (matched_name, similarity_score) or (None, 0.0).
        """
        best_name = None
        best_sim = 0.0
        for reg in registered_faces:
            sim = self.cosine_similarity(embedding, reg["embedding"])
            if sim > best_sim:
                best_sim = sim
                best_name = reg["name"]
        if best_sim >= FACE_MATCH_THRESHOLD:
            return best_name, best_sim
        return None, best_sim

    # ── Batch processing on key frames ──────────────────────

    def process_key_frames(
        self,
        frame_paths: list[str],
        registered_faces: list[dict],
        chunk_start_ts: float = 0.0,
        chunk_end_ts: float = 0.0,
    ) -> list[dict]:
        """Run face recognition on a set of key frame images.

        Returns list of per-detection dicts:
            [{"frame_path": str, "frame_ts": float, "face_name": str|None,
              "confidence": float, "det_score": float}, ...]

        Only registered-face-matched detections are returned (unknown faces skipped).
        frame_ts is estimated linearly across the chunk duration.
        """
        if not frame_paths or not registered_faces:
            return []

        self.load_model()
        detections = []
        n_frames = len(frame_paths)
        duration = chunk_end_ts - chunk_start_ts if chunk_end_ts > chunk_start_ts else 0

        for i, fp in enumerate(frame_paths):
            # Estimate timestamp for this frame
            if duration > 0 and n_frames > 1:
                frame_ts = chunk_start_ts + (duration * i / (n_frames - 1))
            else:
                frame_ts = chunk_start_ts

            faces = self.get_faces(fp)
            for face in faces:
                name, sim = self.match_face(face["embedding"], registered_faces)
                if name is not None:
                    detections.append({
                        "frame_path": fp,
                        "frame_ts": round(frame_ts, 1),
                        "face_name": name,
                        "confidence": round(sim, 3),
                        "det_score": round(face["det_score"], 3),
                    })

        return detections

    # ── Aggregation / deduplication ──────────────────────────

    @staticmethod
    def aggregate_detections(detections: list[dict]) -> str:
        """Collapse per-frame detections into compressed English text.

        Input:  [{"frame_ts": 12.5, "face_name": "John Doe", ...}, ...]
        Output: "Authorized person 'John Doe' detected continuously between 00:12 and 00:16."

        Returns empty string if no detections.
        """
        if not detections:
            return ""

        def _fmt_ts(t: float) -> str:
            m = int(t) // 60
            s = int(t) % 60
            return f"{m:02d}:{s:02d}"

        # Group consecutive detections by name
        # Sort by frame_ts first
        sorted_dets = sorted(detections, key=lambda d: d["frame_ts"])

        # Build contiguous ranges per person
        person_ranges: dict[str, list[tuple[float, float]]] = defaultdict(list)

        for det in sorted_dets:
            name = det["face_name"]
            ts = det["frame_ts"]
            if person_ranges[name]:
                last_start, last_end = person_ranges[name][-1]
                # If this detection is within 15 seconds of the last, extend the range
                if ts - last_end <= 15.0:
                    person_ranges[name][-1] = (last_start, ts)
                else:
                    person_ranges[name].append((ts, ts))
            else:
                person_ranges[name].append((ts, ts))

        # Build compressed sentences
        lines = []
        lines.append("Face Recognition System Report:")
        for name, ranges in sorted(person_ranges.items()):
            for start, end in ranges:
                if abs(end - start) < 1.0:
                    lines.append(
                        f"  - Registered person '{name}' detected at timestamp {_fmt_ts(start)}."
                    )
                else:
                    lines.append(
                        f"  - Registered person '{name}' detected continuously "
                        f"between timestamps {_fmt_ts(start)} and {_fmt_ts(end)}."
                    )

        return "\n".join(lines)


# Module-level singleton
face_engine = FaceRecognitionEngine()
