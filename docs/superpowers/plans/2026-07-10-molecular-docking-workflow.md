# Molecular Docking Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable Linux-first docking workflow in which a new project requires only target, ligand, and configuration changes.

**Architecture:** A Python package owns configuration, validation, state, pocket selection, result parsing, and orchestration. Small external-command adapters invoke PyMOL, Open Babel, MGLTools, Vina, and PLIP; a Bash launcher provides a convenient Linux entry point. Every stage writes a manifest so downstream work and resume decisions are explicit.

**Tech Stack:** Python 3.10+, PyYAML, pytest, Bash, optional PyMOL/Open Babel/MGLTools/AutoDock Vina/PLIP.

## Global Constraints

- Linux is the supported execution platform; cross-platform Python inspection/reporting commands may run on Windows.
- Accept either downloaded PDB IDs or user-supplied PDB/mmCIF structures.
- Support `co_crystal`, `explicit_box`, `reference_ligand`, `residue_box`, `predicted_pocket`, and `blind` pocket strategies.
- Never overwrite source inputs; generated data belongs in `work/` and `results/`.
- Do not commit raw conversations, personal paths, third-party binaries, licensed software, or large calculation outputs.
- Only skip an existing task after an integrity check; `--force` reruns the selected stage.

---

## File Map

- `pyproject.toml`: package metadata, dependencies, CLI and pytest settings.
- `README.md`: Chinese quick start, workflow explanation and result interpretation.
- `LICENSE`: MIT license for repository-owned code.
- `.gitignore`: local config, inputs, work, results, caches and large structures.
- `config/config.example.yaml`: portable software and analysis settings.
- `config/targets.example.tsv`: examples for downloaded/local structures and pocket modes.
- `dockflow.sh`: Linux launcher.
- `src/dockflow/models.py`: typed target, pocket and task records.
- `src/dockflow/config.py`: YAML/TSV loading and validation.
- `src/dockflow/structures.py`: PDB/mmCIF import, download, coordinate and residue parsing.
- `src/dockflow/pockets.py`: pocket strategy resolution and box calculation.
- `src/dockflow/commands.py`: external command discovery and safe subprocess execution.
- `src/dockflow/state.py`: atomic JSON task state and integrity predicates.
- `src/dockflow/pipeline.py`: stage orchestration and manifests.
- `src/dockflow/qc.py`: Vina parsing, pose geometry and evidence-aware classification.
- `src/dockflow/cli.py`: `check`, `run`, `status`, `report` commands.
- `tests/fixtures/`: minimal structures, Vina logs and configs.
- `tests/test_*.py`: unit and orchestration tests.
- `docs/input-formats.md`, `docs/pocket-strategies.md`, `docs/troubleshooting.md`: durable user guidance.

### Task 1: Package skeleton and validated configuration

**Files:** Create `pyproject.toml`, `.gitignore`, `config/config.example.yaml`, `config/targets.example.tsv`, `src/dockflow/__init__.py`, `src/dockflow/models.py`, `src/dockflow/config.py`, `tests/test_config.py`.

**Interfaces:** Produce `WorkflowConfig.from_yaml(path: Path)`, `Target.from_row(row: dict[str, str])`, and `load_targets(path: Path) -> list[Target]`.

- [ ] Write tests proving that a downloaded target, local target, explicit box and invalid mixed source are parsed correctly.
- [ ] Run `python -m pytest tests/test_config.py -v`; expect import failure before implementation.
- [ ] Implement enums for structure source and pocket strategy, immutable dataclasses, relative-path resolution against the project root, required-column validation, numeric box validation and duplicate target rejection.
- [ ] Run the configuration tests; expect all tests to pass.
- [ ] Commit with `git commit -m "feat: add validated workflow configuration"`.

### Task 2: Structure acquisition and coordinate parsing

**Files:** Create `src/dockflow/structures.py`, `tests/fixtures/receptor_with_ligand.pdb`, `tests/fixtures/receptor_without_ligand.pdb`, `tests/test_structures.py`.

**Interfaces:** Produce `acquire_structure(target: Target, raw_dir: Path) -> Path`, `read_atoms(path: Path) -> list[Atom]`, `select_ligand(atoms, residue_name, chain) -> list[Atom]`, and `select_residues(atoms, chain, residue_ids) -> list[Atom]`.

- [ ] Test local copy without source overwrite, cached download validation, PDB atom parsing, alternate-location handling, ligand selection and missing-ligand error messages.
- [ ] Run the tests and confirm missing-module failures.
- [ ] Implement URL download through `urllib.request`, atomic temporary-file replacement, PDB parsing and a clear error for mmCIF when Biopython is unavailable.
- [ ] Run `python -m pytest tests/test_structures.py -v`; expect pass.
- [ ] Commit with `git commit -m "feat: acquire and inspect receptor structures"`.

### Task 3: Pocket strategies and evidence levels

**Files:** Create `src/dockflow/pockets.py`, `tests/test_pockets.py`, `docs/pocket-strategies.md`.

**Interfaces:** Produce `resolve_pocket(target: Target, atoms: list[Atom]) -> PocketDefinition` and `box_from_atoms(atoms, padding: float, minimum_size: float) -> DockingBox`.

