from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from .desktop import load_summary
from .gui import APP_STYLE
from .gui_advanced import DockFlowAdvancedWindow
from .result_workbench import ResultFilter, build_3dmol_preview, export_results_csv, filter_results


class DockFlowWorkbenchWindow(DockFlowAdvancedWindow):
    def __init__(self, runs_dir: Path):
        self.all_result_rows: list[dict[str, str]] = []
        self.filtered_result_rows: list[dict[str, str]] = []
        super().__init__(runs_dir)
        self.setWindowTitle("DockFlow — Molecular Docking Studio 0.6")
        self._install_result_toolbar()

    def _install_result_toolbar(self):
        page = self.pages.widget(2)
        layout = page.layout()
        toolbar = QWidget()
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(0, 0, 0, 0)
        self.result_query = QLineEdit()
        self.result_query.setPlaceholderText("搜索靶标、配体、分类或证据")
        self.result_query.textChanged.connect(self._apply_result_filters)
        self.result_classification = QComboBox()
        self.result_classification.addItems(["全部分类", "reference_consistent", "manual_review", "exploratory", "low_confidence"])
        self.result_classification.currentTextChanged.connect(self._apply_result_filters)
        self.affinity_filter_enabled = QPushButton("启用能量阈值")
        self.affinity_filter_enabled.setCheckable(True)
        self.affinity_filter_enabled.toggled.connect(self._apply_result_filters)
        self.max_affinity = QDoubleSpinBox()
        self.max_affinity.setRange(-30.0, 20.0)
        self.max_affinity.setDecimals(1)
        self.max_affinity.setValue(-7.0)
        self.max_affinity.setSuffix(" kcal/mol")
        self.max_affinity.valueChanged.connect(self._apply_result_filters)
        preview = QPushButton("3D预览")
        preview.clicked.connect(self._preview_selected_result)
        export = QPushButton("导出筛选结果")
        export.clicked.connect(self._export_filtered_results)
        row.addWidget(QLabel("筛选"))
        row.addWidget(self.result_query, 2)
        row.addWidget(self.result_classification)
        row.addWidget(self.affinity_filter_enabled)
        row.addWidget(self.max_affinity)
        row.addWidget(preview)
        row.addWidget(export)
        layout.insertWidget(3, toolbar)
        self.result_table.setSortingEnabled(True)

    def _refresh_results(self):
        self.all_result_rows = []
        if self.current_config:
            self.all_result_rows = load_summary(self.current_config.parent.parent / "results" / "docking_summary.tsv")
        self._apply_result_filters()

    def _apply_result_filters(self):
        if not hasattr(self, "result_query"):
            return
        classification = self.result_classification.currentText()
        if classification == "全部分类":
            classification = ""
        criteria = ResultFilter(
            query=self.result_query.text(),
            max_affinity=self.max_affinity.value() if self.affinity_filter_enabled.isChecked() else None,
            classification=classification,
        )
        self.filtered_result_rows = filter_results(self.all_result_rows, criteria)
        self.result_table.setSortingEnabled(False)
        self.result_table.setRowCount(0)
        for row_data in self.filtered_result_rows:
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            values = [
                row_data.get("target", ""),
                row_data.get("ligand", ""),
                row_data.get("affinity_kcal_mol", ""),
                row_data.get("reference_center_distance_angstrom", ""),
                row_data.get("classification", ""),
                row_data.get("evidence", ""),
            ]
            from PySide6.QtWidgets import QTableWidgetItem
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {2, 3}:
                    try:
                        item.setData(Qt.EditRole, float(value))
                    except (TypeError, ValueError):
                        pass
                self.result_table.setItem(row, column, item)
        self.result_table.setSortingEnabled(True)
        self.statusBar().showMessage(f"显示 {len(self.filtered_result_rows)} / {len(self.all_result_rows)} 条结果", 5000)

    def _selected_identifiers(self) -> tuple[str, str] | None:
        row = self.result_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "未选择结果", "请先在结果表中选择一行。")
            return None
        target = self.result_table.item(row, 0)
        ligand = self.result_table.item(row, 1)
        if not target or not ligand:
            return None
        return target.text(), ligand.text()

    def _preview_selected_result(self):
        if not self.current_config:
            QMessageBox.warning(self, "未选择项目", "请先创建或打开项目。")
            return
        identifiers = self._selected_identifiers()
        if not identifiers:
            return
        try:
            preview = build_3dmol_preview(self.current_config, *identifiers)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(preview)))
        except Exception as error:
            QMessageBox.critical(self, "3D预览生成失败", str(error))

    def _export_filtered_results(self):
        if not self.filtered_result_rows:
            QMessageBox.warning(self, "没有结果", "当前筛选条件下没有可导出的结果。")
            return
        default = "DockFlow_filtered_results.csv"
        if self.current_config:
            default = str(self.current_config.parent.parent / "results" / default)
        path, _ = QFileDialog.getSaveFileName(self, "导出筛选结果", default, "CSV (*.csv)")
        if not path:
            return
        try:
            output = export_results_csv(self.filtered_result_rows, Path(path))
            QMessageBox.information(self, "导出完成", str(output))
        except Exception as error:
            QMessageBox.critical(self, "导出失败", str(error))


def run_gui(runs_dir: Path, smoke_test: bool = False) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("DockFlow")
    app.setOrganizationName("DockFlow")
    app.setStyleSheet(APP_STYLE)
    window = DockFlowWorkbenchWindow(runs_dir)
    if smoke_test:
        window.show()
        app.processEvents()
        window.close()
        print("DockFlow GUI result workbench OK")
        return 0
    window.show()
    return app.exec()
