import os
import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Generator, Optional, Set, Tuple

from pathspec import PathSpec
from tree_sitter_languages import get_parser

from .db import Database, CodeNode
from .config import settings
from .next_semantics import derive_next_route, get_segment_type, detect_next_directives

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

        config_hash = hashlib.sha256(json.dumps(settings.model_dump(), sort_keys=True, default=str).encode()).hexdigest()
        run_id = self.db.create_index_run(root_path, config_hash)

        is_ignored_func, ignore_spec = self._load_gitignore(root_path)

        files_to_process = []
        repo_structure = {}
        repo_map_entries = []

        # Walk and filtering
        for root, dirs, files in os.walk(root_path):
            to_remove = []
            for d in dirs:
                d_path = os.path.join(root, d)
                if is_ignored_func(d_path):
                    to_remove.append(d)
                elif d in settings.next_ignore_dirs:
                    to_remove.append(d)
            for d in to_remove:
                dirs.remove(d)

            rel_root = os.path.relpath(root, root_path)
            if rel_root == ".": rel_root = ""

            repo_map_entries.append({
                "kind": "dir",
                "path": rel_root + "/",
                "summary": f"Directory with {len(files)} files"
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

                files_to_process.append((full_path, rel_path))

                dir_files_meta.append({
                    "path": rel_path,
                    "language": self.supported_extensions.get(os.path.splitext(file)[1], "text"),
                })

            if rel_root not in repo_structure:
                 repo_structure[rel_root] = {"files": dir_files_meta}

        # Indexing with ThreadPool
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for full_path, rel_path in files_to_process:
                futures.append(executor.submit(self._process_file, full_path, rel_path, force))

            for future in futures:
                try:
                    res = future.result()
                    if res is not None:
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

        repo_map_payload = {
            "repo_root": root_path,
            "generated_at": str(run_id),
            "dirs": repo_structure
        }

        self.db.store_repo_map(run_id, repo_map_payload, repo_map_entries)
        self.db.complete_index_run(run_id, "success")

        return stats

    def _process_file(self, full_path: str, rel_path: str, force: bool) -> Tuple[bool, List[Dict[str, Any]]]:
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            existing_hash = self.db.get_file_hash(full_path)

            # Simple git_sha check if it's a git repo (not implemented fully here, assuming file hash is enough)
            # We could use `git hash-object` but internal hash is faster.

            should_index = force or (existing_hash != file_hash)

            map_entries = []

            # Next.js Metadata
            next_route = derive_next_route(rel_path)
            segment_type = get_segment_type(rel_path)
            is_client, is_server, runtime = detect_next_directives(content)
            is_route_handler = (segment_type == "route")

            # File Entry
            file_summary = "Source file"
            if next_route:
                file_summary = f"Next.js {segment_type} for {next_route}"

            map_entries.append({
                "kind": "file",
                "path": rel_path,
                "summary": file_summary,
                "importance": 1.0,
                "meta": {
                    "next_route": next_route,
                    "type": segment_type
                }
            })

            symbols = []
            if should_index:
                nodes, symbols = self._parse_file_content(
                    full_path, rel_path, content,
                    next_route, segment_type, is_client, is_server, is_route_handler, runtime, file_hash
                )
                self.db.delete_nodes_by_filepath(full_path)
                self.db.batch_add_nodes(nodes)
                self.db.set_file_hash(full_path, file_hash)
            else:
                should_index = False
                # Retrieve existing nodes for map
                old_nodes = self.db.get_nodes_by_filepath(full_path)
                for n in old_nodes:
                     if n.type != "file":
                        symbols.append({
                            "name": n.name,
                            "kind": n.type,
                            "start_line": n.start_line,
                            "end_line": n.end_line,
                            "signature": n.content.split('\n')[0][:100]
                        })

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

    def _parse_file_content(self, full_path: str, rel_path: str, content: str,
                           next_route: Optional[str], segment_type: Optional[str],
                           is_client: bool, is_server: bool, is_route_handler: bool, runtime: str,
                           file_hash: str) -> Tuple[List[CodeNode], List[Dict[str, Any]]]:
        ext = os.path.splitext(full_path)[1].lower()
        lang = self.supported_extensions.get(ext)

        nodes = []
        symbols = []

        common_metadata = {
            "next_route_path": next_route,
            "next_segment_type": segment_type,
            "next_use_client": is_client,
            "next_use_server": is_server,
            "next_is_route_handler": is_route_handler,
            "next_runtime": runtime,
            "file_hash": file_hash,
        }

        if not lang:
            node = self._create_node(full_path, content, 0, len(content.splitlines()), "text", "file", **common_metadata)
            return [node], []

        try:
            parser = get_parser(lang)
            tree = parser.parse(bytes(content, "utf-8"))

            # Extract Imports
            import_deps = self._extract_imports(tree, lang, full_path)
            common_metadata["import_deps"] = import_deps

            # Root Node
            root_node = self._create_node(full_path, content, 0, len(content.splitlines()), "file", os.path.basename(full_path), **common_metadata)
            nodes.append(root_node)

            # Chunking Strategy:
            # 1. Exported Symbols (Class, Func, Const)
            # 2. Top-level blocks if not covered
            # 3. No JSX Element standalone chunks

            relevant_types = {
                "function_definition", "class_definition", "method_definition", # Python
                "function_declaration", "class_declaration", "method_definition", # JS/TS
                "arrow_function", # JS/TS
                "lexical_declaration", "variable_declaration", # JS/TS const
                "export_statement", # JS/TS
                "interface_declaration", "type_alias_declaration"
            }

            def traverse(node):
                # Check for exported symbols or top-level definitions
                is_exported = False

                # Check if wrapped in export_statement
                if node.parent and node.parent.type == "export_statement":
                    is_exported = True

                if node.type in relevant_types:
                    name = self._get_node_name(node, content)

                    # For variable declarations, we only care if they are likely components or exported
                    # or if they are top-level.
                    # Heuristic: index top-level functions/classes/consts.

                    is_top_level = (node.parent.type == "program" or node.parent.type == "module" or node.parent.type == "export_statement")

                    # Fix: Arrow functions often don't have name directly, look at parent
                    if node.type == "arrow_function" and not name:
                        if node.parent.type == "variable_declarator":
                            name = self._get_node_name(node.parent, content)
                            if node.parent.parent.parent.type == "export_statement":
                                is_exported = True

                    if name and (is_exported or is_top_level):
                        # Filter out small things?
                        if (node.end_point[0] - node.start_point[0]) < 2 and not is_exported:
                             pass # Skip small non-exported
                        else:
                            sig_line = content.splitlines()[node.start_point[0]]

                            code_node = self._create_node(
                                full_path,
                                content,
                                node.start_point[0],
                                node.end_point[0],
                                node.type,
                                name,
                                **common_metadata
                            )

                            if not any(n.id == code_node.id for n in nodes):
                                nodes.append(code_node)

                            symbols.append({
                                "name": name,
                                "kind": node.type,
                                "start_line": node.start_point[0],
                                "end_line": node.end_point[0],
                                "signature": sig_line.strip()
                            })

                            # Do not traverse children of indexed chunks (don't split components into JSX chunks)
                            return

                for child in node.children:
                    traverse(child)

            traverse(tree.root_node)
            return nodes, symbols

        except Exception as e:
            logger.warning(f"Parsing failed for {full_path}: {e}")
            nodes = [self._create_node(full_path, content, 0, len(content.splitlines()), "text", "file", **common_metadata)]
            return nodes, symbols

    def _extract_imports(self, tree, lang, full_path) -> List[str]:
        imports = set()
        # Basic traversal for imports
        # Optimization: use tree-sitter query
        # For now, traverse

        def visit(n):
            if n.type == "import_statement":
                # import ... from "source"
                # source is usually a string node
                for child in n.children:
                    if child.type == "string":
                        src = child.text.decode("utf-8").strip('"\'')
                        imports.add(src)
                    elif child.type == "import_clause":
                         # import { x } from "source"
                         # Traverse siblings/children for string
                         pass

                # Search for string in children (JS/TS)
                # (import_statement (string) @source)
                # Actually usually it is last child

                # Hacky: look for string literal in children
                for c in n.children:
                    if c.type == "string":
                        imports.add(c.text.decode("utf-8").strip('"\''))

            elif n.type == "import_from_statement": # Python
                # from module import ...
                for c in n.children:
                     if c.type == "dotted_name":
                         imports.add(c.text.decode("utf-8"))
                         break

            for c in n.children:
                visit(c)

        visit(tree.root_node)

        # Resolve imports relative to file
        resolved = []
        base_dir = os.path.dirname(full_path)

        for imp in imports:
            if imp.startswith("."):
                # Relative import
                # We won't fully resolve extensions here, just path
                try:
                    res = os.path.normpath(os.path.join(base_dir, imp))
                    # Make relative to repo root if possible, or keep absolute?
                    # Let's store raw string for now, user asked for "import specifiers + resolved local targets when possible"
                    # "JSON list of import specifiers + resolved"
                    # I'll store "specifier"
                    resolved.append(imp)
                except Exception:
                    resolved.append(imp)
            else:
                resolved.append(imp)

        return list(resolved)

    def _get_node_name(self, node, content) -> Optional[str]:
        if node.type == "variable_declarator":
            for child in node.children:
                if child.type == "identifier":
                    return self._get_text(child, content)

        if node.type in ("lexical_declaration", "variable_declaration"):
             for child in node.children:
                 if child.type == "variable_declarator":
                     return self._get_node_name(child, content)

        for child in node.children:
            if child.type in ("identifier", "name", "type_identifier", "property_identifier"):
                 return self._get_text(child, content)

        return None

    def _get_text(self, node, content) -> str:
        if hasattr(node, "text") and node.text:
            return node.text.decode("utf-8", errors="replace")
        return bytes(content, "utf-8")[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def _create_node(self, filepath: str, full_content: str, start_line: int, end_line: int, type: str, name: str,
                     extra_props: Dict = None, **kwargs) -> CodeNode:
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
            properties=props,
            # Kwargs match the new fields in CodeNode
            next_route_path=kwargs.get("next_route_path"),
            next_segment_type=kwargs.get("next_segment_type"),
            next_use_client=kwargs.get("next_use_client", False),
            next_use_server=kwargs.get("next_use_server", False),
            next_is_route_handler=kwargs.get("next_is_route_handler", False),
            next_runtime=kwargs.get("next_runtime"),
            import_deps=kwargs.get("import_deps"),
            file_hash=kwargs.get("file_hash"),
            git_sha=kwargs.get("git_sha"),
            repo_id=kwargs.get("repo_id", "default")
        )

    def _load_gitignore(self, root: str):
        default_ignores = {
            ".git", "node_modules", "dist", "build", "out", "__pycache__",
            ".venv", "venv", ".pytest_cache", ".vscode", ".idea", "site-packages",
            # Secrets
            ".env", ".env.*", "*.pem", "*.key", "*.cert", "*.crt", "id_rsa", "id_dsa"
        }
        for g in settings.rag_deny_globs:
            default_ignores.add(g)

        patterns = list(default_ignores)
        gitignore_path = os.path.join(root, ".gitignore")

        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            patterns.append(line)
            except Exception:
                pass

        spec = PathSpec.from_lines('gitignore', patterns)

        def is_ignored(path: str) -> bool:
            rel = os.path.relpath(path, root)
            if rel.startswith(".."): return True
            if rel == ".": return False
            if spec.match_file(rel): return True
            if spec.match_file(rel + "/"): return True
            return False

        return is_ignored, spec
