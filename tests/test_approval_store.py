"""验证 ApprovalStore 持久化 + 路径归一化 + 高危操作检测。"""
import hashlib, json, sqlite3, os, tempfile
from pathlib import Path

_TABLE = "user_approval_fingerprints"

def generate_fingerprint(tool_name, tool_args):
    sorted_args = json.dumps(tool_args, sort_keys=True, ensure_ascii=False)
    raw = f"{tool_name}{sorted_args}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def normalize_workspace_path(path):
    if not path:
        return ""
    p = Path(path).resolve()
    s = str(p).replace("\\", "/")
    if len(s) >= 2 and s[1] == ":":
        s = s[0].lower() + s[1:]
    return s.rstrip("/")

HIGH_RISK_PATTERNS = [
    {"tool": "bash", "args_pattern": "rm -rf"},
    {"tool": "bash", "args_pattern": "rmdir /s"},
    {"tool": "bash", "args_pattern": "del /f"},
    {"tool": "bash", "args_pattern": "format "},
    {"tool": "bash", "args_pattern": "diskpart"},
    {"tool": "bash", "args_pattern": "reg delete"},
    {"tool": "bash", "args_pattern": "takeown"},
    {"tool": "bash", "args_pattern": "remove-item"},
]

def is_high_risk(tool_name, tool_args):
    args_str = json.dumps(tool_args, sort_keys=True, ensure_ascii=False).lower()
    for p in HIGH_RISK_PATTERNS:
        if p["tool"] == tool_name and p["args_pattern"].lower() in args_str:
            return True
    return False


class ApprovalStore:
    def __init__(self, db_path):
        self._db_path = db_path
        self._conn = None

    def init(self):
        self._conn = sqlite3.connect(self._db_path, timeout=10.0)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_root TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                UNIQUE(workspace_root, fingerprint)
            )
        """)
        self._conn.commit()

    def is_allowed(self, workspace_root, fingerprint):
        ws = normalize_workspace_path(workspace_root)
        cur = self._conn.execute(
            f"SELECT 1 FROM {_TABLE} WHERE workspace_root=? AND fingerprint=?",
            (ws, fingerprint))
        return cur.fetchone() is not None

    def add_approval(self, workspace_root, fingerprint, tool_name):
        ws = normalize_workspace_path(workspace_root)
        self._conn.execute(
            f"INSERT OR IGNORE INTO {_TABLE} (workspace_root, fingerprint, tool_name) VALUES (?, ?, ?)",
            (ws, fingerprint, tool_name))
        self._conn.commit()

    def remove_approval(self, workspace_root, fingerprint):
        ws = normalize_workspace_path(workspace_root)
        cur = self._conn.execute(
            f"DELETE FROM {_TABLE} WHERE workspace_root=? AND fingerprint=?",
            (ws, fingerprint))
        self._conn.commit()
        return cur.rowcount > 0

    def count(self, workspace_root=None):
        if workspace_root:
            ws = normalize_workspace_path(workspace_root)
            cur = self._conn.execute(f"SELECT COUNT(*) FROM {_TABLE} WHERE workspace_root=?", (ws,))
        else:
            cur = self._conn.execute(f"SELECT COUNT(*) FROM {_TABLE}")
        return cur.fetchone()[0]

    def clear(self, workspace_root=None):
        if workspace_root:
            ws = normalize_workspace_path(workspace_root)
            cur = self._conn.execute(f"DELETE FROM {_TABLE} WHERE workspace_root=?", (ws,))
        else:
            cur = self._conn.execute(f"DELETE FROM {_TABLE}")
        self._conn.commit()
        return cur.rowcount

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


def main():
    db = os.path.join(tempfile.gettempdir(), "test_approval.db")
    if os.path.exists(db):
        os.remove(db)

    store = ApprovalStore(db)
    store.init()

    # 1
    assert os.path.exists(db)
    print("[PASS] 1. init() 建表成功")

    # 2
    cur = store._conn.execute("PRAGMA journal_mode")
    assert cur.fetchone()[0].lower() == "wal"
    print("[PASS] 2. WAL 模式已开启")

    # 3
    fp = generate_fingerprint("delete_file", {"path": "/a.txt"})
    store.add_approval("/test/ws", fp, "delete_file")
    assert store.is_allowed("/test/ws", fp)
    assert not store.is_allowed("/test/ws", "nope")
    assert not store.is_allowed("/other/ws", fp)
    print("[PASS] 3. 写入 + 查询指纹")

    # 4 - Windows 路径归一化
    fp2 = generate_fingerprint("edit_file", {"path": "/b.txt"})
    win_path = "C:" + "\\" + "Users" + "\\" + "test" + "\\" + "project"
    store.add_approval(win_path, fp2, "edit_file")
    win_query = "c:" + "\\" + "Users" + "\\" + "test" + "\\" + "project"
    assert store.is_allowed(win_query, fp2)
    print("[PASS] 4. Windows 路径归一化 (反斜杠 + 盘符小写)")

    # 5
    store.add_approval("/test/ws", fp, "delete_file")
    assert store.count("/test/ws") == 1
    print("[PASS] 5. UNIQUE 约束：重复插入忽略")

    # 6
    assert store.remove_approval("/test/ws", fp)
    assert not store.is_allowed("/test/ws", fp)
    assert not store.remove_approval("/test/ws", fp)
    print("[PASS] 6. 删除指纹")

    # 7 - 清除
    store.add_approval("/ws1", "fp1", "tool1")
    store.add_approval("/ws2", "fp2", "tool2")
    total_before = store.count()
    assert total_before >= 2, f"应至少有2条记录，实际: {total_before}"

    cleared = store.clear("/ws1")
    assert cleared >= 1
    assert not store.is_allowed("/ws1", "fp1")
    assert store.is_allowed("/ws2", "fp2")

    remaining = store.count()
    assert remaining == total_before - cleared, f"清除后应剩 {total_before - cleared} 条，实际: {remaining}"

    cleared_all = store.clear()
    assert cleared_all == remaining
    assert store.count() == 0
    print("[PASS] 7. 按工作区清除 + 全部清除")

    # 8
    cur = store._conn.execute("PRAGMA busy_timeout")
    assert cur.fetchone()[0] == 10000
    print("[PASS] 8. busy_timeout=10000ms")

    # 9
    cur = store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    assert "user_approval_fingerprints" in tables
    for t in tables:
        assert not t.startswith("checkpoint_"), f"checkpoint_ 前缀表: {t}"
    print("[PASS] 9. 表名不以 checkpoint_ 开头")

    # 10 高危操作
    assert is_high_risk("bash", {"command": "rmdir /s /q test"})
    assert is_high_risk("bash", {"command": "Remove-Item -Recurse -Force"})
    assert is_high_risk("bash", {"command": "del /f file.txt"})
    assert is_high_risk("bash", {"command": "format D:"})
    assert not is_high_risk("bash", {"command": "ls -la"})
    print("[PASS] 10. Windows 高危操作检测")

    store.close()
    os.remove(db)
    print("\n=== 全部 10 项测试通过 ===")


if __name__ == "__main__":
    main()
