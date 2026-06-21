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

# Interactive prompt for SSH host if not provided
if not raw_remote:
    print("Sincronización de Conversaciones - Antigravity CLI")
    while True:
        raw_remote = input("* Introduce el host remoto o alias de SSH (ej. pc, portatil, usuario@host): ").strip()
        if not raw_remote:
            print("El host remoto no puede estar vacío.")
            continue
        if not re.match(r"^(?:[a-zA-Z0-9_.-]+@)?[a-zA-Z0-9_.-]+$", raw_remote):
            print("Formato de host inválido. Intenta de nuevo.")
            continue
        break

# Interactive prompt for sync type if not specified via --name and running in a terminal
if not sync_name and is_interactive and len(sys.argv) <= 2:
    print("\n¿Qué tipo de sincronización deseas realizar?")
    print(" 1. Sincronización completa (Espejo de todas las conversaciones)")
    print(" 2. Sincronización selectiva (Una conversación específica)")
    while True:
        opcion = input("Selecciona una opción (1 o 2): ").strip()
        if opcion == "1":
            sync_name = None
            break
        elif opcion == "2":
            while True:
                sync_name = input("Introduce el título o palabras clave de la conversación: ").strip()
                if not sync_name:
                    print("El nombre de la conversación no puede estar vacío.")
                    continue
                break
            break
        else:
            print("Opción inválida. Por favor, selecciona 1 o 2.")

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

