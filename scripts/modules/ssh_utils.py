"""SSH operations: connection, WSL detection, file transfer via tar."""

import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile

from modules.config import SSH_TIMEOUT, REMOTE_TMP, BASE_DIR


# Detect if remote host uses WSL by running wsl --status
def detect_wsl(host):
    """Detect if remote host uses WSL by running wsl --status."""
    try:
        r = subprocess.run(
            ["ssh", host, "wsl --status"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


# Check SSH connection with timeout and optional WSL prefix
def verify_ssh(host, use_wsl):
    """Check SSH connection with timeout and optional WSL prefix."""
    try:
        print(f"Checking SSH connection to {host}...")
        cmd = ["ssh", "-o", f"ConnectTimeout={SSH_TIMEOUT}", host]
        if use_wsl:
            cmd.append("wsl")
        cmd.append("true")
        subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        print("SSH connection successful.\n")
        return True
    except (subprocess.CalledProcessError, Exception):
        print(f"  Could not connect to '{host}'.")
        return False


# Build SSH argument list with optional WSL prefix
def build_ssh_cmd(host, use_wsl, remote_command):
    """Build SSH argument list with optional WSL prefix."""
    cmd = ["ssh", host]
    if use_wsl:
        cmd.append("wsl")
    cmd.append(remote_command)
    return cmd


# Remove temp file ignoring errors
def _cleanup_temp(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


# Download remote history.jsonl to temp file and return list of entries
def download_remote_history(host, use_wsl):
    """Download remote history.jsonl to temp file and return list of entries."""
    cmd = build_ssh_cmd(host, use_wsl, "cat ~/.gemini/antigravity-cli/history.jsonl")
    try:
        with open(REMOTE_TMP, "w") as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode(errors="replace").strip()
        if "No such file or directory" in err:
            print(
                "Warning: Remote history not found. Starting with empty remote history."
            )
            _cleanup_temp(REMOTE_TMP)
            return []
        print(f"Error: Could not fetch remote history - {err}")
        _cleanup_temp(REMOTE_TMP)
        sys.exit(1)

    lines = []
    try:
        with open(REMOTE_TMP, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    data = json.loads(stripped)
                    if isinstance(data, dict) and "timestamp" in data:
                        lines.append(data)
    except FileNotFoundError:
        pass

    _cleanup_temp(REMOTE_TMP)
    return lines


# Scan remote conversations/ and brain/ directories via inline Python, return set of UUIDs
def scan_remote_conversations(host, use_wsl):
    """Scan remote conversations/ and brain/ directories via inline Python, return set of UUIDs."""
    script = (
        "import os,glob,sys;"
        "basedir=os.path.expanduser('~/.gemini/antigravity-cli');"
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
    cmd = build_ssh_cmd(host, use_wsl, f'python3 -c "{script}"')
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        uuids = set()
        for line in r.stdout.splitlines():
            stripped = line.strip()
            if re.match(r"^[a-fA-F0-9-]{36}$", stripped):
                uuids.add(stripped)
        return uuids
    except Exception:
        return set()


# Download files from remote via tar over SSH. If target_id, only that conversation. skip_id excludes active session.
def download_files_via_tar(host, use_wsl, target_id=None, skip_id=None):
    """Download files from remote via tar over SSH. If target_id, only that conversation. skip_id excludes active session."""
    if target_id:
        script = (
            "import sys,os,tarfile,glob;"
            "basedir=os.path.expanduser('~/.gemini/antigravity-cli');"
            "os.chdir(basedir);"
            f"tar=tarfile.open(fileobj=sys.stdout.buffer,mode='w:gz');"
            f"files=glob.glob('brain/{target_id}')+glob.glob('conversations/{target_id}.*');"
            "[tar.add(f) for f in files];tar.close()"
        )
    else:
        script = (
            "import sys,os,tarfile,glob;"
            "basedir=os.path.expanduser('~/.gemini/antigravity-cli');"
            "os.chdir(basedir);"
            "tar=tarfile.open(fileobj=sys.stdout.buffer,mode='w:gz');"
            "files=glob.glob('brain')+glob.glob('conversations')+glob.glob('installation_id');"
            "[tar.add(f) for f in files];tar.close()"
        )

    cmd = build_ssh_cmd(host, use_wsl, f'python3 -c "{script}"')
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    try:
        use_filter = sys.version_info >= (3, 12)
        with tarfile.open(fileobj=proc.stdout, mode="r|gz") as tar:
            for member in tar:
                if skip_id and (
                    member.name.startswith(f"conversations/{skip_id}")
                    or member.name.startswith(f"brain/{skip_id}")
                ):
                    continue
                dest_path = os.path.join(BASE_DIR, member.name)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                if use_filter:
                    tar.extract(member, path=BASE_DIR, filter="data")
                else:
                    tar.extract(member, path=BASE_DIR)
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"Remote command failed with code {proc.returncode}")
        print("Download complete.")
        return True
    except Exception as e:
        print(f"Error during download transfer: {e}")
        proc.kill()
        return False


# Upload local files to remote via tar over SSH
def upload_files_via_tar(host, use_wsl, paths):
    """Upload local files to remote via tar over SSH."""
    script = (
        "import sys,os,tarfile;"
        "basedir=os.path.expanduser('~/.gemini/antigravity-cli');"
        "os.makedirs(basedir,exist_ok=True);"
        "os.chdir(basedir);"
        "tar_remote=tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz');"
        "kwargs={'filter':'data'} if sys.version_info>=(3,12) else {};"
        "tar_remote.extractall(**kwargs);tar_remote.close()"
    )

    cmd = build_ssh_cmd(host, use_wsl, f'python3 -c "{script}"')
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    try:
        with tarfile.open(fileobj=proc.stdin, mode="w|gz") as tar:
            for path in paths:
                tar.add(os.path.join(BASE_DIR, path), arcname=path)
        if proc.stdin:
            proc.stdin.close()
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"Remote command failed with code {proc.returncode}")
        print("Upload complete.")
        return True
    except Exception as e:
        print(f"Error during upload transfer: {e}")
        proc.kill()
        return False


# Upload history entries to remote using temp file to avoid broken pipes
def upload_history_data(host, use_wsl, lines):
    """Upload history entries to remote using temp file to avoid broken pipes."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
        for elem in lines:
            f.write(json.dumps(elem, separators=(",", ":")) + "\n")
        tmp_path = f.name

    try:
        cmd = build_ssh_cmd(
            host, use_wsl, "cat > ~/.gemini/antigravity-cli/history.jsonl"
        )
        print("Uploading updated conversation index to remote...")
        with open(tmp_path, "r") as f:
            subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        print(
            f"Error during history upload: {e.stderr.decode(errors='replace').strip()}"
        )
        sys.exit(1)
    finally:
        _cleanup_temp(tmp_path)
