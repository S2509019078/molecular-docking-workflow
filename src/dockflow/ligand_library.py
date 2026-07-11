from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
import json
import re
import shutil

SUPPORTED_LIGAND_SUFFIXES = {".sdf", ".mol2", ".mol", ".pdb", ".pdbqt", ".smi", ".smiles"}


@dataclass(frozen=True)
class LigandRecord:
    name: str
    source: str
    path: Path
    file_format: str
    status: str
    warning: str = ""


def safe_ligand_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
    return cleaned or "ligand"


def inspect_ligand_file(path: Path, source: str = "local") -> LigandRecord:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_LIGAND_SUFFIXES:
        raise ValueError(f"不支持的配体格式: {suffix or '无扩展名'}")
    if path.stat().st_size == 0:
        raise ValueError(f"配体文件为空: {path.name}")

    warning = ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".sdf":
        molecule_count = text.count("$$$$")
        if molecule_count > 1:
            warning = f"包含 {molecule_count} 个分子；当前流程会把整个文件视为一个输入，请先拆分"
    elif suffix in {".smi", ".smiles"}:
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if len(lines) > 1:
            warning = f"包含 {len(lines)} 条 SMILES；建议拆分为单分子文件"
        if lines and "." in lines[0].split()[0]:
            warning = (warning + "；" if warning else "") + "SMILES 含多个片段，可能是盐或复合物"

    return LigandRecord(
        name=safe_ligand_name(path.stem),
        source=source,
        path=path.resolve(),
        file_format=suffix.lstrip(".").upper(),
        status="可用" if not warning else "需检查",
        warning=warning,
    )


def create_smiles_file(directory: Path, name: str, smiles: str) -> LigandRecord:
    smiles = smiles.strip()
    if not smiles:
        raise ValueError("SMILES 不能为空")
    if any(character.isspace() for character in smiles):
        raise ValueError("请输入单个 SMILES，不要包含空格或附加字段")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{safe_ligand_name(name)}.smi"
    path.write_text(f"{smiles}\t{safe_ligand_name(name)}\n", encoding="utf-8")
    return inspect_ligand_file(path, source="SMILES")


def _pubchem_property(identifier: str) -> dict:
    encoded = quote(identifier.strip())
    if identifier.strip().isdigit():
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{encoded}/property/Title,MolecularFormula,MolecularWeight,CanonicalSMILES/JSON"
    else:
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{encoded}/property/Title,MolecularFormula,MolecularWeight,CanonicalSMILES/JSON"
    request = Request(url, headers={"User-Agent": "DockFlow/1.2"})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    properties = payload.get("PropertyTable", {}).get("Properties", [])
    if not properties:
        raise ValueError(f"PubChem 未找到化合物: {identifier}")
    return properties[0]


def download_pubchem_sdf(directory: Path, identifier: str) -> tuple[LigandRecord, dict]:
    identifier = identifier.strip()
    if not identifier:
        raise ValueError("请输入 PubChem CID 或化合物名称")
    properties = _pubchem_property(identifier)
    cid = str(properties.get("CID", identifier))
    title = properties.get("Title") or identifier
    encoded = quote(cid)
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{encoded}/SDF?record_type=3d"
    request = Request(url, headers={"User-Agent": "DockFlow/1.2"})
    try:
        with urlopen(request, timeout=60) as response:
            content = response.read()
    except Exception:
        fallback = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{encoded}/SDF"
        with urlopen(Request(fallback, headers={"User-Agent": "DockFlow/1.2"}), timeout=60) as response:
            content = response.read()
    if not content:
        raise ValueError(f"PubChem 返回空结构: {identifier}")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{safe_ligand_name(title)}_CID{cid}.sdf"
    path.write_bytes(content)
    return inspect_ligand_file(path, source=f"PubChem CID {cid}"), properties


def copy_records(records: list[LigandRecord], destination: Path) -> list[Path]:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    seen = set()
    for record in records:
        name = record.path.name
        lowered = name.lower()
        if lowered in seen:
            raise ValueError(f"配体文件名重复: {name}")
        seen.add(lowered)
        target = destination / name
        shutil.copy2(record.path, target)
        copied.append(target)
    return copied
