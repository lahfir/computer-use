"""
Safe file operations tool.
"""

import shutil
from pathlib import Path
from typing import List


class FileTool:
    """
    Safe file operations with validation and safety checks.
    """

    def __init__(self, safety_checker=None):
        """
        Initialize file tool with optional safety checker.

        Args:
            safety_checker: SafetyChecker instance
        """
        self.safety_checker = safety_checker

    def read_file(self, filepath: str) -> str:
        """
        Read contents of a text file.

        Args:
            filepath: Path to file

        Returns:
            File contents as string
        """
        path = Path(filepath).expanduser()

        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        if not path.is_file():
            raise ValueError(f"Not a file: {filepath}")

        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, filepath: str, content: str) -> bool:
        """
        Write content to a file.

        Args:
            filepath: Path to file
            content: Content to write

        Returns:
            True if write succeeded
        """
        path = Path(filepath).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return True

    def copy_file(self, source: str, destination: str) -> bool:
        """
        Copy a file from source to destination.

        Args:
            source: Source file path
            destination: Destination file path

        Returns:
            True if copy succeeded
        """
        if self.safety_checker:
            is_safe, reason = self.safety_checker.analyze_file_operation(
                "copy", source, destination
            )
            if not is_safe:
                raise PermissionError(reason)

        src_path = Path(source).expanduser()
        dst_path = Path(destination).expanduser()

        if not src_path.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)

        return True

    def move_file(self, source: str, destination: str) -> bool:
        """
        Move a file from source to destination.

        Args:
            source: Source file path
            destination: Destination file path

        Returns:
            True if move succeeded
        """
        if self.safety_checker:
            is_safe, reason = self.safety_checker.analyze_file_operation(
                "move", source, destination
            )
            if not is_safe:
                raise PermissionError(reason)

        src_path = Path(source).expanduser()
        dst_path = Path(destination).expanduser()

        if not src_path.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))

        return True

    def delete_file(self, filepath: str) -> bool:
        """
        Delete a file.

        Args:
            filepath: Path to file to delete

        Returns:
            True if deletion succeeded
        """
        if self.safety_checker:
            is_safe, reason = self.safety_checker.analyze_file_operation(
                "delete", filepath
            )
            if not is_safe:
                raise PermissionError(reason)

        path = Path(filepath).expanduser()

        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        path.unlink()
        return True

    def list_directory(self, dirpath: str) -> List[str]:
        """
        List contents of a directory.

        Args:
            dirpath: Path to directory

        Returns:
            List of filenames in directory
        """
        path = Path(dirpath).expanduser()

        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {dirpath}")

        if not path.is_dir():
            raise ValueError(f"Not a directory: {dirpath}")

        return [item.name for item in path.iterdir()]

    def create_directory(self, dirpath: str) -> bool:
        """
        Create a directory (including parent directories).

        Args:
            dirpath: Path to directory to create

        Returns:
            True if creation succeeded
        """
        path = Path(dirpath).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return True

    def file_exists(self, filepath: str) -> bool:
        """
        Check if a file exists.

        Args:
            filepath: Path to check

        Returns:
            True if file exists
        """
        return Path(filepath).expanduser().exists()

    def get_file_info(self, filepath: str) -> dict:
        """
        Get information about a file.

        Args:
            filepath: Path to file

        Returns:
            Dictionary with file information
        """
        path = Path(filepath).expanduser()

        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        stat = path.stat()

        return {
            "name": path.name,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "created": stat.st_ctime,
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
        }
