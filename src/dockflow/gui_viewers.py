from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from .gui import APP_STYLE
from .gui_workbench import DockFlowWorkbenchWindow
from .professional_viewers import build_chimerax_launch, build_pymol_launch, discover_viewer


class DockFlowViewerWindow(DockFlowWorkbenchWindow):
    def __init__(self, runs_dir: Path):
        self.viewer_processes: list[QProcess] = []
        super().__init__(runs_dir)
        self.setWindowTitle("DockFlow — Molecular Docking Studio 0.7")
        self._build_viewer_menu()

    def _build_viewer_menu(self):
        viewer_menu = self.menuBar().addMenu("专业查看器")
        pymol_action = QAction("在 PyMOL 中打开", self)
        pymol_action.triggered.connect(lambda: self._launch_professional_viewer("pymol"))
        chimerax_action = QAction("在 ChimeraX 中打开", self)
        chimerax_action.triggered.connect(lambda: self._launch_professional_viewer("chimerax"))
        configure_pymol = QAction("设置 PyMOL 路径", self)
        configure_pymol.triggered.connect(lambda: self._choose_viewer_path("pymol"))
        configure_chimerax = QAction("设置 ChimeraX 路径", self)
        configure_chimerax.triggered.connect(lambda: self._choose_viewer_path("chimerax"))
        viewer_menu.addActions([pymol_action, chimerax_action])
        viewer_menu.addSeparator()
        viewer_menu.addActions([configure_pymol, configure_chimerax])

    def _choose_viewer_path(self, viewer: str):
        label = "PyMOL" if viewer == "pymol" else "ChimeraX"
        path, _ = QFileDialog.getOpenFileName(self, f"选择 {label} 可执行文件", "", "Executable (*.exe);;All files (*)")
        if path:
            self.settings_store.setValue(f"viewer/{viewer}", path)
            self.settings_store.sync()
            QMessageBox.information(self, "路径已保存", f"{label}:\n{path}")

    def _selected_viewer_target(self) -> tuple[str, str] | None:
        return self._selected_identifiers()

    def _launch_professional_viewer(self, viewer: str):
        if not self.current_config:
            QMessageBox.warning(self, "未选择项目", "请先创建或打开项目。")
            return
        identifiers = self._selected_viewer_target()
        if not identifiers:
            return
        label = "PyMOL" if viewer == "pymol" else "ChimeraX"
        configured = self.settings_store.value(f"viewer/{viewer}")
        executable = discover_viewer(viewer, str(configured) if configured else None)
        if not executable:
            answer = QMessageBox.question(
                self,
                f"未找到 {label}",
                f"DockFlow 未检测到 {label}。现在手动选择可执行文件吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return
            self._choose_viewer_path(viewer)
            configured = self.settings_store.value(f"viewer/{viewer}")
            executable = discover_viewer(viewer, str(configured) if configured else None)
            if not executable:
                return
        try:
            launch = (
                build_pymol_launch(self.current_config, *identifiers, executable)
                if viewer == "pymol"
                else build_chimerax_launch(self.current_config, *identifiers, executable)
            )
            process = QProcess(self)
            process.setProgram(str(launch.executable))
            process.setArguments(list(launch.command[1:]))
            process.setWorkingDirectory(str(launch.script.parent))
            process.finished.connect(lambda *_args, p=process: self._release_viewer_process(p))
            process.errorOccurred.connect(lambda error, name=label: QMessageBox.critical(self, f"{name} 启动失败", str(error)))
            process.start()
            self.viewer_processes.append(process)
            self.statusBar().showMessage(f"已启动 {label}: {launch.script.name}", 8000)
        except Exception as error:
            QMessageBox.critical(self, f"{label} 启动失败", str(error))

    def _release_viewer_process(self, process: QProcess):
        if process in self.viewer_processes:
            self.viewer_processes.remove(process)
        process.deleteLater()


def run_gui(runs_dir: Path, smoke_test: bool = False) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("DockFlow")
    app.setOrganizationName("DockFlow")
    app.setStyleSheet(APP_STYLE)
    window = DockFlowViewerWindow(runs_dir)
    if smoke_test:
        window.show()
        app.processEvents()
        window.close()
        print("DockFlow GUI professional viewers OK")
        return 0
    window.show()
    return app.exec()
