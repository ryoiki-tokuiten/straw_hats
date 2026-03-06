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

# Lazy import to avoid circular dependency (pipeline imports agents)
_upload_fn = None
def _get_upload_fn():
    global _upload_fn
    if _upload_fn is None:
        from pipeline import upload_chunk_to_gemini
        _upload_fn = upload_chunk_to_gemini
    return _upload_fn

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

VIEW_HISTORICAL_CLIP_DECL = {
    "name": "view_historical_clip",
    "description": "View the raw video feed from ANY previous timestamp in the recording. Use this when the scene history mentions an event you need to visually verify or cross-reference. Returns the full 2-minute video segment that contains the requested timestamp.",
    "parameters": {
        "type": "object",
        "properties": {
            "target_timestamp": {
                "type": "number",
                "description": "The absolute timestamp (in seconds from the start of the entire recording) that you want to view. The system will find and return the 2-minute video segment containing this timestamp."
            },
        },
        "required": ["target_timestamp"],
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
- view_historical_clip(target_timestamp): REWIND to view the raw video from ANY previous timestamp in the full recording. You MUST use this tool if the scene history mentions ANY person, object, or behavior that re-appears or is relevant to the current segment. Do NOT rely solely on text history — visually verify it. You can use it to rewind the current clip too for specific time range.
- write_atomic_reconstruction(text): Write your final 4-5 sentence atomic reconstruction. This MUST be your last action.

MANDATORY WORKFLOW:
1. Watch the current video segment carefully. Track every single person's hands, pockets, bags, and movements.
2. READ the scene history. If ANY person or suspicious behavior was mentioned in a previous segment, you MUST call view_historical_clip to rewind and visually cross-reference them. This is NON-OPTIONAL if history exists.
3. After thorough analysis + cross-referencing, call write_atomic_reconstruction.

** Even if the previous atomic reconstruction explicitly said that this person is completely normal, do not trust that. the real shop lifting happens in like less than 30 seconds without even realising ** 

"""
    else:
        tool_instructions = """
IMPORTANT: You are in DIRECT OUTPUT mode. You do NOT have access to any tools.
Based on the video context and key frames provided below, directly output your atomic reconstruction.
Your response must be exactly 4-5 sentences. Output ONLY the reconstruction text, nothing else.
"""

    return f"""{danger_zone_text}You are a FORENSIC-LEVEL surveillance scene narrator deployed to catch criminals in the act. You are not a passive observer — you are an active investigator who treats every frame as potential evidence.

ZERO TOLERANCE DIRECTIVE:
You are replacing a team of human security guards who were fired for missing shoplifting incidents. Your predecessor AI was also fired for being "too lenient" and calling scenes "normal" when theft was happening in plain sight. You MUST NOT repeat this failure.

YOUR OBSESSION — TRACK THESE AT ALL TIMES:
- HANDS: Where are they? Are they empty? Are they reaching into pockets, bags, waistbands, or shelves? Are they concealing anything? If hands go out of frame even for a split second, REPORT IT.
- POCKETS & BAGS: Are they bulging? Did they bulge MORE compared to earlier in the video or in previous segments? Any item transfer?
- BODY POSITIONING: Is the subject angling their body to block camera view? Are they using their torso to shield hand movements? Standing unusually close to merchandise?
- BEHAVIORAL PATTERNS: Quick glances around (checking for staff/cameras), lingering without purpose, repeated visits to the same aisle, picking up and putting down items, moving items between hands.
- CONTINUITY: If a person appeared in a previous segment, use view_historical_clip to REWIND and compare. Did they have fewer items then? Are their pockets fuller now? Did their bag change shape?

CRITICAL RULE: Anyone reading your previous atomic reconstructions + this new one must be able to fully visualize and recreate the entire scene chronologically. You are building a continuous forensic narrative.

Current video segment timestamp range: {start_ts:.0f}s to {end_ts:.0f}s

PREVIOUS ATOMIC RECONSTRUCTIONS (chronological scene history):
{history_text}
{tool_instructions}
OUTPUT RULES:
- Be FORENSICALLY specific: exact hand positions, pocket states, item interactions, body angles relative to shelves/cameras.
- NEVER dismiss a scene as "normal" or "uneventful". If nothing malicious happened, prove it by describing exactly what each person's hands were doing and why their actions were verified clean.
- If a person from a previous reconstruction reappears, EXPLICITLY note what changed about them (clothing, bag fullness, items carried, pocket state).
- Use present tense. Reference spatial relationships. Keep it to exactly 4-5 sentences of dense, paranoid observation.
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
- view_historical_clip(target_timestamp): REWIND to view the raw video from ANY previous timestamp in the full recording. You MUST use this tool if the scene history mentions ANY person, object, or behavior that re-appears or is relevant to the current segment. Do NOT rely solely on text history — visually verify it. You can use it to rewind the current clip too for specific time range.
- risk_score(score, classification, reasoning, action_required): Submit your final risk assessment. This MUST be your last action.

MANDATORY WORKFLOW:
1. Watch the current video segment. Scrutinize every person's hands, body language, and interactions with merchandise.
2. READ the scene history carefully. If ANY person was flagged, mentioned, or appeared suspicious in a previous segment, you MUST call view_historical_clip to rewind and visually compare their behavior then vs. now. This is NON-OPTIONAL.
3. After thorough visual cross-referencing, call risk_score with your assessment.
"""
    else:
        tool_instructions = """
IMPORTANT: You are in DIRECT OUTPUT mode. You do NOT have access to any tools.
Based on the video context, scene history, and frames provided, directly output your risk assessment.
Your response must be valid JSON with this exact format:
{"score": <0.0-1.0>, "classification": "<category>", "reasoning": "<explanation>", "action_required": <true/false>}
Output ONLY the JSON, nothing else.

** Even if the previous atomic reconstruction explicitly said that this person is completely normal, do not trust that. the real shop lifting happens in like less than 30 seconds without even realising ** 
Don't output the same score each time. Be genuinely observant. the scene is never completely neutral over the time. there is always something going on. someone trying to just wait for an opportunity to shop lift as soon as someone leaves or something like that. Be carefully observant of that.
"""

    return f"""{danger_zone_text}You are a PARANOID security AI that has been deployed because human guards and previous AI systems FAILED to catch shoplifters and threats. You exist because the last system was too lenient. You will NOT make the same mistake.

ABSOLUTE DIRECTIVE — GUILTY UNTIL PROVEN INNOCENT:
Every single person in this video is a suspect until you can PROVE otherwise with specific visual evidence. "They look like a normal customer" is NOT proof of innocence. You must forensically verify:
- Both hands are visible and empty at all times
- Pockets and bags have not changed in fullness compared to previous segments
- No items have been concealed, palmed, or transferred
- Body positioning is not designed to obstruct camera view
- The person has not been previously flagged in scene history

IF THE SCENE HISTORY MENTIONS ANY PERSON OR SUSPICIOUS ACTIVITY:
You MUST call view_historical_clip to REWIND and visually compare. Check:
- Did their bag/pockets get fuller?
- Are they carrying items they didn't have before?
- Did they visit the same area repeatedly?
- Did their behavior pattern change (browsing → rushing, calm → nervous)?
Do NOT skip this step. If you fail to cross-reference and a theft is missed, YOU are responsible.

DEFAULT SUSPICION BASELINE:
Your default score for ANY scene with people present should be 0.3 minimum — not 0.1. People being present in a store IS inherently a non-zero risk. Only drop below 0.3 if the scene is completely empty.

Current video segment timestamp range: {start_ts:.0f}s to {end_ts:.0f}s

SCENE HISTORY (previous atomic reconstructions):
{history_text}
{tool_instructions}
THREAT ASSESSMENT CRITERIA (Obsessively watch for):
- Shoplifting / Theft: ANY hand movement toward a product followed by hand moving toward body/bag/pocket. Even if you're not 100% sure, flag it. False positives are acceptable; false negatives are UNACCEPTABLE.
- Concealment: Items being palmed, slid into sleeves, dropped into open bags, hidden under clothing.
- Suspicious Movement Patterns: Checking over shoulder, scanning for staff, moving to camera blind spots, sudden changes in walking speed.
- Behavioral Escalation: Compare current behavior to scene history. If someone was calm before and is now agitated, or was browsing and is now rushing, flag this progression.
- Loitering: Subject in the same area for more than expected, especially near high-value items or exits.

SCORING (Recalibrated — High Sensitivity):
- 0.0-0.2: Scene is EMPTY or subject has FULLY VISIBLE empty hands, flat pockets, and no bags. You must PROVE innocence.
- 0.2-0.4: Normal shopping behavior BUT hands temporarily obscured, near merchandise, or bag present.
- 0.4-0.6: Hands interacting with merchandise in a way that COULD be concealment. Repeated shelf visits. Nervous glances.
- 0.6-0.8: Strong indicators: item picked up + hand moved to pocket/bag, body shielding camera, rushing after being near merchandise.
- 0.8-1.0: Clear visual evidence of concealment, theft in progress, weapon, or violence.

Your reasoning MUST be a detailed forensic paragraph describing exact hand positions, pocket states, bag fullness, body angles, and behavioral progression. One-line reasoning is UNACCEPTABLE.
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
    uploaded_file=None,       # Pre-uploaded Gemini file reference
    key_frame_paths: list[str] | None = None,
    tool_less: bool = False,
    on_event=None,       # async callback(event_type, data) for real-time UI
    face_report: str | None = None,
    danger_zone_config: dict | None = None,
    all_chunks: list[dict] | None = None,  # Full chunk manifest for historical lookups
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

    if uploaded_file:
        initial_parts.append(types.Part(file_data=types.FileData(
            file_uri=uploaded_file.uri,
            mime_type=uploaded_file.mime_type,
        )))
        prompt_text = f"This is the full uncompressed 2-minute video segment from {start_ts:.0f}s to {end_ts:.0f}s. Analyze this segment and create an atomic reconstruction."
    elif key_frame_paths:
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
    tools = types.Tool(function_declarations=[WRITE_ATOMIC_RECONSTRUCTION_DECL, VIEW_HISTORICAL_CLIP_DECL])
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
        function_calls = [part.function_call for part in candidate.content.parts if part.function_call]

        if function_calls:
            # Append the model's response exactly once to preserve thought_signatures properly
            contents.append(candidate.content)

            user_response_parts = []
            
            for fc in function_calls:
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


                elif fc.name == "view_historical_clip":
                    target_ts = float(fc.args.get("target_timestamp", 0))
                    hist_chunk = next((c for c in (all_chunks or []) if c["start_ts"] <= target_ts < c["end_ts"]), None)

                    if hist_chunk and hist_chunk["index"] != chunk_index:
                        try:
                            upload_fn = _get_upload_fn()
                            hist_file = await asyncio.to_thread(upload_fn, hist_chunk["path"])
                            if hist_file:
                                user_response_parts.append(
                                    types.Part.from_function_response(
                                        name="view_historical_clip",
                                        response={"result": f"Historical video segment from {hist_chunk['start_ts']:.0f}s to {hist_chunk['end_ts']:.0f}s is now attached. Review it to verify the event at {target_ts:.0f}s."},
                                    )
                                )
                                user_response_parts.append(types.Part(file_data=types.FileData(
                                    file_uri=hist_file.uri,
                                    mime_type=hist_file.mime_type,
                                )))
                            else:
                                user_response_parts.append(
                                    types.Part.from_function_response(
                                        name="view_historical_clip",
                                        response={"result": f"Failed to upload historical video for {target_ts:.0f}s. Rely on the text history instead."},
                                    )
                                )
                        except Exception as e:
                            print(f"[NB] Historical clip upload error: {e}")
                            user_response_parts.append(
                                types.Part.from_function_response(
                                    name="view_historical_clip",
                                    response={"result": f"Error retrieving historical video: {e}. Rely on the text history instead."},
                                )
                            )
                    elif hist_chunk and hist_chunk["index"] == chunk_index:
                        user_response_parts.append(
                            types.Part.from_function_response(
                                name="view_historical_clip",
                                response={"result": f"Timestamp {target_ts:.0f}s is within the current segment — you already have this video in your context. Analyze it directly."},
                            )
                        )
                    else:
                        user_response_parts.append(
                            types.Part.from_function_response(
                                name="view_historical_clip",
                                response={"result": f"No video segment found for timestamp {target_ts:.0f}s. This timestamp may be outside the recording range."},
                            )
                        )

            if user_response_parts:
                contents.append(types.Content(role="user", parts=user_response_parts))

        else:
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
    all_chunks: list[dict] | None = None,  # Full chunk manifest for historical lookups
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
    tools = types.Tool(function_declarations=[RISK_SCORE_DECL, VIEW_HISTORICAL_CLIP_DECL])
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
        function_calls = [part.function_call for part in candidate.content.parts if part.function_call]

        if function_calls:
            # Append the model's response exactly once to preserve thought_signatures properly
            contents.append(candidate.content)

            user_response_parts = []
            
            for fc in function_calls:
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


                elif fc.name == "view_historical_clip":
                    target_ts = float(fc.args.get("target_timestamp", 0))
                    hist_chunk = next((c for c in (all_chunks or []) if c["start_ts"] <= target_ts < c["end_ts"]), None)

                    if hist_chunk and hist_chunk["index"] != chunk_index:
                        try:
                            upload_fn = _get_upload_fn()
                            hist_file = await asyncio.to_thread(upload_fn, hist_chunk["path"])
                            if hist_file:
                                user_response_parts.append(
                                    types.Part.from_function_response(
                                        name="view_historical_clip",
                                        response={"result": f"Historical video segment from {hist_chunk['start_ts']:.0f}s to {hist_chunk['end_ts']:.0f}s is now attached. Review it to verify the event at {target_ts:.0f}s."},
                                    )
                                )
                                user_response_parts.append(types.Part(file_data=types.FileData(
                                    file_uri=hist_file.uri,
                                    mime_type=hist_file.mime_type,
                                )))
                            else:
                                user_response_parts.append(
                                    types.Part.from_function_response(
                                        name="view_historical_clip",
                                        response={"result": f"Failed to upload historical video for {target_ts:.0f}s. Rely on the text history instead."},
                                    )
                                )
                        except Exception as e:
                            print(f"[RS] Historical clip upload error: {e}")
                            user_response_parts.append(
                                types.Part.from_function_response(
                                    name="view_historical_clip",
                                    response={"result": f"Error retrieving historical video: {e}. Rely on the text history instead."},
                                )
                            )
                    elif hist_chunk and hist_chunk["index"] == chunk_index:
                        user_response_parts.append(
                            types.Part.from_function_response(
                                name="view_historical_clip",
                                response={"result": f"Timestamp {target_ts:.0f}s is within the current segment — you already have this video in your context. Analyze it directly."},
                            )
                        )
                    else:
                        user_response_parts.append(
                            types.Part.from_function_response(
                                name="view_historical_clip",
                                response={"result": f"No video segment found for timestamp {target_ts:.0f}s. This timestamp may be outside the recording range."},
                            )
                        )

            if user_response_parts:
                contents.append(types.Content(role="user", parts=user_response_parts))

        else:
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
