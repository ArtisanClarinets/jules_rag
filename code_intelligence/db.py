import sqlite3
import json
import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

import numpy as np

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

class Database:
    def __init__(self, db_path: str = "codegraph.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Enable FTS5 extension if possible (usually built-in)
        # nodes table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            type TEXT,
            name TEXT,
            filepath TEXT,
            start_line INTEGER,
            end_line INTEGER,
            content TEXT,
            properties TEXT
        )
        ''')
        
        # Edges table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS edges (
            source_id TEXT,
            target_id TEXT,
            relationship TEXT,
            properties TEXT,
            PRIMARY KEY (source_id, target_id, relationship),
            FOREIGN KEY (source_id) REFERENCES nodes(id),
            FOREIGN KEY (target_id) REFERENCES nodes(id)
        )
        ''')
        
        # Full Text Search table (for semantic/keyword search)
        cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
            id, name, content
        )
        ''')

        # Embeddings table (OpenAI/OpenRouter/etc.)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS embeddings (
            node_id TEXT,
            model TEXT,
            vector BLOB,
            dim INTEGER,
            PRIMARY KEY (node_id, model),
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        )
        ''')
        
        conn.commit()
        conn.close()

    def add_node(self, node: CodeNode):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        props_json = json.dumps(node.properties)
        
        cursor.execute('''
        INSERT OR REPLACE INTO nodes (id, type, name, filepath, start_line, end_line, content, properties)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (node.id, node.type, node.name, node.filepath, node.start_line, node.end_line, node.content, props_json))
        
        # Update FTS
        cursor.execute('''
        INSERT OR REPLACE INTO nodes_fts (id, name, content)
        VALUES (?, ?, ?)
        ''', (node.id, node.name, node.content))
        
        conn.commit()
        conn.close()

    def add_edge(self, source_id: str, target_id: str, relationship: str, properties: Dict = {}):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        props_json = json.dumps(properties)
        
        cursor.execute('''
        INSERT OR REPLACE INTO edges (source_id, target_id, relationship, properties)
        VALUES (?, ?, ?, ?)
        ''', (source_id, target_id, relationship, props_json))
        
        conn.commit()
        conn.close()

    def get_node(self, node_id: str) -> Optional[CodeNode]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM nodes WHERE id = ?', (node_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return CodeNode(
                id=row[0],
                type=row[1],
                name=row[2],
                filepath=row[3],
                start_line=row[4],
                end_line=row[5],
                content=row[6],
                properties=json.loads(row[7])
            )
        return None

    def search_nodes(self, query: str, limit: int = 10) -> List[CodeNode]:
        """Full text search using FTS5"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Simple match query
        # FTS5 doesn't provide a 'rank' column by default; bm25() is the typical
        # scoring function.
        cursor.execute(
            '''
        SELECT id FROM nodes_fts WHERE nodes_fts MATCH ? ORDER BY bm25(nodes_fts) LIMIT ?
        ''',
            (query, limit),
        )
        
        ids = [row[0] for row in cursor.fetchall()]
        nodes = []
        for nid in ids:
            n = self.get_node(nid)
            if n:
                nodes.append(n)
        
        conn.close()
        return nodes

    def upsert_embedding(self, node_id: str, model: str, vector: np.ndarray):
        """Persist an embedding vector for a node."""

        vec = np.asarray(vector, dtype=np.float32)
        conn = sqlite3.connect(self.db_path)
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

    def get_embedding(self, node_id: str, model: str) -> Optional[np.ndarray]:
        conn = sqlite3.connect(self.db_path)
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

    def get_embeddings_for_nodes(self, node_ids: List[str], model: str) -> Dict[str, np.ndarray]:
        """Fetch embeddings for many nodes at once."""

        if not node_ids:
            return {}
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(node_ids))
        cursor.execute(
            f"SELECT node_id, vector, dim FROM embeddings WHERE model = ? AND node_id IN ({placeholders})",
            [model, *node_ids],
        )
        out: Dict[str, np.ndarray] = {}
        for nid, blob, dim in cursor.fetchall():
            vec = np.frombuffer(blob, dtype=np.float32)
            if dim and vec.shape[0] != dim:
                vec = vec[:dim]
            out[nid] = vec
        conn.close()
        return out

    def get_neighbors(self, node_id: str, relationship: str = None) -> List[CodeNode]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if relationship:
            cursor.execute('''
            SELECT target_id FROM edges WHERE source_id = ? AND relationship = ?
            ''', (node_id, relationship))
        else:
            cursor.execute('''
            SELECT target_id FROM edges WHERE source_id = ?
            ''', (node_id,))
            
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        nodes = []
        for nid in ids:
            n = self.get_node(nid)
            if n:
                nodes.append(n)
        return nodes

    def get_all_nodes(self) -> List[CodeNode]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM nodes')
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        nodes = []
        for nid in ids:
            n = self.get_node(nid)
            if n:
                nodes.append(n)
        return nodes
