from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .ligand_library import (
    LigandRecord,
    create_smiles_file,
    download_pubchem_sdf,
    inspect_ligand_file,
)


class LigandLibraryDialog(QDialog):
    def __init__(self, parent=None, initial_records: list[LigandRecord] | None = None):
        super().__init__(parent)
        self.setWindowTitle("DockFlow 配体库")
        self.resize(920, 620)
        self.records: list[LigandRecord] = list(initial_records or [])
        self.cache_dir = Path(tempfile.gettempdir()) / "DockFlow" / "ligands"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._build_ui()
        self._refresh_table()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        title = QLabel("配体库")
        title.setStyleSheet("font-size: 18pt; font-weight: 700;")
        subtitle = QLabel("可从本地文件、单个 SMILES 或 PubChem CID/名称添加小分子。加入项目后由 Open Babel 和 AutoDockTools 完成三维化与 PDBQT 准备。")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #6b7280;")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        tabs = QTabWidget()
        tabs.addTab(self._local_tab(), "本地文件")
        tabs.addTab(self._smiles_tab(), "SMILES")
        tabs.addTab(self._pubchem_tab(), "PubChem")
        outer.addWidget(tabs)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["名称", "来源", "格式", "状态", "警告", "文件"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        outer.addWidget(self.table, 1)

        remove = QPushButton("移除选中")
        remove.clicked.connect(self._remove_selected)
        footer = QHBoxLayout()
        footer.addWidget(remove)
        footer.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("加入项目")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        outer.addLayout(footer)

    def _local_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        explanation = QLabel("支持 SDF、MOL2、MOL、PDB、PDBQT、SMI 和 SMILES。程序会检查空文件、多分子 SDF 和多片段 SMILES。")
        explanation.setWordWrap(True)
        add = QPushButton("选择一个或多个配体文件")
        add.clicked.connect(self._add_local)
        layout.addWidget(explanation)
        layout.addWidget(add)
        layout.addStretch(1)
        return page

    def _smiles_tab(self):
        page = QWidget()
        layout = QFormLayout(page)
        self.smiles_name = QLineEdit("ligand")
        self.smiles_text = QPlainTextEdit()
        self.smiles_text.setPlaceholderText("例如：CC(=O)OC1=CC=CC=C1C(=O)O")
        self.smiles_text.setMaximumHeight(100)
        add = QPushButton("添加 SMILES")
        add.clicked.connect(self._add_smiles)
        layout.addRow("名称", self.smiles_name)
        layout.addRow("单个 SMILES", self.smiles_text)
        layout.addRow("", add)
        return page

    def _pubchem_tab(self):
        page = QWidget()
        layout = QFormLayout(page)
        self.pubchem_query = QLineEdit()
        self.pubchem_query.setPlaceholderText("例如 Aspirin、Caffeine 或 CID 2244")
        self.pubchem_info = QLabel("优先下载 PubChem 3D SDF；无 3D 记录时自动回退到普通 SDF。")
        self.pubchem_info.setWordWrap(True)
        self.pubchem_info.setStyleSheet("color: #6b7280;")
        add = QPushButton("从 PubChem 获取结构")
        add.clicked.connect(self._add_pubchem)
        layout.addRow("名称或 CID", self.pubchem_query)
        layout.addRow("", self.pubchem_info)
        layout.addRow("", add)
        return page

    def _append(self, record: LigandRecord):
        if any(existing.path.name.lower() == record.path.name.lower() for existing in self.records):
            raise ValueError(f"配体文件名重复: {record.path.name}")
        self.records.append(record)
        self._refresh_table()

    def _add_local(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "添加配体文件",
            "",
            "Ligands (*.sdf *.mol2 *.mol *.pdb *.pdbqt *.smi *.smiles);;All files (*)",
        )
        errors = []
        for path in paths:
            try:
                self._append(inspect_ligand_file(Path(path)))
            except Exception as error:
                errors.append(f"{Path(path).name}: {error}")
        if errors:
            QMessageBox.warning(self, "部分文件未加入", "\n".join(errors))

    def _add_smiles(self):
        try:
            record = create_smiles_file(self.cache_dir, self.smiles_name.text(), self.smiles_text.toPlainText())
            self._append(record)
            self.smiles_text.clear()
        except Exception as error:
            QMessageBox.critical(self, "SMILES 添加失败", str(error))

    def _add_pubchem(self):
        try:
            record, properties = download_pubchem_sdf(self.cache_dir, self.pubchem_query.text())
            self._append(record)
            formula = properties.get("MolecularFormula", "未知")
            weight = properties.get("MolecularWeight", "未知")
            title = properties.get("Title", record.name)
            QMessageBox.information(self, "PubChem 获取完成", f"{title}\n分子式：{formula}\n分子量：{weight}\n文件：{record.path.name}")
        except Exception as error:
            QMessageBox.critical(self, "PubChem 获取失败", str(error))

    def _remove_selected(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.records.pop(row)
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(0)
        for record in self.records:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [record.name, record.source, record.file_format, record.status, record.warning, str(record.path)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {0, 1, 2, 3}:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)

    def selected_records(self) -> list[LigandRecord]:
        return list(self.records)
