import os
import re
import json
from apps.worker.ingestion.utils import clone_repo, cleanup_dir
from apps.api.services.llm import generate_text_sync

try:
    from tree_sitter_languages import get_language, get_parser
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
}

def process_repo(repo_url: str, token: str = None):
    repo_path = clone_repo(repo_url, token)
    chunks = []

    try:
        for root, dirs, files in os.walk(repo_path):
            if ".git" in dirs:
                dirs.remove(".git")

            for file in files:
                ext = os.path.splitext(file)[1]
                if ext in LANGUAGE_MAP:
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, repo_path)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()

                        lang = LANGUAGE_MAP[ext]
                        if HAS_TREE_SITTER:
                            file_chunks = chunk_file_semantic(content, rel_path, lang)
                        else:
                            file_chunks = chunk_file_naive(content, rel_path, lang)

                        chunks.extend(file_chunks)
                    except Exception as e:
                        print(f"Error processing {rel_path}: {e}")
    finally:
        cleanup_dir(repo_path)

    return chunks

def chunk_file_semantic(content: str, filepath: str, lang: str):
    # Attempt to parse with tree-sitter
    try:
        language = get_language(lang)
        parser = get_parser(lang)
        tree = parser.parse(bytes(content, "utf8"))

        # Simplified semantic chunking:
        # We want to grab top-level function and class definitions.
        # This is a heuristic.

        chunks = []
        root_node = tree.root_node

        # If file is small, take whole file
        if len(content.splitlines()) < 50:
             return [{
                "text": content,
                "metadata": {
                    "filepath": filepath,
                    "start_line": 1,
                    "end_line": len(content.splitlines()),
                    "lang": lang,
                    "type": "file"
                }
            }]

        cursor = tree.walk()
        # Traverse top level children
        for child in root_node.children:
             if child.type in ["function_definition", "class_definition", "method_definition"]:
                 start_line = child.start_point[0]
                 end_line = child.end_point[0]
                 text = content.splitlines()[start_line:end_line+1]

                 chunk_content = "\n".join(text)

                 # Agentic: Verify & Summarize
                 summary = None
                 # Heuristic: only summarize "complex" blocks (>15 lines)
                 if len(text) > 15:
                     try:
                        prompt = f"Analyze this code block from {filepath}:\n\n{chunk_content}\n\nProvide a 1-sentence semantic summary. Return JSON {{'summary': '...'}}"
                        # Simple JSON extraction
                        resp = generate_text_sync(prompt, system_prompt="You are a coding expert. Return valid JSON.", temperature=0.0)
                        # Attempt to parse JSON
                        match = re.search(r"\{.*\}", resp, re.DOTALL)
                        if match:
                             data = json.loads(match.group(0))
                             summary = data.get("summary")
                     except Exception as e:
                        print(f"Agentic summary failed: {e}")
                        pass

                 # Graph Extraction (Heuristic)
                 calls = list(set(re.findall(r'\b(?!(?:if|for|while|switch|catch|return|await|async|def|class|function)\b)(\w+)\s*\(', chunk_content)))
                 type_usages = list(set(re.findall(r':\s*([A-Z]\w+)', chunk_content) +
                                        re.findall(r'->\s*([A-Z]\w+)', chunk_content) +
                                        re.findall(r'new\s+([A-Z]\w+)', chunk_content)))

                 metadata = {
                        "filepath": filepath,
                        "start_line": start_line + 1,
                        "end_line": end_line + 1,
                        "lang": lang,
                        "type": child.type,
                        "outgoing_calls": calls,
                        "used_types": type_usages
                 }

                 if summary:
                     metadata["semantic_summary"] = summary

                 chunks.append({
                    "text": chunk_content,
                    "metadata": metadata
                 })

        # If no semantic blocks found (e.g. script), fallback to window
        if not chunks:
            return chunk_file_naive(content, filepath, lang)

        return chunks

    except Exception as e:
        print(f"Tree sitter error for {filepath}: {e}, falling back to naive")
        return chunk_file_naive(content, filepath, lang)

def chunk_file_naive(content: str, filepath: str, lang: str):
    # Naive chunking: 50 lines overlap 10
    lines = content.splitlines()
    chunks = []
    chunk_size = 50
    overlap = 10

    for i in range(0, len(lines), chunk_size - overlap):
        chunk_lines = lines[i:i+chunk_size]
        text = "\n".join(chunk_lines)
        chunks.append({
            "text": text,
            "metadata": {
                "filepath": filepath,
                "start_line": i + 1,
                "end_line": i + len(chunk_lines),
                "lang": lang,
                "type": "window"
            }
        })
    return chunks