- [ ] Test co-crystal center, explicit coordinates, residue-derived boxes, predicted-pocket import, blind box, auto precedence and refusal to auto-select among tied predicted pockets.
- [ ] Run tests and verify failure before implementation.
- [ ] Implement deterministic resolution, dimensions bounded by configured minimum/maximum, evidence values `reference`, `informed`, `predicted`, `exploratory`, and a manifest-ready rationale string.
- [ ] Run pocket tests; expect pass.
- [ ] Document when each strategy is scientifically appropriate and commit with `git commit -m "feat: support evidence-aware pocket strategies"`.

### Task 4: External tools, task state and resume safety

**Files:** Create `src/dockflow/commands.py`, `src/dockflow/state.py`, `tests/test_commands.py`, `tests/test_state.py`.

**Interfaces:** Produce `discover_tool(configured: str | None, candidates: list[str]) -> Path | None`, `run_command(argv: list[str], log_path: Path) -> CommandResult`, `StateStore.begin(key)`, `StateStore.finish(key, outputs)`, and `outputs_are_complete(paths) -> bool`.

- [ ] Test executable discovery, argument preservation for paths with spaces, nonzero exit capture, atomic state writes, stale `running` recovery and refusal to skip empty output.
- [ ] Run tests and confirm failure.
- [ ] Implement subprocess calls without shell interpolation and JSON state replacement through a temporary sibling file.
- [ ] Run both test modules; expect pass.
- [ ] Commit with `git commit -m "feat: add safe command and resume infrastructure"`.

### Task 5: Preparation and docking orchestration

**Files:** Create `src/dockflow/pipeline.py`, `tests/test_pipeline.py`, `dockflow.sh`.

**Interfaces:** Produce `Pipeline.prepare_structures()`, `prepare_ligands()`, `prepare_pockets()`, `dock()`, `build_complexes()`, and `run_plip()`; every method returns a `StageSummary` and writes `work/manifests/<stage>.tsv`.

- [ ] Use fake executable fixtures to test exact PyMOL/Open Babel/MGLTools/Vina/PLIP arguments, target–ligand Cartesian expansion, single-task failure isolation and valid-result skipping.
- [ ] Run pipeline tests and confirm failure.
- [ ] Implement stages using configuration and state interfaces; preserve raw/clean/reference-ligand files separately and never infer identity solely from filename splitting.
- [ ] Run pipeline tests; expect pass.
- [ ] Add a Bash launcher that resolves its own directory and executes `python -m dockflow.cli`; validate with `bash -n dockflow.sh` and commit with `git commit -m "feat: orchestrate docking stages"`.

### Task 6: Evidence-aware QC and reports

**Files:** Create `src/dockflow/qc.py`, `tests/fixtures/vina.log`, `tests/fixtures/pose.pdbqt`, `tests/test_qc.py`.

**Interfaces:** Produce `parse_vina_affinities(path) -> list[float]`, `pose_center(path) -> Point3D`, `classify_result(result, pocket, thresholds) -> QCRecord`, and `write_qc_tables(records, results_dir)`.

- [ ] Test affinity parsing, first-model center, reference-ligand distance, box containment, boundary warnings, and the rule that ligand-free modes never emit a reference distance.
- [ ] Run tests and confirm failure.
- [ ] Implement classifications `high_confidence`, `exploratory`, `manual_review`, `failed` with evidence, reasons and metric names in every row.
- [ ] Run QC tests; expect pass.
- [ ] Commit with `git commit -m "feat: add pocket-aware docking quality control"`.

### Task 7: CLI, documentation and example usability

**Files:** Create `src/dockflow/cli.py`, `README.md`, `LICENSE`, `docs/input-formats.md`, `docs/troubleshooting.md`, `tests/test_cli.py`.

**Interfaces:** Provide `dockflow check`, `dockflow run [--stage NAME] [--force]`, `dockflow status`, and `dockflow report`.

- [ ] Test help output, missing tool report, dry-run task counts, valid stage selection and nonzero exit when failures remain.
- [ ] Run CLI tests and confirm failure.
- [ ] Implement argparse commands and concise Chinese console output.
- [ ] Write a README with five quick-start scenarios: downloaded PDB with ligand, local PDB with ligand, explicit box without ligand, residue/predicted pocket without ligand, and blind exploratory docking.
- [ ] Run `python -m pytest -q`, `python -m dockflow.cli --help`, and `python -m dockflow.cli check --config config/config.example.yaml`; tests must pass and the check command must clearly list optional missing tools.
- [ ] Commit with `git commit -m "docs: deliver reusable docking workflow"`.

### Task 8: Release verification

**Files:** Modify only files implicated by verification failures.

**Interfaces:** Produce a clean Git repository ready for GitHub upload.

- [ ] Run `python -m compileall -q src tests` and `python -m pytest -q`.
- [ ] Run `bash -n dockflow.sh` under WSL or Git Bash.
- [ ] Search tracked files for the original username, desktop paths, JSON conversation IDs and private repository URLs; expect no matches.
- [ ] Run `git status --short`; expect no uncommitted files after fixes.
- [ ] Commit verification fixes with `git commit -m "test: harden docking workflow release"` only if changes were required.

