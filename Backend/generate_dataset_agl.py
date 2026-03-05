"""
Offline script to generate a training dataset using agentlightning.
This script runs the pipeline on a specified video, captures the traces,
and exports them to a JSONL file.
"""

import os
import sys
import asyncio
import argparse
import time

# Set up the Python path so it can import backend modules correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db
from pipeline import process_video
from config import UPLOAD_DIR
import agentlightning as agl

# Ensure logging is enabled for AgentOps traces to show up
agl.setup_logging("INFO")

async def dummy_broadcast(event_type: str, data: dict):
    """A dummy broadcst function so process_video doesn't error out."""
    print(f"[{event_type}] {data}")

@agl.rollout
async def distill_trajectory(task: dict, llm: agl.LLM, rollout: agl.Rollout):
    """The agentlightning task function wrapper."""
    video_id = task["video_id"]
    video_path = task["video_path"]
    print(f"Starting pipeline on video {video_id} using agentlightning wrapped LLM.")
    
    # Run the existing pipeline. Within the pipeline, calls to ai_provider 
    # will emit traces because we monkeypatch it below.
    await process_video(video_id, video_path, broadcast_fn=dummy_broadcast)
    
    # We emit a dummy reward here indicating the "trajectory" was successfully processed
    # In a real environment, you might calculate a reward based on risk_scores or some other metric.
    agl.emit_reward(1.0)

async def main():
    parser = argparse.ArgumentParser(description="Distill trajectory into Agent-Lightning JSONL")
    parser.add_argument("--video-id", required=True, help="Video ID (uuid format from the database)")
    parser.add_argument("--video-path", required=True, help="Path to the source .mp4 file")
    args = parser.parse_args()

    if not os.path.exists(args.video_path):
        print(f"Error: Video file not found: {args.video_path}")
        return

    print("Initializing Database...")
    await db.init_db()

    # Set up Agent-Lightning tracer and store
    tracer = agl.AgentOpsTracer()
    store = agl.InMemoryLightningStore()
    
    # Patch the global provider to intercept calls
    from ai_provider import _provider_instance, GeminiProvider
    if _provider_instance is None:
        from ai_provider import get_provider
        get_provider()
    
    global_provider = _provider_instance
    if not isinstance(global_provider, GeminiProvider):
        print("Warning: Only GeminiProvider tracing is explicitly supported in this script via AgentOpsTracer right now.")
    
    original_generate = global_provider.generate
    
    # Monkeypatch the provider to emit Agent Lightning spans
    # The actual emission uses agl.emit_llm_call or the tracer automatically records openai calls if we use async openai client. 
    # Since we use `google.genai` SDK in GeminiProvider, we will construct a custom LLM Span.
    def traced_generate(system_prompt: str, user_text: str, images=None, temperature=0.3, max_tokens=1024):
        # We manually structure an LLM span for Agent Lightning
        try:
            start_time = time.time()
            response = original_generate(system_prompt, user_text, images, temperature, max_tokens)
            end_time = time.time()
            
            # Record via Agentops tracer manually if possible, or use emit_model_inference placeholder:
            # We emit an annotation for now which Agent-Lightning can digest as intermediate.
            agl.emit_annotation("genai_call", {
                "system_prompt": system_prompt,
                "user_text": user_text,
                "response": response,
                "latency_seconds": end_time - start_time
            })
            return response
        except Exception as e:
            agl.emit_exception(e)
            raise e
            
    # Apply monkeypatch
    global_provider.generate = traced_generate
    print("Monkeypatched ai_provider.generate with tracing hooks.")

    # We start a rollout inside the store manually, or let trigger it using a Trainer dummy
    print("Starting Tracing Rollout...")
    with tracer.lifespan(store):
        dummy_llm = agl.LLM(model="gemini", endpoint="local") # acts as a placeholder resource
        task_info = {"video_id": args.video_id, "video_path": args.video_path}
        rollout_meta = await store.start_rollout(input=task_info)
        
        async with tracer.trace_context("dssa_pipeline", store=store, rollout_id=rollout_meta.rollout_id, attempt_id=rollout_meta.attempt.attempt_id):
            await distill_trajectory(task_info, dummy_llm, rollout_meta)

    # Dump the Spans into a JSONL Dataset
    print("Exporting Traces...")
    spans = await store.query_spans(rollout_id=rollout_meta.rollout_id)
    
    output_file = "training_trajectories.jsonl"
    with open(output_file, "a") as f:
        # Write out raw spans as JSON
        import json
        for span in spans:
            f.write(json.dumps({
                "name": span.name,
                "span_id": span.span_id,
                "attributes": span.attributes,
                "status": span.status.status_code if hasattr(span.status, 'status_code') else span.status,
            }) + "\\n")
            
    print(f"Traces exported successfully to {output_file}. Extracted {len(spans)} spans.")

if __name__ == "__main__":
    asyncio.run(main())
