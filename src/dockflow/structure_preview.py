from __future__ import annotations

from html import escape
from pathlib import Path
import json


def _js_string(value: str) -> str:
    return json.dumps(value)


def build_structure_preview(
    structure_path: Path,
    output_path: Path,
    *,
    title: str,
    format_name: str | None = None,
    ligand_only: bool = False,
    accent: str = "greenCarbon",
) -> Path:
    structure_path = Path(structure_path)
    if not structure_path.is_file():
        raise FileNotFoundError(structure_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = structure_path.read_text(encoding="utf-8", errors="replace")
    fmt = format_name or structure_path.suffix.lower().lstrip(".") or "pdb"
    if fmt == "smi":
        fmt = "smiles"
    style = (
        f"viewer.setStyle({{}}, {{stick:{{colorscheme:'{accent}',radius:0.2}},sphere:{{scale:0.3,colorscheme:'{accent}'}}}});"
        if ligand_only
        else "viewer.setStyle({}, {cartoon:{color:'spectrum'},stick:{radius:0.12}});"
    )
    html = f"""<!doctype html>
<html lang='zh-CN'>
<head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{escape(title)}</title>
<script src='https://3Dmol.org/build/3Dmol-min.js'></script>
<style>
html,body{{height:100%;margin:0;background:#f8fafc;font-family:Segoe UI,Arial,sans-serif}}
header{{height:46px;box-sizing:border-box;padding:12px 16px;background:#111827;color:white;font-weight:600}}
#viewer{{position:absolute;top:46px;bottom:0;left:0;right:0}}
</style>
</head>
<body>
<header>{escape(title)}</header><div id='viewer'></div>
<script>
const viewer=$3Dmol.createViewer('viewer',{{backgroundColor:'#f8fafc'}});
viewer.addModel({_js_string(text)},'{fmt}');
{style}
viewer.zoomTo();viewer.render();
</script>
</body></html>"""
    output_path.write_text(html, encoding="utf-8")
    return output_path
