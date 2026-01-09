import os
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Generator, Optional, Set, Tuple

from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern
from tree_sitter_languages import get_parser

from .db import Database, CodeNode
from .config import settings

logger = logging.getLogger(__name__)

class FileIndexer:
    def __init__(self, db: Database):
        self.db = db
        self.supported_extensions = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".html": "html",
            ".md": "markdown",
        }

    def index_workspace(self, root_path: str, force: bool = False) -> Dict[str, Any]:
        """Iterate over workspace, parsing and indexing files."""
        stats = {"indexed": 0, "skipped": 0, "errors": 0, "deleted": 0}

        # Start Transaction / Index Run
        # We assume one config hash for now (simplification)
        config_hash = hashlib.sha256(json.dumps(settings.model_dump(), sort_keys=True, default=str).encode()).hexdigest()
        run_id = self.db.create_index_run(root_path, config_hash)

        is_ignored_func, ignore_spec = self._load_gitignore(root_path)

        files_to_process = []

        # Accumulate repo map data in memory during traversal
        # Structure: { dir_path: { files: [...], summary: "..." } }
        repo_structure = {}
        repo_map_entries = []

        for root, dirs, files in os.walk(root_path):
            # Normalize and filter dirs
            # os.walk dirs list can be modified in place to prune

            # Prune ignored directories
            # Use the is_ignored helper which now handles slash logic
            to_remove = []
            for d in dirs:
                d_path = os.path.join(root, d)
                if is_ignored_func(d_path):
                    to_remove.append(d)

            for d in to_remove:
                dirs.remove(d)

            rel_root = os.path.relpath(root, root_path)
            if rel_root == ".": rel_root = ""

            # Directory entry for repo map
            repo_map_entries.append({
                "kind": "dir",
                "path": rel_root + "/",
                "summary": f"Directory with {len(files)} files" # Placeholder summary
            })

            dir_files_meta = []

            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, root_path)

                if is_ignored_func(full_path):
                    continue

                try:
                    if os.path.getsize(full_path) > settings.rag_max_file_mb * 1024 * 1024:
                        logger.debug(f"Skipping {file}: too large")
                        stats["skipped"] += 1
                        continue
                except OSError:
                    continue

                # Debug duplication
                if any(f[0] == full_path for f in files_to_process):
                    logger.warning(f"Duplicate file found: {full_path}")

                files_to_process.append((full_path, rel_path))

                # File entry placeholder (to be enriched during processing)
                dir_files_meta.append({
                    "path": rel_path,
                    "language": self.supported_extensions.get(os.path.splitext(file)[1], "text"),
                    # symbols populated later
                })

            if rel_root not in repo_structure:
                 repo_structure[rel_root] = {"files": dir_files_meta}

        # Parallel Processing
        # We need to collect symbols for the repo map from the workers.
        # ThreadPoolExecutor doesn't easily share state, so we return it.

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for full_path, rel_path in files_to_process:
                futures.append(executor.submit(self._process_file, full_path, rel_path, force))

            for future in futures:
                try:
                    res = future.result()
                    # res is (bool, List[entry_dict])
                    if res is not None:
                        # should_index implies it was actually re-indexed.
                        # However, for tests checking stats["indexed"],
                        # we must ensure that we don't double count if force=True or something?
                        # Wait, for test_ignore_rules, indexed should be 0.
                        # If files_to_process is not empty, it tries to index.

                        should_index_flag, entries = res
                        if should_index_flag:
                             stats["indexed"] += 1
                        else:
                             stats["skipped"] += 1

                        if entries:
                            repo_map_entries.extend(entries)
                    else:
                        stats["errors"] += 1
                except Exception as e:
                    logger.error(f"Error indexing file: {e}")
                    stats["errors"] += 1

        # Finalize Repo Map
        # Construct the big JSON payload
        repo_map_payload = {
            "repo_root": root_path,
            "generated_at": str(run_id), # using run_id as timestamp proxy or separate
            "dirs": repo_structure
            # "files" are nested or separate? User suggested "files" list.
            # We can restructure `repo_structure` to match user suggestion.
        }

        # Store Map
        self.db.store_repo_map(run_id, repo_map_payload, repo_map_entries)

        # Complete Run
        self.db.complete_index_run(run_id, "success")

        return stats

    def _process_file(self, full_path: str, rel_path: str, force: bool) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Process a single file.
        Returns: (should_index_bool, repo_map_entries_for_this_file)
        """
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Stable SHA256 hash
            file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            existing_hash = self.db.get_file_hash(full_path)

            should_index = force or (existing_hash != file_hash)

            map_entries = []

            # File Entry
            map_entries.append({
                "kind": "file",
                "path": rel_path,
                "summary": "Source file",
                "importance": 1.0
            })

            symbols = []
            if should_index:
                nodes, symbols = self._parse_file_content(full_path, rel_path, content)
                self.db.delete_nodes_by_filepath(full_path)
                self.db.batch_add_nodes(nodes)
                self.db.set_file_hash(full_path, file_hash)
            else:
                # IMPORTANT: If not indexing, we MUST return False for should_index
                should_index = False
                # If skipping, fetch old nodes from DB to reconstruct symbols
                old_nodes = self.db.get_nodes_by_filepath(full_path)
                for n in old_nodes:
                    if n.type in {"function_definition", "class_definition", "method_definition", "func_literal", "function_declaration"}:
                        symbols.append({
                            "name": n.name,
                            "kind": n.type,
                            "start_line": n.start_line,
                            "end_line": n.end_line,
                            "signature": n.content.split('\n')[0][:100] # Approximate
                        })

            # Convert symbols to map entries
            for s in symbols:
                map_entries.append({
                    "kind": "symbol",
                    "path": rel_path,
                    "symbol_name": s["name"],
                    "signature": s.get("signature"),
                    "start_line": s["start_line"],
                    "end_line": s["end_line"],
                    "importance": 0.8
                })

            return (should_index, map_entries)

        except Exception as e:
            logger.error(f"Failed to process {full_path}: {e}")
            raise e

    def _parse_file_content(self, full_path: str, rel_path: str, content: str) -> Tuple[List[CodeNode], List[Dict[str, Any]]]:
        ext = os.path.splitext(full_path)[1].lower()
        lang = self.supported_extensions.get(ext)

        nodes = []
        symbols = []

        if not lang:
            # Fallback
            nodes = [self._create_node(full_path, content, 0, len(content.splitlines()), "text", "file")]
            return nodes, symbols

        try:
            parser = get_parser(lang)
            tree = parser.parse(bytes(content, "utf-8"))

            root_node = self._create_node(full_path, content, 0, len(content.splitlines()), "file", os.path.basename(full_path))
            nodes.append(root_node)

            cursor = tree.walk()

            relevant_types = {
                "function_definition", "class_definition", "method_definition", # Python, JS
                "function_declaration", "method_declaration", # Java, C++
                "func_literal", # Go
            }

            def traverse(node):
                if node.type in relevant_types:
                    name = self._get_node_name(node, content) or "anon"
                    # Capture signature (first line)
                    sig_line = content.splitlines()[node.start_point[0]]

                    code_node = self._create_node(
                        full_path,
                        content,
                        node.start_point[0],
                        node.end_point[0],
                        node.type,
                        name
                    )
                    nodes.append(code_node)

                    symbols.append({
                        "name": name,
                        "kind": node.type,
                        "start_line": node.start_point[0],
                        "end_line": node.end_point[0],
                        "signature": sig_line.strip()
                    })

                for child in node.children:
                    traverse(child)

            traverse(tree.root_node)
            return nodes, symbols

        except Exception as e:
            logger.warning(f"Parsing failed for {full_path}: {e}")
            nodes = [self._create_node(full_path, content, 0, len(content.splitlines()), "text", "file")]
            return nodes, symbols

    def _get_node_name(self, node, content) -> Optional[str]:
        for child in node.children:
            if child.type in ("identifier", "name"):
                if hasattr(child, "text") and child.text:
                    return child.text.decode("utf-8", errors="replace")
                return bytes(content, "utf-8")[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
        return None

    def _create_node(self, filepath: str, full_content: str, start_line: int, end_line: int, type: str, name: str) -> CodeNode:
        lines = full_content.splitlines()
        start_line = max(0, start_line)
        end_line = min(len(lines), end_line)
        chunk_content = "\n".join(lines[start_line : end_line + 1])
        node_id = f"{filepath}:{start_line}-{end_line}"

        return CodeNode(
            id=node_id,
            type=type,
            name=name,
            filepath=filepath,
            start_line=start_line,
            end_line=end_line,
            content=chunk_content,
            properties={"language": os.path.splitext(filepath)[1]}
        )

    def _load_gitignore(self, root: str):
        default_ignores = {
            ".git", "node_modules", "dist", "build", "out", "__pycache__",
            ".venv", "venv", ".pytest_cache", ".vscode", ".idea", "site-packages"
        }
        for g in settings.rag_deny_globs:
            default_ignores.add(g)

        patterns = list(default_ignores)
        gitignore_path = os.path.join(root, ".gitignore")

        # Proper .gitignore loading
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    # Ignore empty lines and comments
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            patterns.append(line)
            except Exception:
                pass

        # pathspec 1.x logic
        # For gitignore behavior, we should use 'gitignore' style
        spec = PathSpec.from_lines('gitwildmatch', patterns)

        def is_ignored(path: str) -> bool:
            # Pathspec expects path relative to root
            rel = os.path.relpath(path, root)
            if rel.startswith(".."): return True
            if rel == ".": return False # Don't ignore root

            # Check file match
            if spec.match_file(rel):
                return True

            # Check if it matches as a directory (with trailing slash)
            # This is important for patterns like "foo/" which only match directories
            if spec.match_file(rel + "/"):
                return True

            return False

        return is_ignored, spec
