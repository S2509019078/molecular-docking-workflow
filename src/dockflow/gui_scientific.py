from __future__ import annotations

from pathlib import Path

import yaml
from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .gui_preview import DockFlowPreviewWindow, PREVIEW_STYLE
from .preprocess_status import build_preparation_status


SCIENTIFIC_STYLE = PREVIEW_STYLE + """
QLabel#StatusReady { color:#166534; font-weight:700; }
QLabel#StatusWarning { color:#a16207; font-weight:700; }
QLabel#StatusBlocked { color:#b91c1c; font-weight:700; }
QPushButton#PreviewToggle { background:#f8fafc; color:#334155; border:1px solid #cbd5e1; }
QPushButton#PreviewToggle:checked { background:#dbeafe; color:#1d4ed8; }
QTableWidget#PreparationTable { background:white; border:1px solid #dbe3ef; }
QTableWidget#PreparationTable::item:selected { background:#2563eb; color:white; }
"""


class DockFlowScientificWindow(DockFlowPreviewWindow):
    def __init__(self, runs_dir: Path):
        self._active_science_command = ""
        super().__init__(runs_dir)
        self.setWindowTitle("DockFlow — Molecular Docking Studio 1.3")
        self._compress_sidebar()
        self._configure_collapsible_preview()
        self._install_preparation_center()
        self._install_robust_pdb_drop()
        self._refresh_scientific_status()

    def _compress_sidebar(self):
        sidebar = self.findChild(QFrame, "Sidebar")
        if sidebar is not None:
            sidebar.setFixedWidth(168)
        for label in self.findChildren(QLabel):
            if "DockFlow 1.2" in label.text() or "Preview 0.2" in label.text():
                label.setText("DockFlow 1.3 · Scientific Workflow")
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
        self.preview_tabs.setMinimumHeight(220)
        self.preview_tabs.hide()
        self.project_vertical_splitter.setCollapsible(1, True)
        self.project_vertical_splitter.setSizes([800, 0])

    def _toggle_preview(self, visible: bool):
        self.preview_tabs.setVisible(visible)
        self.preview_toggle.setText("隐藏结构预览" if visible else "显示结构预览")
        if visible:
            self.project_vertical_splitter.setSizes([500, 320])
            if self.current_pdb and self.current_pdb.exists():
                self._preview_current_receptor()
        else:
            self.project_vertical_splitter.setSizes([800, 0])

    def _install_preparation_center(self):
        page = self.pages.widget(1)
        outer = page.layout()
        card, layout = self._card("科研预处理中心")
        card.setObjectName("Card")

        self.prep_summary = QLabel("尚未选择项目", objectName="StatusWarning")
        self.prep_summary.setWordWrap(True)
        layout.addWidget(self.prep_summary)

        policy_row = QHBoxLayout()
        policy_row.addWidget(QLabel("科研模式"))
        self.scientific_mode = QComboBox()
        self.scientific_mode.addItem("标准科研", "standard")
        self.scientific_mode.addItem("快速探索", "exploratory")
        self.scientific_mode.addItem("专家", "expert")
        policy_row.addWidget(self.scientific_mode)
        policy_row.addWidget(QLabel("待确认HETATM"))
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
        qc = QPushButton("运行科研QC")
        qc.clicked.connect(lambda: self._start_science_command("qc"))
        plan = QPushButton("生成预处理计划")
        plan.clicked.connect(lambda: self._start_science_command("preparation-report"))
        prepare = QPushButton("自动预处理", objectName="Primary")
        prepare.clicked.connect(lambda: self._start_science_command("prepare"))
        open_report = QPushButton("打开QC报告")
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
        self.prep_table.setMinimumHeight(190)
        self.prep_table.setAlternatingRowColors(True)
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
        return path if path.is_file() and path.suffix.lower() in {".pdb", ".ent"} else None

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

    def _create_project(self):
        previous = self.current_config
        super()._create_project()
        if self.current_config and self.current_config != previous:
            self._save_scientific_policy()
            self._refresh_scientific_status()

    def _set_current_config(self, path: Path):
        super()._set_current_config(path)
        self._load_scientific_policy()
        self._refresh_scientific_status()

    def _load_scientific_policy(self):
        if not self.current_config or not self.current_config.exists():
            return
        try:
            data = yaml.safe_load(self.current_config.read_text(encoding="utf-8")) or {}
            settings = data.get("settings", {})
            mode = str(settings.get("scientific_mode", "standard"))
            review = str(settings.get("hetero_review_action", "error"))
            mode_index = self.scientific_mode.findData(mode)
            review_index = self.hetero_policy.findData(review)
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
        settings["preparation_backend"] = "mgltools"
        self.current_config.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def _start_science_command(self, command: str):
        if not self.current_config:
            QMessageBox.warning(self, "未选择项目", "请先创建项目或打开已有项目。")
            return
        try:
            self._save_scientific_policy()
        except Exception as error:
            QMessageBox.critical(self, "保存预处理策略失败", str(error))
            return
        self._active_science_command = command
        self._start_command(command)

    def _refresh_scientific_status(self):
        self.prep_table.setRowCount(0)
        if not self.current_config:
            self.prep_summary.setObjectName("StatusWarning")
            self.prep_summary.setText("尚未选择项目。创建项目后可运行QC和自动预处理。")
            self.prep_summary.style().unpolish(self.prep_summary)
            self.prep_summary.style().polish(self.prep_summary)
            return
        try:
            status = build_preparation_status(self.current_config)
        except Exception as error:
            self.prep_summary.setObjectName("StatusBlocked")
            self.prep_summary.setText(f"状态读取失败：{error}")
            self.prep_summary.style().unpolish(self.prep_summary)
            self.prep_summary.style().polish(self.prep_summary)
            return

        for check in status.checks:
            row = self.prep_table.rowCount()
            self.prep_table.insertRow(row)
            values = (check.stage, check.label, check.state, check.detail)
            for column, value in enumerate(values):
                self.prep_table.setItem(row, column, QTableWidgetItem(str(value)))

        pending = sum(1 for item in status.checks if item.state in {"待处理", "提示"})
        if status.blockers:
            self.prep_summary.setObjectName("StatusBlocked")
            self.prep_summary.setText(
                f"预处理被阻断：{len(status.blockers)}项。先配置工具或修复输入，再运行自动预处理。"
            )
        elif status.complete:
            self.prep_summary.setObjectName("StatusReady")
            self.prep_summary.setText("预处理与结果检查均已完成。可以查看构象、运行PLIP或生成报告。")
        else:
            self.prep_summary.setObjectName("StatusWarning")
            self.prep_summary.setText(f"环境可用，仍有{pending}项待处理或需确认。")
        self.prep_summary.style().unpolish(self.prep_summary)
        self.prep_summary.style().polish(self.prep_summary)

    def _open_qc_report(self):
        if not self.current_config:
            return
        report = self.current_config.parent.parent / "results" / "qc" / "project_qc.md"
        if not report.exists():
            QMessageBox.information(self, "尚无QC报告", "请先运行科研QC。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(report.resolve())))

    def _process_finished(self, exit_code, status):
        # Skip DockFlowPreviewWindow's unconditional prepared-preview popup.
        super(DockFlowPreviewWindow, self)._process_finished(exit_code, status)
        command = self._active_science_command
        self._active_science_command = ""
        self._refresh_scientific_status()
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
