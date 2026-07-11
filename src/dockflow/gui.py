from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .desktop import (
    cli_program_and_prefix,
    create_gui_project,
    default_tools,
    inspect_structure,
    load_summary,
    recent_configs,
)
from .wizard import acquire_for_wizard, safe_name


APP_STYLE = """
QWidget { background: #f5f7fb; color: #172033; font-family: "Segoe UI"; font-size: 10pt; }
QMainWindow { background: #f5f7fb; }
#Sidebar { background: #111827; border: none; }
#Brand { color: white; font-size: 22pt; font-weight: 700; padding: 8px 12px; }
#Subtitle { color: #9ca3af; padding: 0 12px 18px 12px; }
QPushButton#NavButton { color: #d1d5db; text-align: left; border: none; padding: 12px 16px; border-radius: 8px; }
QPushButton#NavButton:hover { background: #1f2937; color: white; }
QPushButton#NavButton:checked { background: #2563eb; color: white; font-weight: 600; }
QFrame#Card { background: white; border: 1px solid #e5e7eb; border-radius: 12px; }
QLabel#Title { font-size: 20pt; font-weight: 700; color: #111827; }
QLabel#SectionTitle { font-size: 12pt; font-weight: 700; color: #111827; }
QLabel#Muted { color: #6b7280; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QPlainTextEdit, QTableWidget {
    background: white; border: 1px solid #d1d5db; border-radius: 7px; padding: 7px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #2563eb; }
QPushButton { background: #eef2ff; color: #1e3a8a; border: none; border-radius: 7px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: #dbeafe; }
QPushButton#Primary { background: #2563eb; color: white; }
QPushButton#Primary:hover { background: #1d4ed8; }
QPushButton#Danger { background: #fee2e2; color: #991b1b; }
QProgressBar { background: #e5e7eb; border: none; border-radius: 5px; height: 10px; text-align: center; }
QProgressBar::chunk { background: #2563eb; border-radius: 5px; }
QHeaderView::section { background: #eef2f7; color: #374151; border: none; padding: 8px; font-weight: 600; }
"""


