"""Metadados compartilhados pelas execuções do simulador."""

import hashlib
from pathlib import Path

SIMULATOR_VERSION = "development"


class RunMetadata:
    """Registra o código executado sem listas manuais de arquivos."""

    package = Path(__file__).resolve().parent
    project = package.parent.parent

    @classmethod
    def source_files(cls):
        return sorted(
            path
            for path in cls.package.rglob("*")
            if path.is_file()
            and path.suffix in {".py", ".c", ".h"}
            and "__pycache__" not in path.parts
            and "data" not in path.relative_to(cls.package).parts
        )

    @classmethod
    def source_hashes(cls):
        return {
            str(path.relative_to(cls.project)): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in cls.source_files()
        }
