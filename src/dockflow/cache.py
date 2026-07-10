from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import os

SCHEMA_VERSION = 1
WORKFLOW_VERSION = "1.1.0"


def file_sha256(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def signature(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256(encoded).hexdigest()


def build_payload(*, inputs: dict[str, Path] | None = None, parameters: dict | None = None, tools: dict | None = None) -> dict:
    input_hashes = {}
    for name, path in (inputs or {}).items():
        resolved = Path(path)
        input_hashes[name] = {"path": str(resolved), "sha256": file_sha256(resolved)}
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "inputs": input_hashes,
        "parameters": parameters or {},
        "tools": tools or {},
    }


def manifest_valid(path: Path, payload: dict, outputs: list[Path]) -> bool:
    if not path.exists() or not outputs or not all(Path(item).is_file() and Path(item).stat().st_size > 0 for item in outputs):
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("signature") == signature(payload)


def write_manifest(path: Path, payload: dict, outputs: list[Path], command: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        **payload,
        "signature": signature(payload),
        "outputs": [str(item) for item in outputs],
        "command": command or [],
    }
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
