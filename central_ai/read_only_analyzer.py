"""Read-only Python source analyzer for Developer Agent."""

import ast
import os
import stat
from pathlib import Path


class ReadOnlyAnalyzer:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve(strict=True)
        if not self.workspace.is_dir():
            raise ValueError("INVALID_WORKSPACE")

    def analyze(self, filename):
        if not isinstance(filename, str) or not filename:
            raise ValueError("INVALID_FILENAME")

        relative = Path(filename)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("PATH_BLOCKED")
        if relative.suffix != ".py":
            raise ValueError("PYTHON_ONLY")

        parts = relative.parts
        if not parts or any(part in ("", ".") for part in parts):
            raise ValueError("INVALID_FILENAME")

        directory_fd = os.open(
            self.workspace,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            for part in parts[:-1]:
                next_fd = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
                os.close(directory_fd)
                directory_fd = next_fd

            fd = os.open(
                parts[-1],
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory_fd,
            )
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("NOT_REGULAR_FILE")
                if info.st_size > 1_000_000:
                    raise ValueError("FILE_TOO_LARGE")

                with os.fdopen(fd, "rb", closefd=False) as stream:
                    source = stream.read(1_000_001)

                if len(source) > 1_000_000:
                    raise ValueError("FILE_TOO_LARGE")

                tree = ast.parse(source, filename=filename)
                return {
                    "filename": filename,
                    "status": "analyzed",
                    "classes": [
                        node.name for node in ast.walk(tree)
                        if isinstance(node, ast.ClassDef)
                    ],
                    "functions": [
                        node.name for node in ast.walk(tree)
                        if isinstance(
                            node,
                            (ast.FunctionDef, ast.AsyncFunctionDef),
                        )
                    ],
                }
            finally:
                os.close(fd)
        finally:
            os.close(directory_fd)
