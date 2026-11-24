"""Nightly encrypted backups of the database, and restore.

A backup is a consistent SQLite snapshot (the online backup API, so the app keeps running), encrypted with Fernet,
written to ``FHG_BACKUP_DIR`` and, when configured, copied to S3-compatible storage (AWS S3, Cloudflare R2,
Backblaze B2...). The last ``FHG_BACKUP_KEEP`` local copies are kept.

Health fields inside the database are already encrypted with the app's key; the whole-file encryption also covers
the metadata (ids, timestamps, the audit trail). The backup key is ``FHG_BACKUP_KEY``, or else the app's own
encryption key (any high-entropy string works, as for ``FHG_ENCRYPTION_KEY``). Keep it somewhere safe outside
Render: without it no backup can be read.

Restore (with the app stopped)::

    python -m fhg.backup restore /var/data/backups/fhg-20261124-0230.sqlite3.enc /var/data/fhg.sqlite3

Test a backup without touching the live database (prints table row counts)::

    python -m fhg.backup check /var/data/backups/fhg-20261124-0230.sqlite3.enc
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from cryptography.fernet import Fernet

from .security import fernet_key

PREFIX, SUFFIX = "fhg-", ".sqlite3.enc"


def snapshot(conn: sqlite3.Connection) -> bytes:
    """A consistent copy of a live database, as bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snap.sqlite3"
        dest = sqlite3.connect(str(path))
        try:
            conn.backup(dest)
        finally:
            dest.close()
        return path.read_bytes()


def make_backup(conn: sqlite3.Connection, out_dir: str, key: str, keep: int = 14,
                upload: Optional[Callable[[str, bytes], None]] = None, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    data = Fernet(fernet_key(key)).encrypt(snapshot(conn))
    name = f"{PREFIX}{now:%Y%m%d-%H%M}{SUFFIX}"
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    old = sorted(p for p in folder.iterdir() if p.name.startswith(PREFIX) and p.name.endswith(SUFFIX))
    for p in old[:-keep] if keep > 0 else []:
        p.unlink()
    uploaded = False
    if upload:
        upload(name, data)
        uploaded = True
    return {"file": name, "bytes": len(data), "uploaded": uploaded, "kept": min(len(old), keep)}


def decrypt(path: str, key: str) -> bytes:
    return Fernet(fernet_key(key)).decrypt(Path(path).read_bytes())


def check(path: str, key: str) -> dict[str, int]:
    """Row counts per table in a backup, read from a temporary copy."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "check.sqlite3"
        db.write_bytes(decrypt(path, key))
        conn = sqlite3.connect(str(db))
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("The backup failed SQLite's integrity check")
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                                 "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        finally:
            conn.close()


def restore(path: str, key: str, dest: str) -> None:
    """Replace ``dest`` with the backup. The previous file is kept as ``<dest>.before-restore``."""
    data = decrypt(path, key)
    target = Path(dest)
    if target.exists():
        target.replace(target.with_name(target.name + ".before-restore"))
    target.write_bytes(data)


def s3_uploader_from_env() -> Optional[Callable[[str, bytes], None]]:
    """S3-compatible upload when FHG_BACKUP_S3_BUCKET is set (credentials from the standard AWS_* variables)."""
    bucket = os.environ.get("FHG_BACKUP_S3_BUCKET")
    if not bucket:
        return None
    import boto3  # imported only when backups to object storage are configured

    client = boto3.client("s3", endpoint_url=os.environ.get("FHG_BACKUP_S3_ENDPOINT") or None)
    prefix = os.environ.get("FHG_BACKUP_S3_PREFIX", "backups/")

    def upload(name: str, data: bytes) -> None:
        client.put_object(Bucket=bucket, Key=prefix + name, Body=data)
    return upload


def _key_from_env() -> str:
    key = os.environ.get("FHG_BACKUP_KEY") or os.environ.get("FHG_ENCRYPTION_KEY")
    if not key:
        sys.exit("Set FHG_BACKUP_KEY (or FHG_ENCRYPTION_KEY) to the key the backup was made with.")
    return key


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(prog="python -m fhg.backup")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="verify a backup and print row counts")
    c.add_argument("file")
    r = sub.add_parser("restore", help="replace the database with a backup (stop the app first)")
    r.add_argument("file")
    r.add_argument("dest")
    args = p.parse_args(argv)
    key = _key_from_env()
    if args.cmd == "check":
        for table, n in check(args.file, key).items():
            print(f"{table:24} {n}")
    else:
        restore(args.file, key, args.dest)
        print(f"Restored {args.file} to {args.dest}")


if __name__ == "__main__":
    main()
