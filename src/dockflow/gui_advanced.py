from __future__ import annotations

from pathlib import Path

import yaml
from PySide6.QtCore import QProcessEnvironment, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from .diagnostics import diagnose_tools, find_result_pose
from .gui import APP_STYLE
from .gui_v2 import DockFlowWindowV2


class LigandPreparationDialog(QDialog):
    def __init__(self, parent=None, values: dict | None = None):
        super().__init__(parent)
        values = values or {}
        self.setWindowTitle("配体预处理设置")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.ph = QDoubleSpinBox()
        self.ph.setRange(0.0, 14.0)
        self.ph.setDecimals(1)
        self.ph.setValue(float(values.get("ligand_protonation_ph", 7.4)))
        self.minimize = QCheckBox("使用 Open Babel 进行几何优化")
        self.minimize.setChecked(bool(values.get("ligand_minimize", True)))
        self.forcefield = QComboBox()
        self.forcefield.addItems(["MMFF94", "MMFF94s", "UFF", "GAFF"])
        current = str(values.get("ligand_forcefield", "MMFF94"))
        index = self.forcefield.findText(current)
        self.forcefield.setCurrentIndex(max(0, index))
        self.steps = QSpinBox()
        self.steps.setRange(10, 10000)
        self.steps.setValue(int(values.get("ligand_minimization_steps", 250)))
        form.addRow("补氢目标 pH", self.ph)
        form.addRow("几何优化", self.minimize)
        form.addRow("力场", self.forcefield)
        form.addRow("优化步数", self.steps)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "ligand_protonation_ph": self.ph.value(),
            "ligand_minimize": self.minimize.isChecked(),
            "ligand_forcefield": self.forcefield.currentText(),
            "ligand_minimization_steps": self.steps.value(),
        }


class DockFlowAdvancedWindow(DockFlowWindowV2):
    def __init__(self, runs_dir: Path):
        self.ligand_prep = {
            "ligand_protonation_ph": 7.4,
            "ligand_minimize": True,
            "ligand_forcefield": "MMFF94",
            "ligand_minimization_steps": 250,
        }
        super().__init__(runs_dir)
        self.setWindowTitle("DockFlow — Molecular Docking Studio 0.5")
        self._build_advanced_menu()
        self.result_table.doubleClicked.connect(self._open_selected_pose)
        self._restore_ligand_prep()

    def _build_advanced_menu(self):
        prep_menu = self.menuBar().addMenu("配体")
        prep_action = QAction("预处理设置", self)
        prep_action.triggered.connect(self._edit_ligand_prep)
        prep_menu.addAction(prep_action)

        analysis_menu = self.menuBar().addMenu("分析")
        pose_action = QAction("打开选中构象", self)
        pose_action.triggered.connect(self._open_selected_pose)
        diagnostics_action = QAction("依赖诊断报告", self)
        diagnostics_action.triggered.connect(self._show_tool_diagnostics)
        analysis_menu.addActions([pose_action, diagnostics_action])

    def _restore_ligand_prep(self):
        self.ligand_prep = {
            "ligand_protonation_ph": float(self.settings_store.value("ligand/ph", 7.4)),
            "ligand_minimize": str(self.settings_store.value("ligand/minimize", "true")).lower() in {"1", "true", "yes"},
            "ligand_forcefield": str(self.settings_store.value("ligand/forcefield", "MMFF94")),
            "ligand_minimization_steps": int(self.settings_store.value("ligand/steps", 250)),
        }

    def _save_ligand_prep(self):
        self.settings_store.setValue("ligand/ph", self.ligand_prep["ligand_protonation_ph"])
        self.settings_store.setValue("ligand/minimize", self.ligand_prep["ligand_minimize"])
        self.settings_store.setValue("ligand/forcefield", self.ligand_prep["ligand_forcefield"])
        self.settings_store.setValue("ligand/steps", self.ligand_prep["ligand_minimization_steps"])

    def _edit_ligand_prep(self):
        dialog = LigandPreparationDialog(self, self.ligand_prep)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.ligand_prep = dialog.values()
            self._save_ligand_prep()
            QMessageBox.information(
                self,
                "设置已保存",
                f"pH {self.ligand_prep['ligand_protonation_ph']:.1f}；"
                f"力场 {self.ligand_prep['ligand_forcefield']}；"
                f"优化步数 {self.ligand_prep['ligand_minimization_steps']}。",
            )

    def _create_project(self):
        previous = self.current_config
        super()._create_project()
        if self.current_config and self.current_config != previous:
            data = yaml.safe_load(self.current_config.read_text(encoding="utf-8")) or {}
            data.setdefault("settings", {}).update(self.ligand_prep)
            self.current_config.write_text(
                yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            self.log.appendPlainText(
                "\n配体预处理："
                f"pH={self.ligand_prep['ligand_protonation_ph']}, "
                f"minimize={self.ligand_prep['ligand_minimize']}, "
                f"forcefield={self.ligand_prep['ligand_forcefield']}, "
                f"steps={self.ligand_prep['ligand_minimization_steps']}"
            )

    def _start_command(self, command: str):
        environment = QProcessEnvironment.systemEnvironment()
        settings = dict(self.ligand_prep)
        if self.current_config and self.current_config.exists():
            try:
                data = yaml.safe_load(self.current_config.read_text(encoding="utf-8")) or {}
                settings.update(data.get("settings", {}))
            except Exception:
                pass
        environment.insert("DOCKFLOW_LIGAND_PH", str(settings.get("ligand_protonation_ph", 7.4)))
        environment.insert("DOCKFLOW_LIGAND_MINIMIZE", "1" if settings.get("ligand_minimize", True) else "0")
        environment.insert("DOCKFLOW_LIGAND_FORCEFIELD", str(settings.get("ligand_forcefield", "MMFF94")))
        environment.insert("DOCKFLOW_LIGAND_STEPS", str(settings.get("ligand_minimization_steps", 250)))
        self.process.setProcessEnvironment(environment)
        super()._start_command(command)

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
            QMessageBox.warning(self, "构象不存在", "未找到该结果对应的 PDBQT 构象文件。")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(pose))):
            QMessageBox.information(self, "打开构象", f"系统没有关联 PDBQT 查看器。文件位置：\n{pose}")

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
        print("DockFlow GUI advanced QC OK")
        return 0
    window.show()
    return app.exec()
