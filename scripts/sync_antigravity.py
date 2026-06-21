#!/usr/bin/env python3
"""Entry point: CLI, arguments, and interactive sync menu."""

import argparse
import os
import sys

from modules.config import REMOTE_TMP, UUID_REGEX, HOST_REGEX
from modules.history import (
    normalize,
    load_history,
    collect_conversation_info,
    search_conversations,
)
from modules.ssh_utils import (
    detect_wsl,
    verify_ssh,
    scan_remote_conversations,
    download_remote_history,
)
from modules.sync import (
    complete_sync,
    pull_conversation,
    push_conversation,
    bidi_conversation,
)


# Remove remote history temp file if it exists
def _cleanup_remote_tmp():
    if os.path.exists(REMOTE_TMP):
        try:
            os.remove(REMOTE_TMP)
        except OSError:
            pass


# Clean exit: remove temp file, show optional message, and exit with code
def _exit(message=None, code=1):
    _cleanup_remote_tmp()
    if message:
        print(message)
    sys.exit(code)


# Scan local conversations/ and brain/ directories for UUIDs without history.jsonl entries
def _scan_local_conversations(local_dir):
    conv_info = {}
    for candidate_dir in [
        os.path.join(local_dir, "conversations"),
        os.path.join(local_dir, "brain"),
    ]:
        if not os.path.isdir(candidate_dir):
            continue
        for name in os.listdir(candidate_dir):
            uuid = name.split(".")[0]
            if not UUID_REGEX.match(uuid):
                continue
            path = os.path.join(candidate_dir, name)
            if os.path.isdir(path) or name.endswith(".db"):
                if uuid not in conv_info:
                    conv_info[uuid] = {
                        "conversationId": uuid,
                        "display": uuid[:8] + "...",
                        "timestamp": 0,
                        "local": True,
                        "remote": False,
                        "text_content": "",
                    }
                else:
                    conv_info[uuid]["local"] = True
    return conv_info


# Interactive prompt to choose sync direction (pull/push/bidi)
def _prompt_direction():
    print("\nDirection for selective sync?")
    print(" 1. Pull from remote \u2192 bring conversation from remote to this PC")
    print(" 2. Push to remote \u2192 send conversation from this PC to remote")
    print(" 3. Sync both (bidirectional)")
    while True:
        option = input(
            "Select an option (1-3), or 'stop' to cancel: "
        ).strip()
        if option.lower() in ("stop", "c", "q"):
            _exit("Synchronization canceled.")
        if option == "1":
            return "pull"
        elif option == "2":
            return "push"
        elif option == "3":
            return "bidi"
        print("Invalid option. Select 1, 2, 3 or 'stop'.")


# Interactive prompt to select a conversation from the list, with keyword filter
def _select_conversation(conv_list, full_list, direction):
    while True:
        print(f"\nAvailable conversations ({len(conv_list)} total):")
        for idx, conv in enumerate(conv_list, 1):
            local = conv.get("local", False)
            remote = conv.get("remote", False)
            origin = "both" if local and remote else ("remote" if remote else "local")
            name = conv.get("display", "") or ""
            if name.startswith("/") and conv.get("text_content"):
                name = conv["text_content"]
            print(f" {idx:>2}. [{origin:<6}]  {name[:70]}")

        if len(conv_list) < len(full_list):
            sel = input(
                "\nConversation number, keyword to filter, "
                "or 'all' to show full list: "
            ).strip()
        else:
            sel = input(
                "\nConversation number, keyword to search, or 'stop': "
            ).strip()

        if sel.lower() in ("stop", "c", "q"):
            _exit("Synchronization canceled.")
        if sel.lower() == "all" and len(conv_list) < len(full_list):
            conv_list = list(full_list)
            continue

        try:
            sel_idx = int(sel) - 1
            if 0 <= sel_idx < len(conv_list):
                c_sel = conv_list[sel_idx]
                name_sel = c_sel.get("display", "") or ""
                if name_sel.startswith("/") and c_sel.get("text_content"):
                    name_sel = c_sel["text_content"]
                print(f"Selected conversation: '{name_sel[:70]}'")
                return c_sel.get("conversationId")
            print("That number is not in the list. Try again.")
        except ValueError:
            if not sel:
                continue
            filter_text = normalize(sel)
            filtered = [
                c
                for c in full_list
                if filter_text in normalize(c.get("display", "") or "")
                or filter_text in normalize(c.get("text_content", "") or "")
            ]
            if not filtered:
                print(f"No conversation contains '{sel}'.")
                continue
            conv_list = filtered