class DockFlowWindow(QMainWindow):
    def __init__(self, runs_dir: Path):
        super().__init__()
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.current_config: Path | None = None
        self.current_pdb: Path | None = None
        self.inspection = None
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_process_output)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        self.setWindowTitle("DockFlow — Molecular Docking Studio")
        self.resize(1220, 800)
        self.setMinimumSize(1040, 700)
        self._build_ui()
        self._apply_defaults()
        self._refresh_recent_projects()

    def _build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QFrame(objectName="Sidebar")
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 24, 14, 18)
        brand = QLabel("DockFlow", objectName="Brand")
        subtitle = QLabel("Molecular Docking Studio", objectName="Subtitle")
        subtitle.setWordWrap(True)
        side.addWidget(brand)
        side.addWidget(subtitle)
        self.nav_buttons = []
        for index, text in enumerate(("新建项目", "运行中心", "结果分析", "工具设置")):
            button = QPushButton(text, objectName="NavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self._switch_page(i))
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addStretch(1)
        version = QLabel("Preview 0.2 · Windows x64", objectName="Subtitle")
        side.addWidget(version)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_project_page())
        self.pages.addWidget(self._build_run_page())
        self.pages.addWidget(self._build_results_page())
        self.pages.addWidget(self._build_tools_page())
        layout.addWidget(sidebar)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self._switch_page(0)

    def _page_shell(self, title: str, description: str):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(28, 24, 28, 24)
        heading = QLabel(title, objectName="Title")
        detail = QLabel(description, objectName="Muted")
        detail.setWordWrap(True)
        outer.addWidget(heading)
        outer.addWidget(detail)
        outer.addSpacing(10)
        return page, outer

    def _card(self, title: str):
        card = QFrame(objectName="Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(QLabel(title, objectName="SectionTitle"))
        return card, layout

    def _build_project_page(self):
        page, outer = self._page_shell("新建分子对接项目", "从 PDB ID 或本地结构开始，自动识别蛋白链和候选共晶配体，并复制待对接配体到独立项目目录。")
        splitter = QSplitter(Qt.Horizontal)

        left, left_layout = self._card("1. 项目与受体")
        form = QFormLayout()
        self.project_name = QLineEdit("docking_project")
        form.addRow("项目名称", self.project_name)
        self.runs_path = QLineEdit(str(self.runs_dir))
        runs_button = QPushButton("选择目录")
        runs_button.clicked.connect(self._choose_runs_dir)
        runs_row = QHBoxLayout(); runs_row.addWidget(self.runs_path, 1); runs_row.addWidget(runs_button)
        runs_wrap = QWidget(); runs_wrap.setLayout(runs_row)
        form.addRow("项目保存位置", runs_wrap)
        self.structure_input = QLineEdit()
        self.structure_input.setPlaceholderText("输入 4 位 PDB ID，或选择本地 .pdb 文件")
        structure_button = QPushButton("选择 PDB")
        structure_button.clicked.connect(self._choose_pdb)
        structure_row = QHBoxLayout(); structure_row.addWidget(self.structure_input, 1); structure_row.addWidget(structure_button)
        structure_wrap = QWidget(); structure_wrap.setLayout(structure_row)
        form.addRow("受体结构", structure_wrap)
        left_layout.addLayout(form)
        analyze = QPushButton("分析受体结构", objectName="Primary")
        analyze.clicked.connect(self._analyze_structure)
        left_layout.addWidget(analyze)

        self.chain_list = QListWidget()
        self.chain_list.setSelectionMode(QListWidget.MultiSelection)
        self.chain_list.setMinimumHeight(90)
        left_layout.addWidget(QLabel("保留蛋白链", objectName="Muted"))
        left_layout.addWidget(self.chain_list)
        self.ligand_combo = QComboBox()
        self.ligand_combo.addItem("不使用共晶配体（盲对接）", None)
        left_layout.addWidget(QLabel("口袋依据", objectName="Muted"))
        left_layout.addWidget(self.ligand_combo)

        right, right_layout = self._card("2. 待对接配体与参数")
        self.ligand_files = QListWidget()
        self.ligand_files.setMinimumHeight(190)
        right_layout.addWidget(self.ligand_files)
        ligand_buttons = QHBoxLayout()
        add_ligands = QPushButton("添加配体文件")
        add_ligands.clicked.connect(self._add_ligands)
        remove_ligand = QPushButton("移除选中")
        remove_ligand.clicked.connect(lambda: [self.ligand_files.takeItem(row) for row in sorted({i.row() for i in self.ligand_files.selectedIndexes()}, reverse=True)])
        ligand_buttons.addWidget(add_ligands); ligand_buttons.addWidget(remove_ligand); ligand_buttons.addStretch(1)
        right_layout.addLayout(ligand_buttons)

        parameters = QFormLayout()
        self.exhaustiveness = QSpinBox(); self.exhaustiveness.setRange(1, 128); self.exhaustiveness.setValue(8)
        self.num_modes = QSpinBox(); self.num_modes.setRange(1, 50); self.num_modes.setValue(9)
        self.cpu = QSpinBox(); self.cpu.setRange(1, max(1, os.cpu_count() or 1)); self.cpu.setValue(min(4, max(1, os.cpu_count() or 1)))
        self.padding = QDoubleSpinBox(); self.padding.setRange(0.0, 30.0); self.padding.setValue(4.0); self.padding.setSuffix(" Å")
        parameters.addRow("搜索强度", self.exhaustiveness)
        parameters.addRow("输出构象数", self.num_modes)
        parameters.addRow("CPU 线程", self.cpu)
        parameters.addRow("口袋边界扩展", self.padding)
        right_layout.addLayout(parameters)

        create_button = QPushButton("创建项目并进入运行中心", objectName="Primary")
        create_button.clicked.connect(self._create_project)
        right_layout.addWidget(create_button)

        splitter.addWidget(left); splitter.addWidget(right); splitter.setSizes([560, 520])
        outer.addWidget(splitter, 1)
        return page

    def _build_run_page(self):
        page, outer = self._page_shell("运行中心", "检查依赖、启动完整对接流程并实时查看输出。任务在独立项目目录内运行，可重复执行和断点续跑。")
        top, top_layout = self._card("当前项目")
        self.current_project_label = QLabel("尚未选择项目", objectName="Muted")
        self.current_project_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_layout.addWidget(self.current_project_label)
        actions = QHBoxLayout()
        open_config = QPushButton("打开已有项目")
        open_config.clicked.connect(self._open_config)
        check = QPushButton("检查环境")
        check.clicked.connect(lambda: self._start_command("check"))
        run = QPushButton("开始完整对接", objectName="Primary")
        run.clicked.connect(lambda: self._start_command("all"))
        stop = QPushButton("停止任务", objectName="Danger")
        stop.clicked.connect(self._stop_process)
        open_dir = QPushButton("打开项目目录")
        open_dir.clicked.connect(self._open_project_dir)
        for button in (open_config, check, run, stop, open_dir): actions.addWidget(button)
        actions.addStretch(1)
        top_layout.addLayout(actions)
        outer.addWidget(top)

        log_card, log_layout = self._card("实时日志")
        self.progress = QProgressBar(); self.progress.setRange(0, 1); self.progress.setValue(0); self.progress.setTextVisible(False)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.progress)
        log_layout.addWidget(self.log, 1)
        outer.addWidget(log_card, 1)
        return page

    def _build_results_page(self):
        page, outer = self._page_shell("结果分析", "读取 docking_summary.tsv，快速比较结合能、参考口袋距离和证据等级。")
        actions = QHBoxLayout()
        refresh = QPushButton("刷新结果", objectName="Primary")
        refresh.clicked.connect(self._refresh_results)
        export = QPushButton("打开结果目录")
        export.clicked.connect(self._open_results_dir)
        actions.addWidget(refresh); actions.addWidget(export); actions.addStretch(1)
        outer.addLayout(actions)
        self.result_table = QTableWidget(0, 6)
        self.result_table.setHorizontalHeaderLabels(["Target", "Ligand", "Affinity (kcal/mol)", "Distance (Å)", "Classification", "Evidence"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        outer.addWidget(self.result_table, 1)
        return page

    def _build_tools_page(self):
        page, outer = self._page_shell("工具与依赖", "DockFlow 会优先使用明确路径，其次搜索系统 PATH 和少量常见安装目录。PLIP 为可选依赖。")
        card, layout = self._card("外部程序路径")
        form = QFormLayout()
        self.tool_edits = {}
        labels = {
            "vina": "AutoDock Vina",
            "obabel": "Open Babel",
            "mgltools_pythonsh": "MGLTools pythonsh",
            "prepare_receptor4": "prepare_receptor4.py",
            "prepare_ligand4": "prepare_ligand4.py",
            "plip": "PLIP（可选）",
        }
        for key, label in labels.items():
            edit = QLineEdit()
            browse = QPushButton("浏览")
            browse.clicked.connect(lambda checked=False, e=edit: self._choose_tool(e))
            row = QHBoxLayout(); row.addWidget(edit, 1); row.addWidget(browse)
            wrap = QWidget(); wrap.setLayout(row)
            form.addRow(label, wrap)
            self.tool_edits[key] = edit
        layout.addLayout(form)
        detect = QPushButton("自动检测已安装工具", objectName="Primary")
        detect.clicked.connect(self._detect_tools)
        layout.addWidget(detect)
        outer.addWidget(card)

        recent_card, recent_layout = self._card("最近项目")
        self.recent_projects = QListWidget()
        self.recent_projects.itemDoubleClicked.connect(lambda item: self._set_current_config(Path(item.data(Qt.UserRole))))
        recent_layout.addWidget(self.recent_projects)
        outer.addWidget(recent_card, 1)
        return page

    def _apply_defaults(self):
        for key, value in default_tools().items():
            if key in self.tool_edits:
                self.tool_edits[key].setText(value)

    def _switch_page(self, index: int):
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons): button.setChecked(i == index)
        if index == 2: self._refresh_results()
        if index == 3: self._refresh_recent_projects()

    def _choose_runs_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "选择项目保存目录", self.runs_path.text())
        if chosen:
            self.runs_path.setText(chosen); self.runs_dir = Path(chosen)

    def _choose_pdb(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 PDB 文件", "", "PDB structure (*.pdb);;All files (*)")
        if path: self.structure_input.setText(path)

    def _choose_tool(self, edit: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(self, "选择可执行文件或脚本")
        if path: edit.setText(path)

    def _add_ligands(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "添加待对接配体", "", "Ligands (*.sdf *.mol2 *.mol *.pdb *.pdbqt *.smi *.smiles);;All files (*)")
        existing = {self.ligand_files.item(i).text() for i in range(self.ligand_files.count())}
        for path in paths:
            if path not in existing: self.ligand_files.addItem(path)

    def _analyze_structure(self):
        try:
            value = self.structure_input.text().strip()
            if not value: raise ValueError("请输入 PDB ID 或选择本地 PDB 文件")
            source = Path(value).expanduser()
            if source.is_file():
                pdb_path = source
            else:
                temp_dir = Path(tempfile.gettempdir()) / "DockFlow" / "structures"
                temp_dir.mkdir(parents=True, exist_ok=True)
                pdb_path = temp_dir / f"{safe_name(value.upper())}.pdb"
                acquire_for_wizard(value, pdb_path)
            self.current_pdb = pdb_path
            self.inspection = inspect_structure(pdb_path)
            self.chain_list.clear()
            for chain in self.inspection.chains:
                self.chain_list.addItem(chain)
                self.chain_list.item(self.chain_list.count() - 1).setSelected(True)
            self.ligand_combo.clear(); self.ligand_combo.addItem("不使用共晶配体（盲对接）", None)
            for ligand in self.inspection.ligands:
                text = f"{ligand['resname']} · chain {ligand['chain'] or '-'} · residue {ligand['residue_id']} · {ligand['atom_count']} atoms"
                self.ligand_combo.addItem(text, ligand)
            QMessageBox.information(self, "结构分析完成", f"检测到 {len(self.inspection.chains)} 条蛋白链和 {len(self.inspection.ligands)} 个候选共晶配体。")
        except Exception as error:
            QMessageBox.critical(self, "结构分析失败", str(error))

    def _create_project(self):
        try:
            if not self.inspection or not self.current_pdb: self._analyze_structure()
            if not self.inspection or not self.current_pdb: return
            chains = tuple(item.text() for item in self.chain_list.selectedItems())
            ligands = [Path(self.ligand_files.item(i).text()) for i in range(self.ligand_files.count())]
            tools = {key: edit.text().strip() for key, edit in self.tool_edits.items()}
            settings = {
                "box_padding_angstrom": self.padding.value(),
                "exhaustiveness": self.exhaustiveness.value(),
                "num_modes": self.num_modes.value(),
                "cpu": self.cpu.value(),
            }
            config = create_gui_project(
                base_dir=Path(self.runs_path.text()),
                project_name=self.project_name.text(),
                pdb_path=self.current_pdb,
                receptor_chains=chains,
                selected_ligand=self.ligand_combo.currentData(),
                ligand_files=ligands,
                tools=tools,
                settings=settings,
            )
            self._set_current_config(config)
            self.log.setPlainText(f"项目创建完成\n{config.parent.parent}\n\n建议先点击“检查环境”，通过后再开始完整对接。")
            self._switch_page(1)
        except Exception as error:
            QMessageBox.critical(self, "创建项目失败", str(error))

    def _open_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 DockFlow 配置", str(self.runs_dir), "YAML (*.yaml *.yml)")
        if path: self._set_current_config(Path(path))

    def _set_current_config(self, path: Path):
        self.current_config = Path(path).resolve()
        self.current_project_label.setText(str(self.current_config))
        self._refresh_results()

    def _start_command(self, command: str):
        if self.process.state() != QProcess.NotRunning:
            QMessageBox.warning(self, "任务正在运行", "请等待当前任务完成，或先停止任务。")
            return
        if not self.current_config:
            QMessageBox.warning(self, "未选择项目", "请先创建项目或打开已有 config.yaml。")
            return
        program, prefix = cli_program_and_prefix()
        args = prefix + [command, "--config", str(self.current_config)]
        self.log.appendPlainText(f"\n$ {program} {' '.join(args)}\n")
        self.progress.setRange(0, 0)
        self.process.setWorkingDirectory(str(self.current_config.parent.parent))
        self.process.start(program, args)

    def _read_process_output(self):
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if text: self.log.appendPlainText(text.rstrip())

    def _process_finished(self, exit_code, _status):
        self.progress.setRange(0, 1); self.progress.setValue(1 if exit_code == 0 else 0)
        self.log.appendPlainText(f"\n任务结束，退出码: {exit_code}")
        if exit_code == 0: self._refresh_results()

    def _process_error(self, error):
        self.progress.setRange(0, 1); self.progress.setValue(0)
        self.log.appendPlainText(f"\n进程错误: {error}")

    def _stop_process(self):
        if self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(2500): self.process.kill()

    def _open_project_dir(self):
        if self.current_config: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_config.parent.parent)))

    def _open_results_dir(self):
        if self.current_config:
            path = self.current_config.parent.parent / "results"
            path.mkdir(exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _refresh_results(self):
        self.result_table.setRowCount(0)
        if not self.current_config: return
        rows = load_summary(self.current_config.parent.parent / "results" / "docking_summary.tsv")
        for row_data in rows:
            row = self.result_table.rowCount(); self.result_table.insertRow(row)
            values = [row_data.get("target", ""), row_data.get("ligand", ""), row_data.get("affinity_kcal_mol", ""), row_data.get("reference_center_distance_angstrom", ""), row_data.get("classification", ""), row_data.get("evidence", "")]
            for column, value in enumerate(values): self.result_table.setItem(row, column, QTableWidgetItem(value))

    def _detect_tools(self):
        for key, value in default_tools().items():
            if key in self.tool_edits: self.tool_edits[key].setText(value)
        QMessageBox.information(self, "检测完成", "已刷新工具路径。未找到的工具仍显示默认命令名，可手动浏览选择。")

    def _refresh_recent_projects(self):
        if not hasattr(self, "recent_projects"): return
        self.recent_projects.clear()
        for config in recent_configs(Path(self.runs_path.text()) if hasattr(self, "runs_path") else self.runs_dir):
            item_text = f"{config.parent.parent.name}   ·   {config}"
            self.recent_projects.addItem(item_text)
            self.recent_projects.item(self.recent_projects.count() - 1).setData(Qt.UserRole, str(config))


def run_gui(runs_dir: Path, smoke_test: bool = False) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("DockFlow")
    app.setOrganizationName("DockFlow")
    app.setStyleSheet(APP_STYLE)
    window = DockFlowWindow(runs_dir)
    if smoke_test:
        window.show()
        app.processEvents()
        window.close()
        print("DockFlow GUI OK")
        return 0
    window.show()
    return app.exec()
