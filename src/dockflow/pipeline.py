from pathlib import Path
import csv
import json

from .cache import build_payload, manifest_valid, write_manifest
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

    def _manifest(self, stage: str, name: str) -> Path:
        return self.config.work_dir / "manifests" / stage / f"{name}.json"

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
            source_inputs = {}
            if target.structure_source == "local":
                source = Path(target.structure).expanduser()
                if not source.is_absolute():
                    source = self.config.root / source
                source_inputs["structure"] = source
            elif raw.exists():
                source_inputs["downloaded_structure"] = raw
            payload = build_payload(inputs=source_inputs, parameters={"target": target.__dict__, "padding": padding})
            manifest = self._manifest("structures", target.name)
            if not force and manifest_valid(manifest, payload, expected):
                result[target.name] = (clean, self._load_pocket(box_file))
                continue
            self.state.begin(key)
            try:
                raw = acquire_structure(target, self.config.work_dir / "raw", self.config.root, force=force or target.structure_source == "local")
                if target.structure_source == "pdb":
                    payload = build_payload(inputs={"downloaded_structure": raw}, parameters={"target": target.__dict__, "padding": padding})
                pocket = resolve_pocket(target, read_atoms(raw), padding=padding)
                if target.pocket_strategy == "co_crystal":
                    extract_reference_ligand(raw, target, self.config.work_dir / "reference_ligands" / f"{target.name}.pdb")
                clean_receptor(raw, target, clean)
                self._write_pocket(box_file, pocket)
                write_manifest(manifest, payload, expected)
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
            clean = structures[target.name][0]
            output = self.config.work_dir / "receptors_pdbqt" / f"{target.name}.pdbqt"
            payload = build_payload(inputs={"clean_receptor": clean}, parameters={"prepare": "hydrogens,nphs_lps_waters"}, tools={"pythonsh": str(self.config.tools.get("mgltools_pythonsh", "")), "prepare_receptor4": str(self.config.tools.get("prepare_receptor4", ""))})
            manifest = self._manifest("receptors", target.name)
            key = f"receptor:{target.name}"
            if not force and manifest_valid(manifest, payload, [output]):
                result[target.name] = output
                continue
            self.state.begin(key)
            try:
                prepare_receptor(clean, output, self.config.tools, self.config.work_dir / "logs" / "receptors" / f"{target.name}.log")
                write_manifest(manifest, payload, [output])
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
            payload = build_payload(inputs={"ligand_source": source}, parameters={"source_suffix": source.suffix.lower()}, tools={"pythonsh": str(self.config.tools.get("mgltools_pythonsh", "")), "prepare_ligand4": str(self.config.tools.get("prepare_ligand4", "")), "obabel": str(self.config.tools.get("obabel", ""))})
            manifest = self._manifest("ligands", name)
            key = f"ligand:{name}"
            if not force and manifest_valid(manifest, payload, [output]):
                result[name] = output
                continue
            self.state.begin(key)
            try:
                prepare_ligand(source, name, self.config.work_dir / "ligands_pdb", self.config.work_dir / "ligands_pdbqt", self.config.tools, self.config.work_dir / "logs" / "ligands")
                write_manifest(manifest, payload, [output])
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
            box_file = self.config.work_dir / "boxes" / f"{target.name}.json"
            for ligand_name in selected:
                pose = self.config.work_dir / "poses" / target.name / f"{ligand_name}.pdbqt"
                log = self.config.work_dir / "logs" / "vina" / target.name / f"{ligand_name}.log"
                parameters = {"center": pocket.box.center, "size": pocket.box.size, "exhaustiveness": int(self._setting("exhaustiveness", 8)), "num_modes": int(self._setting("num_modes", 9)), "energy_range": float(self._setting("energy_range", 3)), "cpu": int(self._setting("cpu", 1))}
                payload = build_payload(inputs={"receptor": receptors[target.name], "ligand": ligands[ligand_name], "box": box_file}, parameters=parameters, tools={"vina": str(vina)})
                manifest = self._manifest("docking", f"{target.name}__{ligand_name}")
                key = f"dock:{target.name}:{ligand_name}"
                if not force and manifest_valid(manifest, payload, [pose, log]):
                    tasks.append((target, ligand_name, pose, log, pocket))
                    continue
                self.state.begin(key)
                pose.parent.mkdir(parents=True, exist_ok=True)
                command = [str(vina), "--receptor", str(receptors[target.name]), "--ligand", str(ligands[ligand_name]), "--center_x", str(pocket.box.center[0]), "--center_y", str(pocket.box.center[1]), "--center_z", str(pocket.box.center[2]), "--size_x", str(pocket.box.size[0]), "--size_y", str(pocket.box.size[1]), "--size_z", str(pocket.box.size[2]), "--exhaustiveness", str(parameters["exhaustiveness"]), "--num_modes", str(parameters["num_modes"]), "--energy_range", str(parameters["energy_range"]), "--cpu", str(parameters["cpu"]), "--out", str(pose)]
                command_result = run_command(command, log)
                if command_result.returncode != 0 or not outputs_are_complete([pose, log]):
                    self.state.finish(key, [pose, log], status="failed", message=f"Vina return code {command_result.returncode}")
                    raise RuntimeError(f"Vina failed for {target.name}/{ligand_name}; see {log}")
                write_manifest(manifest, payload, [pose, log], command)
                self.state.finish(key, [pose, log])
                tasks.append((target, ligand_name, pose, log, pocket))
        return tasks

    def existing_tasks(self) -> list[tuple[Target, str, Path, Path, PocketDefinition]]:
        ligands = discover_ligands(self.config.ligand_dir)
        tasks = []
        missing = []
        for target in self.targets:
            box_file = self.config.work_dir / "boxes" / f"{target.name}.json"
            if not box_file.exists():
                missing.append(str(box_file))
                continue
            pocket = self._load_pocket(box_file)
            for ligand_name in (target.ligands or tuple(ligands)):
                pose = self.config.work_dir / "poses" / target.name / f"{ligand_name}.pdbqt"
                log = self.config.work_dir / "logs" / "vina" / target.name / f"{ligand_name}.log"
                if not outputs_are_complete([pose, log]):
                    missing.extend([str(path) for path in (pose, log) if not path.exists()])
                    continue
                tasks.append((target, ligand_name, pose, log, pocket))
        if missing:
            raise FileNotFoundError("missing existing docking artifacts: " + "; ".join(sorted(set(missing))))
        return tasks

    def summarize(self) -> Path:
        records: list[DockingRecord] = []
        threshold = float(self._setting("energy_threshold", -8.0))
        distance_limit = float(self._setting("distance_threshold_angstrom", 5.0))
        for target, ligand_name, pose, log, pocket in self.existing_tasks():
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
        for target, ligand_name, pose, _log, _pocket in self.existing_tasks():
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
        receptor_lines = [line for line in receptor_pdb.read_text(errors="replace").splitlines() if line[:6].strip() in {"ATOM", "HETATM"}]
        ligand_lines = []
        serial = len(receptor_lines) + 1
        for line in ligand_pdb.read_text(errors="replace").splitlines():
            if line.startswith("ENDMDL"):
                break
            if line[:6].strip() in {"ATOM", "HETATM"}:
                element = line[76:78] if len(line) >= 78 else "  "
                ligand_lines.append(f"HETATM{serial:5d}" + line[11:17] + "LIG Z   1" + line[26:76] + element)
                serial += 1
        if not ligand_lines:
            raise ValueError(f"converted ligand contains no atoms: {ligand_pdb}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(receptor_lines + ["TER"] + ligand_lines) + "\nEND\n", encoding="utf-8")
