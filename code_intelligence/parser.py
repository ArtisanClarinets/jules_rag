from abc import ABC, abstractmethod
from typing import List, Optional
import os
import tree_sitter_languages
from tree_sitter import Language, Parser
from .db import Database, CodeNode

class BaseParser(ABC):
    def __init__(self, db: Database):
        self.db = db

    @abstractmethod
    def parse_file(self, filepath: str):
        pass

class TreeSitterParser(BaseParser):
    def __init__(self, db: Database, language_name: str):
        super().__init__(db)
        self.language_name = language_name
        self.language = tree_sitter_languages.get_language(language_name)
        self.parser = Parser(self.language)

    def parse_file(self, filepath: str):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = self.parser.parse(bytes(content, "utf8"))
            root_node = tree.root_node
            
            # Create file node
            file_id = f"file:{filepath}"
            file_node = CodeNode(
                id=file_id,
                type='file',
                name=os.path.basename(filepath),
                filepath=filepath,
                start_line=1,
                end_line=len(content.splitlines()),
                content=content,
                properties={"language": self.language_name}
            )
            self.db.add_node(file_node)
            
            self._visit(root_node, file_id, filepath, content.splitlines())
            
        except Exception as e:
            print(f"Error parsing {filepath} with tree-sitter ({self.language_name}): {e}")

    def _visit(self, node, parent_id, filepath, lines):
        # This needs to be implemented by subclasses per language query structure
        # Or we can use generic queries if possible
        pass

    def _get_text(self, node, lines):
        start_row = node.start_point.row
        end_row = node.end_point.row
        return "\n".join(lines[start_row:end_row+1])

class PythonParser(TreeSitterParser):
    def __init__(self, db: Database):
        super().__init__(db, "python")

    # _visit is overridden below, removing duplicate definition

    def _handle_function(self, node, parent_id, filepath, lines):
        name_node = node.child_by_field_name('name')
        if not name_node: return
        
        func_name = name_node.text.decode('utf8')
        func_id = f"func:{filepath}:{func_name}:{node.start_point.row}"
        
        code_node = CodeNode(
            id=func_id,
            type='function',
            name=func_name,
            filepath=filepath,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            content=self._get_text(node, lines),
            properties={}
        )
        self.db.add_node(code_node)
        self.db.add_edge(parent_id, func_id, "CONTAINS")
        
        # Recurse
        body = node.child_by_field_name('body')
        if body:
            self._visit(body, func_id, filepath, lines)

    def _handle_class(self, node, parent_id, filepath, lines):
        name_node = node.child_by_field_name('name')
        if not name_node: return
        
        class_name = name_node.text.decode('utf8')
        class_id = f"class:{filepath}:{class_name}:{node.start_point.row}"
        
        code_node = CodeNode(
            id=class_id,
            type='class',
            name=class_name,
            filepath=filepath,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            content=self._get_text(node, lines),
            properties={}
        )
        self.db.add_node(code_node)
        self.db.add_edge(parent_id, class_id, "CONTAINS")
        
        body = node.child_by_field_name('body')
        if body:
            self._visit(body, class_id, filepath, lines)

    def _handle_import(self, node, parent_id, filepath):
        # Extract import info using AST traversal or Tree-sitter fields
        # Tree-sitter python structure for imports:
        # (import_statement (dotted_name) @name)
        # (import_from_statement module_name: (dotted_name) @module)
        
        # Simple text extraction for now to ensure data is captured
        # Note: In _visit below, we don't pass lines to _handle_import, 
        # but _get_text expects lines. We can use node.text which is bytes.
        import_text = node.text.decode('utf8')
        
        # Store as property on the file node (parent_id is likely file)
        # Since we can't easily modify the parent node without fetching it, 
        # we will add a separate "dependency" node or edge.
        
        # Let's create an edge to a "module" node
        module_name = ""
        if node.type == 'import_statement':
            # import x
            child = node.child_by_field_name('name')
            if child: module_name = child.text.decode('utf8')
        elif node.type == 'import_from_statement':
            # from x import y
            child = node.child_by_field_name('module_name')
            if child: module_name = child.text.decode('utf8')
            
        if module_name:
            # Create a placeholder module node if we don't track external modules yet
            mod_id = f"module:{module_name}"
            # We don't add the node to DB to avoid clutter, but we add the edge
            self.db.add_edge(parent_id, mod_id, "IMPORTS", {"raw": import_text})

    def _visit(self, node, parent_id, filepath, lines):
        # Overriding visit to ensure we catch calls
        # We need to traverse children
        
        # 1. Check for function calls
        if node.type == 'call':
             self._handle_call(node, parent_id, filepath)

        # 2. Check for definitions (recurse)
        if node.type == 'function_definition':
            self._handle_function(node, parent_id, filepath, lines)
        elif node.type == 'class_definition':
            self._handle_class(node, parent_id, filepath, lines)
        elif node.type in ['import_statement', 'import_from_statement']:
             self._handle_import(node, parent_id, filepath)
        else:
            # Recurse
            for child in node.children:
                self._visit(child, parent_id, filepath, lines)

    def _handle_call(self, node, parent_id, filepath):
        # (call function: (identifier) @name arguments: (...))
        func_node = node.child_by_field_name('function')
        if func_node:
            callee = func_node.text.decode('utf8')
            # Add edge
            # Target ID is unknown, so we use a reference ID
            target_ref = f"ref:{callee}"
            self.db.add_edge(parent_id, target_ref, "CALLS", {"line": node.start_point.row + 1})

