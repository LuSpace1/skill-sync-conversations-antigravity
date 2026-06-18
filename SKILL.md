---
name: sync-conversations-antigravity
description: Synchronizes and merges local histories, memories (brain), and databases of Antigravity CLI between different devices, allowing uninterrupted continuation of sessions.
---

# Antigravity CLI Architectural Synchronization

## Directionality: True Bidirectional Sync (Mirror)
This skill performs a **true bidirectional sync**. When executed, it extracts the remote machine's history, intelligently merges it with the local history without deleting anything, and finally pushes the combined state and databases back to the remote machine. As an agent, you should know that executing this script instantly turns both machines into a perfect mirror.

## Main Use Cases
- **Nomad Developers:** Professionals who start a complex project on a powerful desktop PC and need to continue exactly where they left off on their laptop.
- **Session Backups:** Safeguard and restore AI agent contexts without relying exclusively on the cloud.
- **Environment Cloning:** Synchronize the installation ID so the CLI assumes two physically different computers are the same environment.

## Architecture and How It Works
Antigravity CLI has a decentralized client architecture. To "trick" the system and achieve a seamless transition, this skill synchronizes the following critical components:

1. **`history.jsonl` (The Index):** The master file read by the `/resume` command. If a conversation is not here, it does not exist for the UI.
2. **`brain/` (The Memory):** Stores static files, logs, and transcripts of every step executed by the AI.
3. **`conversations/` (The Databases):** Each session generates its own SQLite (`.db`) file. It is crucial for restoring the UI state and rich text blocks in the terminal.
4. **`installation_id` (The Identity Key):** The Antigravity backend server associates Workspaces with this ID. Cloning it prevents the fatal error: *"The project associated with this conversation is no longer valid"*. The backend assumes both devices are the same.

*(Note: When cloning the identity, the system might throw a slight Warning stating that the environment changed, but thanks to the matching keys and databases, it will allow normal operation).*

## Workspace Rule
Conversations are strictly anchored to the project directory. Once synchronized, the developer **must open the terminal inside the same project directory** (e.g., `~/MyProjects/App`) to view them using `/resume`.

## Dedicated Script: `scripts/sync_antigravity.py`
To ensure the local history is not overwritten when fetching the remote history, this skill includes a robust Python script that extracts everything via SSH and intelligently merges the JSONL files (sorting by timestamp and removing duplicates).

### Security & Merge Logic Transparency
To address static analysis security audits, please note that `scripts/sync_antigravity.py` operates entirely locally using only standard Python libraries (`json`, `subprocess`, `shlex`). 
**Exact Merge Logic:** It fetches the remote `history.jsonl` via a secure SSH pipe, sanitizes each JSON object to prevent prompt injections, stores them in memory, deduplicates records based on `timestamp` and `conversationId`, and performs an atomic file replacement before securely piping the tar archives back through your private SSH tunnel. No third-party APIs are called, and no credentials leave your private network.

## How to execute as an Agent
When the user requests to synchronize Antigravity, the agent simply needs to invoke:
`python ~/.agents/skills/sync-conversations-antigravity/scripts/sync_antigravity.py pc`
