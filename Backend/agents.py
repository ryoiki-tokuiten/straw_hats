"""
DSSA Agents — AI agents for Narrative Builder and Reasoner.

Supports both Gemini (full function-calling loop) and local GGUF models
(tool-less mode with frame-based vision). Provider selected via AI_PROVIDER env.
"""
import os
import json
import base64
import asyncio
import subprocess

from config import (
    GENERATION_MODEL, MAX_TOOL_CALLS, FRAMES_DIR, AI_PROVIDER
)
from ai_provider import get_provider

# Lazily import Gemini types only when Gemini is active
_gemini_types = None
def _get_gemini_types():
    global _gemini_types
    if _gemini_types is None:
        from google.genai import types
        _gemini_types = types
    return _gemini_types

provider = get_provider()

# Gemini-specific helpers (only used when provider.supports_function_calling)
def _sync_generate(model, contents, config):
    """Synchronous wrapper for Gemini generate_content."""
    return provider.client.models.generate_content(model=model, contents=contents, config=config)


def _even_spacing_fallback(duration: float) -> list[dict]:
    """4 evenly-spaced timestamp ranges as fallback."""
    step = duration / 4
    return [{"start": i * step, "end": min((i * step) + 8, duration)} for i in range(4)]


def get_key_timestamps(uploaded_file, start_ts: float, end_ts: float) -> list[dict]:
    """Identify key timestamp ranges from a video chunk.

    When using Gemini: sends the uploaded video file to ask for key moments.
    When using local model: falls back to even spacing (can't send video).

    Returns a list of dicts like:
      [{"start": 30.0, "end": 35.0}, {"start": 80.0, "end": 95.0}, ...]
    These are timestamps *relative to the chunk* (0-based).
    """
    duration = end_ts - start_ts

    # Local model cannot process video — use even spacing
    if not provider.supports_video_upload:
        print("[KeyTimestamps] Local provider — using even spacing")
        return _even_spacing_fallback(duration)

    # Gemini path
    types = _get_gemini_types()
    prompt = f"""You are a surveillance video analyzer. This is a {duration:.0f}-second video clip from a security camera feed (covering {start_ts:.0f}s to {end_ts:.0f}s of the full recording).

Identify the KEY MOMENTS — the most important timestamp ranges where notable activity, movement changes, or relevant events occur. Select 3-6 non-overlapping ranges.

Output ONLY valid JSON — an array of objects with "start" and "end" keys (in seconds, relative to this clip starting at 0):

Example output:
[{{"start": 5.0, "end": 12.0}}, {{"start": 30.0, "end": 38.0}}, {{"start": 55.0, "end": 65.0}}]

Rules:
- Timestamps are relative to THIS clip (0 to {duration:.0f})
- Each range should be 3-15 seconds long
- Output 3-6 ranges, ordered chronologically
- Output ONLY the JSON array, no markdown, no explanation"""

    parts = []
    if uploaded_file:
        parts.append(types.Part(file_data=types.FileData(
            file_uri=uploaded_file.uri,
            mime_type=uploaded_file.mime_type,
        )))
    parts.append(types.Part(text=prompt))

    config = types.GenerateContentConfig(
        temperature=0.1,
    )

    try:
        response = provider.client.models.generate_content(
            model=GENERATION_MODEL,
            contents=[types.Content(role="user", parts=parts)],
            config=config,
        )
        text = response.text.strip() if response.text else ""
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        parsed = json.loads(text)
        if isinstance(parsed, list) and len(parsed) > 0:
            validated = []
            for item in parsed[:6]:
                s = max(0.0, float(item.get("start", 0)))
                e = min(duration, float(item.get("end", duration)))
                if e > s and (e - s) >= 1.0:
                    validated.append({"start": s, "end": e})
            if validated:
                print(f"[KeyTimestamps] Gemini returned {len(validated)} key ranges")
                return validated
    except Exception as e:
        print(f"[KeyTimestamps] Gemini extraction failed: {e}")

    print("[KeyTimestamps] Falling back to even spacing")
    return _even_spacing_fallback(duration)


# ════════════════════════════════════════════════════════════
#  TOOL IMPLEMENTATIONS (executed locally when model calls them)
# ════════════════════════════════════════════════════════════

