---
name: sync-conversations-antigravity
description: Synchronizes and merges local histories, memories (brain), session databases (conversations/*.db), annotations, and global SQLite indexes (conversation_summaries.db) of Antigravity CLI between different devices, allowing uninterrupted continuation of sessions across Linux, macOS, Windows, and WSL.
---

# Antigravity CLI Architectural Synchronization

## Directionality: True Bidirectional Sync (Mirror)
This skill performs a **true bidirectional sync**. When executed, it extracts the remote machine's history, intelligently merges it with the local history without deleting anything, and finally pushes the combined state, databases, annotations, and global SQLite summaries back to the remote machine. As an agent, you should know that executing this script instantly turns both machines into a perfect mirror.

## Main Use Cases
- **Nomad Developers:** Professionals who start a complex project on a powerful desktop PC and need to continue exactly where they left off on their laptop.
- **Session Backups:** Safeguard and restore AI agent contexts without relying exclusively on the cloud.
- **Environment Synchronization:** Synchronize the installation ID and SQLite indices to maintain session continuity across physically different computers.

## Architecture and How It Works
Antigravity CLI has an advanced decentralized client architecture. To achieve a seamless transition and maintain session continuity with full `/resume` recognition, this skill synchronizes the following critical components:

1. **`history.jsonl` (The Index):** The master file read by the CLI history. It is merged chronologically and deduplicated by timestamp and conversation ID.
2. **`brain/` (The Memory):** Stores static files, logs, subagent traces, and transcripts of every step executed by the AI.
3. **`conversations/` (Session Databases):** Each session generates its own SQLite (`.db`) file. This file contains the complete step trajectory required by `GetConversationDetail` when resuming.
4. **`annotations/` (Annotations):** Protobuf text files (`.pbtxt`) containing session annotations and metadata.
5. **`conversation_summaries.db` (Global Summary & FTS Index):** Global SQLite database used by `agy` to populate `/resume` and search sessions. The skill synchronizes both the `conversation_summaries` rows and full-text search (`conversations_fts`) entries, ensuring proper status (`CASCADE_RUN_STATUS_IDLE`) and valid timestamps.
6. **Cross-Platform SSH & WSL Compatibility:** Fully supports Windows hosts with WSL targets via safe shell escaping (`wsl -e bash -c "<command>"`), preventing path expansion issues over SSH tunnels.

## Workspace Rule
Conversations are strictly anchored to the project directory. Once synchronized, the developer **must open the terminal inside the same project directory** (e.g., `~/MyProjects/App`) to view them using `/resume`, or toggle between tabs using `Tab` / `Ctrl+F` in the interactive picker.

## Dedicated Script: `scripts/sync_antigravity.py`
To ensure data safety, this skill includes a robust Python script that securely transfers data via SSH and intelligently merges history and database records.

### Security & Merge Logic Transparency
- Operates entirely using Python standard libraries (`json`, `sqlite3`, `subprocess`, `tarfile`, `shlex`).
- Sanitizes and deduplicates records.
- Avoids overwriting active sessions by checking `ACTIVE_CONVERSATION_ID`.
- No third-party APIs called; zero credentials leave your private network.

## How to execute as an Agent
When the user requests to synchronize Antigravity, the agent must:
1. Identify the remote host alias or IP address (e.g. `pc`, `notebook`, `user@remote_host`) from the user's request or `~/.ssh/config`.
2. Determine if the user wants to sync a specific conversation by name/title (e.g., "sync the conversation about notifications").
   - If a specific conversation is requested, pass its name/title using `--name "<term>"`. The script will search both `history.jsonl` and `conversation_summaries.db` to resolve the conversation ID even if slash commands were used.
3. Invoke the script setting `ACTIVE_CONVERSATION_ID` to your current conversation ID:
   - **Full Sync:**
     `ACTIVE_CONVERSATION_ID=<current_conversation_id> python ~/.agents/skills/sync-conversations-antigravity/scripts/sync_antigravity.py <remote_host>`
   - **Specific Conversation Sync:**
     `ACTIVE_CONVERSATION_ID=<current_conversation_id> python ~/.agents/skills/sync-conversations-antigravity/scripts/sync_antigravity.py <remote_host> --name "<exact_or_partial_conversation_title>"`
