import subprocess
import sys
import json
import os

# Validate input arguments
if len(sys.argv) < 2:
    print("Usage: python sync_antigravity.py <user@remote_host>")
    sys.exit(1)

# Assign environment variables
remote = sys.argv[1]
local_history = os.path.expanduser("~/.gemini/antigravity-cli/history.jsonl")
remote_history_tmp = "/tmp/history.jsonl.remote"
merged_history = local_history + ".merged"

# PHASE 1: PULL (Fetch from remote)

# Download remote history
subprocess.run(f"ssh {remote} 'wsl cat ~/.gemini/antigravity-cli/history.jsonl' > {remote_history_tmp}", shell=True)

# Load histories into memory
lines = []
for f in [local_history, remote_history_tmp]:
    try:
        with open(f, encoding='utf-8') as fp:
            for line in fp:
                if line.strip():
                    lines.append(json.loads(line))
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

# Replace local history
subprocess.run(f"mv {merged_history} {local_history}", shell=True)

# Clean up temporary files
subprocess.run(f"rm -f {remote_history_tmp}", shell=True)

# Pull databases, memories, and identity from remote to local
subprocess.run(f"ssh {remote} 'wsl tar -czf - -C ~/.gemini/antigravity-cli brain conversations installation_id' | tar -xzf - -C ~/.gemini/antigravity-cli", shell=True)

# PHASE 2: PUSH (Send back to remote)

# Push the merged master history back to the remote server
subprocess.run(f"cat {local_history} | ssh {remote} 'wsl bash -c \"cat > ~/.gemini/antigravity-cli/history.jsonl\"'", shell=True)

# Push our local databases and memories back to the remote server
subprocess.run(f"tar -czf - -C ~/.gemini/antigravity-cli brain conversations | ssh {remote} 'wsl tar -xzf - -C ~/.gemini/antigravity-cli'", shell=True)