def _extract_frames_for_range(video_path: str, start_ts: float, end_ts: float, chunk_index: int, call_id: str) -> list[str]:
    """Use ffmpeg to extract key frames from a timestamp range. Returns list of image file paths."""
    out_dir = os.path.join(FRAMES_DIR, f"chunk_{chunk_index}_{call_id}")
    os.makedirs(out_dir, exist_ok=True)

    duration = end_ts - start_ts
    # Extract ~5 evenly spaced frames from the range
    fps_val = 5.0 / max(duration, 1.0)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_ts),
        "-t", str(duration),
        "-i", video_path,
        "-vf", f"fps={fps_val:.4f}",
        "-frames:v", "5",
        "-q:v", "2",
        os.path.join(out_dir, "frame_%03d.jpg"),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=30, check=True)
    except Exception as e:
        print(f"[ffmpeg] Frame extraction warning: {e}")

    frames = sorted([
        os.path.join(out_dir, f)
        for f in os.listdir(out_dir)
        if f.endswith(".jpg")
    ])
    return frames


def _load_frames_as_bytes(frame_paths: list[str]) -> list[bytes]:
    """Load frame images and return as raw bytes (provider-agnostic)."""
    result = []
    for fp in frame_paths:
        if not os.path.exists(fp):
            continue
        with open(fp, "rb") as f:
            result.append(f.read())
    return result


def _load_frames_as_parts(frame_paths: list[str]) -> list:
    """Load frame images and return as Gemini Part objects.
    Only used in Gemini function-calling paths."""
    types = _get_gemini_types()
    parts = []
    for fp in frame_paths:
        if not os.path.exists(fp):
            continue
        with open(fp, "rb") as f:
            data = f.read()
        parts.append(types.Part(inline_data=types.Blob(data=data, mime_type="image/jpeg")))
    return parts


# ════════════════════════════════════════════════════════════
#  TOOL DECLARATIONS
# ════════════════════════════════════════════════════════════

VIEW_KEY_CLIP_DECL = {
    "name": "view_key_clip",
    "description": "View key frame images from a specific timestamp range within the current video chunk. Returns the extracted frames for visual analysis. Use this to examine specific moments in the video segment.",
    "parameters": {
        "type": "object",
        "properties": {
            "start_seconds": {
                "type": "number",
                "description": "Start time in seconds (relative to video start) for the clip range to view."
            },
            "end_seconds": {
                "type": "number",
                "description": "End time in seconds (relative to video start) for the clip range to view."
            },
        },
        "required": ["start_seconds", "end_seconds"],
    },
}

WRITE_ATOMIC_RECONSTRUCTION_DECL = {
    "name": "write_atomic_reconstruction",
    "description": "Write the final atomic reconstruction for this video chunk. This is a 4-5 sentence narrative that provides the shortest, most complete description of what happened. Anyone reading your previous atomic reconstructions plus this one must be able to fully visualize the scene. Call this when you have finished your analysis.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The 4-5 sentence atomic reconstruction narrative. Be specific about subjects, movements, positions, interactions, objects, and environmental changes."
            },
        },
        "required": ["text"],
    },
}

VIEW_FEED_TIMESTAMP_DECL = {
    "name": "view_feed_timestamp",
    "description": "View uncompressed video frames from a specific timestamp range for detailed analysis. Returns extracted frames from the full-quality video feed. Use this to examine suspicious moments closely.",
    "parameters": {
        "type": "object",
        "properties": {
            "start_seconds": {
                "type": "number",
                "description": "Start time in seconds (relative to video start) for the feed range to view."
            },
            "end_seconds": {
                "type": "number",
                "description": "End time in seconds (relative to video start) for the feed range to view."
            },
        },
        "required": ["start_seconds", "end_seconds"],
    },
}

RISK_SCORE_DECL = {
    "name": "risk_score",
    "description": "Submit the final risk assessment for this video chunk. Call this when you have finished analyzing the video and are ready to output your security assessment.",
    "parameters": {
        "type": "object",
        "properties": {
            "score": {
                "type": "number",
                "description": "Risk score from 0.0 (no risk) to 1.0 (maximum threat). Scores above 0.7 trigger an alert."
            },
            "classification": {
                "type": "string",
                "description": "Threat classification, e.g. 'Loitering', 'Unauthorized Access', 'Suspicious Object', 'Aggressive Behavior', 'Benign Activity', 'Normal Transit'."
            },
            "reasoning": {
                "type": "string",
                "description": "Detailed reasoning for the risk score, referencing specific observations from the video analysis."
            },
            "action_required": {
                "type": "boolean",
                "description": "Whether immediate security action is required."
            },
        },
        "required": ["score", "classification", "reasoning", "action_required"],
    },
}


