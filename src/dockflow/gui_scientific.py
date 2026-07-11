from __future__ import annotations

from pathlib import Path

import yaml
from PySide6.QtCore import QEvent, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from .gui_preview import DockFlowPreviewWindow, PREVIEW_STYLE
from .preprocess_status import build_preparation_status


SCIENTIFIC_STYLE = PREVIEW_STYLE


class DockFlowScientificWindow(DockFlowPreviewWindow):
    def __init__(self, runs_dir: Path):
        self._active_science_command = ""
        super().__init__(runs_dir)
        self.setWindowTitle("DockFlow — Molecular Docking Studio 1.4")
        self._compress_sidebar()
        self._install_preparation_center()
        self._install_robust_pdb_drop()
        self._refresh_scientific_status()

    def _compress_sidebar(self):
        sidebar = self.findChild(type(self), "Sidebar")
        if sidebar:
            sidebar.setFixedWidth(168)

    def _analyze_structure(self):
        super()._analyze_structure()
        if self.current_pdb and self.current_pdb.exists():
            self._preview_current_receptor()
            if hasattr(self, "preview_tabs"):
                self.preview_tabs.show()
                self.preview_toggle.setChecked(True) if hasattr(self, "preview_toggle") else None

    def _set_current_config(self, path: Path):
        super()._set_current_config(path)
        self._restore_project_preview()
        self._refresh_scientific_status()

    def _restore_project_preview(self):
        if not self.current_config:
            return
        try:
            config_dir = self.current_config.parent.parent
            structures = list((config_dir / "inputs" / "structures").glob("*.pdb"))
            if structures:
                self.current_pdb = structures[0]
                self._preview_current_receptor()
        except Exception:
            pass

    def _install_robust_pdb_drop(self):
        self.structure_input.setAcceptDrops(True)
        self.ligand_files.setAcceptDrops(True)

    def _install_preparation_center(self):
        # Existing scientific preparation widgets remain loaded from the v1.3 layer.
        return

    def _refresh_scientific_status(self):
        if not self.current_config or not hasattr(self, "prep_table"):
            return
        try:
            status = build_preparation_status(self.current_config)
            self.prep_table.setRowCount(0)
            for item in status.checks:
                row = self.prep_table.rowCount()
                self.prep_table.insertRow(row)
                for col, value in enumerate((item.stage, item.label, item.state, item.detail)):
                    self.prep_table.setItem(row, col, QTableWidgetItem(str(value)))
        except Exception:
            pass


def run_gui(runs_dir: Path, smoke_test: bool = False) -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(SCIENTIFIC_STYLE)
    window = DockFlowScientificWindow(runs_dir)
    if smoke_test:
        window.show()
        app.processEvents()
        window.close()
        return 0
    window.show()
    return app.exec()
