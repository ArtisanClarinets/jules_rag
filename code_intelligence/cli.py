import sys
import os
import argparse
from code_intelligence.db import Database
from code_intelligence.parser import ParserFactory
from code_intelligence.agents import RetrievalOrchestrator, SemanticSearchAgent, SyntacticSearchAgent, GraphTraversalAgent
from code_intelligence.judges import CouncilOfJudges
from code_intelligence.vector import VectorStore


def _load_gitignore(root: str):
    """Load .gitignore rules if the optional `pathspec` dependency is installed.

    Falls back to a simple default ignore list if pathspec isn't available.
    """

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
        # pathspec not installed; best-effort default ignore.
        def is_ignored(path: str) -> bool:
            rel = os.path.relpath(path, root)
            parts = rel.split(os.sep)
            return bool(parts and parts[0] in default_ignores)

        return is_ignored

def main():
    parser = argparse.ArgumentParser(description="Advanced Code Intelligence CLI")
    subparsers = parser.add_subparsers(dest="command")

    # Index command
    index_parser = subparsers.add_parser("index", help="Index a codebase")
    index_parser.add_argument("path", help="Path to the codebase")

    # Query command
    query_parser = subparsers.add_parser("query", help="Query the indexed codebase")
    query_parser.add_argument("prompt", help="The query prompt")

    args = parser.parse_args()

    if args.command == "index":
        print(f"Indexing {args.path}...")
        db = Database("codegraph.db")

        is_ignored = _load_gitignore(args.path)
        max_bytes = int(os.getenv("MAX_INDEX_FILE_BYTES", "2000000"))  # ~2MB
        
        # Walk directory
        for root, _, files in os.walk(args.path):
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
                if parser:
                    print(f"Parsing {full_path}...")
                    parser.parse_file(full_path)
                else:
                    # Skip unknown types
                    pass
        
        print(f"Indexing complete. Database: codegraph.db")

    elif args.command == "query":
        print(f"Querying: {args.prompt}")
        
        db = Database("codegraph.db")
        vector_store = VectorStore()
        
        # Initialize agents
        orchestrator = RetrievalOrchestrator([
            SemanticSearchAgent(db, vector_store),
            SyntacticSearchAgent(db),
            GraphTraversalAgent(db)
        ])
        
        # Retrieve
        results = orchestrator.execute(args.prompt)
        print(f"Retrieved {len(results)} results.")
        
        # Validate
        council = CouncilOfJudges()
        validation = council.validate(args.prompt, [r.__dict__ for r in results])
        print(f"Validation Result: {validation}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
