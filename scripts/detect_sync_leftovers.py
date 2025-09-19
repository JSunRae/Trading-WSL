#!/usr/bin/env python3
"""
Detect synchronous code patterns that should be async in an async codebase.

This script scans Python files for common patterns that indicate synchronous
code that might need to be converted to async/await patterns.
"""

import argparse
import ast
import sys
from pathlib import Path
from typing import List, Tuple


class SyncPatternDetector(ast.NodeVisitor):
    """AST visitor to detect synchronous patterns that should be async."""
    
    def __init__(self):
        self.issues: List[Tuple[int, str]] = []
        
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check function definitions for sync patterns."""
        # Check if function contains async operations but isn't async
        has_async_calls = False
        has_await = False
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                # Check for asyncio calls that suggest async context
                if (isinstance(child.func, ast.Attribute) and 
                    isinstance(child.func.value, ast.Name) and
                    child.func.value.id == 'asyncio'):
                    has_async_calls = True
            elif isinstance(child, ast.Await):
                has_await = True
                
        # If function has async calls but no await, it might be a sync function
        # that should be async
        if has_async_calls and not has_await and not node.name.startswith('_'):
            self.issues.append((
                node.lineno,
                f"Function '{node.name}' uses asyncio but is not async"
            ))
            
        self.generic_visit(node)
        
    def visit_Call(self, node: ast.Call) -> None:
        """Check for blocking calls that should be async."""
        # Check for time.sleep (should be asyncio.sleep)
        if (isinstance(node.func, ast.Attribute) and
            isinstance(node.func.value, ast.Name) and
            node.func.value.id == 'time' and
            node.func.attr == 'sleep'):
            self.issues.append((
                node.lineno,
                "time.sleep() found - consider asyncio.sleep() in async context"
            ))
            
        # Check for requests calls (should use aiohttp)
        if (isinstance(node.func, ast.Name) and
            node.func.id in ['get', 'post', 'put', 'delete'] and
            hasattr(node, 'keywords')):
            # This is a heuristic - requests functions are usually imported
            self.issues.append((
                node.lineno,
                f"Synchronous HTTP call '{node.func.id}' found - consider aiohttp"
            ))
            
        self.generic_visit(node)


def check_file(filepath: Path) -> List[Tuple[int, str]]:
    """Check a single file for sync patterns."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        tree = ast.parse(content, filename=str(filepath))
        detector = SyncPatternDetector()
        detector.visit(tree)
        return detector.issues
    except SyntaxError:
        return [(1, "Syntax error - cannot parse file")]
    except Exception as e:
        return [(1, f"Error checking file: {e}")]


def main():
    parser = argparse.ArgumentParser(
        description="Detect synchronous code patterns in async codebase"
    )
    parser.add_argument(
        'paths',
        nargs='+',
        help='Paths to check (files or directories)'
    )
    parser.add_argument(
        '--exclude',
        nargs='*',
        default=['__pycache__', '.venv', 'node_modules'],
        help='Directories to exclude'
    )
    
    args = parser.parse_args()
    
    all_issues = []
    
    for path_str in args.paths:
        path = Path(path_str)
        if path.is_file() and path.suffix == '.py':
            issues = check_file(path)
            for lineno, message in issues:
                all_issues.append((str(path), lineno, message))
        elif path.is_dir():
            for py_file in path.rglob('*.py'):
                skip = False
                for exclude in args.exclude:
                    if exclude in str(py_file):
                        skip = True
                        break
                if not skip:
                    issues = check_file(py_file)
                    for lineno, message in issues:
                        all_issues.append((str(py_file), lineno, message))
    
    if all_issues:
        print("Found potential sync leftovers:")
        for filepath, lineno, message in all_issues:
            print(f"{filepath}:{lineno}: {message}")
        return 1
    else:
        print("No sync leftovers detected.")
        return 0


if __name__ == '__main__':
    sys.exit(main())
