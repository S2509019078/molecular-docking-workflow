from __future__ import annotations

from pathlib import Path
import tempfile

from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .gui import APP_STYLE
from .gui_viewers import DockFlowViewerWindow
from .ligand_library import SUPPORTED_LIGAND_SUFFIXES, inspect_ligand_file
from .structure_preview import build_structure_preview

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception:  # pragma: no cover
    QWebEngineView = None

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
"""


class PreviewPane(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.current_html: Path | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if QWebEngineView is not None:
            self.web = QWebEngineView()
            layout.addWidget(self.web, 1)
            self.fallback = None
        else:
            self.web = None
            self.fallback = QLabel("当前安装包未包含 Qt WebEngine。可点击下方按钮在浏览器中查看结构。")
            self.fallback.setAlignment(Qt.AlignCenter)
            self.fallback.setWordWrap(True)
            self.fallback.setStyleSheet("padding:24px;color:#64748b;background:white;")
            layout.addWidget(self.fallback, 1)
        open_button = QPushButton("在浏览器中打开")
        open_button.clicked.connect(self.open_external)
        layout.addWidget(open_button)

    def load(self, html_path: Path):
        self.current_html = Path(html_path).resolve()
        if self.web is not None:
            self.web.setUrl(QUrl.fromLocalFile(str(self.current_html)))
        elif self.fallback is not None:
            self.fallback.setText(f"{self.title}\n\n{self.current_html}")

    def open_external(self):
        if self.current_html:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_html)))


class DockFlowPreviewWindow(DockFlowViewerWindow):
    def __init__(self, runs_dir: Path):
        super().__init__(runs_dir)
        self.setWindowTitle("DockFlow — Molecular Docking Studio 1.0")
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
            if "Preview 0.2" in label.text() or "DockFlow 0.9" in label.text():
                label.setText("DockFlow 1.0 · Windows x64")
                label.setStyleSheet("color:#cbd5e1;padding:8px 12px;")

    def _build_inline_preview(self):
        self.preview_tabs = QTabWidget(objectName="InlinePreview")
        self.preview_tabs.setMinimumHeight(300)
        self.receptor_preview = PreviewPane("受体结构")
        self.ligand_preview = PreviewPane("原始配体")
        self.prepared_preview = PreviewPane("预处理后配体")
        self.preview_tabs.addTab(self.receptor_preview, "受体结构")
        self.preview_tabs.addTab(self.ligand_preview, "原始配体")
        self.preview_tabs.addTab(self.prepared_preview, "预处理后")

        self.chain_list.setMaximumHeight(72)
        parent_layout = self.chain_list.parentWidget().layout()
        index = parent_layout.indexOf(self.chain_list)
        parent_layout.insertWidget(index + 1, self.preview_tabs, 1)

    def _build_preview_menu(self):
        menu = self.menuBar().addMenu("结构预览")
        receptor_action = QAction("刷新受体预览", self)
        receptor_action.triggered.connect(self._preview_current_receptor)
        ligand_action = QAction("刷新原始配体", self)
        ligand_action.triggered.connect(self._preview_selected_ligand)
        prepared_action = QAction("刷新预处理后配体", self)
        prepared_action.triggered.connect(self._preview_prepared_ligand)
        menu.addActions([receptor_action, ligand_action, prepared_action])

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
                accepted = self._valid_pdb_drop(paths) if watched is self.structure_input else self._valid_ligand_drop(paths)
                if accepted:
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Drop:
                paths = self._drop_paths(event.mimeData())
                if watched is self.structure_input and self._valid_pdb_drop(paths):
                    self.structure_input.setText(str(paths[0]))
                    event.acceptProposedAction()
                    self._analyze_structure()
                    return True
                if watched is self.ligand_files and self._valid_ligand_drop(paths):
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
        return len(paths) == 1 and paths[0].is_file() and paths[0].suffix.lower() == ".pdb"

    @staticmethod
    def _valid_ligand_drop(paths: list[Path]) -> bool:
        return bool(paths) and all(path.is_file() and path.suffix.lower() in SUPPORTED_LIGAND_SUFFIXES for path in paths)

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

    def _preview_file(self, path: Path, pane: PreviewPane, title: str, ligand_only: bool):
        try:
            cache = Path(tempfile.gettempdir()) / "DockFlow" / "preview"
            html = build_structure_preview(
                path,
                cache / f"{path.stem}_{'ligand' if ligand_only else 'receptor'}.html",
                title=title,
                ligand_only=ligand_only,
            )
            pane.load(html)
        except Exception as error:
            QMessageBox.warning(self, "结构预览失败", str(error))

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
        print("DockFlow GUI drag-drop inline preview OK")
        return 0
    window.show()
    return app.exec()
