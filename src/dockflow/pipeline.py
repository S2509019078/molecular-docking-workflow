from pathlib import Path
import csv
import json

from .cache import build_payload, manifest_valid, write_manifest
from .commands import require_tool, run_command
from .config import WorkflowConfig, load_targets
from .models import DockingRecord, PocketDefinition, Target
from .pockets import resolve_pocket
from .preparation import discover_ligands, prepare_ligand, prepare_receptor, resolve_preparation_backend
from .qc import best_affinity, classify_result, pose_center
from .receptor_plan import (
    apply_receptor_preparation_plan,
    build_receptor_preparation_plan,
    write_receptor_preparation_plan,
)
from .scientific_qc import ProjectQC, build_project_qc, write_project_qc
from .state import StateStore, outputs_are_complete
from .structures import acquire_structure, extract_reference_ligand, read_atoms


class DockingWorkflow:
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.targets = load_targets(config.target_table)
        self.state = StateStore(config.work_dir / "state.json")

    def _setting(self, key: str, default):
        return self.config.settings.get(key, default)

    def _manifest(self, stage: str, name: str) -> Path:
        return self.config.work_dir / "manifests" / stage / f"{name}.json"

    def preparation_backend(self) -> str:
        return resolve_preparation_backend(
            self.config.tools,
            str(self._setting("preparation_backend", "auto")),
        )

    def scientific_qc(self) -> ProjectQC:
        report = build_project_qc(self.config.path)
        write_project_qc(report, self.config.result_dir / "qc")
        return report

    def check(self, require_plip: bool = False) -> list[str]:
        problems: list[str] = []
        for path, label in ((self.config.target_table, "target table"), (self.config.ligand_dir, "ligand directory")):
            if not path.exists():
                problems.append(f"missing {label}: {path}")
        checks = [
            ("obabel", ("obabel.exe", "obabel"), "Open Babel"),
            ("vina", ("vina.exe", "vina"), "AutoDock Vina"),
        ]
        if require_plip:
            checks.append(("plip", ("plip.exe", "plip"), "PLIP"))
        for key, candidates, label in checks:
            try:
                require_tool(self.config.tools.get(key), candidates, label)
            except FileNotFoundError as error:
                problems.append(str(error))
        try:
            self.preparation_backend()
        except (FileNotFoundError, ValueError) as error:
            problems.append(str(error))
        if self.config.ligand_dir.exists():
            try:
                discover_ligands(self.config.ligand_dir)
            except (ValueError, FileNotFoundError) as error:
                problems.append(str(error))
        return problems

    def _receptor_plan_settings(self) -> dict:
        mode = str(self._setting("scientific_mode", "standard")).strip().lower()
        default_review = "remove" if mode == "exploratory" else "error"
        return {
            "scientific_mode": mode,
            "pocket_water_cutoff_angstrom": float(self._setting("pocket_water_cutoff_angstrom", 4.0)),
            "keep_pocket_waters": self._setting("keep_pocket_waters", False),
            "auto_keep_metals": self._setting("auto_keep_metals", True),
            "auto_keep_cofactors": self._setting("auto_keep_cofactors", True),
            "unknown_hetero_policy": str(self._setting("unknown_hetero_policy", "review")),
            "hetero_review_action": str(self._setting("hetero_review_action", default_review)),
        }

    def prepare_structures(self, force: bool = False) -> dict[str, tuple[Path, PocketDefinition]]:
        result = {}
        padding = float(self._setting("box_padding_angstrom", 4.0))
        plan_settings = self._receptor_plan_settings()
        plan_dir = self.config.result_dir / "preparation" / "receptor_plans"
        for target in self.targets:
            key = f"structure:{target.name}"
            raw = self.config.work_dir / "raw" / f"{target.name}.pdb"
            clean = self.config.work_dir / "receptors_clean" / f"{target.name}.pdb"
            box_file = self.config.work_dir / "boxes" / f"{target.name}.json"
            plan_json = plan_dir / f"{target.name}.json"
            plan_tsv = plan_dir / f"{target.name}.tsv"
            plan_markdown = plan_dir / f"{target.name}.md"
            expected = [raw, clean, box_file, plan_json, plan_tsv, plan_markdown]
            source_inputs = {}
            if target.structure_source == "local":
                source = Path(target.structure).expanduser()
                if not source.is_absolute():
                    source = self.config.root / source
                source_inputs["structure"] = source
            elif raw.exists():
                source_inputs["downloaded_structure"] = raw
            payload = build_payload(
                inputs=source_inputs,
                parameters={"target": target.__dict__, "padding": padding, "receptor_plan": plan_settings},
            )
            manifest = self._manifest("structures", target.name)
            if not force and manifest_valid(manifest, payload, expected):
                result[target.name] = (clean, self._load_pocket(box_file))
                continue
            self.state.begin(key)
            try:
                raw = acquire_structure(
                    target,
                    self.config.work_dir / "raw",
                    self.config.root,
                    force=force or target.structure_source == "local",
                )
                if target.structure_source == "pdb":
                    payload = build_payload(
                        inputs={"downloaded_structure": raw},
                        parameters={"target": target.__dict__, "padding": padding, "receptor_plan": plan_settings},
                    )
                atoms = read_atoms(raw)
                pocket = resolve_pocket(target, atoms, padding=padding)
                if target.pocket_strategy == "co_crystal":
                    extract_reference_ligand(
                        raw,
                        target,
                        self.config.work_dir / "reference_ligands" / f"{target.name}.pdb",
                    )
                plan = build_receptor_preparation_plan(raw, target, plan_settings)
                write_receptor_preparation_plan(plan, None, plan_dir)
                summary = apply_receptor_preparation_plan(
                    raw,
                    target,
                    plan,
                    clean,
                    review_action=plan_settings["hetero_review_action"],
                )
                write_receptor_preparation_plan(plan, summary, plan_dir)
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
        backend = self.preparation_backend()
        receptor_settings = {"preparation_backend": backend}
        for target in self.targets:
            clean = structures[target.name][0]
            output = self.config.work_dir / "receptors_pdbqt" / f"{target.name}.pdbqt"
            payload = build_payload(
                inputs={"clean_receptor": clean},
                parameters=receptor_settings,
                tools={
                    "backend": backend,
                    "pythonsh": str(self.config.tools.get("mgltools_pythonsh", "")),
                    "prepare_receptor4": str(self.config.tools.get("prepare_receptor4", "")),
                },
            )
            manifest = self._manifest("receptors", target.name)
            key = f"receptor:{target.name}"
            if not force and manifest_valid(manifest, payload, [output]):
                result[target.name] = output
                continue
            self.state.begin(key)
            try:
                prepare_receptor(
                    clean,
                    output,
                    self.config.tools,
                    self.config.work_dir / "logs" / "receptors" / f"{target.name}.log",
                    settings=receptor_settings,
                )
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
        backend = self.preparation_backend()
        ligand_settings = {"preparation_backend": backend}
        for name, source in sources.items():
            output = self.config.work_dir / "ligands_pdbqt" / f"{name}.pdbqt"
            payload = build_payload(
                inputs={"ligand_source": source},
                parameters={"source_suffix": source.suffix.lower(), **ligand_settings},
                tools={
                    "backend": backend,
                    "pythonsh": str(self.config.tools.get("mgltools_pythonsh", "")),
                    "prepare_ligand4": str(self.config.tools.get("prepare_ligand4", "")),
                    "obabel": str(self.config.tools.get("obabel", "")),
                },
            )
            manifest = self._manifest("ligands", name)
            key = f"ligand:{name}"
            if not force and manifest_valid(manifest, payload, [output]):
                result[name] = output
                continue
            self.state.begin(key)
            try:
                prepare_ligand(
                    source,
                    name,
                    self.config.work_dir / "ligands_pdb",
                    self.config.work_dir / "ligands_pdbqt",
                    self.config.tools,
                    self.config.work_dir / "logs" / "ligands",
                    settings=ligand_settings,
                )
                write_manifest(manifest, payload, [output])
                self.state.finish(key, [output])
                result[name] = output
            except Exception as error:
                self.state.finish(key, [], status="failed", message=str(error))
                raise
        return result

    def _docking_parameters(self, pocket: PocketDefinition) -> dict:
        return {
            "center": pocket.box.center,
            "size": pocket.box.size,
            "exhaustiveness": int(self._setting("exhaustiveness", 8)),
            "num_modes": int(self._setting("num_modes", 9)),
            "energy_range": float(self._setting("energy_range", 3)),
            "cpu": int(self._setting("cpu", 1)),
            "seed": int(self._setting("seed", 42)),
        }

    def _docking_payload(
        self,
        receptor: Path,
        ligand: Path,
        box_file: Path,
        pocket: PocketDefinition,
        vina: Path,
    ) -> tuple[dict, dict]:
        parameters = self._docking_parameters(pocket)
        payload = build_payload(
            inputs={"receptor": receptor, "ligand": ligand, "box": box_file},
            parameters=parameters,
            tools={"vina": str(vina)},
        )
        return parameters, payload

    def dock(self, force: bool = False) -> list[tuple[Target, str, Path, Path, PocketDefinition]]:
        report = self.scientific_qc()
        if report.blockers:
            labels = "; ".join(f"{issue.code}: {issue.message}" for issue in report.blockers)
            raise ValueError(f"scientific QC blocked docking: {labels}")
        receptors = self.prepare_receptors(force=force)
        ligands = self.prepare_ligands(force=force)
        structures = self.prepare_structures(force=False)
        vina = require_tool(self.config.tools.get("vina"), ("vina.exe", "vina"), "AutoDock Vina")
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
                parameters, payload = self._docking_payload(
                    receptors[target.name], ligands[ligand_name], box_file, pocket, vina
                )
                manifest = self._manifest("docking", f"{target.name}__{ligand_name}")
                key = f"dock:{target.name}:{ligand_name}"
                if not force and manifest_valid(manifest, payload, [pose, log]):
                    tasks.append((target, ligand_name, pose, log, pocket))
                    continue
                self.state.begin(key)
                pose.parent.mkdir(parents=True, exist_ok=True)
                command = [
                    str(vina),
                    "--receptor", str(receptors[target.name]),
                    "--ligand", str(ligands[ligand_name]),
                    "--center_x", str(pocket.box.center[0]),
                    "--center_y", str(pocket.box.center[1]),
                    "--center_z", str(pocket.box.center[2]),
                    "--size_x", str(pocket.box.size[0]),
                    "--size_y", str(pocket.box.size[1]),
                    "--size_z", str(pocket.box.size[2]),
                    "--exhaustiveness", str(parameters["exhaustiveness"]),
                    "--num_modes", str(parameters["num_modes"]),
                    "--energy_range", str(parameters["energy_range"]),
                    "--cpu", str(parameters["cpu"]),
                    "--seed", str(parameters["seed"]),
                    "--out", str(pose),
                ]
                command_result = run_command(command, log)
                if command_result.returncode != 0 or not outputs_are_complete([pose, log]):
                    self.state.finish(
                        key,
                        [pose, log],
                        status="failed",
                        message=f"Vina return code {command_result.returncode}",
                    )
                    raise RuntimeError(f"Vina failed for {target.name}/{ligand_name}; see {log}")
                write_manifest(manifest, payload, [pose, log], command)
                self.state.finish(key, [pose, log])
                tasks.append((target, ligand_name, pose, log, pocket))
        return tasks

    def existing_tasks(self) -> list[tuple[Target, str, Path, Path, PocketDefinition]]:
        ligands = discover_ligands(self.config.ligand_dir)
        vina = require_tool(self.config.tools.get("vina"), ("vina.exe", "vina"), "AutoDock Vina")
        tasks = []
        invalid = []
        for target in self.targets:
            box_file = self.config.work_dir / "boxes" / f"{target.name}.json"
            receptor = self.config.work_dir / "receptors_pdbqt" / f"{target.name}.pdbqt"
            if not box_file.exists() or not receptor.exists():
                invalid.extend(str(path) for path in (box_file, receptor) if not path.exists())
                continue
            pocket = self._load_pocket(box_file)
            for ligand_name in (target.ligands or tuple(ligands)):
                ligand = self.config.work_dir / "ligands_pdbqt" / f"{ligand_name}.pdbqt"
                pose = self.config.work_dir / "poses" / target.name / f"{ligand_name}.pdbqt"
                log = self.config.work_dir / "logs" / "vina" / target.name / f"{ligand_name}.log"
                manifest = self._manifest("docking", f"{target.name}__{ligand_name}")
                if not ligand.exists():
                    invalid.append(str(ligand))
                    continue
                _parameters, payload = self._docking_payload(receptor, ligand, box_file, pocket, vina)
                if not manifest_valid(manifest, payload, [pose, log]):
                    invalid.append(f"stale or missing docking manifest: {target.name}/{ligand_name}")
                    continue
                tasks.append((target, ligand_name, pose, log, pocket))
        if invalid:
            raise FileNotFoundError("invalid existing docking artifacts: " + "; ".join(sorted(set(invalid))))
        return tasks

    def summarize(self) -> Path:
        records: list[DockingRecord] = []
        threshold = float(self._setting("energy_threshold", -8.0))
        distance_limit = float(self._setting("distance_threshold_angstrom", 5.0))
        for target, ligand_name, pose, log, pocket in self.existing_tasks():
            affinity = best_affinity(log, pose)
            qc = classify_result(
                affinity,
                pose_center(pose),
                pocket,
                threshold=threshold,
                distance_limit=distance_limit,
            )
            records.append(
                DockingRecord(
                    target.name,
                    ligand_name,
                    qc.affinity,
                    qc.distance,
                    qc.classification,
                    qc.evidence,
                    pose,
                    log,
                    qc.reason,
                )
            )
        output = self.config.result_dir / "docking_summary.tsv"
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow([
                "target", "ligand", "affinity_kcal_mol",
                "reference_center_distance_angstrom", "classification", "evidence",
                "reason", "pose", "log",
            ])
            for record in records:
                writer.writerow([
                    record.target,
                    record.ligand,
                    "" if record.affinity is None else f"{record.affinity:.3f}",
                    "" if record.distance is None else f"{record.distance:.3f}",
                    record.classification,
                    record.evidence,
                    record.reason,
                    record.pose_path,
                    record.log_path,
                ])
        return output

    def plip(self, force: bool = False) -> list[Path]:
        summary = self.config.result_dir / "docking_summary.tsv"
        if not summary.exists():
            self.summarize()
        obabel = require_tool(self.config.tools.get("obabel"), ("obabel.exe", "obabel"), "Open Babel")
        plip = require_tool(self.config.tools.get("plip"), ("plip.exe", "plip"), "PLIP")
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
            self._make_complex(
                self.config.work_dir / "receptors_clean" / f"{target.name}.pdb",
                ligand_pdb,
                complex_pdb,
            )
            plip_log = self.config.work_dir / "logs" / "plip" / target.name / f"{ligand_name}.log"
            plip_result = run_command(
                [str(plip), "-f", str(complex_pdb), "-o", str(output_dir), "--txt", "--xml"],
                plip_log,
            )
            if plip_result.returncode != 0:
                raise RuntimeError(f"PLIP failed for {target.name}/{ligand_name}; see {plip_log}")
            if not report.exists():
                report.write_text(plip_result.stdout or "PLIP completed; inspect generated files.\n", encoding="utf-8")
            outputs.append(report)
        return outputs

    def run_all(self, force: bool = False, with_plip: bool = False) -> Path:
        report = self.scientific_qc()
        if report.blockers:
            raise ValueError("scientific QC contains blockers; inspect results/qc/project_qc.md")
        self.dock(force=force)
        summary = self.summarize()
        if with_plip:
            self.plip(force=force)
        return summary

    @staticmethod
    def _write_pocket(path: Path, pocket: PocketDefinition) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "strategy": pocket.strategy,
                    "evidence": pocket.evidence,
                    "center": pocket.box.center,
                    "size": pocket.box.size,
                    "reference_center": pocket.reference_center,
                    "rationale": pocket.rationale,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _load_pocket(path: Path) -> PocketDefinition:
        from .models import DockingBox

        data = json.loads(path.read_text(encoding="utf-8"))
        reference = tuple(data["reference_center"]) if data.get("reference_center") else None
        return PocketDefinition(
            data["strategy"],
            data["evidence"],
            DockingBox(tuple(data["center"]), tuple(data["size"])),
            reference,
            data.get("rationale", ""),
        )

    @staticmethod
    def _make_complex(receptor_pdb: Path, ligand_pdb: Path, output: Path) -> None:
        receptor_lines = [
            line
            for line in receptor_pdb.read_text(errors="replace").splitlines()
            if line[:6].strip() in {"ATOM", "HETATM"}
        ]
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
