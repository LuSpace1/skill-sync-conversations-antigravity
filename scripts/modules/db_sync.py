"""SQLite helpers for conversation_summaries.db synchronization."""

import os
import sqlite3
from modules.config import SUMMARIES_DB


def get_db_titles(db_path=SUMMARIES_DB):
    """Return a mapping of conversation_id -> {'title': title, 'preview': preview}."""
    titles = {}
    if not os.path.exists(db_path):
        return titles
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT conversation_id, title, preview FROM conversation_summaries")
        for cid, title, preview in c.fetchall():
            if cid:
                titles[cid] = {
                    "title": (title or "").strip(),
                    "preview": (preview or "").strip(),
                }
        conn.close()
    except Exception:
        pass
    return titles


def export_conversation_row(db_path, target_id, output_path):
    """Export conversation_summaries and conversations_fts rows for target_id to a portable SQLite file."""
    if not os.path.exists(db_path):
        return False
    try:
        conn_src = sqlite3.connect(db_path)
        c_src = conn_src.cursor()

        c_src.execute(
            "SELECT * FROM conversation_summaries WHERE conversation_id = ?",
            (target_id,),
        )
        row_cs = c_src.fetchone()
        if not row_cs:
            conn_src.close()
            return False

        cols_cs = [d[0] for d in c_src.description]

        if os.path.exists(output_path):
            os.remove(output_path)

        conn_dst = sqlite3.connect(output_path)
        c_dst = conn_dst.cursor()

        # Create portable table for conversation_summaries
        c_dst.execute(f"CREATE TABLE conversation_summaries ({','.join(cols_cs)})")
        placeholders_cs = ",".join(["?"] * len(cols_cs))
        c_dst.execute(
            f"INSERT INTO conversation_summaries VALUES ({placeholders_cs})", row_cs
        )

        # Export fts rows if available
        try:
            c_src.execute(
                "SELECT conversation_id, chunk_index, chunk_first_step, chunk_last_step, "
                "last_modified_time, step_count, last_step_created_at, archived, "
                "user_step_byte_offsets, agent_step_byte_offsets, title, workspace, "
                "project, user_body, agent_body FROM conversations_fts WHERE conversation_id = ?",
                (target_id,),
            )
            rows_fts = c_src.fetchall()
            if rows_fts:
                c_dst.execute(
                    "CREATE TABLE fts_export ("
                    "conversation_id, chunk_index, chunk_first_step, chunk_last_step, "
                    "last_modified_time, step_count, last_step_created_at, archived, "
                    "user_step_byte_offsets, agent_step_byte_offsets, title, workspace, "
                    "project, user_body, agent_body)"
                )
                c_dst.executemany(
                    "INSERT INTO fts_export VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    rows_fts,
                )
        except Exception:
            pass

        conn_dst.commit()
        conn_dst.close()
        conn_src.close()
        return True
    except Exception as e:
        print(f"Warning: Failed to export DB summary for {target_id}: {e}")
        return False


def import_conversation_row(db_path, input_path, target_id):
    """Import conversation_summaries and conversations_fts rows from portable SQLite file into destination DB."""
    if not os.path.exists(input_path) or not os.path.exists(db_path):
        return False
    try:
        conn_dst = sqlite3.connect(db_path)
        conn_src = sqlite3.connect(input_path)

        c_src = conn_src.cursor()
        c_dst = conn_dst.cursor()

        c_src.execute("SELECT * FROM conversation_summaries WHERE conversation_id = ?", (target_id,))
        row = c_src.fetchone()
        if row:
            cols = [d[0] for d in c_src.description]
            row_list = list(row)

            # Ensure valid status so agy picks it up
            if "status" in cols:
                idx_st = cols.index("status")
                if not row_list[idx_st]:
                    row_list[idx_st] = "CASCADE_RUN_STATUS_IDLE"

            # Ensure last_user_input_time is not 0001-01-01
            if "last_user_input_time" in cols and "last_modified_time" in cols:
                idx_luit = cols.index("last_user_input_time")
                idx_lmt = cols.index("last_modified_time")
                if not row_list[idx_luit] or str(row_list[idx_luit]).startswith("0001-01-01"):
                    row_list[idx_luit] = row_list[idx_lmt]

            placeholders = ",".join(["?"] * len(cols))
            c_dst.execute(
                f"INSERT OR REPLACE INTO conversation_summaries ({','.join(cols)}) VALUES ({placeholders})",
                row_list,
            )

        # Import FTS
        try:
            c_src.execute("SELECT * FROM fts_export WHERE conversation_id = ?", (target_id,))
            fts_rows = c_src.fetchall()
            if fts_rows:
                c_dst.execute("DELETE FROM conversations_fts WHERE conversation_id = ?", (target_id,))
                c_dst.executemany(
                    "INSERT INTO conversations_fts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    fts_rows,
                )
        except Exception:
            pass

        conn_dst.commit()
        conn_dst.close()
        conn_src.close()
        return True
    except Exception as e:
        print(f"Warning: Failed to import DB summary for {target_id}: {e}")
        return False
