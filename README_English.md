# Sync Conversations - Antigravity CLI

Welcome to the Sync Conversations skill for Antigravity CLI. This skill allows you to backup, merge, and synchronize your AI conversational history across multiple devices (desktop PCs, laptops, servers, etc.).

## Who is this for?
- **Nomad Developers:** If you start a complex project on a powerful desktop PC and need to continue exactly where you left off on your laptop.
- **Data Safekeepers:** Developers who want to maintain local backups of their AI agent's context and memories.
- **Multi-Device Power Users:** Anyone who wants to keep their agent's sessions synchronized and unified across all physical machines.

## What does it do?
This skill automates the secure transfer, merging, and integration of your AI's SQLite databases, memory logs, and JSON indexes so you can use the `/resume` command on a new machine as if you never left.

It supports two modes of operation:
1. **Full Synchronization (Mirror):** Consolidates and synchronizes all your conversations between devices in a bidirectional and additive manner.
2. **Selective Synchronization:** Allows you to fetch or send a single conversation by searching the history for its display title, without altering the rest of your local chats.

## Prerequisites (CRITICAL)
For this skill to work, it must communicate between your devices securely. You must meet the following requirements:
1. **Network Connection:** Both devices must be on the same local network, or connected via a virtual private network (like Tailscale or a VPN).
2. **SSH Access:** The machine running the skill must have configured SSH access to the remote machine. Public key authentication (passwordless) is highly recommended for friction-free automation.
3. **Packaging Tools:** The script requires the `tar` command to be available on the system (included by default in Linux, macOS, and native Windows 10/11).

## Multiplatform Compatibility
This skill has been designed to be compatible out-of-the-box with the following local and remote environments:
- **macOS**
- **Native Linux**
- **Windows WSL**
- **Native Windows** (CMD and PowerShell)

The script dynamically detects if the remote host requires bridging through the `wsl` command and securely utilizes standard temporary directories based on the running operating system, eliminating the need to manually edit the code.

## How it Works
1. **Index Merging:** It downloads the `history.jsonl` from the remote machine and performs an in-memory merge with the local history, deduplicating by `timestamp` while preserving metadata.
2. **Active Session Exclusion:** If the agent executes the script, it will automatically pass the `ACTIVE_CONVERSATION_ID` environment variable. The script will exclude those specific files from being overwritten during download to prevent corruption of the active SQLite session database.
3. **Compressed Tar Pipeline:** It transmits memory directories (`brain/`) and conversation databases (`conversations/`) over an encrypted SSH pipe.

## How to Use It

### Automatic Invocation by the Agent (Natural Language)
Once the skill is installed, you can ask the Antigravity agent directly:
* *"Sync all my Antigravity conversations from my PC"*
* *"Bring the conversation about 'code refactoring' from my notebook"*

### Manual Invocation (Command Line)
You can run the script directly from your local PC terminal:

- **Full Sync (All conversations):**
  ```bash
  ACTIVE_CONVERSATION_ID=<session_id> python scripts/sync_antigravity.py <remote_host>
  ```
- **Selective Sync (A specific conversation by its title):**
  ```bash
  ACTIVE_CONVERSATION_ID=<session_id> python scripts/sync_antigravity.py <remote_host> --name "Conversation Title"
  ```
*(Replace `<remote_host>` with the alias configured in your SSH config, e.g., `pc` or `notebook`, and `<session_id>` with the ID of the current conversation if you wish to protect it).*

## Security Audits (False Positives)
If you scan this skill with security tools (like Gen Agent Trust Hub or Snyk), they will flag alerts such as `DATA_EXFILTRATION` and `CREDENTIALS_UNSAFE`. These are false positives and represent the expected, required behavior: the tool explicitly transfers local databases and synchronizes the `installation_id` across your private network to achieve session continuity between your own devices.