class JavascriptParser(TreeSitterParser):
    def __init__(self, db: Database):
        super().__init__(db, "javascript")

    def _visit(self, node, parent_id, filepath, lines):
        for child in node.children:
            if child.type == 'function_declaration':
                self._handle_function(child, parent_id, filepath, lines)
            elif child.type == 'class_declaration':
                self._handle_class(child, parent_id, filepath, lines)
            elif child.type == 'lexical_declaration': 
                 # Handle const x = function() ...
                 pass
            else:
                self._visit(child, parent_id, filepath, lines)

    def _handle_function(self, node, parent_id, filepath, lines):
        name_node = node.child_by_field_name('name')
        if not name_node: return
        
        func_name = name_node.text.decode('utf8')
        func_id = f"func:{filepath}:{func_name}:{node.start_point.row}"
        
        code_node = CodeNode(
            id=func_id,
            type='function',
            name=func_name,
            filepath=filepath,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            content=self._get_text(node, lines),
            properties={}
        )
        self.db.add_node(code_node)
        self.db.add_edge(parent_id, func_id, "CONTAINS")
        
        body = node.child_by_field_name('body')
        if body:
            self._visit(body, func_id, filepath, lines)

    def _handle_class(self, node, parent_id, filepath, lines):
        name_node = node.child_by_field_name('name')
        if not name_node: return
        
        class_name = name_node.text.decode('utf8')
        class_id = f"class:{filepath}:{class_name}:{node.start_point.row}"
        
        code_node = CodeNode(
            id=class_id,
            type='class',
            name=class_name,
            filepath=filepath,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            content=self._get_text(node, lines),
            properties={}
        )
        self.db.add_node(code_node)
        self.db.add_edge(parent_id, class_id, "CONTAINS")
        
        body = node.child_by_field_name('body')
        if body:
            self._visit(body, class_id, filepath, lines)

class GenericParser(TreeSitterParser):
    def __init__(self, db: Database, lang: str):
        super().__init__(db, lang)
    
    def _visit(self, node, parent_id, filepath, lines):
        # Generic traversal for C-style languages (Java, C#, Go, Rust often share similar structure names)
        # or just fallback to naive traversal
        if node.type in ['function_definition', 'method_declaration', 'function_declaration']:
             self._handle_function(node, parent_id, filepath, lines)
        elif node.type in ['class_definition', 'class_declaration']:
             self._handle_class(node, parent_id, filepath, lines)
        else:
             for child in node.children:
                 self._visit(child, parent_id, filepath, lines)

    def _handle_function(self, node, parent_id, filepath, lines):
        # Try to find name
        name_node = node.child_by_field_name('name')
        if not name_node:
            # Fallback: look for identifier child
            for child in node.children:
                if child.type == 'identifier':
                    name_node = child
                    break
        
        if name_node:
            func_name = name_node.text.decode('utf8', errors='ignore')
            func_id = f"func:{filepath}:{func_name}:{node.start_point.row}"
            code_node = CodeNode(
                id=func_id, type='function', name=func_name,
                filepath=filepath, start_line=node.start_point.row+1, end_line=node.end_point.row+1,
                content=self._get_text(node, lines), properties={}
            )
            self.db.add_node(code_node)
            self.db.add_edge(parent_id, func_id, "CONTAINS")
            
            # Recurse body
            body = node.child_by_field_name('body')
            if body:
                for child in body.children:
                    self._visit(child, func_id, filepath, lines)

    def _handle_class(self, node, parent_id, filepath, lines):
        name_node = node.child_by_field_name('name')
        if not name_node:
             for child in node.children:
                if child.type == 'type_identifier':
                    name_node = child
                    break
        
        if name_node:
            class_name = name_node.text.decode('utf8', errors='ignore')
            class_id = f"class:{filepath}:{class_name}:{node.start_point.row}"
            code_node = CodeNode(
                id=class_id, type='class', name=class_name,
                filepath=filepath, start_line=node.start_point.row+1, end_line=node.end_point.row+1,
                content=self._get_text(node, lines), properties={}
            )
            self.db.add_node(code_node)
            self.db.add_edge(parent_id, class_id, "CONTAINS")
            
            body = node.child_by_field_name('body')
            if body:
                for child in body.children:
                    self._visit(child, class_id, filepath, lines)

class ParserFactory:
    @staticmethod
    def get_parser(filepath: str, db: Database) -> Optional[BaseParser]:
        ext = os.path.splitext(filepath)[1]
        if ext == '.py':
            return PythonParser(db)
        elif ext in ['.js', '.jsx', '.ts', '.tsx']:
            return JavascriptParser(db)
        elif ext == '.java':
            return GenericParser(db, 'java')
        elif ext == '.go':
            return GenericParser(db, 'go')
        elif ext == '.rs':
            return GenericParser(db, 'rust')
        elif ext == '.cs':
            return GenericParser(db, 'c_sharp')
        return None
