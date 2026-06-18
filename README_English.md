# Sync Conversations - Antigravity CLI

Welcome to the Sync Conversations skill for Antigravity CLI. This skill allows you to seamlessly backup, merge, and synchronize your entire AI conversational history across multiple devices.

## Who is this for?
- Nomad Developers: If you start a complex project on a powerful desktop PC and need to continue exactly where you left off on your laptop at a coffee shop.
- Data Safekeepers: Developers who want to maintain local backups of their AI agent's context and memories without relying entirely on cloud synchronization.
- Multi-Device Power Users: Anyone who wants their AI assistant to feel like a single, unified entity across all their physical machines.

## What does it do?
When you move to a new machine, your Antigravity CLI conversations are left behind on the original device. This skill automates the secure transfer, merging, and integration of your AI's SQLite databases, memory logs, and JSON indexes so you can use /resume on a new machine as if you never left.

## Prerequisites (CRITICAL)
For this skill to work, it must communicate between your devices. You must have SSH configured:
1. Network Connection: Both machines must be on the same local network, or connected via a virtual network like Tailscale, ZeroTier, or a VPN.
2. SSH Access: The destination machine must have SSH access configured to reach the source machine. Passwordless SSH is highly recommended for automation.
3. Linux / WSL Environment: The scripts are written using bash commands (tar, cat).
   - If your remote machine is Native Linux (Ubuntu, Fedora, Mac, etc.), or if you SSH directly into the WSL Linux IP: You must edit the python script to remove the 'wsl ' prefix from the SSH commands.
   - If your remote machine is Windows and you SSH into the Windows Host (CMD/PowerShell): The script works out of the box, as the 'wsl ' prefix bridges the command into your WSL environment.

## macOS Compatibility
Antigravity CLI and this skill are fully compatible with macOS, as they rely on universal UNIX commands and standard paths (~/.gemini/antigravity-cli).
What you need to do: If your remote machine is a Mac (or native Linux), the 'wsl ' prefix in the SSH commands will fail.
The Agentic Solution: You don't need to code! Once you download this skill, simply ask your AI agent:
"I am on macOS. Please edit the python script in the sync-conversations-antigravity skill to remove all 'wsl ' prefixes from the SSH commands."
Your agent will automatically adapt the script for your environment.

## Native Windows Compatibility (Without WSL)
If you are running Antigravity CLI on pure Windows (CMD or PowerShell) without using WSL, the underlying commands (tar, cat) and paths may behave differently.
The Agentic Solution: Simply ask your AI agent to adapt the script:
"I am on Native Windows without WSL. Please edit the python script in the sync-conversations-antigravity skill to use native PowerShell commands instead of bash, and remove the 'wsl ' prefixes from the SSH commands."

## True Bidirectional Sync (Non-Destructive)
This skill performs a True Bidirectional Sync. Because Antigravity stores conversations in separate databases, the script safely pulls the remote data, merges it with your local data without deleting anything, and then pushes the combined master history back to the remote machine. Both devices become a perfect mirror instantly.

## How it Works (Under the Hood)
Antigravity CLI has a decentralized client architecture. To achieve a perfect transition, this skill performs the following pipeline:
1. Index Merging: It securely downloads the history.jsonl from the remote machine and runs a Python algorithm to merge it with your local history chronologically, removing duplicates.
2. Atomic Tar Pipeline: It streams your brain/ folder and conversations/ folder over SSH using a compressed tarball pipeline.
3. Environment Synchronization: It copies the installation_id. By synchronizing it, we prevent project validation errors and securely maintain the session connection across machines.

## How to Use It
1. Ensure your SSH connection is working.
2. Install this skill into your ~/.agents/skills/ directory.
3. Open Antigravity CLI and prompt your agent:
   "Run the sync-conversations-antigravity skill to bring my sessions from my PC (user@ip_address)."
4. Once completed, navigate to the exact same project folder and type /resume.

## Security Audits (False Positives)
If you scan this skill with security tools (like Gen Agent Trust Hub or Snyk), they will likely flag alerts such as `DATA_EXFILTRATION` and `CREDENTIALS_UNSAFE`. These are **false positives** and represent the expected, required behavior: the tool explicitly transfers local databases and synchronizes the `installation_id` across your private network to achieve session continuity between your own devices.
