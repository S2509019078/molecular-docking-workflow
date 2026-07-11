from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QProcess, QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QListWidgetItem, QMessageBox

from .desktop import cli_program_and_prefix, create_gui_project
from .gui import APP_STYLE, DockFlowWindow
from .gui_ligands import LigandLibraryDialog
from .ligand_library import LigandRecord, inspect_ligand_file
from .preflight import build_preflight


class DockFlowWindowV2(DockFlowWindow):
    def __init__(self, runs_dir: Path):
        self.ligand_records: list[LigandRecord] = []
        self.force_next_run = False
        self.with_plip_next_run = False
        self.settings_store = QSettings("DockFlow", "MolecularDockingStudio")
        super().__init__(runs_dir)
        self.setWindowTitle("DockFlow — Molecular Docking Studio 0.4")
        self._build_product_menu()
        self._restore_preferences()
        self.statusBar().showMessage("就绪")

    def _build_product_menu(self):
        workflow_menu = self.menuBar().addMenu("工作流")
        check_action = QAction("项目预检", self)
        check_action.triggered.connect(self._show_preflight)
        run_action = QAction("开始完整对接", self)
        run_action.triggered.connect(lambda: self._start_command("all"))
        force_action = QAction("强制重新计算", self)
        force_action.triggered.connect(self._run_force)
        plip_action = QAction("完整对接并运行 PLIP", self)
        plip_action.triggered.connect(self._run_with_plip)
        workflow_menu.addActions([check_action, run_action, force_action, plip_action])

        project_menu = self.menuBar().addMenu("项目")
        open_action = QAction("打开已有项目", self)
        open_action.triggered.connect(self._open_config)
        project_menu.addAction(open_action)

    def _restore_preferences(self):
        runs = self.settings_store.value("runs_dir", str(self.runs_dir))
        if runs:
            self.runs_dir = Path(str(runs))
            self.runs_path.setText(str(runs))
        self.exhaustiveness.setValue(int(self.settings_store.value("exhaustiveness", self.exhaustiveness.value())))
        self.num_modes.setValue(int(self.settings_store.value("num_modes", self.num_modes.value())))
        self.cpu.setValue(int(self.settings_store.value("cpu", self.cpu.value())))
        self.padding.setValue(float(self.settings_store.value("padding", self.padding.value())))
        for key, edit in self.tool_edits.items():
            value = self.settings_store.value(f"tool/{key}")
            if value:
                edit.setText(str(value))
        geometry = self.settings_store.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def _save_preferences(self):
        self.settings_store.setValue("runs_dir", self.runs_path.text())
        self.settings_store.setValue("exhaustiveness", self.exhaustiveness.value())
        self.settings_store.setValue("num_modes", self.num_modes.value())
        self.settings_store.setValue("cpu", self.cpu.value())
        self.settings_store.setValue("padding", self.padding.value())
        self.settings_store.setValue("window_geometry", self.saveGeometry())
        for key, edit in self.tool_edits.items():
            self.settings_store.setValue(f"tool/{key}", edit.text().strip())
        self.settings_store.sync()

    def closeEvent(self, event):
        self._save_preferences()
        if self.process.state() != QProcess.NotRunning:
            answer = QMessageBox.question(
                self,
                "任务仍在运行",
                "关闭窗口会终止当前任务。确定继续吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._stop_process()
        event.accept()

    def _add_ligands(self):
        try:
            initial = list(self.ligand_records)
            if not initial:
                for index in range(self.ligand_files.count()):
                    item = self.ligand_files.item(index)
                    path = item.data(Qt.UserRole) or item.text()
                    try:
                        initial.append(inspect_ligand_file(Path(path)))
                    except Exception:
                        pass
            dialog = LigandLibraryDialog(self, initial_records=initial)
            if dialog.exec() != dialog.Accepted:
                return
            self.ligand_records = dialog.selected_records()
            self._refresh_ligand_list()
            self.statusBar().showMessage(f"已载入 {len(self.ligand_records)} 个配体", 5000)
        except Exception as error:
            QMessageBox.critical(self, "配体库打开失败", str(error))

    def _refresh_ligand_list(self):
        self.ligand_files.clear()
        for record in self.ligand_records:
            warning = f" · {record.warning}" if record.warning else ""
            item = QListWidgetItem(f"{record.name}  |  {record.source}  |  {record.file_format}  |  {record.status}{warning}")
            item.setData(Qt.UserRole, str(record.path))
            item.setToolTip(str(record.path))
            self.ligand_files.addItem(item)

    def _create_project(self):
        try:
            if not self.inspection or not self.current_pdb:
                self._analyze_structure()
            if not self.inspection or not self.current_pdb:
                return
            records = list(self.ligand_records)
            if not records:
                for index in range(self.ligand_files.count()):
                    item = self.ligand_files.item(index)
                    path = item.data(Qt.UserRole) or item.text()
                    records.append(inspect_ligand_file(Path(path)))
            if not records:
                raise ValueError("请先打开配体库，并至少加入一个小分子")
            warnings = [f"{record.name}: {record.warning}" for record in records if record.warning]
            if warnings:
                answer = QMessageBox.question(
                    self,
                    "配体需要检查",
                    "以下配体存在结构提示：\n\n" + "\n".join(warnings) + "\n\n仍然创建项目吗？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
            chains = tuple(item.text() for item in self.chain_list.selectedItems())
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
                ligand_files=[record.path for record in records],
                tools=tools,
                settings=settings,
            )
            manifest = config.parent.parent / "inputs" / "ligands" / "LIGAND_SOURCES.tsv"
            lines = ["name\tsource\tformat\tstatus\twarning\tfile"]
            for record in records:
                warning = record.warning.replace("\t", " ").replace("\n", " ")
                lines.append(f"{record.name}\t{record.source}\t{record.file_format}\t{record.status}\t{warning}\t{record.path.name}")
            manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._save_preferences()
            self._set_current_config(config)
            report = build_preflight(config)
            self.log.setPlainText(
                f"项目创建完成\n{config.parent.parent}\n\n"
                f"受体: {report.target_count}  配体: {report.ligand_count}  预计对接任务: {report.docking_task_count}\n"
                "已保存配体来源清单 LIGAND_SOURCES.tsv。"
            )
            self._switch_page(1)
            self._show_preflight()
        except Exception as error:
            QMessageBox.critical(self, "创建项目失败", str(error))

    def _show_preflight(self) -> bool:
        if not self.current_config:
            QMessageBox.warning(self, "未选择项目", "请先创建项目或打开已有 config.yaml。")
            return False
        try:
            report = build_preflight(self.current_config, require_plip=self.with_plip_next_run)
        except Exception as error:
            QMessageBox.critical(self, "项目预检失败", str(error))
            return False
        lines = [
            f"受体数量：{report.target_count}",
            f"配体数量：{report.ligand_count}",
            f"预计对接任务：{report.docking_task_count}",
        ]
        if report.warnings:
            lines.append("\n警告：\n- " + "\n- ".join(report.warnings))
        if report.problems:
            lines.append("\n必须解决的问题：\n- " + "\n- ".join(report.problems))
            QMessageBox.critical(self, "项目尚未就绪", "\n".join(lines))
            self.statusBar().showMessage("预检未通过", 5000)
            return False
        QMessageBox.information(self, "项目预检通过", "\n".join(lines))
        self.statusBar().showMessage("预检通过", 5000)
        return True

    def _run_force(self):
        self.force_next_run = True
        self._start_command("all")

    def _run_with_plip(self):
        self.with_plip_next_run = True
        self._start_command("all")

    def _start_command(self, command: str):
        if command == "all" and not self._show_preflight():
            self.force_next_run = False
            self.with_plip_next_run = False
            return
        if self.process.state() != QProcess.NotRunning:
            QMessageBox.warning(self, "任务正在运行", "请等待当前任务完成，或先停止任务。")
            return
        if not self.current_config:
            QMessageBox.warning(self, "未选择项目", "请先创建项目或打开已有 config.yaml。")
            return
        program, prefix = cli_program_and_prefix()
        args = prefix + [command, "--config", str(self.current_config)]
        if self.force_next_run:
            args.append("--force")
        if self.with_plip_next_run:
            args.append("--with-plip")
        self.log.appendPlainText(f"\n$ {program} {' '.join(args)}\n")
        self.progress.setRange(0, 0)
        self.process.setWorkingDirectory(str(self.current_config.parent.parent))
        self.process.start(program, args)
        self.statusBar().showMessage("任务运行中")
        self.force_next_run = False
        self.with_plip_next_run = False

    def _process_finished(self, exit_code, status):
        super()._process_finished(exit_code, status)
        self.statusBar().showMessage("任务完成" if exit_code == 0 else f"任务失败，退出码 {exit_code}", 10000)


def run_gui(runs_dir: Path, smoke_test: bool = False) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("DockFlow")
    app.setOrganizationName("DockFlow")
    app.setStyleSheet(APP_STYLE)
    window = DockFlowWindowV2(runs_dir)
    if smoke_test:
        window.show()
        app.processEvents()
        window.close()
        print("DockFlow GUI product readiness OK")
        return 0
    window.show()
    return app.exec()
