#Import standard libraries
import subprocess
import sys
import json
import os
import re
import tempfile
import argparse
import unicodedata
import tarfile
import base64

#Normalize text to lowercase and remove accents
def normalize(text):
    if not text:
        return ""
    text = text.lower().strip()
    return "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def extract_text(entry):
    """Extract all readable text from a history entry (display, parts, text, content)."""
    texts = []
    disp = entry.get("display")
    if isinstance(disp, str) and disp:
        texts.append(disp)
    parts = entry.get("parts")
    if isinstance(parts, list):
        for p in parts:
            if isinstance(p, dict):
                txt = p.get("text") or p.get("content") or ""
                if txt:
                    texts.append(str(txt))
    for field in ("text", "content", "title"):
        val = entry.get(field)
        if isinstance(val, str) and val:
            texts.append(val)
    return " ".join(texts)

#Parse input arguments
parser = argparse.ArgumentParser(description="Synchronize Antigravity CLI conversations.")
parser.add_argument("remote", nargs="?", help="Remote host alias or user@host.")
parser.add_argument("-n", "--name", help="Specific conversation title/display name to sync.")
args = parser.parse_args()

raw_remote = args.remote
sync_name = args.name
is_interactive = sys.stdin and sys.stdin.isatty()

#FUNCTION: detect if remote uses WSL
def detect_wsl(host):
    try:
        r = subprocess.run(["ssh", host, "wsl --status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return r.returncode == 0
    except Exception:
        return False

#FUNCTION: check SSH connection, print message, return True/False
def check_ssh(host, prefix):
    try:
        print(f"Checking SSH connection to {host}...")
        subprocess.run(["ssh", "-o", "ConnectTimeout=10", host] + prefix + ["true"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print("SSH connection successful.\n")
        return True
    except (subprocess.CalledProcessError, Exception) as e:
        print(f"  Could not connect to '{host}'.")
        return False

#Interactive prompt for SSH host if not provided
if not raw_remote:
    if not is_interactive:
        print("Error: Remote host is required. Pass it as the first argument (e.g. python sync_antigravity.py pc).")
        sys.exit(1)
    print("Conversation Synchronization - Antigravity CLI")
    while True:
        raw_remote = input("* Enter the remote SSH host or alias, or 'exit': ").strip()
        if raw_remote.lower() in ('exit', 'c', 'q'):
            print("Synchronization canceled.")
            sys.exit(0)
        if not raw_remote:
            continue
        if not re.match(r"^(?:[a-zA-Z0-9_.-]+@)?[a-zA-Z0-9_.-]+$", raw_remote):
            print("  Invalid format. Example: pc, laptop, user@host")
            continue
        remote = raw_remote
        use_wsl_remote = detect_wsl(remote)
        wsl_prefix = ["wsl"] if use_wsl_remote else []
        if check_ssh(remote, wsl_prefix):
            break
        #If failed, ask for host again
        raw_remote = None

else:
    #CLI: host passed as argument, validate and verify once
    if not re.match(r"^(?:[a-zA-Z0-9_.-]+@)?[a-zA-Z0-9_.-]+$", raw_remote):
        print("Error: Invalid remote host format. Example: pc, user@host")
        sys.exit(1)
    remote = raw_remote
    use_wsl_remote = detect_wsl(remote)
    wsl_prefix = ["wsl"] if use_wsl_remote else []
    if not check_ssh(remote, wsl_prefix):
        print("  Check the host name or your SSH configuration.")
        sys.exit(1)

local_dir = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-cli")
local_history = os.path.join(local_dir, "history.jsonl")
remote_history_tmp = os.path.join(tempfile.gettempdir(), "history.jsonl.remote")
merged_history = local_history + ".merged"

#Interactive prompt for sync type if not specified via --name and running in a terminal
direct_selection = False
sync_option = None
if not sync_name and is_interactive and len(sys.argv) <= 2:
    print("\nWhat type of synchronization do you want to perform?")
    print(" 1. Full synchronization (Mirror all conversations)")
    print(" 2. Selective synchronization (Choose from the list of available conversations)")
    while True:
        option = input("Select an option (1 or 2): ").strip()
        if option == "1":
            sync_option = "full"
            break
        elif option == "2":
            sync_option = "selective"
            break
        else:
            print("Invalid option. Please select 1 or 2.")

#PHASE 1: PULL (Fetch from remote)

#Download remote history safely
try:
    print("Downloading index of remote conversations...")
    with open(remote_history_tmp, "w") as out:
        subprocess.run(
            ["ssh", remote] + wsl_prefix + ["cat ~/.gemini/antigravity-cli/history.jsonl"],
            stdout=out,
            stderr=subprocess.PIPE,
            check=True
        )
except subprocess.CalledProcessError as e:
    err_stderr = e.stderr.decode().strip()
    if "No such file or directory" in err_stderr:
        print("Warning: Remote history file not found. Starting with a blank remote history.")
    else:
        print(f"Error: Failed to fetch remote history - {err_stderr}")
        if os.path.exists(remote_history_tmp):
            os.remove(remote_history_tmp)
        sys.exit(1)

#Load histories into memory with validation against prompt injection
local_lines = []
remote_lines = []
for f, lst in [(local_history, local_lines), (remote_history_tmp, remote_lines)]:
    try:
        with open(f, encoding='utf-8') as fp:
            for line in fp:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    #Sanitize: preserve any valid dict entry that has a timestamp.
                    #Entries without conversationId (e.g. slash commands, session markers)
                    #are kept as-is so they are not silently lost during a full sync.
                    if isinstance(data, dict) and "timestamp" in data:
                        lst.append(data)
    except FileNotFoundError:
        pass

lines = local_lines + remote_lines

#Interactive selective mode: show numbered list of available conversations
#This happens here because we already have the remote history loaded in memory.
direct_target_id = None
if sync_option == "selective" and is_interactive:
    #Collect UUIDs and names from history.jsonl (local + remote)
    conv_info = {}
    for elem, is_local in [(e, True) for e in local_lines] + [(e, False) for e in remote_lines]:
        cid = elem.get("conversationId")
        if not cid:
            continue
        if cid not in conv_info:
            conv_info[cid] = {"conversationId": cid, "display": "", "timestamp": elem.get("timestamp", 0), "local": False, "remote": False}
            if elem.get("display"):
                conv_info[cid]["display"] = elem.get("display", "")
        else:
            if elem.get("timestamp", 0) < conv_info[cid]["timestamp"]:
                conv_info[cid]["timestamp"] = elem.get("timestamp", 0)
                if elem.get("display"):
                    conv_info[cid]["display"] = elem.get("display", "")
        if is_local:
            conv_info[cid]["local"] = True
        else:
            conv_info[cid]["remote"] = True

    #Remote scan via inline Python to list conversations/ and brain/
    #Using remote Python is more reliable than ls (no shell dependency, handles trailing /, etc.)
    print("Scanning conversation directories on remote...")
    scan_script = (
        "import os,glob,sys;basedir=os.path.expanduser('~/.gemini/antigravity-cli');"
        "found=set();"
        "for root in ('conversations','brain'):"
        "  p=os.path.join(basedir,root);"
        "  if os.path.isdir(p):"
        "    for f in os.listdir(p):"
        "      name=f.split('.')[0];"
        "      if len(name)==36 and name.replace('-','').isalnum():"
        "        found.add(name);"
        "for n in sorted(found): print(n)"
    )
    script_b64 = base64.urlsafe_b64encode(scan_script.encode()).decode()
    scan_cmd = f"python3 -c \"import base64; exec(base64.b64decode('{script_b64}'))\""
    try:
        r = subprocess.run(["ssh", remote] + wsl_prefix + [scan_cmd], capture_output=True, text=True, timeout=15)
        for uuid_line in r.stdout.splitlines():
            uuid_line = uuid_line.strip()
            if re.match(r"^[a-fA-F0-9-]{36}$", uuid_line):
                if uuid_line not in conv_info:
                    conv_info[uuid_line] = {"conversationId": uuid_line, "display": uuid_line[:8] + "...", "timestamp": 0, "local": False, "remote": True}
                else:
                    conv_info[uuid_line]["remote"] = True
    except Exception:
        pass

    #Local scan: list conversations/ and brain/
    for candidate_dir in [
        os.path.join(local_dir, "conversations"),
        os.path.join(local_dir, "brain")
    ]:
        if os.path.isdir(candidate_dir):
            for name in os.listdir(candidate_dir):
                uuid = name.split(".")[0]
                if re.match(r"^[a-fA-F0-9-]{36}$", uuid):
                    path = os.path.join(candidate_dir, name)
                    if os.path.isdir(path) or name.endswith(".db"):
                        if uuid not in conv_info:
                            conv_info[uuid] = {"conversationId": uuid, "display": uuid[:8] + "...", "timestamp": 0, "local": True, "remote": False}
                        else:
                            conv_info[uuid]["local"] = True

    #Sort chronologically by first message (most recent first)
    full_list = sorted(conv_info.values(), key=lambda x: x.get("timestamp", 0), reverse=True)
    if not full_list:
        print("No conversations found on either machine.")
        sys.exit(1)

    conv_list = list(full_list)
    while True:
        print(f"\nAvailable conversations ({len(conv_list)} total):")
        for idx, conv in enumerate(conv_list, 1):
            in_local = conv.get("local", False)
            in_remote = conv.get("remote", False)
            origin = "both" if in_local and in_remote else ("remote" if in_remote else "local")
            display_text = (conv.get("display", "") or "")[:70]
            print(f" {idx:>2}. [{origin:<6}]  {display_text}")
        if len(conv_list) < len(full_list):
            sel = input(f"\nConversation number, keyword to filter, or 'all' to show full list: ").strip()
        else:
            sel = input(f"\nConversation number, keyword to search, or 'exit': ").strip()
        if sel.lower() in ('exit', 'c', 'q'):
            print("Synchronization canceled.")
            if os.path.exists(remote_history_tmp):
                os.remove(remote_history_tmp)
            sys.exit(0)
        if sel.lower() == 'all' and len(conv_list) < len(full_list):
            conv_list = list(full_list)
            continue
        try:
            sel_idx = int(sel) - 1
            if 0 <= sel_idx < len(conv_list):
                direct_target_id = conv_list[sel_idx].get("conversationId")
                print(f"Selected conversation: '{conv_list[sel_idx].get('display', '')[:70]}'")
                direct_selection = True
                break
            else:
                print("That number is not in the list. Try again.")
        except ValueError:
            if not sel:
                continue
            filter_text = normalize(sel)
            filtered = [c for c in full_list if filter_text in normalize(extract_text(c))]
            if not filtered:
                print(f"No conversation contains '{sel}'.")
                continue
            conv_list = filtered

#Resolve specific conversation ID if sync_name is provided
target_id = None
if sync_name:
    norm_search = normalize(sync_name)

    #Group all messages by conversationId to search the full content
    #of each conversation and use the oldest message as its visible representative.
    #This avoids false positives from substrings (e.g. "list" in "minimalist")
    #and ensures the result always shows the session's initial message.
    conv_groups = {}
    for item in lines:
        conv_id = item.get("conversationId")
        if not conv_id:
            continue
        if conv_id not in conv_groups:
            conv_groups[conv_id] = []
        conv_groups[conv_id].append(item)

    #Search without word boundaries to capture partial matches,
    #and across all text fields (display, parts, text, content) to
    #not rely solely on the AI-generated title.
    pattern = re.compile(re.escape(norm_search))
    matches = []
    for conv_id, messages in conv_groups.items():
        found = any(pattern.search(normalize(extract_text(m))) for m in messages)
        if found:
            representative = min(messages, key=lambda x: x.get("timestamp", 0))
            matches.append(representative)

    if not matches:
        print(f"Error: No conversation matching '{sync_name}' was found.")
        sys.exit(1)
    elif len(matches) > 1:
        if is_interactive:
            print(f"\nMultiple conversations found matching '{sync_name}':")
            for idx, m in enumerate(matches, 1):
                print(f" {idx}. '{m.get('display')}' (ID: {m.get('conversationId')})")
            while True:
                try:
                    sel = input(f"Select an option (1-{len(matches)}) or type 'c' to cancel: ").strip()
                    if sel.lower() == 'c':
                        print("Synchronization canceled by user.")
                        if os.path.exists(remote_history_tmp):
                            os.remove(remote_history_tmp)
                        sys.exit(0)
                    sel_idx = int(sel) - 1
                    if 0 <= sel_idx < len(matches):
                        target_id = matches[sel_idx].get("conversationId")
                        print(f"Selected conversation: '{matches[sel_idx].get('display')}'")
                        break
                    else:
                        print("Number out of range. Please try again.")
                except ValueError:
                    print("Invalid input. Enter a number or 'c'.")
        else:
            print(f"Error: Ambiguity detected. Multiple conversations matched '{sync_name}':")
            for m in matches:
                print(f" - '{m.get('display')}' (ID: {m.get('conversationId')})")
            sys.exit(1)
    else:
        target_id = matches[0].get("conversationId")
        print(f"Selected conversation: '{matches[0].get('display')}' (ID: {target_id})")

#Validate target_id format to prevent command injection
if target_id and not re.match(r"^[a-fA-F0-9-]{36}$", target_id):
    print("Error: Target conversation ID has an invalid format.")
    sys.exit(1)

#Determine where the target conversation exists
exists_locally = True
exists_remotely = True
if target_id:
    exists_locally = any(item.get("conversationId") == target_id for item in local_lines)
    exists_remotely = any(item.get("conversationId") == target_id for item in remote_lines)

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
if not target_id or exists_remotely:
    active_id = os.environ.get("ACTIVE_CONVERSATION_ID")
    #Validate active_id format to prevent command injection
    if active_id and not re.match(r"^[a-fA-F0-9-]{36}$", active_id):
        active_id = None

    #Build remote Python command using base64 to avoid shell interpretation issues
    if target_id:
        pull_script = (
            "import sys, os, tarfile, glob; "
            f"basedir = os.path.expanduser('~/.gemini/antigravity-cli'); "
            f"os.chdir(basedir); "
            f"tar = tarfile.open(fileobj=sys.stdout.buffer, mode='w:gz'); "
            f"files = glob.glob('brain/{target_id}') + glob.glob('conversations/{target_id}.*'); "
            f"[tar.add(f) for f in files]; tar.close()"
        )
    else:
        pull_script = (
            "import sys, os, tarfile, glob; "
            "basedir = os.path.expanduser('~/.gemini/antigravity-cli'); "
            "os.chdir(basedir); "
            "tar = tarfile.open(fileobj=sys.stdout.buffer, mode='w:gz'); "
            "files = glob.glob('brain') + glob.glob('conversations') + glob.glob('installation_id'); "
            "[tar.add(f) for f in files]; tar.close()"
        )

    script_b64 = base64.urlsafe_b64encode(pull_script.encode()).decode()
    remote_cmd = f"python3 -c \"import base64; exec(base64.b64decode('{script_b64}'))\""

    print("Pulling files from remote...")
    p1 = subprocess.Popen(["ssh", remote] + wsl_prefix + [remote_cmd], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    try:
        #Extract files locally using Python's tarfile module
        #filter='data' (Python 3.12+) blocks path traversal attacks safely.
        #Older versions fall back to default behavior which is acceptable for trusted SSH sources.
        _use_filter = sys.version_info >= (3, 12)
        with tarfile.open(fileobj=p1.stdout, mode="r|gz") as tar:
            for member in tar:
                #Exclude active session files to prevent SQL database corruption
                if active_id and (member.name.startswith(f"conversations/{active_id}") or member.name.startswith(f"brain/{active_id}")):
                    continue
                #Ensure local directory structure exists
                dest_path = os.path.join(local_dir, member.name)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                if _use_filter:
                    tar.extract(member, path=local_dir, filter='data')
                else:
                    tar.extract(member, path=local_dir)
        p1.wait()
        if p1.returncode != 0:
            raise RuntimeError(f"Remote command failed with code {p1.returncode}")
        print("Pull complete.")
    except Exception as e:
        print(f"Error during PULL file transfer: {e}")
        p1.kill()
        sys.exit(1)
else:
    print("Conversation does not exist on remote. Skipping file pull.")

#PHASE 2: PUSH (Send back to remote)

#Push the merged master history back to the remote server safely
try:
    print("Pushing updated index of conversations back to remote...")
    with open(local_history, "r") as hist_in:
        subprocess.run(
            ["ssh", remote] + wsl_prefix + ["bash -c 'cat > ~/.gemini/antigravity-cli/history.jsonl'"],
            stdin=hist_in,
            stderr=subprocess.PIPE,
            check=True
        )
except subprocess.CalledProcessError as e:
    print(f"Error during PUSH history update: {e.stderr.decode().strip()}")
    sys.exit(1)

#Push our local databases and memories back to the remote server safely
if not target_id or exists_locally:
    files_to_push = []
    if target_id:
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
    else:
        # Full sync files
        for item in ["brain", "conversations"]:
            if os.path.exists(os.path.join(local_dir, item)):
                files_to_push.append(item)

    if files_to_push:
        print("Pushing files to remote...")
        #Command on remote to extract files from stdin (base64 to avoid shell issues)
        extract_script = (
            "import sys, os, tarfile; "
            "basedir = os.path.expanduser('~/.gemini/antigravity-cli'); "
            "os.makedirs(basedir, exist_ok=True); "
            "os.chdir(basedir); "
            "tar = tarfile.open(fileobj=sys.stdin.buffer, mode='r|gz'); "
            "tar.extractall(); tar.close()"
        )
        script_b64 = base64.urlsafe_b64encode(extract_script.encode()).decode()
        remote_extract_cmd = f"python3 -c \"import base64; exec(base64.b64decode('{script_b64}'))\""

        p2 = subprocess.Popen(["ssh", remote] + wsl_prefix + [remote_extract_cmd], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

        try:
            #Create tarball locally in Python and write directly to the SSH stdin stream
            with tarfile.open(fileobj=p2.stdin, mode="w:gz") as tar:
                for path in files_to_push:
                    #Add target to tar with relative path inside local_dir
                    tar.add(os.path.join(local_dir, path), arcname=path)
            p2.stdin.close()
            p2.wait()
            if p2.returncode != 0:
                raise RuntimeError(f"Remote command failed with code {p2.returncode}")
            print("Push complete.")
        except Exception as e:
            print(f"Error during PUSH file transfer: {e}")
            p2.kill()
            sys.exit(1)
else:
    print("Conversation does not exist locally. Skipping file push.")

print("\n--- Synchronization completed successfully! ---")