# ════════════════════════════════════════════════════════════
#  SYSTEM PROMPTS
# ════════════════════════════════════════════════════════════

def _narrative_builder_system_prompt(start_ts: float, end_ts: float, history: list[dict], tool_less: bool = False, danger_zone_config: dict | None = None) -> str:
    danger_zone_text = ""
    if danger_zone_config and danger_zone_config.get("description"):
        danger_zone_text = f"""[CRITICAL SYSTEM DIRECTIVE: DANGER ZONE CONTEXT]
The operator has defined the following danger zone / dangerous behavior criteria:
\"\"\"
{danger_zone_config['description']}
\"\"\"
Any activity matching this criteria MUST be explicitly noted in your reconstruction. Treat any match as highly significant.
[END DANGER ZONE CONTEXT]

"""

    history_text = ""
    if history:
        for h in history:
            history_text += f"[{h['start_ts']:.0f}s – {h['end_ts']:.0f}s]: {h['text']}\n"
    else:
        history_text = "(No previous reconstructions — this is the first segment.)\n"

    tool_instructions = ""
    if not tool_less:
        tool_instructions = """
You have the following tools available:
- view_key_clip(start_seconds, end_seconds): View key frame images from a timestamp range. You can call this up to 5 times to examine different moments.
- write_atomic_reconstruction(text): Write your final 4-5 sentence atomic reconstruction. This MUST be your last action.

WORKFLOW:
1. Use view_key_clip to examine key moments in the video segment.
2. After sufficient analysis, call write_atomic_reconstruction with your narrative.
"""
    else:
        tool_instructions = """
IMPORTANT: You are in DIRECT OUTPUT mode. You do NOT have access to any tools.
Based on the video context and key frames provided below, directly output your atomic reconstruction.
Your response must be exactly 4-5 sentences. Output ONLY the reconstruction text, nothing else.
"""

    return f"""{danger_zone_text}You are a surveillance scene narrator for a security monitoring system. Your job is to create an "atomic reconstruction" — the shortest, most complete description of what happened in this video segment.

CRITICAL RULE: Anyone reading your previous atomic reconstructions + this new one must be able to fully visualize and recreate the entire scene chronologically. You are building a continuous narrative.

Current video segment timestamp range: {start_ts:.0f}s to {end_ts:.0f}s

PREVIOUS ATOMIC RECONSTRUCTIONS (chronological scene history):
{history_text}
{tool_instructions}
GUIDELINES:
- Be specific about: number of subjects, their movements, positions, interactions, objects carried, clothing if notable, environmental conditions.
- Use present tense for the current segment.
- Reference spatial relationships (left/right, near/far, entering/exiting).
- Note anything that changed compared to previous reconstructions.
- Keep it to exactly 4-5 sentences. Every word must carry information.
"""


