#Import standard libraries
import subprocess
import sys
import json
import os
import re
import tempfile
import argparse
import unicodedata

#Normalize text to lowercase and remove accents
def normalize(text):
    if not text:
        return ""
    text = text.lower().strip()
    return "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

#Parse input arguments
parser = argparse.ArgumentParser(description="Synchronize Antigravity CLI conversations.")
parser.add_argument("remote", help="Remote host alias or user@host.")
parser.add_argument("-n", "--name", help="Specific conversation title/display name to sync.")
args = parser.parse_args()

raw_remote = args.remote
sync_name = args.name

#Basic validation to prevent arbitrary flags
if not re.match(r"^(?:[a-zA-Z0-9_.-]+@)?[a-zA-Z0-9_.-]+$", raw_remote):
    print("Error: Invalid remote format. Expected user@host or host alias (e.g. pc).")
    sys.exit(1)
remote = raw_remote
local_dir = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-cli")
local_history = os.path.join(local_dir, "history.jsonl")
remote_history_tmp = os.path.join(tempfile.gettempdir(), "history.jsonl.remote")
merged_history = local_history + ".merged"

#Detect if remote requires the 'wsl' prefix (Windows WSL via native SSH)
use_wsl_remote = False
try:
    test_wsl = subprocess.run(["ssh", remote, "wsl --status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if test_wsl.returncode == 0:
        use_wsl_remote = True
except Exception:
    pass

wsl_prefix = ["wsl"] if use_wsl_remote else []

#PHASE 1: PULL (Fetch from remote)

#Download remote history safely
with open(remote_history_tmp, "w") as out:
    subprocess.run(["ssh", remote] + wsl_prefix + ["cat ~/.gemini/antigravity-cli/history.jsonl"], stdout=out, check=False)

#Load histories into memory with validation against prompt injection
lines = []
for f in [local_history, remote_history_tmp]:
    try:
        with open(f, encoding='utf-8') as fp:
            for line in fp:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    #Sanitize: ensure valid keys to prevent arbitrary payload injections
                    if isinstance(data, dict) and "timestamp" in data and "conversationId" in data:
                        lines.append(data)
    except FileNotFoundError:
        pass

#Resolve specific conversation ID if sync_name is provided
target_id = None
if sync_name:
    norm_search = normalize(sync_name)
    matches = []
    seen_ids = set()
    for item in lines:
        conv_id = item.get("conversationId")
        display = item.get("display", "")
        if conv_id and conv_id not in seen_ids:
            if norm_search in normalize(display):
                matches.append(item)
                seen_ids.add(conv_id)
                
    if not matches:
        print(f"Error: No conversation matching '{sync_name}' was found.")
        sys.exit(1)
    elif len(matches) > 1:
        print(f"Error: Ambiguity detected. Multiple conversations matched '{sync_name}':")
        for m in matches:
            print(f" - '{m.get('display')}' (ID: {m.get('conversationId')})")
        sys.exit(1)
    else:
        target_id = matches[0].get("conversationId")
        print(f"Selected conversation: '{matches[0].get('display')}' (ID: {target_id})")

#Filter duplicates and sort chronologically
seen = set()
merged = []
for item in sorted(lines, key=lambda x: x.get('timestamp', 0)):
    key = str(item.get('timestamp')) + str(item.get('conversationId', ''))
    if key not in seen:
        seen.add(key)
        merged.append(item)

#Save merged history locally
if target_id:
    #Selective merge for history.jsonl
    local_lines = []
    if os.path.exists(local_history):
        with open(local_history, encoding='utf-8') as fp:
            for line in fp:
                if line.strip():
                    local_lines.append(json.loads(line.strip()))
    
    #Check if target_id is already in local history
    if not any(item.get("conversationId") == target_id for item in local_lines):
        target_meta = next((item for item in merged if item.get("conversationId") == target_id), None)
        if target_meta:
            local_lines.append(target_meta)
            local_lines.sort(key=lambda x: x.get('timestamp', 0))
            with open(merged_history, 'w', encoding='utf-8') as out:
                for item in local_lines:
                    out.write(json.dumps(item, separators=(',', ':')) + '\n')
            os.replace(merged_history, local_history)
            print("History updated with the selected conversation.")
else:
    #Full history merge
    with open(merged_history, 'w', encoding='utf-8') as out:
        for item in merged:
            out.write(json.dumps(item, separators=(',', ':')) + '\n')
    os.replace(merged_history, local_history)
    print("Full history merged and updated.")

#Clean up temporary files
if os.path.exists(remote_history_tmp):
    os.remove(remote_history_tmp)

#Pull databases, memories, and identity from remote to local safely without shell
active_id = os.environ.get("ACTIVE_CONVERSATION_ID")
exclude_args = []
if active_id:
    exclude_args = [
        f"--exclude=conversations/{active_id}.db",
        f"--exclude=conversations/{active_id}.db-wal",
        f"--exclude=conversations/{active_id}.db-shm",
        f"--exclude=brain/{active_id}"
    ]

if target_id:
    #Package only the files/directories matching the specific conversation ID
    remote_cmd = f"cd ~/.gemini/antigravity-cli && tar -czf - $(find brain -name {target_id} 2>/dev/null) $(find conversations -name '{target_id}.*' 2>/dev/null)"
else:
    remote_cmd = "tar -czf - -C ~/.gemini/antigravity-cli brain conversations installation_id"

p1 = subprocess.Popen(["ssh", remote] + wsl_prefix + [remote_cmd], stdout=subprocess.PIPE)
p2 = subprocess.Popen(["tar", "-xzf", "-"] + exclude_args + ["-C", local_dir], stdin=p1.stdout)
p1.stdout.close()
p2.communicate()

#PHASE 2: PUSH (Send back to remote)

#Push the merged master history back to the remote server safely
with open(local_history, "r") as hist_in:
    subprocess.run(["ssh", remote] + wsl_prefix + ["bash -c 'cat > ~/.gemini/antigravity-cli/history.jsonl'"], stdin=hist_in)

#Push our local databases and memories back to the remote server safely
if target_id:
    #Initialize files to push
    files_to_push = []
    
    #Check if local brain directory for target ID exists
    brain_path_local = os.path.join(local_dir, "brain", target_id)
    if os.path.exists(brain_path_local):
        files_to_push.append(os.path.join("brain", target_id))
    
    #Check if local conversation files exist
    conv_dir_local = os.path.join(local_dir, "conversations")
    if os.path.exists(conv_dir_local):
        for filename in os.listdir(conv_dir_local):
            if filename.startswith(target_id):
                files_to_push.append(os.path.join("conversations", filename))
                
    #Push targeted files via SSH and tar
    if files_to_push:
        p3 = subprocess.Popen(["tar", "-czf", "-"] + files_to_push + ["-C", local_dir], stdout=subprocess.PIPE)
        p4 = subprocess.Popen(["ssh", remote] + wsl_prefix + ["tar -xzf - -C ~/.gemini/antigravity-cli"], stdin=p3.stdout)
        p3.stdout.close()
        p4.communicate()
else:
    #Full PUSH
    p3 = subprocess.Popen(["tar", "-czf", "-", "-C", local_dir, "brain", "conversations"], stdout=subprocess.PIPE)
    p4 = subprocess.Popen(["ssh", remote] + wsl_prefix + ["tar -xzf - -C ~/.gemini/antigravity-cli"], stdin=p3.stdout)
    p3.stdout.close()
    p4.communicate()
