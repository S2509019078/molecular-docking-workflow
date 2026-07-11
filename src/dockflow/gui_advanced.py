from __future__ import annotations

from pathlib import Path

import yaml
from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from .diagnostics import diagnose_tools, find_result_pose
from .gui import APP_STYLE
from .gui_v2 import DockFlowWindowV2


class DockFlowAdvancedWindow(DockFlowWindowV2):
    def __init__(self, runs_dir: Path):
        super().__init__(runs_dir)
        self.setWindowTitle("DockFlow — Molecular Docking Studio 1.2")
        self._build_advanced_menu()
        self.result_table.doubleClicked.connect(self._open_selected_pose)

    def _build_advanced_menu(self):
        prep_menu = self.menuBar().addMenu("配体")
        prep_action = QAction("PDBQT预处理说明", self)
        prep_action.triggered.connect(self._show_preparation_policy)
        prep_menu.addAction(prep_action)

        analysis_menu = self.menuBar().addMenu("分析")
        pose_action = QAction("打开选中构象", self)
        pose_action.triggered.connect(self._open_selected_pose)
        diagnostics_action = QAction("依赖诊断报告", self)
        diagnostics_action.triggered.connect(self._show_tool_diagnostics)
        analysis_menu.addActions([pose_action, diagnostics_action])

    def _show_preparation_policy(self):
        QMessageBox.information(
            self,
            "PDBQT预处理策略",
            "DockFlow采用保守且可追溯的预处理流程：\n\n"
            "1. Open Babel仅用于SDF/MOL到MOL2的格式转换，不补氢、不改变pH、不生成构象、不执行能量最小化。\n"
            "2. AutoDockTools prepare_receptor4.py负责受体补氢、AutoDock原子类型、Gasteiger部分电荷和PDBQT生成。\n"
            "3. AutoDockTools prepare_ligand4.py负责配体补氢、Gasteiger部分电荷、非极性氢合并、可旋转键和PDBQT生成。\n"
            "4. 正式电荷、质子化状态和初始三维构象必须在导入前确认；AutoDockTools不会替代化学状态判断。\n"
            "5. SMILES没有经过确认的三维坐标，不能直接进入正式对接。",
        )

    def _create_project(self):
        previous = self.current_config
        super()._create_project()
        if self.current_config and self.current_config != previous:
            data = yaml.safe_load(self.current_config.read_text(encoding="utf-8")) or {}
            settings = data.setdefault("settings", {})
            settings["preparation_backend"] = "mgltools"
            for obsolete in (
                "ligand_protonation_ph",
                "ligand_minimize",
                "ligand_forcefield",
                "ligand_minimization_steps",
                "receptor_protonation_ph",
            ):
                settings.pop(obsolete, None)
            self.current_config.write_text(
                yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            self.log.appendPlainText(
                "\nPDBQT预处理：AutoDockTools/MGLTools\n"
                "Open Babel仅用于格式转换；补氢、Gasteiger部分电荷、原子类型和可旋转键由AutoDockTools处理。\n"
                "未自动执行能量最小化，也未自动改变正式电荷或pH质子化状态。"
            )

    def _open_selected_pose(self):
        if not self.current_config:
            QMessageBox.warning(self, "未选择项目", "请先打开项目。")
            return
        row = self.result_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "未选择结果", "请先在结果表中选择一行。")
            return
        target_item = self.result_table.item(row, 0)
        ligand_item = self.result_table.item(row, 1)
        if not target_item or not ligand_item:
            return
        pose = find_result_pose(self.current_config, target_item.text(), ligand_item.text())
        if not pose or not pose.exists():
            QMessageBox.warning(self, "构象不存在", "未找到该结果对应的PDBQT构象文件。")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(pose))):
            QMessageBox.information(self, "打开构象", f"系统没有关联PDBQT查看器。文件位置：\n{pose}")

    def _show_tool_diagnostics(self):
        if not self.current_config:
            QMessageBox.warning(self, "未选择项目", "请先创建或打开项目。")
            return
        rows = diagnose_tools(self.current_config)
        lines = []
        for row in rows:
            status = "可用" if row.available else ("缺失" if row.required else "未安装（可选）")
            resolved = str(row.resolved) if row.resolved else row.hint
            lines.append(f"{row.label}: {status}\n  {resolved}")
        QMessageBox.information(self, "依赖诊断报告", "\n\n".join(lines))


def run_gui(runs_dir: Path, smoke_test: bool = False) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("DockFlow")
    app.setOrganizationName("DockFlow")
    app.setStyleSheet(APP_STYLE)
    window = DockFlowAdvancedWindow(runs_dir)
    if smoke_test:
        window.show()
        app.processEvents()
        window.close()
        print("DockFlow GUI AutoDockTools preparation policy OK")
        return 0
    window.show()
    return app.exec()
