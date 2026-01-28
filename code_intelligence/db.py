from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Iterable

import numpy as np
from .config import settings

logger = logging.getLogger(__name__)

@dataclass
class CodeNode:
    id: str
    type: str
    name: str
    filepath: str
    start_line: int
    end_line: int
    content: str
    properties: Dict[str, Any]
    # New fields for Next.js and Metadata
    next_route_path: Optional[str] = None
    next_segment_type: Optional[str] = None
    next_use_client: bool = False
    next_use_server: bool = False
    next_is_route_handler: bool = False
    next_runtime: Optional[str] = None
    import_deps: Optional[List[str]] = None
    file_hash: Optional[str] = None
    git_sha: Optional[str] = None
    repo_id: str = "default"

class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.db_path
        self._migrate()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _migrate(self):
        """Run migrations to ensure schema is up to date."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)')
        cursor.execute('SELECT version FROM schema_version')
        row = cursor.fetchone()
        current_version = row[0] if row else 0
        
        # Migration 1: Initial Schema
        if current_version < 1:
            logger.info("Applying migration 1")
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT,
                name TEXT,
                filepath TEXT,
                start_line INTEGER,
                end_line INTEGER,
                content TEXT,
                properties TEXT,
                last_modified REAL
            )
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS edges (
                source_id TEXT,
                target_id TEXT,
                relationship TEXT,
                properties TEXT,
                PRIMARY KEY (source_id, target_id, relationship),
                FOREIGN KEY (source_id) REFERENCES nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (target_id) REFERENCES nodes(id) ON DELETE CASCADE
            )
            ''')
            cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                id, name, content, filepath
            )
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS embeddings (
                node_id TEXT,
                model TEXT,
                vector BLOB,
                dim INTEGER,
                PRIMARY KEY (node_id, model),
                FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
            )
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_hashes (
                filepath TEXT PRIMARY KEY,
                hash TEXT,
                last_indexed REAL
            )
            ''')
            cursor.execute('DELETE FROM schema_version')
            cursor.execute('INSERT INTO schema_version VALUES (1)')
            current_version = 1
            conn.commit()

        # Migration 2: Repo Map Persistence
        if current_version < 2:
            logger.info("Applying migration 2")
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS index_runs (
                id              INTEGER PRIMARY KEY,
                repo_root       TEXT NOT NULL,
                vcs_revision    TEXT,
                created_at      TEXT NOT NULL,
                config_hash     TEXT NOT NULL,
                status          TEXT NOT NULL
            )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_index_runs_root_time ON index_runs(repo_root, created_at)')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS repo_maps (
                index_run_id    INTEGER PRIMARY KEY,
                format_version  INTEGER NOT NULL,
                generated_at    TEXT NOT NULL,
                token_estimate  INTEGER,
                payload_json    TEXT NOT NULL,
                summary_text    TEXT,
                FOREIGN KEY(index_run_id) REFERENCES index_runs(id) ON DELETE CASCADE
            )
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS repo_map_entries (
                id              INTEGER PRIMARY KEY,
                index_run_id    INTEGER NOT NULL,
                kind            TEXT NOT NULL,
                path            TEXT NOT NULL,
                symbol_name     TEXT,
                signature       TEXT,
                start_line      INTEGER,
                end_line        INTEGER,
                importance      REAL,
                summary         TEXT,
                excerpt         TEXT,
                meta_json       TEXT,
                FOREIGN KEY(index_run_id) REFERENCES index_runs(id) ON DELETE CASCADE
            )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_repo_map_entries_run_kind ON repo_map_entries(index_run_id, kind)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_repo_map_entries_run_path ON repo_map_entries(index_run_id, path)')
            cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS repo_map_entries_fts
            USING fts5(path, symbol_name, signature, summary, excerpt,
                    content='repo_map_entries', content_rowid='id')
            ''')
            cursor.execute('DELETE FROM schema_version')
            cursor.execute('INSERT INTO schema_version VALUES (2)')
            conn.commit()

        # Migration 3: Next.js Metadata & FTS Upgrade
        if current_version < 3:
            logger.info("Applying migration 3")
            try:
                cursor.execute('ALTER TABLE nodes ADD COLUMN next_route_path TEXT')
                cursor.execute('ALTER TABLE nodes ADD COLUMN next_segment_type TEXT')
                cursor.execute('ALTER TABLE nodes ADD COLUMN next_use_client INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE nodes ADD COLUMN next_use_server INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE nodes ADD COLUMN next_is_route_handler INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE nodes ADD COLUMN next_runtime TEXT')
                cursor.execute('ALTER TABLE nodes ADD COLUMN import_deps TEXT')
                cursor.execute('ALTER TABLE nodes ADD COLUMN file_hash TEXT')
                cursor.execute('ALTER TABLE nodes ADD COLUMN git_sha TEXT')
                cursor.execute('ALTER TABLE nodes ADD COLUMN repo_id TEXT DEFAULT "default"')
            except sqlite3.OperationalError:
                pass

            # Recreate FTS table to include new fields
            cursor.execute('DROP TABLE IF EXISTS nodes_fts')
            cursor.execute('''
            CREATE VIRTUAL TABLE nodes_fts USING fts5(
                id, name, content, filepath, next_route_path, next_segment_type, symbol_kind
            )
            ''')

            cursor.execute('''
            INSERT INTO nodes_fts (id, name, content, filepath, next_route_path, next_segment_type, symbol_kind)
            SELECT id, name, content, filepath, next_route_path, next_segment_type, type FROM nodes
            ''')

            cursor.execute('DELETE FROM schema_version')
            cursor.execute('INSERT INTO schema_version VALUES (3)')
            conn.commit()

        conn.close()

    def add_node(self, node: CodeNode):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        props_json = json.dumps(node.properties)
        import_deps_json = json.dumps(node.import_deps) if node.import_deps else None
        
        sql = '''
        INSERT OR REPLACE INTO nodes (
            id, type, name, filepath, start_line, end_line, content, properties, last_modified,
            next_route_path, next_segment_type, next_use_client, next_use_server, next_is_route_handler,
            next_runtime, import_deps, file_hash, git_sha, repo_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            node.id, node.type, node.name, node.filepath, node.start_line, node.end_line, node.content, props_json, time.time(),
            node.next_route_path, node.next_segment_type,
            1 if node.next_use_client else 0, 1 if node.next_use_server else 0, 1 if node.next_is_route_handler else 0,
            node.next_runtime, import_deps_json, node.file_hash, node.git_sha, node.repo_id
        )
        cursor.execute(sql, params)
        
        cursor.execute('''
        INSERT OR REPLACE INTO nodes_fts (id, name, content, filepath, next_route_path, next_segment_type, symbol_kind)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (node.id, node.name, node.content, node.filepath, node.next_route_path, node.next_segment_type, node.type))

        conn.commit()
        conn.close()

    def batch_add_nodes(self, nodes: Iterable[CodeNode]):
        conn = self._get_conn()
        cursor = conn.cursor()

        node_data = []
        fts_data = []

        for node in nodes:
            props_json = json.dumps(node.properties)
            import_deps_json = json.dumps(node.import_deps) if node.import_deps else None

            node_data.append((
                node.id, node.type, node.name, node.filepath, node.start_line, node.end_line, node.content, props_json, time.time(),
                node.next_route_path, node.next_segment_type,
                1 if node.next_use_client else 0, 1 if node.next_use_server else 0, 1 if node.next_is_route_handler else 0,
                node.next_runtime, import_deps_json, node.file_hash, node.git_sha, node.repo_id
            ))

            fts_data.append((
                node.id, node.name, node.content, node.filepath, node.next_route_path, node.next_segment_type, node.type
            ))

        sql = '''
        INSERT OR REPLACE INTO nodes (
            id, type, name, filepath, start_line, end_line, content, properties, last_modified,
            next_route_path, next_segment_type, next_use_client, next_use_server, next_is_route_handler,
            next_runtime, import_deps, file_hash, git_sha, repo_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        cursor.executemany(sql, node_data)

        cursor.executemany('''
        INSERT OR REPLACE INTO nodes_fts (id, name, content, filepath, next_route_path, next_segment_type, symbol_kind)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', fts_data)
        
        conn.commit()
        conn.close()

    def add_edge(self, source_id: str, target_id: str, relationship: str, properties: Dict = {}):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        props_json = json.dumps(properties)
        
        cursor.execute('''
        INSERT OR REPLACE INTO edges (source_id, target_id, relationship, properties)
        VALUES (?, ?, ?, ?)
        ''', (source_id, target_id, relationship, props_json))
        
        conn.commit()
        conn.close()

    def get_edges(self, node_id: str, direction: str = "out") -> List[Tuple[str, str]]:
        conn = self._get_conn()
        cursor = conn.cursor()

        if direction == "out":
            cursor.execute('SELECT target_id, relationship FROM edges WHERE source_id = ?', (node_id,))
        else:
            cursor.execute('SELECT source_id, relationship FROM edges WHERE target_id = ?', (node_id,))

        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_node(self, node_id: str) -> Optional[CodeNode]:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT
                id, type, name, filepath, start_line, end_line, content, properties,
                next_route_path, next_segment_type, next_use_client, next_use_server, next_is_route_handler,
                next_runtime, import_deps, file_hash, git_sha, repo_id
            FROM nodes WHERE id = ?
        ''', (node_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            import_deps = json.loads(row[14]) if row[14] else None
            return CodeNode(
                id=row[0],
                type=row[1],
                name=row[2],
                filepath=row[3],
                start_line=row[4],
                end_line=row[5],
                content=row[6],
                properties=json.loads(row[7]),
                next_route_path=row[8],
                next_segment_type=row[9],
                next_use_client=bool(row[10]),
                next_use_server=bool(row[11]),
                next_is_route_handler=bool(row[12]),
                next_runtime=row[13],
                import_deps=import_deps,
                file_hash=row[15],
                git_sha=row[16],
                repo_id=row[17]
            )
        return None

    def get_nodes_by_filepath(self, filepath: str) -> List[CodeNode]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                id, type, name, filepath, start_line, end_line, content, properties,
                next_route_path, next_segment_type, next_use_client, next_use_server, next_is_route_handler,
                next_runtime, import_deps, file_hash, git_sha, repo_id
            FROM nodes WHERE filepath = ?
        ''', (filepath,))
        rows = cursor.fetchall()
        conn.close()

        nodes = []
        for row in rows:
            import_deps = json.loads(row[14]) if row[14] else None
            nodes.append(CodeNode(
                id=row[0],
                type=row[1],
                name=row[2],
                filepath=row[3],
                start_line=row[4],
                end_line=row[5],
                content=row[6],
                properties=json.loads(row[7]),
                next_route_path=row[8],
                next_segment_type=row[9],
                next_use_client=bool(row[10]),
                next_use_server=bool(row[11]),
                next_is_route_handler=bool(row[12]),
                next_runtime=row[13],
                import_deps=import_deps,
                file_hash=row[15],
                git_sha=row[16],
                repo_id=row[17]
            ))
        return nodes

    def delete_nodes_by_filepath(self, filepath: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM nodes WHERE filepath = ?', (filepath,))
        ids = [row[0] for row in cursor.fetchall()]

        if not ids:
            conn.close()
            return

        cursor.execute('DELETE FROM nodes WHERE filepath = ?', (filepath,))
        placeholders = ",".join(["?"] * len(ids))
        cursor.execute(f'DELETE FROM nodes_fts WHERE id IN ({placeholders})', ids)
        cursor.execute(f'DELETE FROM embeddings WHERE node_id IN ({placeholders})', ids)
        cursor.execute(f'DELETE FROM edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})', ids + ids)
        conn.commit()
        conn.close()

    def search_nodes(self, query: str, limit: int = 10) -> List[CodeNode]:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        safe_query = query.replace('"', '""')
        try:
            cursor.execute(
                '''
            SELECT id FROM nodes_fts WHERE nodes_fts MATCH ? ORDER BY bm25(nodes_fts) LIMIT ?
            ''',
                (safe_query, limit),
            )
            ids = [row[0] for row in cursor.fetchall()]
        except sqlite3.OperationalError:
             logger.warning(f"FTS5 query failed: {safe_query}. Retrying sanitized.")
             sanitized = "".join(c for c in safe_query if c.isalnum() or c.isspace())
             cursor.execute(
                '''
            SELECT id FROM nodes_fts WHERE nodes_fts MATCH ? ORDER BY bm25(nodes_fts) LIMIT ?
            ''',
                (sanitized, limit),
            )
             ids = [row[0] for row in cursor.fetchall()]

        conn.close()
        
        nodes = []
        for nid in ids:
            n = self.get_node(nid)
            if n:
                nodes.append(n)
        return nodes

    def upsert_embedding(self, node_id: str, model: str, vector: np.ndarray):
        vec = np.asarray(vector, dtype=np.float32)
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT OR REPLACE INTO embeddings (node_id, model, vector, dim)
            VALUES (?, ?, ?, ?)
            ''',
            (node_id, model, sqlite3.Binary(vec.tobytes()), int(vec.shape[0])),
        )
        conn.commit()
        conn.close()

    def upsert_embeddings_batch(self, embeddings: List[Tuple[str, List[float], str]]):
        """Batch insert embeddings. List of (node_id, vector, model)"""
        conn = self._get_conn()
        cursor = conn.cursor()

        data = []
        for nid, vec, model in embeddings:
            v_np = np.asarray(vec, dtype=np.float32)
            data.append((nid, model, sqlite3.Binary(v_np.tobytes()), int(v_np.shape[0])))

        cursor.executemany(
            '''
            INSERT OR REPLACE INTO embeddings (node_id, model, vector, dim)
            VALUES (?, ?, ?, ?)
            ''',
            data
        )
        conn.commit()
        conn.close()

    def get_embedding(self, node_id: str, model: str) -> Optional[np.ndarray]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT vector, dim FROM embeddings WHERE node_id = ? AND model = ?',
            (node_id, model),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        blob, dim = row
        vec = np.frombuffer(blob, dtype=np.float32)
        if dim and vec.shape[0] != dim:
            vec = vec[:dim]
        return vec

    def get_chunks_without_embeddings(self, model: str) -> List[CodeNode]:
        """Get nodes that do not have embeddings for the specified model."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # We exclude 'file' type nodes if they are just containers,
        # but often file summaries are useful. The 'file' type usually contains the whole file content.
        # Let's exclude 'file' type to save tokens, as we chunk them into symbols/blocks.
        # But wait, sometimes file summary is in 'file' node props.
        # If the file is small, it's a chunk.

        cursor.execute('''
            SELECT
                n.id, n.type, n.name, n.filepath, n.start_line, n.end_line, n.content, n.properties,
                n.next_route_path, n.next_segment_type, n.next_use_client, n.next_use_server, n.next_is_route_handler,
                n.next_runtime, n.import_deps, n.file_hash, n.git_sha, n.repo_id
            FROM nodes n
            LEFT JOIN embeddings e ON n.id = e.node_id AND e.model = ?
            WHERE e.node_id IS NULL AND n.type != 'file'
        ''', (model,))

        rows = cursor.fetchall()
        conn.close()

        nodes = []
        for row in rows:
            import_deps = json.loads(row[14]) if row[14] else None
            nodes.append(CodeNode(
                id=row[0],
                type=row[1],
                name=row[2],
                filepath=row[3],
                start_line=row[4],
                end_line=row[5],
                content=row[6],
                properties=json.loads(row[7]),
                next_route_path=row[8],
                next_segment_type=row[9],
                next_use_client=bool(row[10]),
                next_use_server=bool(row[11]),
                next_is_route_handler=bool(row[12]),
                next_runtime=row[13],
                import_deps=import_deps,
                file_hash=row[15],
                git_sha=row[16],
                repo_id=row[17]
            ))
        return nodes

    def get_file_hash(self, filepath: str) -> Optional[str]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT hash FROM file_hashes WHERE filepath = ?', (filepath,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def set_file_hash(self, filepath: str, file_hash: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO file_hashes (filepath, hash, last_indexed) VALUES (?, ?, ?)',
            (filepath, file_hash, time.time())
        )
        conn.commit()
        conn.close()

    def get_all_nodes(self) -> List[CodeNode]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                id, type, name, filepath, start_line, end_line, content, properties,
                next_route_path, next_segment_type, next_use_client, next_use_server, next_is_route_handler,
                next_runtime, import_deps, file_hash, git_sha, repo_id
            FROM nodes
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        nodes = []
        for row in rows:
            import_deps = json.loads(row[14]) if row[14] else None
            nodes.append(CodeNode(
                id=row[0],
                type=row[1],
                name=row[2],
                filepath=row[3],
                start_line=row[4],
                end_line=row[5],
                content=row[6],
                properties=json.loads(row[7]),
                next_route_path=row[8],
                next_segment_type=row[9],
                next_use_client=bool(row[10]),
                next_use_server=bool(row[11]),
                next_is_route_handler=bool(row[12]),
                next_runtime=row[13],
                import_deps=import_deps,
                file_hash=row[15],
                git_sha=row[16],
                repo_id=row[17]
            ))
        return nodes

    # --- Repo Map Methods ---
    def create_index_run(self, repo_root: str, config_hash: str) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO index_runs (repo_root, created_at, config_hash, status)
            VALUES (?, ?, ?, ?)
        ''', (repo_root, time.time(), config_hash, "pending"))
        run_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return run_id

    def complete_index_run(self, run_id: int, status: str = "success"):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('UPDATE index_runs SET status = ? WHERE id = ?', (status, run_id))
        conn.commit()
        conn.close()

    def store_repo_map(self, run_id: int, payload: Dict[str, Any], entries: List[Dict[str, Any]]):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        payload_json = json.dumps(payload)
        cursor.execute('''
            INSERT INTO repo_maps (index_run_id, format_version, generated_at, payload_json)
            VALUES (?, ?, ?, ?)
        ''', (run_id, 1, time.time(), payload_json))

        entries_data = []
        for e in entries:
            meta_json = json.dumps(e.get("meta", {}))
            entries_data.append((
                run_id,
                e["kind"],
                e["path"],
                e.get("symbol_name"),
                e.get("signature"),
                e.get("start_line"),
                e.get("end_line"),
                e.get("importance", 0.0),
                e.get("summary"),
                e.get("excerpt"),
                meta_json
            ))

        cursor.executemany('''
            INSERT INTO repo_map_entries
            (index_run_id, kind, path, symbol_name, signature, start_line, end_line, importance, summary, excerpt, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', entries_data)

        cursor.execute('''
            INSERT INTO repo_map_entries_fts (rowid, path, symbol_name, signature, summary, excerpt)
            SELECT id, path, symbol_name, signature, summary, excerpt FROM repo_map_entries WHERE index_run_id = ?
        ''', (run_id,))

        conn.commit()
        conn.close()

    def get_latest_repo_map(self, repo_root: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.payload_json
            FROM repo_maps m
            JOIN index_runs r ON m.index_run_id = r.id
            WHERE r.repo_root = ? AND r.status = 'success'
            ORDER BY r.created_at DESC LIMIT 1
        ''', (repo_root,))
        row = cursor.fetchone()
        conn.close()
        return json.loads(row[0]) if row else None
