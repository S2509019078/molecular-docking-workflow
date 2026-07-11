from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem, QMessageBox

from .desktop import create_gui_project
from .gui import APP_STYLE, DockFlowWindow
from .gui_ligands import LigandLibraryDialog
from .ligand_library import LigandRecord, inspect_ligand_file


class DockFlowWindowV2(DockFlowWindow):
    def __init__(self, runs_dir: Path):
        self.ligand_records: list[LigandRecord] = []
        super().__init__(runs_dir)
        self.setWindowTitle("DockFlow — Molecular Docking Studio 0.3")

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
        except Exception as error:
            QMessageBox.critical(self, "配体库打开失败", str(error))

    def _refresh_ligand_list(self):
        self.ligand_files.clear()
        for record in self.ligand_records:
            warning = f" · {record.warning}" if record.warning else ""
            item = QListWidgetItem(
                f"{record.name}  |  {record.source}  |  {record.file_format}  |  {record.status}{warning}"
            )
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
                raise ValueError("请先通过“添加配体文件”打开配体库，并至少加入一个小分子")

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
                lines.append(
                    f"{record.name}\t{record.source}\t{record.file_format}\t{record.status}\t{warning}\t{record.path.name}"
                )
            manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._set_current_config(config)
            self.log.setPlainText(
                f"项目创建完成\n{config.parent.parent}\n\n已加入 {len(records)} 个配体，并保存来源清单 LIGAND_SOURCES.tsv。\n建议先点击“检查环境”，通过后再开始完整对接。"
            )
            self._switch_page(1)
        except Exception as error:
            QMessageBox.critical(self, "创建项目失败", str(error))


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
        print("DockFlow GUI ligand library OK")
        return 0
    window.show()
    return app.exec()
