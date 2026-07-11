from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QSplitter,
    QTabWidget,
)

from .drop_validation import valid_ligand_drop, valid_pdb_drop
from .gui import APP_STYLE
from .gui_viewers import DockFlowViewerWindow
from .ligand_library import inspect_ligand_file
from .native_viewer import NativePreviewPane


PREVIEW_STYLE = APP_STYLE + """
#Sidebar { background: #0b1220; }
#Brand { color: #ffffff; background: transparent; }
#Subtitle { color: #cbd5e1; background: transparent; }
QPushButton#NavButton { color: #e5e7eb; background: transparent; font-weight: 600; }
QPushButton#NavButton:hover { background: #1e293b; color: #ffffff; }
QPushButton#NavButton:checked { background: #2563eb; color: #ffffff; }
QPushButton#NavButton:disabled { color: #94a3b8; background: #172033; }
QMenuBar { background: #ffffff; color: #172033; border-bottom: 1px solid #dbe3ef; }
QMenuBar::item:selected { background: #dbeafe; color: #1d4ed8; }
QTabWidget#InlinePreview { background: white; border: 1px solid #cbd5e1; border-radius: 8px; }
QTabBar::tab { background: #e8edf5; color: #334155; padding: 8px 14px; }
QTabBar::tab:selected { background: #2563eb; color: white; }
QListWidget#LigandDropZone { border: 2px dashed #94a3b8; background: #fbfdff; }
QListWidget#LigandDropZone:hover { border-color: #2563eb; background: #eff6ff; }
QLineEdit#PdbDropZone { border: 2px dashed #94a3b8; background: #fbfdff; }
QLineEdit#PdbDropZone:focus { border-color: #2563eb; background: #ffffff; }
QSplitter::handle { background: #dbe3ef; }
QSplitter::handle:vertical { height: 6px; }
QTableView::item:selected, QTableWidget::item:selected {
    background: #2563eb;
    color: #ffffff;
}
QTableView::item:selected:!active, QTableWidget::item:selected:!active {
    background: #3b82f6;
    color: #ffffff;
}
"""