# PRE-FLIGHT CHECK: Verify SSH connection is active and valid before doing anything
try:
    print(f"\nChecking SSH connection to {remote}...")
    subprocess.run(["ssh", "-o", "ConnectTimeout=10", remote] + wsl_prefix + ["true"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    print("SSH connection successful.")
except (subprocess.CalledProcessError, Exception) as e:
    err_msg = ""
    if isinstance(e, subprocess.CalledProcessError):
        err_msg = e.stderr.decode().strip()
    print(f"Error: Unable to establish an SSH connection to '{remote}'.")
    if err_msg:
        print(f"Details: {err_msg}")
    print("Please check your SSH configuration or network connection.")
    sys.exit(1)

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
                    #Sanitize: ensure valid keys to prevent arbitrary payload injections
                    if isinstance(data, dict) and "timestamp" in data and "conversationId" in data:
                        lst.append(data)
    except FileNotFoundError:
        pass

lines = local_lines + remote_lines

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
            print(f"\nSe encontraron múltiples conversaciones que coinciden con '{sync_name}':")
            for idx, m in enumerate(matches, 1):
                print(f" {idx}. '{m.get('display')}' (ID: {m.get('conversationId')})")
            while True:
                try:
                    sel = input(f"Selecciona una opción (1-{len(matches)}) o escribe 'c' para cancelar: ").strip()
                    if sel.lower() == 'c':
                        print("Sincronización cancelada por el usuario.")
                        if os.path.exists(remote_history_tmp):
                            os.remove(remote_history_tmp)
                        sys.exit(0)
                    sel_idx = int(sel) - 1
                    if 0 <= sel_idx < len(matches):
                        target_id = matches[sel_idx].get("conversationId")
                        print(f"Conversación seleccionada: '{matches[sel_idx].get('display')}'")
                        break
                    else:
                        print("Número fuera de rango. Por favor intenta de nuevo.")
                except ValueError:
                    print("Entrada inválida. Introduce un número o 'c'.")
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

# Determine where the target conversation exists
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

    if target_id:
        # Package only matching files using Python on the remote (no shell dependency)
        remote_cmd = (
            f"(python3 -c \"import sys, os, tarfile, glob; "
            f"os.chdir(os.path.expanduser('~/.gemini/antigravity-cli')) if os.path.exists(os.path.expanduser('~/.gemini/antigravity-cli')) else sys.exit(1); "
            f"tar = tarfile.open(fileobj=sys.stdout.buffer, mode='w:gz'); "
            f"files = glob.glob('brain/{target_id}') + glob.glob('conversations/{target_id}.*'); "
            f"[tar.add(f) for f in files]; tar.close()\" 2>/dev/null || "
            f"python -c \"import sys, os, tarfile, glob; "
            f"os.chdir(os.path.expanduser('~/.gemini/antigravity-cli')) if os.path.exists(os.path.expanduser('~/.gemini/antigravity-cli')) else sys.exit(1); "
            f"tar = tarfile.open(fileobj=sys.stdout.buffer, mode='w:gz'); "
            f"files = glob.glob('brain/{target_id}') + glob.glob('conversations/{target_id}.*'); "
            f"[tar.add(f) for f in files]; tar.close()\")"
        )
    else:
        # Full package using Python on the remote
        remote_cmd = (
            "(python3 -c \"import sys, os, tarfile, glob; "
            "os.chdir(os.path.expanduser('~/.gemini/antigravity-cli')) if os.path.exists(os.path.expanduser('~/.gemini/antigravity-cli')) else sys.exit(1); "
            "tar = tarfile.open(fileobj=sys.stdout.buffer, mode='w:gz'); "
            "files = glob.glob('brain') + glob.glob('conversations') + glob.glob('installation_id'); "
            "[tar.add(f) for f in files]; tar.close()\" 2>/dev/null || "
            "python -c \"import sys, os, tarfile, glob; "
            "os.chdir(os.path.expanduser('~/.gemini/antigravity-cli')) if os.path.exists(os.path.expanduser('~/.gemini/antigravity-cli')) else sys.exit(1); "
            "tar = tarfile.open(fileobj=sys.stdout.buffer, mode='w:gz'); "
            "files = glob.glob('brain') + glob.glob('conversations') + glob.glob('installation_id'); "
            "[tar.add(f) for f in files]; tar.close()\")"
        )

    print("Pulling files from remote...")
    p1 = subprocess.Popen(["ssh", remote] + wsl_prefix + [remote_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    try:
        # Extract files locally using Python's tarfile module
        with tarfile.open(fileobj=p1.stdout, mode="r|gz") as tar:
            for member in tar:
                # Exclude active session files to prevent SQL database corruption
                if active_id and (member.name.startswith(f"conversations/{active_id}") or member.name.startswith(f"brain/{active_id}")):
                    continue
                # Ensure local directory structure exists
                dest_path = os.path.join(local_dir, member.name)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                tar.extract(member, path=local_dir)
        p1.wait()
        if p1.returncode != 0:
            err_out = p1.stderr.read().decode().strip()
            raise RuntimeError(f"Remote command failed with code {p1.returncode}: {err_out}")
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
        # Command on remote to extract files from stdin
        remote_extract_cmd = (
            "python3 -c \"import sys, os, tarfile; "
            "os.chdir(os.path.expanduser('~/.gemini/antigravity-cli')) if os.path.exists(os.path.expanduser('~/.gemini/antigravity-cli')) else sys.exit(1); "
            "tar = tarfile.open(fileobj=sys.stdin.buffer, mode='r|gz'); "
            "tar.extractall(); tar.close()\" 2>/dev/null || "
            "python -c \"import sys, os, tarfile; "
            "os.chdir(os.path.expanduser('~/.gemini/antigravity-cli')) if os.path.exists(os.path.expanduser('~/.gemini/antigravity-cli')) else sys.exit(1); "
            "tar = tarfile.open(fileobj=sys.stdin.buffer, mode='r|gz'); "
            "tar.extractall(); tar.close()\""
        )

        p2 = subprocess.Popen(["ssh", remote] + wsl_prefix + [remote_extract_cmd], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        
        try:
            # Create tarball locally in Python and write directly to the SSH stdin stream
            with tarfile.open(fileobj=p2.stdin, mode="w:gz") as tar:
                for path in files_to_push:
                    # add target to tar with relative path inside local_dir
                    tar.add(os.path.join(local_dir, path), arcname=path)
            p2.stdin.close()
            p2.wait()
            if p2.returncode != 0:
                err_out = p2.stderr.read().decode().strip()
                raise RuntimeError(f"Remote command failed with code {p2.returncode}: {err_out}")
            print("Push complete.")
        except Exception as e:
            print(f"Error during PUSH file transfer: {e}")
            p2.kill()
            sys.exit(1)
else:
    print("Conversation does not exist locally. Skipping file push.")

print("\n--- ¡Sincronización completada exitosamente! ---")
