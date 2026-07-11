from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path
from statistics import mean
import csv
import re

from .config import WorkflowConfig
from .desktop import load_summary


@dataclass(frozen=True)
class ReportSummary:
    result_count: int
    scored_count: int
    best_target: str
    best_ligand: str
    best_affinity: float | None
    mean_affinity: float | None
    classifications: dict[str, int]


def summarize_rows(rows: list[dict[str, str]]) -> ReportSummary:
    scored: list[tuple[float, dict[str, str]]] = []
    for row in rows:
        try:
            scored.append((float(row.get("affinity_kcal_mol", "")), row))
        except (TypeError, ValueError):
            continue
    scored.sort(key=lambda item: item[0])
    best = scored[0] if scored else None
    return ReportSummary(
        result_count=len(rows),
        scored_count=len(scored),
        best_target=best[1].get("target", "") if best else "",
        best_ligand=best[1].get("ligand", "") if best else "",
        best_affinity=best[0] if best else None,
        mean_affinity=mean(item[0] for item in scored) if scored else None,
        classifications=dict(Counter(row.get("classification", "unknown") or "unknown" for row in rows)),
    )


def parse_plip_report(path: Path) -> dict[str, int]:
    path = Path(path)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "hydrogen_bonds": r"HYDROGEN BONDS?",
        "hydrophobic_contacts": r"HYDROPHOBIC INTERACTIONS?",
        "salt_bridges": r"SALT BRIDGES?",
        "pi_stacking": r"PI-STACKING",
        "pi_cation": r"PI-CATION",
        "halogen_bonds": r"HALOGEN BONDS?",
        "metal_complexes": r"METAL COMPLEXES?",
    }
    return {name: len(re.findall(pattern, text, flags=re.IGNORECASE)) for name, pattern in patterns.items() if re.search(pattern, text, flags=re.IGNORECASE)}


def collect_plip_counts(config: WorkflowConfig) -> dict[tuple[str, str], dict[str, int]]:
    result: dict[tuple[str, str], dict[str, int]] = {}
    root = config.result_dir / "plip"
    if not root.exists():
        return result
    for report in root.glob("*/*/report.txt"):
        result[(report.parent.parent.name, report.parent.name)] = parse_plip_report(report)
    return result


