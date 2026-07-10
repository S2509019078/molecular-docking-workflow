from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen
import csv
import re
import shutil
import yaml

WATERS = {"HOH", "WAT", "DOD"}
COMMON_IONS = {"NA", "K", "CL", "CA", "MG", "MN", "ZN", "FE", "CU", "CO", "NI", "CD", "HG", "SO4", "PO4"}
TARGET_COLUMNS = ["name", "structure_source", "structure", "pocket_strategy", "receptor_chains", "ligand", "ligand_chain", "ligand_residue_id", "center_x", "center_y", "center_z", "size_x", "size_y", "size_z", "residue_ids", "keep_hetero_resnames", "ligands"]


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
    return cleaned or "docking_run"


def detect_hetero_residues(pdb_path: Path) -> list[dict]:
    groups: Counter[tuple[str, str, int]] = Counter()
    for line in pdb_path.read_text(errors="replace").splitlines():
        if line[:6].strip() != "HETATM" or line[16:17] not in {" ", "A"}:
            continue
        resname = line[17:20].strip().upper()
        if not resname or resname in WATERS:
            continue
        try:
            residue_id = int(line[22:26])
        except ValueError:
            continue
        groups[(resname, line[21:22].strip(), residue_id)] += 1
    rows = [{"resname": key[0], "chain": key[1], "residue_id": key[2], "atom_count": count, "likely_ligand": key[0] not in COMMON_IONS and count >= 5} for key, count in groups.items()]
    return sorted(rows, key=lambda row: (not row["likely_ligand"], -row["atom_count"], row["resname"], row["chain"], row["residue_id"]))


def acquire_for_wizard(structure: str, destination: Path) -> tuple[str, str, Path]:
    source = Path(structure).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_file():
        shutil.copy2(source, destination)
        return "local", str(destination), destination
    pdb_id = structure.strip().upper()
    if not re.fullmatch(r"[A-Za-z0-9]{4}", pdb_id):
        raise ValueError("请输入4位 PDB ID，或现有本地 PDB 文件路径")
    with urlopen(f"https://files.rcsb.org/download/{pdb_id}.pdb", timeout=60) as response:
        destination.write_bytes(response.read())
    if destination.stat().st_size == 0:
        raise ValueError(f"下载的 PDB 文件为空: {pdb_id}")
    return "local", str(destination), destination


def create_run_directory(base: Path, project_name: str, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    run_dir = base / f"{stamp}_{safe_name(project_name)}"
    suffix = 1
    while run_dir.exists():
        run_dir = base / f"{stamp}_{safe_name(project_name)}_{suffix:02d}"
        suffix += 1
    for relative in ("config", "inputs/structures", "inputs/ligands", "work", "results", "logs"):
        (run_dir / relative).mkdir(parents=True, exist_ok=True)
    return run_dir


def write_project(run_dir: Path, target_row: dict, tools: dict | None = None) -> Path:
    target_path = run_dir / "config" / "targets.tsv"
    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TARGET_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerow({key: target_row.get(key, "") for key in TARGET_COLUMNS})
    config = {
        "tools": tools or {"mgltools_pythonsh": "pythonsh", "prepare_receptor4": "prepare_receptor4.py", "prepare_ligand4": "prepare_ligand4.py", "obabel": "obabel", "vina": "vina", "plip": "plip"},
        "settings": {"box_padding_angstrom": 4.0, "exhaustiveness": 8, "num_modes": 9, "energy_range": 3, "cpu": 1, "energy_threshold": -8.0, "distance_threshold_angstrom": 5.0},
        "paths": {"targets": "config/targets.tsv", "ligands": "inputs/ligands", "work": "work", "results": "results"},
    }
    config_path = run_dir / "config" / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (run_dir / "RUN_INFO.txt").write_text("本目录是一次独立运行。输入、配置、中间文件、结果和日志不会与其他运行混用。\n", encoding="utf-8")
    return config_path


def interactive_wizard(input_fn=input, print_fn=print, base_dir: Path = Path("runs")) -> Path:
    print_fn("DockFlow 交互式项目向导")
    project_name = input_fn("项目名称: ").strip() or "docking"
    run_dir = create_run_directory(base_dir, project_name)
    structure_input = input_fn("输入4位 PDB ID 或本地 PDB 路径: ").strip()
    structure_file = run_dir / "inputs" / "structures" / f"{safe_name(project_name)}.pdb"
    source_type, stored_path, pdb_path = acquire_for_wizard(structure_input, structure_file)
    hetero = detect_hetero_residues(pdb_path)
    candidates = [item for item in hetero if item["likely_ligand"]]
    if candidates:
        print_fn("检测到可能的共晶配体:")
        for index, item in enumerate(candidates, 1):
            print_fn(f"  {index}. {item['resname']} chain={item['chain'] or '-'} residue={item['residue_id']} atoms={item['atom_count']}")
        choice = input_fn("选择配体编号；直接回车则不用共晶配体: ").strip()
    else:
        print_fn("未检测到明显的共晶小分子配体，将使用盲对接。")
        choice = ""
    selected = None
    if choice:
        index = int(choice)
        if index < 1 or index > len(candidates):
            raise ValueError("配体编号超出范围")
        selected = candidates[index - 1]
    chains = sorted({line[21:22].strip() for line in pdb_path.read_text(errors="replace").splitlines() if line.startswith("ATOM") and line[21:22].strip()})
    print_fn("检测到蛋白链: " + (", ".join(chains) if chains else "未标注链"))
    receptor_chains = input_fn("保留的蛋白链，多个用逗号分隔；直接回车保留全部: ").strip()
    target_row = {
        "name": safe_name(project_name),
        "structure_source": source_type,
        "structure": str(Path(stored_path).relative_to(run_dir)),
        "pocket_strategy": "co_crystal" if selected else "blind",
        "receptor_chains": receptor_chains,
        "ligand": selected["resname"] if selected else "",
        "ligand_chain": selected["chain"] if selected else "",
        "ligand_residue_id": selected["residue_id"] if selected else "",
    }
    config_path = write_project(run_dir, target_row)
    print_fn(f"项目已创建: {run_dir}")
    print_fn(f"把待对接配体放入: {run_dir / 'inputs' / 'ligands'}")
    print_fn(f"运行: dockflow all --config {config_path}")
    return config_path
