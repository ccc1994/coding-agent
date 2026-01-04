import os
import threading
import json
from typing import List, Dict, Any
from openai import OpenAI
from opentelemetry import trace
from rich.console import Console

console = Console()
tracer = trace.get_tracer(__name__)

SUMMARY_FILENAME = "project_summary.md"
CHAOS_DIR = ".chaos"

SUMMARY_PROMPT = """
You are the Knowledge Keeper for this software project. Your job is to maintain a "Project Summary" file.
I will provide you with:
1. The CURRENT Project Summary (if it exists).
2. The RECENT CONVERSATION history from the Architect agent.

Your task is to merge the new information from the conversation into the Current Summary. 
Do not delete existing valid information, but refine it if the new conversation provides more specific details or updates.

The Output MUST follow this exact Markdown format:

# Project Summary

## A. Project Introduction
[Brief description of what the project is, its goal, and value proposition]

## B. Technology Stack
[List of languages, frameworks, core libraries, and tools used]

## C. Project Structure & Modules
[Hierarchical list or description of folders/files and their specific responsibilities]

## D. Development Standards & Rules
[Coding conventions, specific "Do's and Don'ts", security rules, and workflow requirements identified in the conversation]

---
**Instructions:**
- If the Current Summary is empty, build it entirely from the Conversation.
- If information is conflicting, trust the RECENT CONVERSATION more as it represents the latest state.
- Keep the tone professional, concise, and documentation-oriented.
- Output ONLY the Markdown content, no extra conversational filler.
"""

def _get_architect_model_config():
    """Retrieve model config for the direct LLM call."""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL")
    # Use Architect's specific model if available, otherwise default
    model_id = os.getenv("ARCHITECT_MODEL_ID")
    return api_key, base_url, model_id

def _read_existing_summary(project_root: str) -> str:
    path = os.path.join(project_root, CHAOS_DIR, SUMMARY_FILENAME)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
    return ""

def _write_summary(project_root: str, content: str):
    chaos_path = os.path.join(project_root, CHAOS_DIR)
    if not os.path.exists(chaos_path):
        os.makedirs(chaos_path, exist_ok=True)
    
    path = os.path.join(chaos_path, SUMMARY_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def _perform_memory_update(project_root: str, chat_history: List[Dict]):
    """
    The actual logic running in the background thread.
    """
    with tracer.start_as_current_span("project_memory_update"):
        try:
            api_key, base_url, model_id = _get_architect_model_config()
            if not api_key:
                return

            # 1. Prepare Context
            existing_summary = _read_existing_summary(project_root)
            
            # Convert chat history to a readable string format
            # Filter for Architect's perspective (system prompts + user interactions + tool outputs)
            conversation_text = ""
            for msg in chat_history:
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                if content:
                    conversation_text += f"[{role}]: {content}\n\n"

            # 2. Call LLM
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            messages = [
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": f"### CURRENT SUMMARY:\n{existing_summary}\n\n### RECENT CONVERSATION:\n{conversation_text}"}
            ]

            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=0.1 # Low temperature for consistent documentation
            )
            
            new_summary = response.choices[0].message.content.strip()

            # 3. Write Back
            # Basic validation to ensure we don't overwrite with empty garbage
            if len(new_summary) > 50 and "# Project Summary" in new_summary:
                _write_summary(project_root, new_summary)
                # Not printing to console to avoid cluttering the CLI, 
                # but it will be visible in Phoenix/OpenTelemetry.
            
        except Exception as e:
            # Silently fail in background, but log to trace if possible
            print(f"[MemoryUpdateError] {e}")

def trigger_project_memory_update(architect_agent, project_root: str):
    """
    Triggers the asynchronous update of the project summary.
    """
    # Extract the chat history from the agent. 
    # AutoGen agents usually store history in .chat_messages[partner_agent]
    # For the Architect, we want the history of the main session.
    # We'll take a flattening of all messages.
    
    history = []
    # Collect all messages the Architect has seen/sent
    for agent, messages in architect_agent.chat_messages.items():
        history.extend(messages)
    
    # Sort by time isn't strictly possible with the dict structure without timestamps,
    # but AutoGen usually maintains order in list. 
    # If there are multiple conversations, we dump them all. 
    
    if not history:
        return

    # Run in background thread
    thread = threading.Thread(
        target=_perform_memory_update,
        args=(project_root, history),
        daemon=True
    )
    thread.start()