def export_summary_csv(rows: list[dict[str, str]], destination: Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["target", "ligand", "affinity_kcal_mol", "classification", "evidence"]
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return destination


def _bar_chart(rows: list[dict[str, str]]) -> str:
    scored = []
    for row in rows:
        try:
            scored.append((float(row.get("affinity_kcal_mol", "")), row))
        except (TypeError, ValueError):
            pass
    scored = sorted(scored, key=lambda item: item[0])[:20]
    if not scored:
        return "<p class='muted'>没有可绘制的结合能结果。</p>"
    values = [abs(item[0]) for item in scored]
    maximum = max(values) or 1.0
    bars = []
    for affinity, row in scored:
        width = max(2.0, abs(affinity) / maximum * 100.0)
        label = f"{row.get('target','')} / {row.get('ligand','')}"
        bars.append(
            f"<div class='bar-row'><div class='bar-label'>{escape(label)}</div>"
            f"<div class='bar-track'><div class='bar' style='width:{width:.1f}%'></div></div>"
            f"<div class='bar-value'>{affinity:.2f}</div></div>"
        )
    return "".join(bars)


def build_project_report(config_path: Path) -> Path:
    config = WorkflowConfig.from_yaml(Path(config_path))
    rows = load_summary(config.result_dir / "docking_summary.tsv")
    summary = summarize_rows(rows)
    plip = collect_plip_counts(config)
    output_dir = config.result_dir / "report"
    output_dir.mkdir(parents=True, exist_ok=True)
    export_summary_csv(rows, output_dir / "docking_results.csv")

    class_cards = "".join(
        f"<div class='metric'><span>{escape(name)}</span><strong>{count}</strong></div>"
        for name, count in sorted(summary.classifications.items())
    )
    table_rows = []
    for row in sorted(rows, key=lambda item: float(item.get("affinity_kcal_mol", "inf")) if item.get("affinity_kcal_mol") else float("inf")):
        key = (row.get("target", ""), row.get("ligand", ""))
        interactions = plip.get(key, {})
        interaction_text = ", ".join(f"{name}: {count}" for name, count in interactions.items()) or "—"
        viewer = config.result_dir / "viewer" / f"{key[0]}__{key[1]}.html"
        viewer_link = f"<a href='../viewer/{escape(viewer.name)}'>3D</a>" if viewer.exists() else "—"
        table_rows.append(
            "<tr>"
            f"<td>{escape(key[0])}</td><td>{escape(key[1])}</td>"
            f"<td>{escape(row.get('affinity_kcal_mol',''))}</td>"
            f"<td>{escape(row.get('reference_center_distance_angstrom',''))}</td>"
            f"<td>{escape(row.get('classification',''))}</td>"
            f"<td>{escape(row.get('evidence',''))}</td>"
            f"<td>{escape(interaction_text)}</td><td>{viewer_link}</td>"
            "</tr>"
        )

    best_text = "无可用评分"
    if summary.best_affinity is not None:
        best_text = f"{escape(summary.best_target)} / {escape(summary.best_ligand)} ({summary.best_affinity:.2f} kcal/mol)"
    mean_text = "—" if summary.mean_affinity is None else f"{summary.mean_affinity:.2f} kcal/mol"
    html = f"""<!doctype html>
<html lang='zh-CN'>
<head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>DockFlow 项目报告</title>
<style>
body{{margin:0;background:#f3f6fb;color:#172033;font-family:Segoe UI,Arial,sans-serif}}
main{{max-width:1280px;margin:0 auto;padding:30px}}
h1{{margin:0 0 6px}} .muted{{color:#64748b}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:22px 0}}
.metric,.card{{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:18px;box-shadow:0 4px 18px rgba(15,23,42,.04)}}
.metric span{{display:block;color:#64748b;font-size:13px}} .metric strong{{display:block;font-size:24px;margin-top:8px}}
.bar-row{{display:grid;grid-template-columns:240px 1fr 70px;gap:12px;align-items:center;margin:9px 0}}
.bar-label{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}} .bar-track{{height:14px;background:#e2e8f0;border-radius:999px}}
.bar{{height:100%;background:#2563eb;border-radius:999px}} .bar-value{{text-align:right;font-variant-numeric:tabular-nums}}
table{{width:100%;border-collapse:collapse;background:white}} th,td{{padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:13px}}
th{{background:#eef2f7;position:sticky;top:0}} .table-wrap{{overflow:auto;max-height:620px;border:1px solid #e2e8f0;border-radius:12px}}
a{{color:#2563eb;text-decoration:none}}
</style>
</head>
<body><main>
<h1>DockFlow 分子对接项目报告</h1><div class='muted'>{escape(config.root.name)}</div>
<div class='grid'>
<div class='metric'><span>结果总数</span><strong>{summary.result_count}</strong></div>
<div class='metric'><span>有效评分</span><strong>{summary.scored_count}</strong></div>
<div class='metric'><span>最佳结果</span><strong style='font-size:15px'>{best_text}</strong></div>
<div class='metric'><span>平均结合能</span><strong>{mean_text}</strong></div>
{class_cards}
</div>
<div class='card'><h2>Top 20 结合能</h2>{_bar_chart(rows)}</div>
<h2>完整结果</h2><div class='table-wrap'><table><thead><tr><th>靶标</th><th>配体</th><th>结合能</th><th>参考距离</th><th>分类</th><th>证据</th><th>PLIP摘要</th><th>预览</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></div>
<p class='muted'>报告由 DockFlow 自动生成。对接评分和计算相互作用不能替代实验验证。</p>
</main></body></html>"""
    output = output_dir / "index.html"
    output.write_text(html, encoding="utf-8")
    return output