def main():
    """Entry point: CLI, arguments, and interactive sync menu."""
    parser = argparse.ArgumentParser(
        description="Synchronize Antigravity CLI conversations."
    )
    parser.add_argument(
        "remote", nargs="?", help="Remote host alias or user@host."
    )
    parser.add_argument(
        "-n", "--name", help="Specific conversation title/display name to sync."
    )
    args = parser.parse_args()

    remote_raw = args.remote
    sync_name = args.name
    is_interactive = sys.stdin and sys.stdin.isatty()

    host = None
    use_wsl = False

    # If no host was passed, ask interactively
    if not remote_raw:
        if not is_interactive:
            _exit(
                "Error: Remote host is required. "
                "Pass it as the first argument "
                "(e.g. python sync_antigravity.py pc)."
            )
        print("Conversation Synchronization - Antigravity CLI")
        while True:
            entry = input(
                "* Enter the remote SSH host or alias, or 'stop': "
            ).strip()
            if entry.lower() in ("stop", "c", "q"):
                _exit("Synchronization canceled.", code=0)
            if not entry:
                continue
            if not HOST_REGEX.match(entry):
                print("  Invalid format. Example: pc, notebook, user@host")
                continue
            use_wsl = detect_wsl(entry)
            if verify_ssh(entry, use_wsl):
                host = entry
                break
    else:
        if not HOST_REGEX.match(remote_raw):
            _exit("Error: Invalid remote host format. Example: pc, user@host")
        host = remote_raw
        use_wsl = detect_wsl(host)
        if not verify_ssh(host, use_wsl):
            _exit("  Check the host name or your SSH configuration.")

    local_dir = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-cli")

    # Ask sync type if not specified via --name in interactive mode
    sync_option = None
    if not sync_name and is_interactive and len(sys.argv) <= 2:
        print("What type of synchronization do you want to perform?")
        print(" 1. Full synchronization (Mirror all conversations)")
        print(
            " 2. Selective synchronization (Choose from the list of available conversations)"
        )
        while True:
            option = input("Select an option (1 or 2): ").strip()
            if option == "1":
                sync_option = "full"
                break
            elif option == "2":
                sync_option = "selective"
                break
            print("Invalid option. Please select 1 or 2.")

    local_lines = load_history(os.path.join(local_dir, "history.jsonl"))
    remote_lines = download_remote_history(host, use_wsl)
    lines = local_lines + remote_lines

    target_id = None
    direction = "bidi"

    # If --name was passed, search for the conversation by title/text
    if sync_name:
        matches = search_conversations(sync_name, lines)
        if not matches:
            _exit(
                f"Error: No conversation matching '{sync_name}' was found."
            )
        elif len(matches) > 1:
            if is_interactive:
                print(
                    f"\nMultiple conversations found matching '{sync_name}':"
                )
                for index, c in enumerate(matches, 1):
                    print(
                        f" {index}. '{c.get('display')}' (ID: {c.get('conversationId')})"
                    )
                while True:
                    try:
                        selection = input(
                            f"Select an option (1-{len(matches)}) or type 'c' to cancel: "
                        ).strip()
                        if selection.lower() == "c":
                            _exit("Synchronization canceled by user.")
                        index_sel = int(selection) - 1
                        if 0 <= index_sel < len(matches):
                            target_id = matches[index_sel].get(
                                "conversationId"
                            )
                            print(
                                f"Selected conversation: '{matches[index_sel].get('display')}'"
                            )
                            break
                        print("Number out of range. Please try again.")
                    except ValueError:
                        print("Invalid input. Enter a number or 'c'.")
            else:
                message = f"Error: Ambiguity detected. Multiple conversations matched '{sync_name}':\n"
                for c in matches:
                    message += (
                        f" - '{c.get('display')}' (ID: {c.get('conversationId')})\n"
                    )
                _exit(message.strip())
        else:
            target_id = matches[0].get("conversationId")
            print(
                f"Selected conversation: '{matches[0].get('display')}' (ID: {target_id})"
            )

    if sync_option == "full" and not target_id:
        complete_sync(host, use_wsl)
        return

    # Interactive selective mode: scan remote and local, show list, choose
    if sync_option == "selective" and is_interactive:
        conv_info = collect_conversation_info(local_lines, remote_lines)

        remote_uuids = scan_remote_conversations(host, use_wsl)
        for uuid_line in remote_uuids:
            if uuid_line not in conv_info:
                conv_info[uuid_line] = {
                    "conversationId": uuid_line,
                    "display": uuid_line[:8] + "...",
                    "timestamp": 0,
                    "local": False,
                    "remote": True,
                    "text_content": "",
                }
            else:
                conv_info[uuid_line]["remote"] = True

        local_conv_scan = _scan_local_conversations(local_dir)
        for uuid_line, info in local_conv_scan.items():
            if uuid_line not in conv_info:
                conv_info[uuid_line] = info
            else:
                conv_info[uuid_line]["local"] = True

        direction = _prompt_direction()

        full_list = sorted(
            conv_info.values(), key=lambda x: x.get("timestamp", 0), reverse=True
        )
        if not full_list:
            _exit("No conversations found on either machine.")

        conv_list = list(full_list)
        if direction == "pull":
            conv_list = [c for c in conv_list if c.get("remote")]
        elif direction == "push":
            conv_list = [c for c in conv_list if c.get("local")]

        if not conv_list:
            msg = (
                "pull from remote"
                if direction == "pull"
                else "push to remote"
                if direction == "push"
                else "sync"
            )
            _exit(f"No conversations available to {msg}.")

        target_id = _select_conversation(conv_list, full_list, direction)

    # Execute sync according to direction and existence
    if target_id:
        if not UUID_REGEX.match(target_id):
            _exit("Error: Target conversation ID has an invalid format.")

        exists_local = any(e.get("conversationId") == target_id for e in local_lines)
        exists_remote = any(
            e.get("conversationId") == target_id for e in remote_lines
        )

        if direction == "pull":
            pull_conversation(host, use_wsl, target_id)
        elif direction == "push":
            push_conversation(host, use_wsl, target_id)
        elif sync_name:
            if exists_remote and exists_local:
                bidi_conversation(host, use_wsl, target_id)
            elif exists_remote:
                pull_conversation(host, use_wsl, target_id)
            elif exists_local:
                push_conversation(host, use_wsl, target_id)
        else:
            bidi_conversation(host, use_wsl, target_id)
    else:
        complete_sync(host, use_wsl)


if __name__ == "__main__":
    main()
