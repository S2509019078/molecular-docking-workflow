from __future__ import annotations

from pathlib import Path

import yaml
from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from .gui_preview import DockFlowPreviewWindow, PREVIEW_STYLE
from .preprocess_status import build_preparation_status
from .tooling import (
    TOOL_SPECS,
    discover_tools,
    discover_tools_deep,
    find_autodocktools_components,
    read_project_tools,
    write_project_tools,
)


SCIENTIFIC_STYLE = PREVIEW_STYLE + """
QWidget { font-size:10pt; }
QFrame#Card { background:#ffffff; border:1px solid #dce4f0; border-radius:14px; }
QLabel#Title { color:#14213d; font-size:21pt; font-weight:700; }
QLabel#SectionTitle { color:#1e293b; font-size:11pt; font-weight:700; }
QLabel#StatusReady { color:#166534; background:#dcfce7; border:1px solid #bbf7d0; border-radius:8px; padding:8px 10px; font-weight:700; }
QLabel#StatusWarning { color:#92400e; background:#fef3c7; border:1px solid #fde68a; border-radius:8px; padding:8px 10px; font-weight:700; }
QLabel#StatusBlocked { color:#991b1b; background:#fee2e2; border:1px solid #fecaca; border-radius:8px; padding:8px 10px; font-weight:700; }
QLabel#StageChip { color:#334155; background:#eef2f7; border:1px solid #dbe3ef; border-radius:8px; padding:6px 10px; font-weight:600; }
QPushButton { min-height:32px; padding:4px 12px; border-radius:7px; }
QPushButton#Primary { background:#2563eb; color:white; border:1px solid #2563eb; font-weight:700; }
QPushButton#Primary:hover { background:#1d4ed8; }
QPushButton#PreviewToggle { background:#ffffff; color:#334155; border:1px solid #cbd5e1; min-height:34px; }
QPushButton#PreviewToggle:checked { background:#dbeafe; color:#1d4ed8; border-color:#93c5fd; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { min-height:32px; border:1px solid #cbd5e1; border-radius:7px; background:white; padding:2px 8px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border:1px solid #2563eb; }
QTableWidget#PreparationTable, QTableWidget#ToolStatusTable { background:white; border:1px solid #dbe3ef; border-radius:8px; gridline-color:#e5e7eb; }
QTableWidget::item { padding:5px; }
QTableWidget::item:selected { background:#2563eb; color:white; }
QHeaderView::section { background:#eef2f7; color:#334155; border:none; border-bottom:1px solid #dbe3ef; padding:7px; font-weight:700; }
QSplitter::handle { background:#dbe3ef; width:2px; height:2px; }
"""


