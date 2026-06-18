import subprocess
import sys
import json
import os
import shlex
import re
import tempfile

# Validate input arguments
if len(sys.argv) < 2:
    print("Usage: python sync_antigravity.py <user@remote_host>")
    sys.exit(1)

# Assign environment variables
raw_remote = sys.argv[1]
# Basic validation to prevent arbitrary flags
if not re.match(r"^(?:[a-zA-Z0-9_.-]+@)?[a-zA-Z0-9_.-]+$", raw_remote):
    print("Error: Invalid remote format. Expected user@host or host alias (e.g. pc).")
    sys.exit(1)
remote = raw_remote
local_history = os.path.expanduser("~/.gemini/antigravity-cli/history.jsonl")
remote_history_tmp = os.path.join(tempfile.gettempdir(), "history.jsonl.remote")
merged_history = local_history + ".merged"
local_dir = os.path.expanduser("~/.gemini/antigravity-cli")

# PHASE 1: PULL (Fetch from remote)

# Download remote history safely
with open(remote_history_tmp, "w") as out:
    subprocess.run(["ssh", remote, "wsl cat ~/.gemini/antigravity-cli/history.jsonl"], stdout=out, check=False)

# Load histories into memory with validation against prompt injection
lines = []
for f in [local_history, remote_history_tmp]:
    try:
        with open(f, encoding='utf-8') as fp:
            for line in fp:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    # Sanitize: ensure valid keys to prevent arbitrary payload injections
                    if isinstance(data, dict) and "timestamp" in data and "conversationId" in data:
                        lines.append(data)
    except FileNotFoundError:
        pass

# Filter duplicates and sort chronologically
seen = set()
merged = []
for item in sorted(lines, key=lambda x: x.get('timestamp', 0)):
    key = str(item.get('timestamp')) + str(item.get('conversationId', ''))
    if key not in seen:
        seen.add(key)
        merged.append(item)

# Save merged history locally
with open(merged_history, 'w', encoding='utf-8') as out:
    for item in merged:
        out.write(json.dumps(item, separators=(',', ':')) + '\n')

# Replace local history securely
os.replace(merged_history, local_history)

# Clean up temporary files
if os.path.exists(remote_history_tmp):
    os.remove(remote_history_tmp)

# Pull databases, memories, and identity from remote to local safely without shell
active_id = os.environ.get("ACTIVE_CONVERSATION_ID")
exclude_args = []
if active_id:
    exclude_args = [
        f"--exclude=conversations/{active_id}.db",
        f"--exclude=conversations/{active_id}.db-wal",
        f"--exclude=conversations/{active_id}.db-shm",
        f"--exclude=brain/{active_id}"
    ]

p1 = subprocess.Popen(["ssh", remote, "wsl tar -czf - -C ~/.gemini/antigravity-cli brain conversations installation_id"], stdout=subprocess.PIPE)
p2 = subprocess.Popen(["tar", "-xzf", "-"] + exclude_args + ["-C", local_dir], stdin=p1.stdout)
p1.stdout.close()
p2.communicate()

# PHASE 2: PUSH (Send back to remote)

# Push the merged master history back to the remote server safely
with open(local_history, "r") as hist_in:
    subprocess.run(["ssh", remote, "wsl bash -c 'cat > ~/.gemini/antigravity-cli/history.jsonl'"], stdin=hist_in)

# Push our local databases and memories back to the remote server safely
p3 = subprocess.Popen(["tar", "-czf", "-", "-C", local_dir, "brain", "conversations"], stdout=subprocess.PIPE)
p4 = subprocess.Popen(["ssh", remote, "wsl tar -xzf - -C ~/.gemini/antigravity-cli"], stdin=p3.stdout)
p3.stdout.close()
p4.communicate()