def _reasoner_system_prompt(start_ts: float, end_ts: float, history: list[dict], tool_less: bool = False, danger_zone_config: dict | None = None) -> str:
    danger_zone_text = ""
    if danger_zone_config and danger_zone_config.get("description"):
        danger_zone_text = f"""[CRITICAL SYSTEM DIRECTIVE: DANGER ZONE CONTEXT]
The operator has defined the following danger zone / dangerous behavior criteria:
\"\"\"
{danger_zone_config['description']}
\"\"\"
Any activity matching this criteria MUST be classified as HIGH RISK (score >= 0.8) and marked as action_required=true. This takes absolute priority over default scoring.
[END DANGER ZONE CONTEXT]

"""

    history_text = ""
    if history:
        for h in history:
            history_text += f"[{h['start_ts']:.0f}s – {h['end_ts']:.0f}s]: {h['text']}\n"
    else:
        history_text = "(No previous reconstructions available.)\n"

    tool_instructions = ""
    if not tool_less:
        tool_instructions = """
You have the following tools available:
- view_feed_timestamp(start_seconds, end_seconds): View uncompressed video frames from a specific range. You can call this up to 5 times.
- risk_score(score, classification, reasoning, action_required): Submit your final risk assessment. This MUST be your last action.

WORKFLOW:
1. Review the video feed and previous scene history.
2. Use view_feed_timestamp to closely examine any suspicious moments.
3. Call risk_score with your final assessment.
"""
    else:
        tool_instructions = """
IMPORTANT: You are in DIRECT OUTPUT mode. You do NOT have access to any tools.
Based on the video context, scene history, and frames provided, directly output your risk assessment.
Your response must be valid JSON with this exact format:
{"score": <0.0-1.0>, "classification": "<category>", "reasoning": "<explanation>", "action_required": <true/false>}
Output ONLY the JSON, nothing else.
"""

    return f"""{danger_zone_text}You are a security surveillance analyst for a real-time monitoring system. Analyze the current 2-minute video segment for potential threats, suspicious behavior, or security concerns.

Current video segment timestamp range: {start_ts:.0f}s to {end_ts:.0f}s

SCENE HISTORY (previous atomic reconstructions):
{history_text}
{tool_instructions}
THREAT ASSESSMENT CRITERIA:
- Loitering: Subject remaining stationary in non-resting areas for extended periods
- Unauthorized Access: Attempts to enter restricted zones, tampering with locks/gates
- Suspicious Objects: Unattended bags, packages left near entry points
- Aggressive Behavior: Running, sudden movements, physical confrontation
- Perimeter Violations: Climbing fences, entering through non-entry points
- Pattern Anomalies: Behavior that deviates significantly from the scene history

SCORING GUIDE:
- 0.0-0.2: Normal activity, routine movement
- 0.2-0.4: Mildly unusual but likely benign
- 0.4-0.6: Moderately suspicious, warrants continued monitoring
- 0.6-0.8: Suspicious, recommend review
- 0.8-1.0: High threat, immediate action recommended

Be precise and justify your score with specific observations.
"""


# ════════════════════════════════════════════════════════════
#  AGENT RUNNERS
# ════════════════════════════════════════════════════════════

