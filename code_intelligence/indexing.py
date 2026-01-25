import os
import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Generator, Optional, Set, Tuple

from pathspec import PathSpec
from tree_sitter_languages import get_parser
import numpy as np

from .db import Database, CodeNode
from .config import settings
from .next_semantics import derive_next_route, get_segment_type, detect_next_directives
from .providers import LLMInterface, EmbeddingsInterface

logger = logging.getLogger(__name__)

class FileIndexer:
    def __init__(self, db: Database):
        self.db = db
        self.llm = LLMInterface()
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
                rel_path = os.path.join(rel_root, file) # Use os.path.join for correct separators

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

        # Trigger Embedding Generation & Index Rebuild
        self._generate_embeddings()

        return stats

    def _generate_embeddings(self):
        """Generate embeddings for chunks that don't have them and rebuild index."""
        logger.info("Generating embeddings for new chunks...")

        model = settings.embeddings_model
        nodes = self.db.get_chunks_without_embeddings(model)

        if nodes:
            logger.info(f"Found {len(nodes)} chunks to embed with {model}")
            embeddings_interface = EmbeddingsInterface()

            if embeddings_interface.client:
                batch_size = 32
                for i in range(0, len(nodes), batch_size):
                    batch = nodes[i : i + batch_size]
                    texts = []
                    for n in batch:
                        text = n.content
                        if n.properties.get("semantic_summary"):
                            text = f"{n.properties['semantic_summary']}\n{text}"
                        texts.append(text)

                    try:
                        vectors = embeddings_interface.embed(texts)
                        updates = []
                        for node, vec in zip(batch, vectors):
                            updates.append((node.id, vec, model))

                        self.db.upsert_embeddings_batch(updates)
                        if (i // batch_size) % 5 == 0:
                             logger.info(f"Embedded batch {i // batch_size + 1}/{(len(nodes) + batch_size - 1) // batch_size}")
                    except Exception as e:
                        logger.error(f"Embedding batch failed: {e}")
            else:
                logger.warning("No embedding provider configured, skipping dense vector generation.")
        else:
            logger.info("All chunks already embedded.")

        # Rebuild ANN Index
        from .ann_index import ANNIndex

        vector_path = os.path.join(os.path.dirname(settings.db_path), "vectors.bin")
        ann_index = ANNIndex(vector_path)

        logger.info("Fetching all embeddings to rebuild ANN index...")
        conn = self.db._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT node_id, vector FROM embeddings WHERE model = ?", (model,))
        rows = cursor.fetchall()
        conn.close()

        if rows:
            ids = [r[0] for r in rows]
            vecs = [np.frombuffer(r[1], dtype=np.float32) for r in rows]
            matrix = np.vstack(vecs)
            ann_index.build(matrix, ids)
            logger.info(f"ANN index rebuilt with {len(ids)} vectors.")
        else:
            logger.info("No embeddings found, skipping ANN build.")

    def _process_file(self, full_path: str, rel_path: str, force: bool) -> Tuple[bool, List[Dict[str, Any]]]:
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            # Check hash using rel_path?
            # The get_file_hash usually expects filepath stored in DB.
            # If we switch to rel_path in DB, we should pass rel_path here.
            existing_hash = self.db.get_file_hash(rel_path)

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
                # Use rel_path for node creation and deletion
                nodes, symbols, edges = self._parse_file_content(
                    full_path, rel_path, content,
                    next_route, segment_type, is_client, is_server, is_route_handler, runtime, file_hash
                )
                self.db.delete_nodes_by_filepath(rel_path)
                self.db.batch_add_nodes(nodes)
                for src, tgt, rel, props in edges:
                    self.db.add_edge(src, tgt, rel, props)
                self.db.set_file_hash(rel_path, file_hash)
            else:
                should_index = False
                # Retrieve existing nodes for map using rel_path
                old_nodes = self.db.get_nodes_by_filepath(rel_path)
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
                           file_hash: str) -> Tuple[List[CodeNode], List[Dict[str, Any]], List[Tuple]]:
        ext = os.path.splitext(full_path)[1].lower()
        lang = self.supported_extensions.get(ext)

        nodes = []
        symbols = []
        edges = []

        common_metadata = {
            "next_route_path": next_route,
            "next_segment_type": segment_type,
            "next_use_client": is_client,
            "next_use_server": is_server,
            "next_is_route_handler": is_route_handler,
            "next_runtime": runtime,
            "file_hash": file_hash,
        }

        # Note: we pass rel_path to _create_node for filepath
        if not lang:
            node = self._create_node(rel_path, content, 0, len(content.splitlines()), "text", "file", **common_metadata)
            return [node], [], []

        try:
            parser = get_parser(lang)
            tree = parser.parse(bytes(content, "utf-8"))

            # Extract Imports
            import_deps = self._extract_imports(tree, lang, full_path)
            common_metadata["import_deps"] = import_deps

            # Root Node
            root_node = self._create_node(rel_path, content, 0, len(content.splitlines()), "file", os.path.basename(rel_path), **common_metadata)
            nodes.append(root_node)

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

                if node.parent and node.parent.type == "export_statement":
                    is_exported = True

                if node.type in relevant_types:
                    name = self._get_node_name(node, content)

                    is_top_level = (node.parent.type == "program" or node.parent.type == "module" or node.parent.type == "export_statement")

                    if node.type == "arrow_function" and not name:
                        if node.parent.type == "variable_declarator":
                            name = self._get_node_name(node.parent, content)
                            if node.parent.parent.parent.type == "export_statement":
                                is_exported = True

                    if name and (is_exported or is_top_level):
                        lines_count = node.end_point[0] - node.start_point[0]
                        if lines_count < 2 and not is_exported:
                             pass
                        else:
                            sig_line = content.splitlines()[node.start_point[0]]

                            summary = None
                            if lines_count > 15:
                                try:
                                    chunk_text = self._get_text(node, content)
                                    prompt = f"Analyze this code block from {rel_path}:\n\n{chunk_text}\n\nProvide a 1-sentence semantic summary of what this code DOES (not just what it is). Return JSON {{'summary': '...'}}"
                                    # Use LLMInterface but catch errors
                                    resp = self.llm.generate_response(prompt, json_mode=True)
                                    data = json.loads(resp)
                                    summary = data.get("summary")
                                except Exception:
                                    pass

                            props = common_metadata.copy()
                            if summary:
                                props["semantic_summary"] = summary

                            code_node = self._create_node(
                                rel_path,
                                content,
                                node.start_point[0],
                                node.end_point[0],
                                node.type,
                                name,
                                **props
                            )

                            if not any(n.id == code_node.id for n in nodes):
                                nodes.append(code_node)

                            chunk_text = self._get_text(node, content)
                            calls = set(re.findall(r'\b(?!(?:if|for|while|switch|catch|return|await|async|def|class|function)\b)(\w+)\s*\(', chunk_text))
                            type_usages = set(re.findall(r':\s*([A-Z]\w+)', chunk_text))
                            type_usages.update(re.findall(r'->\s*([A-Z]\w+)', chunk_text))
                            type_usages.update(re.findall(r'new\s+([A-Z]\w+)', chunk_text))

                            for called_func in calls:
                                if called_func != name and len(called_func) > 2:
                                    edges.append((
                                        code_node.id,
                                        f"symbol:{called_func}",
                                        "calls",
                                        {"target_name": called_func, "resolved": False}
                                    ))

                            for type_name in type_usages:
                                if type_name != name and len(type_name) > 2:
                                    edges.append((
                                        code_node.id,
                                        f"symbol:{type_name}",
                                        "uses_type",
                                        {"target_name": type_name, "resolved": False}
                                    ))

                            symbols.append({
                                "name": name,
                                "kind": node.type,
                                "start_line": node.start_point[0],
                                "end_line": node.end_point[0],
                                "signature": sig_line.strip()
                            })
                            return

                for child in node.children:
                    traverse(child)

            traverse(tree.root_node)
            return nodes, symbols, edges

        except Exception as e:
            logger.warning(f"Parsing failed for {full_path}: {e}")
            nodes = [self._create_node(rel_path, content, 0, len(content.splitlines()), "text", "file", **common_metadata)]
            return nodes, symbols, edges

    def _extract_imports(self, tree, lang, full_path) -> List[str]:
        imports = set()

        def visit(n):
            if n.type == "import_statement":
                for child in n.children:
                    if child.type == "string":
                        src = child.text.decode("utf-8").strip('"\'')
                        imports.add(src)
                for c in n.children:
                    if c.type == "string":
                        imports.add(c.text.decode("utf-8").strip('"\''))
            elif n.type == "import_from_statement":
                for c in n.children:
                     if c.type == "dotted_name":
                         imports.add(c.text.decode("utf-8"))
                         break
            for c in n.children:
                visit(c)

        visit(tree.root_node)

        resolved = []
        base_dir = os.path.dirname(full_path) # still need full_path for resolving relative imports

        for imp in imports:
            if imp.startswith("."):
                try:
                    # We store the specifier, maybe we can resolve it to rel_path?
                    # The user prompt mentions "metadata (repo-relative path, ... imports)".
                    # Storing just specifier is fine for now.
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
        # Unique ID now uses relative path
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
