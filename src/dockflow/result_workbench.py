from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import csv
import json

from .config import WorkflowConfig
from .desktop import load_summary


@dataclass(frozen=True)
class ResultFilter:
    query: str = ""
    max_affinity: float | None = None
    classification: str = ""


def filter_results(rows: list[dict[str, str]], criteria: ResultFilter) -> list[dict[str, str]]:
    query = criteria.query.strip().lower()
    filtered = []
    for row in rows:
        if query and query not in " ".join(str(value).lower() for value in row.values()):
            continue
        if criteria.classification and row.get("classification", "") != criteria.classification:
            continue
        if criteria.max_affinity is not None:
            try:
                affinity = float(row.get("affinity_kcal_mol", ""))
            except (TypeError, ValueError):
                continue
            if affinity > criteria.max_affinity:
                continue
        filtered.append(row)
    return sorted(
        filtered,
        key=lambda row: float(row.get("affinity_kcal_mol", "inf")) if row.get("affinity_kcal_mol") not in {None, ""} else float("inf"),
    )


def export_results_csv(rows: list[dict[str, str]], destination: Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "target",
        "ligand",
        "affinity_kcal_mol",
        "reference_center_distance_angstrom",
        "classification",
        "evidence",
        "reason",
        "pose",
        "log",
    ]
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return destination


def _js_string(value: str) -> str:
    return json.dumps(value)


def build_3dmol_preview(config_path: Path, target: str, ligand: str) -> Path:
    config = WorkflowConfig.from_yaml(Path(config_path))
    rows = load_summary(config.result_dir / "docking_summary.tsv")
    match = next((row for row in rows if row.get("target") == target and row.get("ligand") == ligand), None)
    if not match:
        raise ValueError(f"结果表中未找到 {target}/{ligand}")

    receptor = config.work_dir / "receptors_clean" / f"{target}.pdb"
    pose_value = match.get("pose", "").strip()
    pose = Path(pose_value)
    if not pose.is_absolute():
        pose = config.root / pose
    if not receptor.exists():
        raise FileNotFoundError(receptor)
    if not pose.exists():
        raise FileNotFoundError(pose)

    receptor_text = receptor.read_text(encoding="utf-8", errors="replace")
    pose_text = pose.read_text(encoding="utf-8", errors="replace")
    title = f"{target} · {ligand} · {match.get('affinity_kcal_mol', '')} kcal/mol"
    output = config.result_dir / "viewer" / f"{target}__{ligand}.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<script src="https://3Dmol.org/build/3Dmol-min.js"></script>
<style>
html,body{{height:100%;margin:0;font-family:Segoe UI,Arial,sans-serif;background:#0f172a;color:#e5e7eb}}
header{{height:58px;box-sizing:border-box;padding:16px 22px;background:#111827;border-bottom:1px solid #334155}}
#viewer{{position:absolute;top:58px;bottom:0;left:0;right:0}}
.badge{{display:inline-block;margin-left:12px;padding:3px 8px;border-radius:999px;background:#1d4ed8;font-size:12px}}
</style>
</head>
<body>
<header><strong>{escape(target)} / {escape(ligand)}</strong><span class="badge">{escape(match.get('affinity_kcal_mol',''))} kcal/mol</span></header>
<div id="viewer"></div>
<script>
const viewer = $3Dmol.createViewer('viewer', {{backgroundColor:'#f8fafc'}});
viewer.addModel({_js_string(receptor_text)}, 'pdb');
viewer.setStyle({{}}, {{cartoon:{{color:'spectrum'}}, stick:{{hidden:true}}}});
viewer.addModel({_js_string(pose_text)}, 'pdbqt');
viewer.setStyle({{model:1}}, {{stick:{{colorscheme:'greenCarbon',radius:0.18}}, sphere:{{scale:0.28,colorscheme:'greenCarbon'}}}});
viewer.zoomTo({{model:1}});
viewer.render();
</script>
</body>
</html>"""
    output.write_text(html, encoding="utf-8")
    return output