class DockFlowScientificWindow(DockFlowPreviewWindow):
    def __init__(self, runs_dir: Path):
        self._active_science_command = ""
        super().__init__(runs_dir)
        self.setWindowTitle("DockFlow — Molecular Docking Studio 1.4.1")
        self._compress_sidebar()
        self._configure_collapsible_preview()
        self._install_preparation_center()
        self._install_robust_pdb_drop()
        self._update_tool_status_table()
        self._refresh_scientific_status()

    def _build_tools_page(self):
        page = super()._build_tools_page()
        for label in page.findChildren(QLabel):
            if label.text() == "MGLTools pythonsh":
                label.setText("AutoDockTools Python")

        outer = page.layout()
        guide, layout = self._card("AutoDockTools 配置助手")
        description = QLabel(
            "无需识别 MGLTools 名称。选择 AutoDockTools、ADFRsuite 或旧版 MGLTools 的安装目录，"
            "DockFlow 会自动寻找 Python 解释器、prepare_receptor4.py 和 prepare_ligand4.py。"
        )
        description.setWordWrap(True)
        description.setObjectName("Muted")
        layout.addWidget(description)

        actions = QHBoxLayout()
        choose = QPushButton("选择 AutoDockTools 安装目录", objectName="Primary")
        choose.clicked.connect(self._choose_autodocktools_directory)
        deep = QPushButton("深度扫描本机")
        deep.clicked.connect(self._detect_tools)
        save = QPushButton("保存到当前项目")
        save.clicked.connect(self._save_tools_for_current_project)
        actions.addWidget(choose)
        actions.addWidget(deep)
        actions.addWidget(save)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.tool_status_table = QTableWidget(0, 3, objectName="ToolStatusTable")
        self.tool_status_table.setHorizontalHeaderLabels(["组件", "状态", "路径"])
        self.tool_status_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tool_status_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tool_status_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tool_status_table.verticalHeader().setVisible(False)
        self.tool_status_table.setMinimumHeight(190)
        self.tool_status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tool_status_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.tool_status_table)
        outer.insertWidget(3, guide)
        return page

    def _compress_sidebar(self):
        sidebar = self.findChild(QFrame, "Sidebar")
        if sidebar is not None:
            sidebar.setFixedWidth(184)
        for label in self.findChildren(QLabel):
            text = label.text()
            if "DockFlow 1." in text or "Preview 0.2" in text:
                label.setText("DockFlow 1.4.1\nScientific Workflow")
                label.setWordWrap(True)

    def _configure_collapsible_preview(self):
        self.preview_toggle = QPushButton("显示结构预览", objectName="PreviewToggle")
        self.preview_toggle.setCheckable(True)
        self.preview_toggle.setChecked(False)
        self.preview_toggle.toggled.connect(self._toggle_preview)

        page = self.pages.widget(0)
        outer = page.layout()
        index = outer.indexOf(self.project_vertical_splitter)
        outer.insertWidget(max(0, index), self.preview_toggle)
        self.preview_tabs.setMinimumHeight(250)
        self.preview_tabs.hide()
        self.project_vertical_splitter.setCollapsible(1, True)
        self.project_vertical_splitter.setSizes([800, 0])

    def _toggle_preview(self, visible: bool):
        self.preview_tabs.setVisible(visible)
        self.preview_toggle.setText("隐藏结构预览" if visible else "显示结构预览")
        if visible:
            self.project_vertical_splitter.setSizes([520, 320])
            if self.current_pdb and self.current_pdb.exists():
                self._preview_current_receptor()
        else:
            self.project_vertical_splitter.setSizes([820, 0])

    def _install_preparation_center(self):
        page = self.pages.widget(1)
        outer = page.layout()
        card, layout = self._card("科研预处理中心")

        self.prep_summary = QLabel("尚未选择项目", objectName="StatusWarning")
        self.prep_summary.setWordWrap(True)
        layout.addWidget(self.prep_summary)

        chip_row = QHBoxLayout()
        self.stage_chips = {}
        for stage in ("环境", "受体", "配体", "口袋", "结果"):
            chip = QLabel(f"{stage} · 未检查", objectName="StageChip")
            chip_row.addWidget(chip)
            self.stage_chips[stage] = chip
        chip_row.addStretch(1)
        layout.addLayout(chip_row)

        policy_row = QHBoxLayout()
        policy_row.addWidget(QLabel("科研模式"))
        self.scientific_mode = QComboBox()
        self.scientific_mode.addItem("标准科研", "standard")
        self.scientific_mode.addItem("快速探索", "exploratory")
        self.scientific_mode.addItem("专家", "expert")
        policy_row.addWidget(self.scientific_mode)
        policy_row.addWidget(QLabel("待确认 HETATM"))
        self.hetero_policy = QComboBox()
        self.hetero_policy.addItem("阻止并要求确认", "error")
        self.hetero_policy.addItem("保留待确认项", "keep")
        self.hetero_policy.addItem("探索模式：删除待确认项", "remove")
        policy_row.addWidget(self.hetero_policy)
        policy_row.addStretch(1)
        layout.addLayout(policy_row)

        actions = QHBoxLayout()
        refresh = QPushButton("刷新状态")
        refresh.clicked.connect(self._refresh_scientific_status)
        qc = QPushButton("运行科研 QC")
        qc.clicked.connect(lambda: self._start_science_command("qc"))
        plan = QPushButton("生成预处理计划")
        plan.clicked.connect(lambda: self._start_science_command("preparation-report"))
        prepare = QPushButton("自动预处理", objectName="Primary")
        prepare.clicked.connect(lambda: self._start_science_command("prepare"))
        open_report = QPushButton("打开 QC 报告")
        open_report.clicked.connect(self._open_qc_report)
        for button in (refresh, qc, plan, prepare, open_report):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.prep_table = QTableWidget(0, 4, objectName="PreparationTable")
        self.prep_table.setHorizontalHeaderLabels(["阶段", "检查项", "状态", "说明"])
        self.prep_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.prep_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.prep_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.prep_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.prep_table.verticalHeader().setVisible(False)
        self.prep_table.setMinimumHeight(230)
        self.prep_table.setAlternatingRowColors(True)
        self.prep_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.prep_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.prep_table)

        insert_at = max(0, outer.count() - 1)
        outer.insertWidget(insert_at, card)

    def _install_robust_pdb_drop(self):
        self._pdb_drop_targets = {self.structure_input}
        parent = self.structure_input.parentWidget()
        if parent is not None:
            parent.setAcceptDrops(True)
            parent.installEventFilter(self)
            self._pdb_drop_targets.add(parent)
        self.structure_input.setAcceptDrops(True)
        self.structure_input.installEventFilter(self)

    @staticmethod
    def _pdb_drop_path(event) -> Path | None:
        mime = event.mimeData()
        if not mime.hasUrls():
            return None
        paths = [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
        if len(paths) != 1:
            return None
        path = paths[0]
        return path if path.is_file() and path.suffix.lower() in {".pdb", ".ent", ".pdb1", ".pdb2", ".pdb3"} else None

    def eventFilter(self, watched, event):
        if watched in getattr(self, "_pdb_drop_targets", set()):
            if event.type() in {QEvent.DragEnter, QEvent.DragMove}:
                if self._pdb_drop_path(event):
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Drop:
                path = self._pdb_drop_path(event)
                if path:
                    self.structure_input.setText(str(path.resolve()))
                    event.acceptProposedAction()
                    self._analyze_structure()
                    return True
        return super().eventFilter(watched, event)

    def _analyze_structure(self):
        super()._analyze_structure()
        if self.current_pdb and self.current_pdb.exists():
            self.preview_toggle.setChecked(True)
            self._preview_current_receptor()

    def _create_project(self):
        self._resolve_visible_tool_paths()
        previous = self.current_config
        super()._create_project()
        if self.current_config and self.current_config != previous:
            self._save_scientific_policy()
            self._sync_tool_paths_to_project()
            self._refresh_scientific_status()

    def _set_current_config(self, path: Path):
        super()._set_current_config(path)
        self._load_project_tools()
        self._load_scientific_policy()
        self._restore_project_preview()
        self._update_tool_status_table()
        self._refresh_scientific_status()

    def _restore_project_preview(self):
        if not self.current_config:
            return
        root = self.current_config.parent.parent
        candidates = []
        for pattern in ("*.pdb", "*.ent", "*.pdb1", "*.pdb2", "*.pdb3"):
            candidates.extend((root / "inputs" / "structures").glob(pattern))
        if candidates:
            self.current_pdb = sorted(candidates)[0]
            self._preview_current_receptor()

    def _load_scientific_policy(self):
        if not self.current_config or not self.current_config.exists():
            return
        try:
            data = yaml.safe_load(self.current_config.read_text(encoding="utf-8")) or {}
            settings = data.get("settings", {})
            mode_index = self.scientific_mode.findData(str(settings.get("scientific_mode", "standard")))
            review_index = self.hetero_policy.findData(str(settings.get("hetero_review_action", "error")))
            if mode_index >= 0:
                self.scientific_mode.setCurrentIndex(mode_index)
            if review_index >= 0:
                self.hetero_policy.setCurrentIndex(review_index)
        except Exception as error:
            self.statusBar().showMessage(f"读取科研策略失败：{error}", 8000)

    def _save_scientific_policy(self):
        if not self.current_config:
            return
        data = yaml.safe_load(self.current_config.read_text(encoding="utf-8")) or {}
        settings = data.setdefault("settings", {})
        settings["scientific_mode"] = self.scientific_mode.currentData()
        settings["hetero_review_action"] = self.hetero_policy.currentData()
        settings.setdefault("unknown_hetero_policy", "review")
        settings.setdefault("pocket_water_cutoff_angstrom", 4.0)
        settings.setdefault("keep_pocket_waters", False)
        settings.setdefault("auto_keep_metals", True)
        settings.setdefault("auto_keep_cofactors", True)
        settings["preparation_backend"] = "autodocktools"
        self.current_config.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def _tool_values(self) -> dict[str, str]:
        return {key: edit.text().strip() for key, edit in self.tool_edits.items()}

    def _fill_tool_edits(self, resolved: dict[str, Path | None]):
        for key, path in resolved.items():
            if path is not None and key in self.tool_edits:
                self.tool_edits[key].setText(str(path))

    def _resolve_visible_tool_paths(self):
        resolved = discover_tools(self._tool_values())
        self._fill_tool_edits(resolved)
        self._update_tool_status_table(resolved)
        return resolved

    def _load_project_tools(self):
        if not self.current_config or not self.current_config.exists():
            return
        try:
            values = read_project_tools(self.current_config)
            for key, value in values.items():
                if value and key in self.tool_edits:
                    self.tool_edits[key].setText(value)
            self._resolve_visible_tool_paths()
        except Exception as error:
            self.statusBar().showMessage(f"读取项目工具路径失败：{error}", 8000)

    def _sync_tool_paths_to_project(self):
        if self.current_config:
            write_project_tools(self.current_config, self._tool_values())

    def _save_tools_for_current_project(self):
        if not self.current_config:
            QMessageBox.information(self, "尚未选择项目", "创建或打开项目后再保存工具路径。")
            return
        self._resolve_visible_tool_paths()
        self._sync_tool_paths_to_project()
        self._refresh_scientific_status()
        QMessageBox.information(self, "已保存", "工具路径已写入当前项目 config.yaml。")

    def _choose_tool(self, edit):
        super()._choose_tool(edit)
        self._resolve_visible_tool_paths()
        if self.current_config:
            self._sync_tool_paths_to_project()
            self._refresh_scientific_status()

    def _choose_autodocktools_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择 AutoDockTools 安装目录", str(Path.home()))
        if not directory:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            found = find_autodocktools_components(Path(directory))
        finally:
            QApplication.restoreOverrideCursor()
        self._fill_tool_edits(found)
        self._update_tool_status_table()
        if self.current_config:
            self._sync_tool_paths_to_project()
            self._refresh_scientific_status()
        missing = [key for key, value in found.items() if value is None]
        if missing:
            QMessageBox.warning(
                self,
                "AutoDockTools 未完整识别",
                "已扫描所选目录，但仍缺少：\n" + "\n".join(missing) +
                "\n\n请选择更上层的安装目录，或分别使用“浏览”指定文件。",
            )
        else:
            QMessageBox.information(self, "AutoDockTools 已识别", "三个必要组件已经自动填入。")

    def _detect_tools(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            resolved = discover_tools_deep(self._tool_values())
        finally:
            QApplication.restoreOverrideCursor()
        self._fill_tool_edits(resolved)
        self._update_tool_status_table(resolved)
        if self.current_config:
            self._sync_tool_paths_to_project()
            self._refresh_scientific_status()
        found = sum(path is not None for path in resolved.values())
        missing_required = [spec.label for spec in TOOL_SPECS if spec.required and resolved.get(spec.key) is None]
        message = f"已识别 {found}/{len(TOOL_SPECS)} 个组件。"
        if missing_required:
            message += "\n\n仍缺少：\n" + "\n".join(missing_required)
        QMessageBox.information(self, "工具扫描完成", message)

    def _update_tool_status_table(self, resolved: dict[str, Path | None] | None = None):
        if not hasattr(self, "tool_status_table"):
            return
        resolved = resolved or discover_tools(self._tool_values())
        self.tool_status_table.setRowCount(0)
        for spec in TOOL_SPECS:
            row = self.tool_status_table.rowCount()
            self.tool_status_table.insertRow(row)
            path = resolved.get(spec.key)
            status = "已找到" if path else ("缺失" if spec.required else "未安装（可选）")
            values = (spec.label, status, str(path or ""))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 1:
                    color = "#166534" if path else ("#991b1b" if spec.required else "#92400e")
                    item.setForeground(QBrush(QColor(color)))
                self.tool_status_table.setItem(row, column, item)

    def _required_tool_keys(self, command: str) -> set[str]:
        required: set[str] = set()
        if command in {"prepare", "prepare-receptors", "prepare-ligands", "dock", "all"}:
            required.update({"mgltools_pythonsh", "prepare_receptor4", "prepare_ligand4"})
        if command in {"dock", "all"}:
            required.add("vina")
        if command in {"plip", "plip-pose"}:
            required.update({"obabel", "plip"})
        if self.current_config and command in {"prepare", "prepare-ligands", "dock", "all"}:
            ligand_dir = self.current_config.parent.parent / "inputs" / "ligands"
            if any(path.suffix.lower() in {".sdf", ".mol"} for path in ligand_dir.glob("*")):
                required.add("obabel")
        return required

    def _guide_missing_tools(self, command: str) -> bool:
        required = self._required_tool_keys(command)
        if not required:
            return True
        resolved = discover_tools(self._tool_values())
        missing = [spec.label for spec in TOOL_SPECS if spec.key in required and resolved.get(spec.key) is None]
        if not missing:
            self._fill_tool_edits(resolved)
            return True

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("需要配置外部工具")
        box.setText("当前任务缺少必要组件")
        box.setInformativeText("\n".join(missing) + "\n\n可以自动搜索，或进入工具设置手动选择。")
        scan = box.addButton("自动搜索", QMessageBox.ActionRole)
        settings = box.addButton("打开工具设置", QMessageBox.AcceptRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is scan:
            self._detect_tools()
            resolved = discover_tools(self._tool_values())
            missing = [spec.label for spec in TOOL_SPECS if spec.key in required and resolved.get(spec.key) is None]
            if not missing:
                return True
            self._switch_page(3)
            return False
        if clicked is settings:
            self._switch_page(3)
        return False

    def _start_command(self, command: str):
        if self.current_config:
            self._save_scientific_policy()
            self._resolve_visible_tool_paths()
            self._sync_tool_paths_to_project()
        if command not in {"check", "qc", "preparation-report", "status", "pockets"}:
            if not self._guide_missing_tools(command):
                return
        self._active_science_command = command
        super()._start_command(command)

    def _start_science_command(self, command: str):
        if not self.current_config:
            QMessageBox.warning(self, "未选择项目", "请先创建项目或打开已有项目。")
            return
        self._start_command(command)

    def _refresh_scientific_status(self):
        if not hasattr(self, "prep_table"):
            return
        self.prep_table.setRowCount(0)
        if not self.current_config:
            self._set_summary_state("StatusWarning", "尚未选择项目。创建项目后可运行 QC 和自动预处理。")
            return
        try:
            status = build_preparation_status(self.current_config)
        except Exception as error:
            self._set_summary_state("StatusBlocked", f"状态读取失败：{error}")
            return

        counts: dict[str, dict[str, int]] = {}
        for check in status.checks:
            row = self.prep_table.rowCount()
            self.prep_table.insertRow(row)
            values = (check.stage, check.label, check.state, check.detail)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 2:
                    color = "#166534" if check.state == "完成" else ("#991b1b" if check.blocking else "#92400e")
                    item.setForeground(QBrush(QColor(color)))
                self.prep_table.setItem(row, column, item)
            stage = counts.setdefault(check.stage, {"done": 0, "total": 0, "blocked": 0})
            stage["total"] += 1
            if check.state == "完成":
                stage["done"] += 1
            if check.blocking and check.state != "完成":
                stage["blocked"] += 1

        for stage, chip in self.stage_chips.items():
            values = counts.get(stage, {"done": 0, "total": 0, "blocked": 0})
            if values["blocked"]:
                chip.setText(f"{stage} · 阻断 {values['blocked']}")
            elif values["total"]:
                chip.setText(f"{stage} · {values['done']}/{values['total']}")
            else:
                chip.setText(f"{stage} · 未检查")

        pending = sum(1 for item in status.checks if item.state in {"待处理", "提示"})
        if status.blockers:
            self._set_summary_state(
                "StatusBlocked",
                f"预处理被阻断：{len(status.blockers)}项。可先点击“深度扫描本机”或选择 AutoDockTools 安装目录。",
            )
        elif status.complete:
            self._set_summary_state("StatusReady", "预处理与结果检查均已完成。可以查看构象、运行 PLIP 或生成报告。")
        else:
            self._set_summary_state("StatusWarning", f"环境可用，仍有 {pending} 项待处理或需确认。")

    def _set_summary_state(self, object_name: str, text: str):
        self.prep_summary.setObjectName(object_name)
        self.prep_summary.setText(text)
        self.prep_summary.style().unpolish(self.prep_summary)
        self.prep_summary.style().polish(self.prep_summary)

    def _open_qc_report(self):
        if not self.current_config:
            return
        report = self.current_config.parent.parent / "results" / "qc" / "project_qc.md"
        if not report.exists():
            QMessageBox.information(self, "尚无 QC 报告", "请先运行科研 QC。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(report.resolve())))

    def _process_finished(self, exit_code, status):
        super(DockFlowPreviewWindow, self)._process_finished(exit_code, status)
        command = self._active_science_command
        self._active_science_command = ""
        self._refresh_scientific_status()
        self._update_tool_status_table()
        if exit_code == 0 and command in {"prepare", "prepare-ligands", "all"}:
            try:
                self._preview_prepared_ligand()
            except Exception:
                pass


def run_gui(runs_dir: Path, smoke_test: bool = False) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("DockFlow")
    app.setOrganizationName("DockFlow")
    app.setStyleSheet(SCIENTIFIC_STYLE)
    window = DockFlowScientificWindow(runs_dir)
    if smoke_test:
        window.show()
        app.processEvents()
        window.close()
        print("DockFlow GUI scientific workflow OK")
        return 0
    window.show()
    return app.exec()