async def run_narrative_builder(
    video_path: str,
    chunk_index: int,
    start_ts: float,
    end_ts: float,
    history: list[dict],
    key_frame_paths: list[str] | None = None,
    tool_less: bool = False,
    on_event=None,       # async callback(event_type, data) for real-time UI
    face_report: str | None = None,
    danger_zone_config: dict | None = None,
) -> dict:
    """
    Run the Narrative Builder agent.
    Returns: {"text": str, "tool_calls": list[dict]}
    """
    # Force tool-less when provider doesn't support function calling
    if not provider.supports_function_calling:
        tool_less = True

    system_prompt = _narrative_builder_system_prompt(start_ts, end_ts, history, tool_less, danger_zone_config)

    # ── LOCAL MODEL PATH (tool-less only) ──
    if not provider.supports_function_calling:
        if on_event:
            await on_event("agent_status", {"agent": "narrative_builder", "status": "running_local", "chunk": chunk_index})

        # Collect all image bytes
        all_images: list[bytes] = []
        if danger_zone_config and danger_zone_config.get("image_paths"):
            all_images.extend(_load_frames_as_bytes(danger_zone_config["image_paths"]))
        if key_frame_paths:
            all_images.extend(_load_frames_as_bytes(key_frame_paths))

        prompt_text = f"These are key frames from the video segment ({start_ts:.0f}s to {end_ts:.0f}s). Analyze this segment and create an atomic reconstruction."
        if face_report:
            prompt_text += f"\n\nDeterministic Face Recognition Report:\n{face_report}"

        text = await asyncio.to_thread(
            provider.generate, system_prompt, prompt_text, all_images,
            0.3, 1024,
        )
        text = text.strip() or "No reconstruction generated."
        if on_event:
            await on_event("reconstruction_complete", {"chunk": chunk_index, "text": text, "tool_less": True})
        return {"text": text, "tool_calls": []}

    # ── GEMINI PATH ──
    types = _get_gemini_types()

    # Build initial user content — danger zone images first, then key frames
    initial_parts = []

    if danger_zone_config and danger_zone_config.get("image_paths"):
        dz_image_parts = _load_frames_as_parts(danger_zone_config["image_paths"])
        if dz_image_parts:
            initial_parts.extend(dz_image_parts)
            initial_parts.append(types.Part(text="[DANGER ZONE REFERENCE IMAGES] The images above show the operator-defined danger zone or dangerous behavior examples. Use these as reference when analyzing the video segment."))

    if key_frame_paths:
        initial_parts.extend(_load_frames_as_parts(key_frame_paths))
        prompt_text = f"These are key frames from the video segment ({start_ts:.0f}s to {end_ts:.0f}s). Analyze this segment and create an atomic reconstruction."
    else:
        prompt_text = f"Analyze the video segment from {start_ts:.0f}s to {end_ts:.0f}s and create an atomic reconstruction."

    if face_report:
        prompt_text += f"\n\nDeterministic Face Recognition Report:\n{face_report}"

    initial_parts.append(types.Part(text=prompt_text))
    contents = [types.Content(role="user", parts=initial_parts)]

    # Tool-less Gemini mode (race condition catch-up)
    if tool_less:
        if on_event:
            await on_event("agent_status", {"agent": "narrative_builder", "status": "running_tool_less", "chunk": chunk_index})

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3,
        )
        response = await asyncio.to_thread(_sync_generate, GENERATION_MODEL, contents, config)
        text = response.text.strip() if response.text else "No reconstruction generated."
        if on_event:
            await on_event("reconstruction_complete", {"chunk": chunk_index, "text": text, "tool_less": True})
        return {"text": text, "tool_calls": []}

    # Normal Gemini mode with tools
    tools = types.Tool(function_declarations=[VIEW_KEY_CLIP_DECL, WRITE_ATOMIC_RECONSTRUCTION_DECL])
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[tools],
        temperature=0.3,
    )

    tool_call_log = []
    result_text = None

    if on_event:
        await on_event("agent_status", {"agent": "narrative_builder", "status": "started", "chunk": chunk_index})

    for iteration in range(MAX_TOOL_CALLS + 1):
        print(f"[NB] Chunk {chunk_index} iteration {iteration} — calling Gemini...")
        response = await asyncio.to_thread(_sync_generate, GENERATION_MODEL, contents, config)
        print(f"[NB] Chunk {chunk_index} iteration {iteration} — response received")

        candidate = response.candidates[0]
        has_function_call = False

        for part in candidate.content.parts:
            if part.function_call:
                has_function_call = True
                fc = part.function_call
                tool_call_log.append({"name": fc.name, "args": dict(fc.args) if fc.args else {}})

                if on_event:
                    await on_event("tool_call", {
                        "agent": "narrative_builder",
                        "tool": fc.name,
                        "args": dict(fc.args) if fc.args else {},
                        "chunk": chunk_index,
                        "iteration": iteration,
                    })

                if fc.name == "write_atomic_reconstruction":
                    result_text = fc.args.get("text", "")
                    if on_event:
                        await on_event("reconstruction_complete", {"chunk": chunk_index, "text": result_text, "tool_less": False})
                    return {"text": result_text, "tool_calls": tool_call_log}

                elif fc.name == "view_key_clip":
                    s = float(fc.args.get("start_seconds", start_ts))
                    e = float(fc.args.get("end_seconds", end_ts))
                    frames = _extract_frames_for_range(video_path, s, e, chunk_index, f"nb_{iteration}")
                    frame_parts = _load_frames_as_parts(frames)

                    contents.append(candidate.content)
                    contents.append(types.Content(role="user", parts=[
                        types.Part.from_function_response(
                            name="view_key_clip",
                            response={"result": f"Extracted {len(frames)} frames from {s:.0f}s to {e:.0f}s.", "frame_count": len(frames)},
                        )
                    ]))
                    if frame_parts:
                        frame_parts.append(types.Part(text=f"Here are the extracted frames from {s:.0f}s to {e:.0f}s."))
                        contents.append(types.Content(role="user", parts=frame_parts))

        if not has_function_call:
            text = response.text if response.text else ""
            if text and not result_text:
                result_text = text.strip()
            break

    if result_text is None:
        result_text = "Unable to generate reconstruction."

    if on_event:
        await on_event("reconstruction_complete", {"chunk": chunk_index, "text": result_text, "tool_less": False})

    return {"text": result_text, "tool_calls": tool_call_log}


