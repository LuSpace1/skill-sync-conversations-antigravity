"""Load, merge, search, and normalize conversation history."""

import json
import os
import re
import unicodedata


# Normalize text to lowercase and without accents for searching
def normalize(text):
    """Normalize text to lowercase and without accents for searching."""
    if not text:
        return ""
    text = text.lower().strip()
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


# Extract all readable text from an entry (display, parts, text, content)
def extract_text(entry):
    """Extract all readable text from an entry (display, parts, text, content)."""
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


# Load history from JSONL file, filtering valid entries with timestamp
def load_history(path):
    """Load history from JSONL file, filtering valid entries with timestamp."""
    lines = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    data = json.loads(stripped)
                    if isinstance(data, dict) and "timestamp" in data:
                        lines.append(data)
    except FileNotFoundError:
        pass
    return lines


# Save history to JSONL with atomic write via .tmp + os.replace
def save_history(path, lines):
    """Save history to JSONL with atomic write via .tmp + os.replace."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for elem in lines:
            f.write(json.dumps(elem, separators=(",", ":")) + "\n")
    os.replace(tmp, path)


# Merge two histories sorted by timestamp, deduplicating by (ts, conversationId)
def merge_and_dedup(local_lines, remote_lines):
    """Merge two histories sorted by timestamp, deduplicating by (ts, conversationId)."""
    seen = set()
    merged = []
    all_items = sorted(local_lines + remote_lines, key=lambda x: x.get("timestamp", 0))
    for elem in all_items:
        key = str(elem.get("timestamp")) + str(elem.get("conversationId", ""))
        if key not in seen:
            seen.add(key)
            merged.append(elem)
    return merged


# Search conversations whose text matches a term (partial, normalized search)
def search_conversations(term, lines):
    """Search conversations whose text matches a term (partial, normalized search)."""
    from modules.db_sync import get_db_titles

    search_term = normalize(term)
    pattern = re.compile(re.escape(search_term))
    groups = {}
    for elem in lines:
        cid = elem.get("conversationId")
        if not cid:
            continue
        if cid not in groups:
            groups[cid] = []
        groups[cid].append(elem)

    # Enrich with database titles
    db_titles = get_db_titles()

    matches = []
    # 1. Match from history messages
    matched_cids = set()
    for cid, messages in groups.items():
        if any(pattern.search(normalize(extract_text(m))) for m in messages):
            matches.append(min(messages, key=lambda x: x.get("timestamp", 0)))
            matched_cids.add(cid)

    # 2. Match from database titles if not already matched
    for cid, info in db_titles.items():
        if cid not in matched_cids:
            title_text = f"{info.get('title', '')} {info.get('preview', '')}"
            if pattern.search(normalize(title_text)):
                # If conversation exists in history, pick its earliest message
                if cid in groups:
                    matches.append(min(groups[cid], key=lambda x: x.get("timestamp", 0)))
                else:
                    matches.append({
                        "conversationId": cid,
                        "display": info.get("title") or info.get("preview") or cid,
                        "timestamp": 0,
                    })
                matched_cids.add(cid)

    return matches


# Collect metadata of each conversation from both histories for interactive listing
def collect_conversation_info(local_lines, remote_lines):
    """Collect metadata of each conversation from both histories for interactive listing."""
    from modules.db_sync import get_db_titles

    db_titles = get_db_titles()
    conv_info = {}
    for elem, is_local in [(e, True) for e in local_lines] + [
        (e, False) for e in remote_lines
    ]:
        cid = elem.get("conversationId")
        if not cid:
            continue
        if cid not in conv_info:
            conv_info[cid] = {
                "conversationId": cid,
                "display": "",
                "display_ts": 0,
                "timestamp": elem.get("timestamp", 0),
                "local": False,
                "remote": False,
                "text_content": "",
            }
            if elem.get("display"):
                conv_info[cid]["display"] = elem.get("display", "")
                conv_info[cid]["display_ts"] = elem.get("timestamp", 0)
        else:
            if elem.get("timestamp", 0) < conv_info[cid]["timestamp"]:
                conv_info[cid]["timestamp"] = elem.get("timestamp", 0)
            if (
                elem.get("display")
                and elem.get("timestamp", 0) > conv_info[cid]["display_ts"]
            ):
                conv_info[cid]["display"] = elem.get("display", "")
                conv_info[cid]["display_ts"] = elem.get("timestamp", 0)
        if is_local:
            conv_info[cid]["local"] = True
        else:
            conv_info[cid]["remote"] = True
        if not conv_info[cid]["text_content"]:
            text = extract_text(elem)
            if text and not text.startswith("/"):
                conv_info[cid]["text_content"] = text[:70]

    # If display is a slash command or empty, enrich with DB title
    for cid, info in conv_info.items():
        if cid in db_titles:
            db_title = db_titles[cid].get("title")
            if db_title and (not info["display"] or info["display"].startswith("/")):
                info["display"] = db_title

    return conv_info
