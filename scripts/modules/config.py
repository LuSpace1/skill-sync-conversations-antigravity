"""Constants, paths, and shared regular expressions."""

import os
import re
import tempfile

# Antigravity CLI base directory
BASE_DIR = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-cli")
# Local history file
HISTORY_FILE = os.path.join(BASE_DIR, "history.jsonl")
# Temporary file for downloaded remote history
REMOTE_TMP = os.path.join(tempfile.gettempdir(), "history.jsonl.remote")

# UUID v4 regex with dashes (36 characters)
UUID_REGEX = re.compile(r"^[a-fA-F0-9-]{36}$")
# SSH alias regex: user@host or host only
HOST_REGEX = re.compile(r"^(?:[a-zA-Z0-9_.-]+@)?[a-zA-Z0-9_.-]+$")

# SSH connection timeout in seconds
SSH_TIMEOUT = "10"
