"""Durable, fail-closed paper cutover write fence (SQLite test prototype).

All writers must call check_write_allowed inside their own transaction.
This does NOT stop legacy API writers until they are explicitly integrated.
"""
import sqlite3

class PaperWriteFence:
    def __init__(self,path):
        self.path=path

    def initialize(self):
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS paper_write_fence (
                id INTEGER PRIMARY KEY CHECK(id=1),
                mode TEXT NOT NULL CHECK(mode IN ('LEGACY','QUIESCED')),
                generation INTEGER NOT NULL CHECK(generation >= 0)
            )""")
            db.execute("INSERT OR IGNORE INTO paper_write_fence VALUES (1,'LEGACY',0)")

    def read(self):
        with sqlite3.connect(self.path) as db:
            record=db.execute("SELECT mode,generation FROM paper_write_fence WHERE id=1").fetchone()
            if record is None:
                raise PermissionError("FENCE_NOT_INITIALIZED")
            return {"mode":record[0],"generation":record[1]}

    def quiesce(self,*,expected_generation:int,manual_approval:bool=False):
        if not manual_approval:
            raise PermissionError("APPROVAL_REQUIRED")
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            result=db.execute(
                "UPDATE paper_write_fence SET mode='QUIESCED',generation=generation+1 "
                "WHERE id=1 AND mode='LEGACY' AND generation=?",(expected_generation,))
            if result.rowcount!=1:
                raise PermissionError("STALE_GENERATION_OR_ALREADY_QUIESCED")
            return {"mode":"QUIESCED","generation":expected_generation+1}

    def check_write_allowed(self,db,*,generation:int):
        row=db.execute("SELECT mode,generation FROM paper_write_fence WHERE id=1").fetchone()
        if row is None or row!=("LEGACY",generation):
            raise PermissionError("PAPER_WRITES_FENCED")
