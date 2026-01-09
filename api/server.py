from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import time

from code_intelligence.agents import RetrievalOrchestrator, SemanticSearchAgent, SyntacticSearchAgent, GraphTraversalAgent
from code_intelligence.judges import CouncilOfJudges
from code_intelligence.meta_learning import PerformanceAnalyzer, SelfImprovementEngine

# Global initialization to avoid reloading on every request
from code_intelligence.db import Database
from code_intelligence.vector import VectorStore
from code_intelligence.parser import ParserFactory


def _load_gitignore(root: str):
    default_ignores = {
        ".git",
        "node_modules",
        "dist",
        "build",
        "out",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
    }
    gitignore_path = os.path.join(root, ".gitignore")
    try:
        from pathspec import PathSpec
        from pathspec.patterns import GitWildMatchPattern

        patterns = []
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                patterns = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        spec = PathSpec.from_lines(GitWildMatchPattern, patterns)

        def is_ignored(path: str) -> bool:
            rel = os.path.relpath(path, root)
            parts = rel.split(os.sep)
            if parts and parts[0] in default_ignores:
                return True
            return spec.match_file(rel)

        return is_ignored
    except Exception:
        def is_ignored(path: str) -> bool:
            rel = os.path.relpath(path, root)
            parts = rel.split(os.sep)
            return bool(parts and parts[0] in default_ignores)

        return is_ignored


def index_codebase(path: str, db: Database):
    is_ignored = _load_gitignore(path)
    max_bytes = int(os.getenv("MAX_INDEX_FILE_BYTES", "2000000"))
    parsed = 0
    for root, _, files in os.walk(path):
        for file in files:
            full_path = os.path.join(root, file)
            if is_ignored(full_path):
                continue
            try:
                if os.path.getsize(full_path) > max_bytes:
                    continue
            except OSError:
                continue
            parser = ParserFactory.get_parser(full_path, db)
            if not parser:
                continue
            parser.parse_file(full_path)
            parsed += 1
    return parsed

def build_engine():
    """(Re)initialize DB + in-memory indexes."""

    global db, vector_store, orchestrator
    db = Database("codegraph.db")
    vector_store = VectorStore()
    orchestrator = RetrievalOrchestrator(
        [
            SemanticSearchAgent(db, vector_store),
            SyntacticSearchAgent(db),
            GraphTraversalAgent(db),
        ]
    )


print("Initializing Code Intelligence Engine...")
build_engine()
print("Initialization Complete.")

class RequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        start_time = time.time()
        if self.path == '/query':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
            query = data.get('query')
            
            results = orchestrator.execute(query)
            
            # Validate
            council = CouncilOfJudges()
            validation = council.validate(query, [r.__dict__ for r in results])
            
            # Meta-Learning Loop
            latency = (time.time() - start_time) * 1000
            analyzer = PerformanceAnalyzer()
            analyzer.log_session(query, validation, latency)
            
            improver = SelfImprovementEngine()
            optimization = improver.optimize()

            response = {
                "results": [r.__dict__ for r in results],
                "validation": validation.__dict__ if hasattr(validation, '__dict__') else validation,
                "meta_learning": optimization
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        elif self.path == '/index':
            # Index a workspace. Body: {"path": "/absolute/or/relative"}
            content_length = int(self.headers.get('Content-Length', '0') or '0')
            post_data = self.rfile.read(content_length) if content_length else b"{}"
            data = json.loads(post_data.decode('utf-8') or "{}")
            path = data.get("path")
            if not path:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing 'path'"}).encode())
                return

            try:
                parsed = index_codebase(path, db)
                # Rebuild in-memory indexes.
                build_engine()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "parsed_files": parsed}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
        else:
            self.send_response(404)
            self.end_headers()

def run(server_class=HTTPServer, handler_class=RequestHandler, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f'Starting API server on port {port}...')
    httpd.serve_forever()

if __name__ == '__main__':
    run()
