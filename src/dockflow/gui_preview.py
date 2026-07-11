from __future__ import annotations

from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .gui import APP_STYLE
from .gui_viewers import DockFlowViewerWindow
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
QDockWidget { color: #111827; font-weight: 600; }
QTabBar::tab { background: #e8edf5; color: #334155; padding: 8px 14px; }
QTabBar::tab:selected { background: #2563eb; color: white; }
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
        self.setWindowTitle("DockFlow — Molecular Docking Studio 0.9")
        self._build_preview_dock()
        self._build_preview_menu()
        self._fix_sidebar_text()

    def _fix_sidebar_text(self):
        labels = ["新建项目", "运行中心", "结果分析", "工具设置"]
        for button, text in zip(self.nav_buttons, labels):
            button.setText(text)
            button.setEnabled(True)
        for label in self.findChildren(QLabel):
            if "Preview 0.2" in label.text():
                label.setText("DockFlow 0.9 · Windows x64")
                label.setStyleSheet("color:#cbd5e1;padding:8px 12px;")

    def _build_preview_dock(self):
        self.preview_dock = QDockWidget("结构预览", self)
        self.preview_dock.setObjectName("StructurePreviewDock")
        self.preview_tabs = QTabWidget()
        self.receptor_preview = PreviewPane("受体结构")
        self.ligand_preview = PreviewPane("原始配体")
        self.prepared_preview = PreviewPane("预处理后配体")
        self.preview_tabs.addTab(self.receptor_preview, "受体")
        self.preview_tabs.addTab(self.ligand_preview, "原始配体")
        self.preview_tabs.addTab(self.prepared_preview, "预处理后")
        self.preview_dock.setWidget(self.preview_tabs)
        self.addDockWidget(Qt.RightDockWidgetArea, self.preview_dock)
        self.preview_dock.resize(480, 650)

    def _build_preview_menu(self):
        menu = self.menuBar().addMenu("结构预览")
        show_action = QAction("显示/隐藏预览面板", self)
        show_action.setCheckable(True)
        show_action.setChecked(True)
        show_action.toggled.connect(self.preview_dock.setVisible)
        receptor_action = QAction("刷新受体预览", self)
        receptor_action.triggered.connect(self._preview_current_receptor)
        ligand_action = QAction("刷新配体预览", self)
        ligand_action.triggered.connect(self._preview_first_ligand)
        prepared_action = QAction("刷新预处理后配体", self)
        prepared_action.triggered.connect(self._preview_prepared_ligand)
        menu.addActions([show_action, receptor_action, ligand_action, prepared_action])

    def _preview_file(self, path: Path, pane: PreviewPane, title: str, ligand_only: bool):
        try:
            cache = Path(tempfile.gettempdir()) / "DockFlow" / "preview"
            html = build_structure_preview(path, cache / f"{path.stem}_{'ligand' if ligand_only else 'receptor'}.html", title=title, ligand_only=ligand_only)
            pane.load(html)
            self.preview_dock.show()
        except Exception as error:
            QMessageBox.warning(self, "结构预览失败", str(error))

    def _analyze_structure(self):
        super()._analyze_structure()
        if self.current_pdb and self.current_pdb.exists():
            self._preview_file(self.current_pdb, self.receptor_preview, f"受体：{self.current_pdb.name}", False)
            self.preview_tabs.setCurrentWidget(self.receptor_preview)

    def _add_ligands(self):
        super()._add_ligands()
        self._preview_first_ligand()

    def _preview_current_receptor(self):
        if self.current_pdb and self.current_pdb.exists():
            self._preview_file(self.current_pdb, self.receptor_preview, f"受体：{self.current_pdb.name}", False)
        else:
            QMessageBox.information(self, "尚无受体", "请先输入 PDB ID 或选择本地 PDB，并执行结构分析。")

    def _preview_first_ligand(self):
        records = getattr(self, "ligand_records", [])
        if records:
            record = records[0]
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
        path = candidates[0]
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
        print("DockFlow GUI embedded previews OK")
        return 0
    window.show()
    return app.exec()