async def run_reasoner(
    video_path: str,
    chunk_index: int,
    start_ts: float,
    end_ts: float,
    history: list[dict],
    uploaded_file=None,       # Pre-uploaded Gemini file reference
    key_frame_paths: list[str] | None = None,
    tool_less: bool = False,
    on_event=None,
    face_report: str | None = None,
    danger_zone_config: dict | None = None,
) -> dict:
    """
    Run the Reasoner agent.
    Returns: {"score": float, "classification": str, "reasoning": str, "action_required": bool, "tool_calls": list}
    """
    # Force tool-less when provider doesn't support function calling
    if not provider.supports_function_calling:
        tool_less = True

    system_prompt = _reasoner_system_prompt(start_ts, end_ts, history, tool_less, danger_zone_config)
    default_result = {"score": 0.1, "classification": "Normal Activity", "reasoning": "Insufficient data for assessment.", "action_required": False, "tool_calls": []}

    # ── LOCAL MODEL PATH (tool-less only) ──
    if not provider.supports_function_calling:
        if on_event:
            await on_event("agent_status", {"agent": "reasoner", "status": "running_local", "chunk": chunk_index})

        all_images: list[bytes] = []
        if danger_zone_config and danger_zone_config.get("image_paths"):
            all_images.extend(_load_frames_as_bytes(danger_zone_config["image_paths"]))
        if key_frame_paths:
            all_images.extend(_load_frames_as_bytes(key_frame_paths))

        prompt_text = f"These are frames from the video feed ({start_ts:.0f}s to {end_ts:.0f}s). Analyze for security threats."
        if face_report:
            prompt_text += f"\n\nDeterministic Face Recognition Report:\n{face_report}"

        text = await asyncio.to_thread(
            provider.generate, system_prompt, prompt_text, all_images,
            0.2, 1024,
        )
        text = text.strip()

        try:
            # Try to extract JSON from potentially markdown-wrapped response
            json_text = text
            if json_text.startswith("```"):
                json_text = json_text.split("\n", 1)[-1]
                if json_text.endswith("```"):
                    json_text = json_text[:-3]
                json_text = json_text.strip()
            parsed = json.loads(json_text)
            result = {
                "score": float(parsed.get("score", 0.1)),
                "classification": parsed.get("classification", "Unknown"),
                "reasoning": parsed.get("reasoning", ""),
                "action_required": bool(parsed.get("action_required", False)),
                "tool_calls": [],
            }
        except (json.JSONDecodeError, AttributeError):
            result = {**default_result, "reasoning": text}

        if on_event:
            await on_event("risk_complete", {"chunk": chunk_index, "result": result, "tool_less": True})
        return result

    # ── GEMINI PATH ──
    types = _get_gemini_types()

    # Build initial content — danger zone images first, then video/frames
    initial_parts = []

    if danger_zone_config and danger_zone_config.get("image_paths"):
        dz_image_parts = _load_frames_as_parts(danger_zone_config["image_paths"])
        if dz_image_parts:
            initial_parts.extend(dz_image_parts)
            initial_parts.append(types.Part(text="[DANGER ZONE REFERENCE IMAGES] The images above show the operator-defined danger zone or dangerous behavior examples. Any activity matching these should be classified as HIGH RISK."))

    if uploaded_file:
        initial_parts.append(types.Part(file_data=types.FileData(
            file_uri=uploaded_file.uri,
            mime_type=uploaded_file.mime_type,
        )))
        prompt_text = f"This is the full uncompressed 2-minute video feed from {start_ts:.0f}s to {end_ts:.0f}s. Analyze it for security threats."
    elif key_frame_paths:
        initial_parts.extend(_load_frames_as_parts(key_frame_paths))
        prompt_text = f"These are frames from the video feed ({start_ts:.0f}s to {end_ts:.0f}s). Analyze for security threats."
    else:
        prompt_text = f"Analyze the video segment from {start_ts:.0f}s to {end_ts:.0f}s for security threats."

    if face_report:
        prompt_text += f"\n\nDeterministic Face Recognition Report:\n{face_report}"

    initial_parts.append(types.Part(text=prompt_text))
    contents = [types.Content(role="user", parts=initial_parts)]

    # Tool-less Gemini mode
    if tool_less:
        if on_event:
            await on_event("agent_status", {"agent": "reasoner", "status": "running_tool_less", "chunk": chunk_index})

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.2,
        )
        response = await asyncio.to_thread(_sync_generate, GENERATION_MODEL, contents, config)
        text = response.text.strip() if response.text else ""
        try:
            parsed = json.loads(text)
            result = {
                "score": float(parsed.get("score", 0.1)),
                "classification": parsed.get("classification", "Unknown"),
                "reasoning": parsed.get("reasoning", ""),
                "action_required": bool(parsed.get("action_required", False)),
                "tool_calls": [],
            }
        except json.JSONDecodeError:
            result = {**default_result, "reasoning": text}

        if on_event:
            await on_event("risk_complete", {"chunk": chunk_index, "result": result, "tool_less": True})
        return result

    # Normal Gemini mode with tools
    tools = types.Tool(function_declarations=[VIEW_FEED_TIMESTAMP_DECL, RISK_SCORE_DECL])
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[tools],
        temperature=0.2,
    )

    tool_call_log = []

    if on_event:
        await on_event("agent_status", {"agent": "reasoner", "status": "started", "chunk": chunk_index})

    for iteration in range(MAX_TOOL_CALLS + 1):
        print(f"[RS] Chunk {chunk_index} iteration {iteration} — calling Gemini...")
        response = await asyncio.to_thread(_sync_generate, GENERATION_MODEL, contents, config)
        print(f"[RS] Chunk {chunk_index} iteration {iteration} — response received")

        candidate = response.candidates[0]
        has_function_call = False

        for part in candidate.content.parts:
            if part.function_call:
                has_function_call = True
                fc = part.function_call
                tool_call_log.append({"name": fc.name, "args": dict(fc.args) if fc.args else {}})

                if on_event:
                    await on_event("tool_call", {
                        "agent": "reasoner",
                        "tool": fc.name,
                        "args": dict(fc.args) if fc.args else {},
                        "chunk": chunk_index,
                        "iteration": iteration,
                    })

                if fc.name == "risk_score":
                    result = {
                        "score": float(fc.args.get("score", 0.1)),
                        "classification": str(fc.args.get("classification", "Unknown")),
                        "reasoning": str(fc.args.get("reasoning", "")),
                        "action_required": bool(fc.args.get("action_required", False)),
                        "tool_calls": tool_call_log,
                    }
                    if on_event:
                        await on_event("risk_complete", {"chunk": chunk_index, "result": result, "tool_less": False})
                    return result

                elif fc.name == "view_feed_timestamp":
                    s = float(fc.args.get("start_seconds", start_ts))
                    e = float(fc.args.get("end_seconds", end_ts))
                    frames = _extract_frames_for_range(video_path, s, e, chunk_index, f"rs_{iteration}")
                    frame_parts = _load_frames_as_parts(frames)

                    contents.append(candidate.content)
                    contents.append(types.Content(role="user", parts=[
                        types.Part.from_function_response(
                            name="view_feed_timestamp",
                            response={"result": f"Extracted {len(frames)} frames from {s:.0f}s to {e:.0f}s.", "frame_count": len(frames)},
                        )
                    ]))
                    if frame_parts:
                        frame_parts.append(types.Part(text=f"Here are the extracted frames from {s:.0f}s to {e:.0f}s."))
                        contents.append(types.Content(role="user", parts=frame_parts))

        if not has_function_call:
            text = response.text if response.text else ""
            try:
                parsed = json.loads(text)
                result = {
                    "score": float(parsed.get("score", 0.1)),
                    "classification": parsed.get("classification", "Unknown"),
                    "reasoning": parsed.get("reasoning", text),
                    "action_required": bool(parsed.get("action_required", False)),
                    "tool_calls": tool_call_log,
                }
            except (json.JSONDecodeError, AttributeError):
                result = {**default_result, "reasoning": text, "tool_calls": tool_call_log}
            if on_event:
                await on_event("risk_complete", {"chunk": chunk_index, "result": result, "tool_less": False})
            return result

    return {**default_result, "tool_calls": tool_call_log}


# ════════════════════════════════════════════════════════════
#  EMBEDDINGS
# ════════════════════════════════════════════════════════════

def generate_embedding(text: str) -> list[float]:
    """Generate embedding for text using the configured provider."""
    return provider.generate_embedding(text)


def generate_embedding_for_search(query: str) -> list[float]:
    """Generate embedding for a search query."""
    return generate_embedding(query)
