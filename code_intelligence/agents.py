from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class RetrievalResult:
    content: str
    score: float
    source: str
    metadata: Dict[str, Any]

from .db import Database
from .search import SearchEngine
from .vector import VectorStore

class BaseRetrievalAgent:
    def __init__(self, db: Database, vector_store: VectorStore = None):
        self.db = db
        self.vector_store = vector_store

    def retrieve(self, query: str, context: Dict) -> List[RetrievalResult]:
        raise NotImplementedError

class SemanticSearchAgent(BaseRetrievalAgent):
    def __init__(self, db: Database, vector_store: VectorStore = None):
        super().__init__(db, vector_store)
        self.engine = SearchEngine(db)
        # Populate vector store if provided and empty (lazy load)
        if self.vector_store and not self.vector_store.ids:
            nodes = self.db.get_all_nodes()
            for node in nodes:
                self.vector_store.add_vector(node.id, node.content)

    def retrieve(self, query: str, context: Dict) -> List[RetrievalResult]:
        results = []
        
        # 1. Vector Search (if available)
        if self.vector_store:
            vector_ids = self.vector_store.search(query, limit=5)
            for vid in vector_ids:
                node = self.db.get_node(vid)
                if node:
                    results.append(RetrievalResult(
                        content=node.content,
                        score=0.9, # High confidence for vector match
                        source="semantic-vector",
                        metadata={"id": node.id, "filepath": node.filepath}
                    ))

        # 2. BM25 Search (Fallback/Hybrid)
        bm25_nodes = self.engine.search(query, limit=5)
        for node in bm25_nodes:
            # Check if already added
            if not any(r.metadata['id'] == node.id for r in results):
                results.append(RetrievalResult(
                    content=node.content,
                    score=0.85,
                    source="semantic-bm25",
                    metadata={"id": node.id, "filepath": node.filepath}
                ))
                
        return results

class SyntacticSearchAgent(BaseRetrievalAgent):
    def retrieve(self, query: str, context: Dict) -> List[RetrievalResult]:
        # Use FTS from DB for keyword matching
        nodes = self.db.search_nodes(query)
        results = []
        for node in nodes:
            results.append(RetrievalResult(
                content=node.content,
                score=0.9,
                source="syntactic-fts",
                metadata={"id": node.id, "filepath": node.filepath}
            ))
        return results

class GraphTraversalAgent(BaseRetrievalAgent):
    def retrieve(self, query: str, context: Dict) -> List[RetrievalResult]:
        # Heuristic: if query contains "calls" or "dependencies", look for edges
        results = []
        # This requires parsing the query to find the target function.
        # For prototype, we assume the query IS the function name if we want to find neighbors
        # A real agent would use an LLM to extract the entity.
        
        # Simple heuristic: treat query as potential node name
        nodes = self.db.search_nodes(query, limit=1)
        if nodes:
            target = nodes[0]
            neighbors = self.db.get_neighbors(target.id)
            for n in neighbors:
                 results.append(RetrievalResult(
                    content=n.content,
                    score=0.7,
                    source="graph-neighbor",
                    metadata={"id": n.id, "relation": "connected_to"}
                ))
        return results

class RetrievalOrchestrator:
    def __init__(self, agents: List[BaseRetrievalAgent]):
        self.agents = agents

    def execute(self, query: str) -> List[RetrievalResult]:
        results = []
        for agent in self.agents:
            try:
                results.extend(agent.retrieve(query, {}))
            except Exception as e:
                print(f"Agent failed: {e}")
        
        # Deduplicate by ID
        seen = set()
        unique_results = []
        for r in results:
            nid = r.metadata.get('id')
            if nid and nid not in seen:
                seen.add(nid)
                unique_results.append(r)
        
        # Fusion: sort by score
        unique_results.sort(key=lambda x: x.score, reverse=True)
        return unique_results[:10]