class DockFlowPreviewWindow(DockFlowViewerWindow):
    def __init__(self, runs_dir: Path):
        super().__init__(runs_dir)
        self.setWindowTitle("DockFlow — Molecular Docking Studio 1.2")
        self._build_inline_preview()
        self._build_preview_menu()
        self._configure_drag_drop()
        self._fix_sidebar_text()

    def _fix_sidebar_text(self):
        labels = ["新建项目", "运行中心", "结果分析", "工具设置"]
        for button, text in zip(self.nav_buttons, labels):
            button.setText(text)
            button.setEnabled(True)
        for label in self.findChildren(QLabel):
            if any(version in label.text() for version in ("Preview 0.2", "DockFlow 0.9", "DockFlow 1.0", "DockFlow 1.1")):
                label.setText("DockFlow 1.2 · Windows x64")
                label.setStyleSheet("color:#cbd5e1;padding:8px 12px;")

    def _build_inline_preview(self):
        self.preview_tabs = QTabWidget(objectName="InlinePreview")
        self.preview_tabs.setMinimumHeight(240)
        self.receptor_preview = NativePreviewPane("受体结构")
        self.ligand_preview = NativePreviewPane("原始配体")
        self.prepared_preview = NativePreviewPane("预处理后配体")
        self.preview_tabs.addTab(self.receptor_preview, "受体结构")
        self.preview_tabs.addTab(self.ligand_preview, "原始配体")
        self.preview_tabs.addTab(self.prepared_preview, "预处理后")

        page = self.pages.widget(0)
        outer = page.layout()
        project_splitter = page.findChild(QSplitter)
        if project_splitter is None:
            outer.addWidget(self.preview_tabs, 1)
            return
        project_splitter.setMinimumHeight(430)
        index = outer.indexOf(project_splitter)
        outer.takeAt(index)
        vertical = QSplitter(Qt.Vertical)
        vertical.setChildrenCollapsible(False)
        vertical.addWidget(project_splitter)
        vertical.addWidget(self.preview_tabs)
        vertical.setStretchFactor(0, 3)
        vertical.setStretchFactor(1, 2)
        vertical.setSizes([520, 320])
        outer.insertWidget(index, vertical, 1)
        self.project_vertical_splitter = vertical

    def _build_preview_menu(self):
        menu = self.menuBar().addMenu("结构预览")
        receptor_action = QAction("刷新受体预览", self)
        receptor_action.triggered.connect(self._preview_current_receptor)
        ligand_action = QAction("刷新原始配体", self)
        ligand_action.triggered.connect(self._preview_selected_ligand)
        prepared_action = QAction("刷新预处理后配体", self)
        prepared_action.triggered.connect(self._preview_prepared_ligand)
        expand_action = QAction("放大结构预览", self)
        expand_action.triggered.connect(lambda: self.project_vertical_splitter.setSizes([430, 520]))
        restore_action = QAction("恢复平衡布局", self)
        restore_action.triggered.connect(lambda: self.project_vertical_splitter.setSizes([520, 320]))
        menu.addActions([receptor_action, ligand_action, prepared_action])
        menu.addSeparator()
        menu.addActions([expand_action, restore_action])

    def _configure_drag_drop(self):
        self.structure_input.setObjectName("PdbDropZone")
        self.structure_input.setAcceptDrops(True)
        self.structure_input.installEventFilter(self)
        self.structure_input.setToolTip("可输入4位 PDB ID，也可将 .pdb 文件直接拖到此处")

        self.ligand_files.setObjectName("LigandDropZone")
        self.ligand_files.setAcceptDrops(True)
        self.ligand_files.installEventFilter(self)
        self.ligand_files.setToolTip("可拖入 SDF、MOL2、MOL、PDB、PDBQT、SMI 或 SMILES 文件")
        self.ligand_files.currentRowChanged.connect(lambda _row: self._preview_selected_ligand())

    def eventFilter(self, watched, event):
        if watched in {self.structure_input, self.ligand_files}:
            if event.type() == QEvent.DragEnter:
                paths = self._drop_paths(event.mimeData())
                accepted = valid_pdb_drop(paths) if watched is self.structure_input else valid_ligand_drop(paths)
                if accepted:
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Drop:
                paths = self._drop_paths(event.mimeData())
                if watched is self.structure_input and valid_pdb_drop(paths):
                    self.structure_input.setText(str(paths[0]))
                    event.acceptProposedAction()
                    self._analyze_structure()
                    return True
                if watched is self.ligand_files and valid_ligand_drop(paths):
                    self._add_dropped_ligands(paths)
                    event.acceptProposedAction()
                    return True
        return super().eventFilter(watched, event)

    @staticmethod
    def _drop_paths(mime_data) -> list[Path]:
        if not mime_data.hasUrls():
            return []
        return [Path(url.toLocalFile()) for url in mime_data.urls() if url.isLocalFile()]

    @staticmethod
    def _valid_pdb_drop(paths: list[Path]) -> bool:
        return valid_pdb_drop(paths)

    @staticmethod
    def _valid_ligand_drop(paths: list[Path]) -> bool:
        return valid_ligand_drop(paths)

    def _add_dropped_ligands(self, paths: list[Path]):
        errors = []
        existing = {record.path.name.lower() for record in self.ligand_records}
        for path in paths:
            try:
                record = inspect_ligand_file(path)
                if record.path.name.lower() in existing:
                    continue
                self.ligand_records.append(record)
                existing.add(record.path.name.lower())
            except Exception as error:
                errors.append(f"{path.name}: {error}")
        self._refresh_ligand_list()
        if self.ligand_files.count():
            self.ligand_files.setCurrentRow(self.ligand_files.count() - 1)
        self._preview_selected_ligand()
        self.statusBar().showMessage(f"已拖入 {len(paths) - len(errors)} 个配体", 5000)
        if errors:
            QMessageBox.warning(self, "部分配体未加入", "\n".join(errors))

    def _preview_file(self, path: Path, pane: NativePreviewPane, title: str, ligand_only: bool):
        pane.title = title
        pane.load_structure(path, ligand_only=ligand_only)

    def _analyze_structure(self):
        super()._analyze_structure()
        if self.current_pdb and self.current_pdb.exists():
            self._preview_file(self.current_pdb, self.receptor_preview, f"受体：{self.current_pdb.name}", False)
            self.preview_tabs.setCurrentWidget(self.receptor_preview)

    def _add_ligands(self):
        super()._add_ligands()
        if self.ligand_files.count() and self.ligand_files.currentRow() < 0:
            self.ligand_files.setCurrentRow(0)
        self._preview_selected_ligand()

    def _preview_current_receptor(self):
        if self.current_pdb and self.current_pdb.exists():
            self._preview_file(self.current_pdb, self.receptor_preview, f"受体：{self.current_pdb.name}", False)
            self.preview_tabs.setCurrentWidget(self.receptor_preview)
        else:
            QMessageBox.information(self, "尚无受体", "请拖入 PDB 文件，或输入 PDB ID 后执行结构分析。")

    def _preview_selected_ligand(self):
        records = getattr(self, "ligand_records", [])
        if not records:
            return
        row = self.ligand_files.currentRow()
        if row < 0 or row >= len(records):
            row = 0
        record = records[row]
        self._preview_file(record.path, self.ligand_preview, f"原始配体：{record.name}", True)
        self.preview_tabs.setCurrentWidget(self.ligand_preview)

    def _preview_prepared_ligand(self):
        if not self.current_config:
            QMessageBox.information(self, "尚无项目", "请先创建或打开项目。")
            return
        prepared_dir = self.current_config.parent.parent / "work" / "ligands_pdb"
        candidates = sorted(prepared_dir.glob("*.pdb")) if prepared_dir.exists() else []
        if not candidates:
            QMessageBox.information(self, "尚未预处理", "当前项目还没有生成预处理后的配体 PDB。请先运行配体准备或完整对接。")
            return
        row = self.ligand_files.currentRow()
        selected_name = self.ligand_records[row].name if self.ligand_records and 0 <= row < len(self.ligand_records) else ""
        path = next((candidate for candidate in candidates if candidate.stem == selected_name), candidates[0])
        self._preview_file(path, self.prepared_preview, f"预处理后配体：{path.stem}", True)
        self.preview_tabs.setCurrentWidget(self.prepared_preview)

    def _process_finished(self, exit_code, status):
        super()._process_finished(exit_code, status)
        if exit_code == 0:
            self._preview_prepared_ligand()


def run_gui(runs_dir: Path, smoke_test: bool = False) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("DockFlow")
    app.setOrganizationName("DockFlow")
    app.setStyleSheet(PREVIEW_STYLE)
    window = DockFlowPreviewWindow(runs_dir)
    if smoke_test:
        window.show()
        app.processEvents()
        window.close()
        print("DockFlow GUI offline native preview OK")
        return 0
    window.show()
    return app.exec()
