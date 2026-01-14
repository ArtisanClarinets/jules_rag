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
                "arrow_function", # JS/TS
                "lexical_declaration", "variable_declaration", # JS/TS constants
                "interface_declaration", "type_alias_declaration", # TS
                "jsx_element", "jsx_self_closing_element" # React
            }

            def traverse(node):
                if node.type in relevant_types:
                    # Filter small variable declarations (likely not components)
                    if node.type in ("lexical_declaration", "variable_declaration"):
                        # Only index if it seems like a component or major constant (e.g. exported, or large body)
                        # For now, we rely on _get_node_name logic.
                        # Also check if it contains an arrow function to avoid double indexing if we index arrow_function too?
                        # Actually, better to index the variable declaration if it creates a named component.
                        pass

                    name = self._get_node_name(node, content)

                    # If it's an arrow function, it might be anonymous unless we look at parent
                    if node.type == "arrow_function" and not name:
                         # Try to get name from parent variable_declarator
                         parent = node.parent
                         if parent and parent.type == "variable_declarator":
                             name = self._get_node_name(parent, content)

                    if name and name != "anon":
                        # Capture signature (first line)
                        sig_line = content.splitlines()[node.start_point[0]]

                        # Extra properties for JSX
                        extra_props = {}
                        if node.type in ("jsx_element", "jsx_self_closing_element"):
                            extra_props = self._extract_jsx_props(node, content)

                        # Deduplicate if we already indexed this range (e.g. var decl vs arrow func)
                        # Use start line as proxy

                        code_node = self._create_node(
                            full_path,
                            content,
                            node.start_point[0],
                            node.end_point[0],
                            node.type,
                            name,
                            extra_props=extra_props
                        )

                        # Prevent duplicates (e.g. variable declaration and arrow function often share the same range/lines)
                        if not any(n.id == code_node.id for n in nodes):
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
        # Specific handling for variable declarators (const x = ...)
        if node.type == "variable_declarator":
            for child in node.children:
                if child.type == "identifier":
                    return self._get_text(child, content)

        # Specific handling for lexical declaration (const x = ...) - usually has a variable_declarator child
        if node.type in ("lexical_declaration", "variable_declaration"):
             for child in node.children:
                 if child.type == "variable_declarator":
                     return self._get_node_name(child, content)

        # Class/Function declarations
        for child in node.children:
            if child.type in ("identifier", "name", "type_identifier", "property_identifier"):
                 return self._get_text(child, content)

            # JSX Component Name
            if child.type == "jsx_opening_element":
                 for subchild in child.children:
                     if subchild.type in ("identifier", "jsx_identifier", "member_expression"):
                         return self._get_text(subchild, content)

        return None

    def _get_text(self, node, content) -> str:
        if hasattr(node, "text") and node.text:
            return node.text.decode("utf-8", errors="replace")
        return bytes(content, "utf-8")[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def _extract_jsx_props(self, node, content) -> Dict[str, Any]:
        props = {}
        # Find opening element
        opening = None
        for child in node.children:
            if child.type in ("jsx_opening_element", "jsx_self_closing_element"): # self closing is the node itself? No, node is parent usually, but if type is self_closing it works
                opening = child
                break

        # If the node itself is self-closing
        if node.type == "jsx_self_closing_element":
            opening = node

        if not opening:
            return props

        for child in opening.children:
            if child.type == "jsx_attribute":
                # name = value
                prop_name = None
                prop_value = None
                for sub in child.children:
                    if sub.type == "property_identifier":
                        prop_name = self._get_text(sub, content)
                    elif sub.type == "string":
                        prop_value = self._get_text(sub, content).strip('"\'')
                    elif sub.type == "jsx_expression":
                        # Just capture that it's an expression
                        prop_value = "{...}"

                if prop_name:
                    props[prop_name] = prop_value

        return props

    def _create_node(self, filepath: str, full_content: str, start_line: int, end_line: int, type: str, name: str, extra_props: Dict = None) -> CodeNode:
        lines = full_content.splitlines()
        start_line = max(0, start_line)
        end_line = min(len(lines), end_line)
        chunk_content = "\n".join(lines[start_line : end_line + 1])
        node_id = f"{filepath}:{start_line}-{end_line}"

        props = {"language": os.path.splitext(filepath)[1]}
        if extra_props:
            props.update(extra_props)

        return CodeNode(
            id=node_id,
            type=type,
            name=name,
            filepath=filepath,
            start_line=start_line,
            end_line=end_line,
            content=chunk_content,
            properties=props
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
        spec = PathSpec.from_lines('gitignore', patterns)

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
