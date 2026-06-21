"""Orchestration of full sync, pull, push, and bidirectional."""

import os
import re
import sys

from modules.config import BASE_DIR, HISTORY_FILE
from modules.history import (
    load_history,
    save_history,
    merge_and_dedup,
)
from modules.ssh_utils import (
    download_remote_history,
    download_files_via_tar,
    upload_files_via_tar,
    upload_history_data,
)


# Get active conversation ID from environment to avoid transferring in-use DBs
def _get_active_id():
    return os.environ.get("ACTIVE_CONVERSATION_ID")


# Collect relative paths of local files for a specific conversation
def _get_local_conversation_paths(target_id):
    paths = []
    brain_path = os.path.join(BASE_DIR, "brain", target_id)
    if os.path.exists(brain_path):
        paths.append(os.path.join("brain", target_id))
    conv_dir = os.path.join(BASE_DIR, "conversations")
    if os.path.exists(conv_dir):
        for fname in os.listdir(conv_dir):
            if fname.startswith(target_id):
                paths.append(os.path.join("conversations", fname))
    return paths


# Full sync: merge histories, download everything from remote, upload everything local
def complete_sync(host, use_wsl):
    """Full sync: merge histories, download everything from remote, upload everything local."""
    local_lines = load_history(HISTORY_FILE)
    remote_lines = download_remote_history(host, use_wsl)

    merged = merge_and_dedup(local_lines, remote_lines)
    save_history(HISTORY_FILE, merged)
    print("Full history merged and updated.")

    active_id = _get_active_id()
    if active_id and not re.match(r"^[a-fA-F0-9-]{36}$", active_id):
        active_id = None

    ok = download_files_via_tar(host, use_wsl, skip_id=active_id)
    if not ok:
        sys.exit(1)

    paths = []
    for item in ["brain", "conversations"]:
        path = os.path.join(BASE_DIR, item)
        if os.path.exists(path):
            paths.append(item)
    if paths:
        ok = upload_files_via_tar(host, use_wsl, paths)
        if not ok:
            sys.exit(1)

    upload_history_data(host, use_wsl, merged)

    print("\n--- Synchronization completed successfully! ---")


# Pull: bring a specific conversation from remote to local
def pull_conversation(host, use_wsl, target_id):
    """Pull: bring a specific conversation from remote to local."""
    local_lines = load_history(HISTORY_FILE)
    remote_lines = download_remote_history(host, use_wsl)

    if not any(e.get("conversationId") == target_id for e in remote_lines):
        print("Conversation does not exist on remote. Skipping download.")
        return

    merged = merge_and_dedup(local_lines, remote_lines)

    if not any(e.get("conversationId") == target_id for e in local_lines):
        target = next(
            (e for e in merged if e.get("conversationId") == target_id),
            None,
        )
        if target:
            local_lines.append(target)
            local_lines.sort(key=lambda x: x.get("timestamp", 0))
            save_history(HISTORY_FILE, local_lines)
            print("History updated with the selected conversation.")

    active_id = _get_active_id()
    if active_id and not re.match(r"^[a-fA-F0-9-]{36}$", active_id):
        active_id = None

    ok = download_files_via_tar(
        host, use_wsl, target_id=target_id, skip_id=active_id
    )
    if not ok:
        sys.exit(1)


#Push: send a specific conversation from local to remote
def push_conversation(host, use_wsl, target_id):
    """Push: send a specific conversation from local to remote."""
    local_lines = load_history(HISTORY_FILE)
    remote_lines = download_remote_history(host, use_wsl)

    if not any(e.get("conversationId") == target_id for e in local_lines):
        print("Conversation does not exist locally. Skipping upload.")
        return

    remote_keys = set(
        str(e.get("timestamp")) + str(e.get("conversationId", ""))
        for e in remote_lines
    )
    lines_to_upload = list(remote_lines)
    for elem in local_lines:
        if elem.get("conversationId") == target_id:
            key = str(elem.get("timestamp")) + str(elem.get("conversationId", ""))
            if key not in remote_keys:
                lines_to_upload.append(elem)
                remote_keys.add(key)
    lines_to_upload.sort(key=lambda x: x.get("timestamp", 0))

    upload_history_data(host, use_wsl, lines_to_upload)

    paths = _get_local_conversation_paths(target_id)
    if paths:
        ok = upload_files_via_tar(host, use_wsl, paths)
        if not ok:
            sys.exit(1)
    else:
        print("No local files found to upload.")


# Bidi: sequential pull + push of a single conversation
def bidi_conversation(host, use_wsl, target_id):
    """Bidi: sequential pull + push of a single conversation."""
    pull_conversation(host, use_wsl, target_id)
    push_conversation(host, use_wsl, target_id)
