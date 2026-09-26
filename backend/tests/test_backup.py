import sqlite3
from pathlib import Path

from dartscore.storage.backup import create_backup, list_backups, restore_backup


def test_backup_rotation_and_restore(tmp_path: Path) -> None:
    db = tmp_path / "dartscore.db"
    with sqlite3.connect(db) as conn:
        conn.execute("create table t (v int)")
        conn.execute("insert into t values (1)")

    backups = tmp_path / "backups"
    first = create_backup(db, backups, keep=2)
    with sqlite3.connect(db) as conn:
        conn.execute("update t set v = 2")

    for i in range(3):
        (backups / f"dartscore-2000010{i}-000000.db").write_bytes(first.read_bytes())
    create_backup(db, backups, keep=2)
    assert len(list_backups(backups)) == 2

    restore_backup(first, db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("select v from t").fetchone() == (1,)
