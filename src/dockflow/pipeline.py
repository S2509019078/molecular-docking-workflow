from pathlib import Path
import csv
import json

from .commands import require_tool, run_command
from .config import WorkflowConfig, load_targets
from .models import DockingRecord, PocketDefinition, Target
from .pockets import resolve_pocket
from .preparation import discover_ligands, prepare_ligand, prepare_receptor
from .qc import best_affinity, classify_result, pose_center
from .state import StateStore, outputs_are_complete
from .structures import acquire_structure, clean_receptor, extract_reference_ligand, read_atoms


class DockingWorkflow:
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.targets = load_targets(config.target_table)
        self.state = StateStore(config.work_dir / "state.json")

    def _setting(self, key: str, default):
        return self.config.settings.get(key, default)

    def check(self, require_plip: bool = False) -> list[str]:
        problems: list[str] = []
        for path, label in ((self.config.target_table, "target table"), (self.config.ligand_dir, "ligand directory")):
            if not path.exists():
                problems.append(f"missing {label}: {path}")
        checks = [("mgltools_pythonsh", ("pythonsh",), "MGLTools pythonsh"), ("prepare_receptor4", (), "prepare_receptor4.py"), ("prepare_ligand4", (), "prepare_ligand4.py"), ("obabel", ("obabel",), "Open Babel"), ("vina", ("vina",), "AutoDock Vina")]
        if require_plip:
            checks.append(("plip", ("plip",), "PLIP"))
        for key, candidates, label in checks:
            try:
                require_tool(self.config.tools.get(key), candidates, label)
            except FileNotFoundError as error:
                problems.append(str(error))
        if self.config.ligand_dir.exists():
            try:
                discover_ligands(self.config.ligand_dir)
            except (ValueError, FileNotFoundError) as error:
                problems.append(str(error))
        return problems

    def prepare_structures(self, force: bool = False) -> dict[str, tuple[Path, PocketDefinition]]:
        result = {}
        padding = float(self._setting("box_padding_angstrom", 4.0))
        for target in self.targets:
            key = f"structure:{target.name}"
            raw = self.config.work_dir / "raw" / f"{target.name}.pdb"
            clean = self.config.work_dir / "receptors_clean" / f"{target.name}.pdb"
            box_file = self.config.work_dir / "boxes" / f"{target.name}.json"
            expected = [raw, clean, box_file]
            if not force and outputs_are_complete(expected):
                result[target.name] = (clean, self._load_pocket(box_file))
                continue
            self.state.begin(key)
            try:
                raw = acquire_structure(target, self.config.work_dir / "raw", self.config.root, force=force)
                pocket = resolve_pocket(target, read_atoms(raw), padding=padding)
                if target.pocket_strategy == "co_crystal":
                    extract_reference_ligand(raw, target, self.config.work_dir / "reference_ligands" / f"{target.name}.pdb")
                clean_receptor(raw, target, clean)
                self._write_pocket(box_file, pocket)
                self.state.finish(key, expected)
                result[target.name] = (clean, pocket)
            except Exception as error:
                self.state.finish(key, [], status="failed", message=str(error))
                raise
        return result

    def prepare_receptors(self, force: bool = False) -> dict[str, Path]:
        structures = self.prepare_structures(force=force)
        result = {}
        for target in self.targets:
            output = self.config.work_dir / "receptors_pdbqt" / f"{target.name}.pdbqt"
            key = f"receptor:{target.name}"
            if not force and outputs_are_complete([output]):
                result[target.name] = output
                continue
            self.state.begin(key)
            try:
                prepare_receptor(structures[target.name][0], output, self.config.tools, self.config.work_dir / "logs" / "receptors" / f"{target.name}.log")
                self.state.finish(key, [output])
                result[target.name] = output
            except Exception as error:
                self.state.finish(key, [], status="failed", message=str(error))
                raise
        return result

    def prepare_ligands(self, force: bool = False) -> dict[str, Path]:
        sources = discover_ligands(self.config.ligand_dir)
        result = {}
        for name, source in sources.items():
            output = self.config.work_dir / "ligands_pdbqt" / f"{name}.pdbqt"
            key = f"ligand:{name}"
            if not force and outputs_are_complete([output]):
                result[name] = output
                continue
            self.state.begin(key)
            try:
                prepare_ligand(source, name, self.config.work_dir / "ligands_pdb", self.config.work_dir / "ligands_pdbqt", self.config.tools, self.config.work_dir / "logs" / "ligands")
                self.state.finish(key, [output])
                result[name] = output
            except Exception as error:
                self.state.finish(key, [], status="failed", message=str(error))
                raise
        return result

    def dock(self, force: bool = False) -> list[tuple[Target, str, Path, Path, PocketDefinition]]:
        receptors = self.prepare_receptors(force=force)
        ligands = self.prepare_ligands(force=force)
        structures = self.prepare_structures(force=False)
        vina = require_tool(self.config.tools.get("vina"), ("vina",), "AutoDock Vina")
        tasks = []
        for target in self.targets:
            selected = target.ligands or tuple(ligands)
            unknown = sorted(set(selected) - set(ligands))
            if unknown:
                raise ValueError(f"unknown ligands for {target.name}: {', '.join(unknown)}")
            pocket = structures[target.name][1]
            for ligand_name in selected:
                pose = self.config.work_dir / "poses" / target.name / f"{ligand_name}.pdbqt"
                log = self.config.work_dir / "logs" / "vina" / target.name / f"{ligand_name}.log"
                key = f"dock:{target.name}:{ligand_name}"
                if not force and outputs_are_complete([pose, log]):
                    tasks.append((target, ligand_name, pose, log, pocket))
                    continue
                self.state.begin(key)
                pose.parent.mkdir(parents=True, exist_ok=True)
                box = pocket.box
                command = [str(vina), "--receptor", str(receptors[target.name]), "--ligand", str(ligands[ligand_name]), "--center_x", str(box.center[0]), "--center_y", str(box.center[1]), "--center_z", str(box.center[2]), "--size_x", str(box.size[0]), "--size_y", str(box.size[1]), "--size_z", str(box.size[2]), "--exhaustiveness", str(int(self._setting("exhaustiveness", 8))), "--num_modes", str(int(self._setting("num_modes", 9))), "--energy_range", str(float(self._setting("energy_range", 3))), "--cpu", str(int(self._setting("cpu", 1))), "--out", str(pose)]
                command_result = run_command(command, log)
                if command_result.returncode != 0 or not outputs_are_complete([pose, log]):
                    self.state.finish(key, [pose, log], status="failed", message=f"Vina return code {command_result.returncode}")
                    raise RuntimeError(f"Vina failed for {target.name}/{ligand_name}; see {log}")
                self.state.finish(key, [pose, log])
                tasks.append((target, ligand_name, pose, log, pocket))
        return tasks

    def summarize(self) -> Path:
        records: list[DockingRecord] = []
        threshold = float(self._setting("energy_threshold", -8.0))
        distance_limit = float(self._setting("distance_threshold_angstrom", 5.0))
        for target, ligand_name, pose, log, pocket in self.dock(force=False):
            affinity = best_affinity(log, pose)
            qc = classify_result(affinity, pose_center(pose), pocket, threshold=threshold, distance_limit=distance_limit)
            records.append(DockingRecord(target.name, ligand_name, qc.affinity, qc.distance, qc.classification, qc.evidence, pose, log, qc.reason))
        output = self.config.result_dir / "docking_summary.tsv"
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(["target", "ligand", "affinity_kcal_mol", "reference_center_distance_angstrom", "classification", "evidence", "reason", "pose", "log"])
            for record in records:
                writer.writerow([record.target, record.ligand, "" if record.affinity is None else f"{record.affinity:.3f}", "" if record.distance is None else f"{record.distance:.3f}", record.classification, record.evidence, record.reason, record.pose_path, record.log_path])
        return output

    def plip(self, force: bool = False) -> list[Path]:
        self.summarize()
        obabel = require_tool(self.config.tools.get("obabel"), ("obabel",), "Open Babel")
        plip = require_tool(self.config.tools.get("plip"), ("plip",), "PLIP")
        outputs = []
        for target, ligand_name, pose, _log, _pocket in self.dock(force=False):
            output_dir = self.config.result_dir / "plip" / target.name / ligand_name
            report = output_dir / "report.txt"
            if report.exists() and report.stat().st_size > 0 and not force:
                outputs.append(report)
                continue
            output_dir.mkdir(parents=True, exist_ok=True)
            ligand_pdb = self.config.work_dir / "plip_ligands" / target.name / f"{ligand_name}.pdb"
            ligand_pdb.parent.mkdir(parents=True, exist_ok=True)
            conversion_log = self.config.work_dir / "logs" / "plip" / target.name / f"{ligand_name}_obabel.log"
            conversion = run_command([str(obabel), str(pose), "-O", str(ligand_pdb)], conversion_log)
            if conversion.returncode != 0 or not outputs_are_complete([ligand_pdb]):
                raise RuntimeError(f"failed to convert Vina pose for PLIP; see {conversion_log}")
            complex_pdb = self.config.work_dir / "complexes" / target.name / f"{ligand_name}.pdb"
            self._make_complex(self.config.work_dir / "receptors_clean" / f"{target.name}.pdb", ligand_pdb, complex_pdb)
            plip_log = self.config.work_dir / "logs" / "plip" / target.name / f"{ligand_name}.log"
            plip_result = run_command([str(plip), "-f", str(complex_pdb), "-o", str(output_dir), "--txt", "--xml"], plip_log)
            if plip_result.returncode != 0:
                raise RuntimeError(f"PLIP failed for {target.name}/{ligand_name}; see {plip_log}")
            if not report.exists():
                report.write_text(plip_result.stdout or "PLIP completed; inspect generated files.\n", encoding="utf-8")
            outputs.append(report)
        return outputs

    def run_all(self, force: bool = False, with_plip: bool = False) -> Path:
        self.dock(force=force)
        summary = self.summarize()
        if with_plip:
            self.plip(force=force)
        return summary

    @staticmethod
    def _write_pocket(path: Path, pocket: PocketDefinition) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"strategy": pocket.strategy, "evidence": pocket.evidence, "center": pocket.box.center, "size": pocket.box.size, "reference_center": pocket.reference_center, "rationale": pocket.rationale}, indent=2), encoding="utf-8")

    @staticmethod
    def _load_pocket(path: Path) -> PocketDefinition:
        from .models import DockingBox
        data = json.loads(path.read_text(encoding="utf-8"))
        reference = tuple(data["reference_center"]) if data.get("reference_center") else None
        return PocketDefinition(data["strategy"], data["evidence"], DockingBox(tuple(data["center"]), tuple(data["size"])), reference, data.get("rationale", ""))

    @staticmethod
    def _make_complex(receptor_pdb: Path, ligand_pdb: Path, output: Path) -> None:
        receptor_lines = [line for line in receptor_pdb.read_text(errors="replace").splitlines() if line[:6].strip() in {"ATOM", "HETATM", "TER"}]
        ligand_lines = []
        model_open = False
        for line in ligand_pdb.read_text(errors="replace").splitlines():
            if line.startswith("MODEL"):
                if model_open:
                    break
                model_open = True
                continue
            if line.startswith("ENDMDL") and model_open:
                break
            if line[:6].strip() in {"ATOM", "HETATM"}:
                ligand_lines.append("HETATM" + line[6:17] + "LIG" + line[20:])
        if not ligand_lines:
            raise ValueError(f"converted ligand contains no atoms: {ligand_pdb}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(receptor_lines + ligand_lines) + "\nEND\n", encoding="utf-8")
