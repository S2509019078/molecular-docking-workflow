from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QUrl, QEvent
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import *

from .desktop import cli_program_and_prefix, create_gui_project, default_tools, inspect_structure, load_summary, recent_configs
from .wizard import acquire_for_wizard, safe_name

APP_STYLE = """
QWidget { background:#f5f7fb; color:#172033; font-family:'Segoe UI'; font-size:10pt; }
#Sidebar { background:#111827; }
#Brand { color:white; font-size:20pt; font-weight:700; }
#Subtitle { color:#9ca3af; }
QFrame#Card { background:white; border:1px solid #e5e7eb; border-radius:10px; }
QPushButton#Primary { background:#2563eb; color:white; }
QTableWidget::item:selected { background:#2563eb; color:white; }
"""


class DockFlowWindow(QMainWindow):
    def __init__(self, runs_dir: Path):
        super().__init__()
        self.runs_dir = Path(runs_dir)
        self.current_config = None
        self.current_pdb = None
        self.inspection = None
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_process_output)
        self.process.finished.connect(self._process_finished)
        self.setWindowTitle('DockFlow — Molecular Docking Studio')
        self.resize(1280, 850)
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0,0,0,0)
        sidebar = QFrame(objectName='Sidebar')
        sidebar.setFixedWidth(170)
        side = QVBoxLayout(sidebar)
        brand = QLabel('DockFlow', objectName='Brand')
        side.addWidget(brand)
        side.addWidget(QLabel('Molecular Docking Studio', objectName='Subtitle'))
        self.nav_buttons=[]
        for i,text in enumerate(['新建项目','运行中心','结果分析','工具设置']):
            b=QPushButton(text, objectName='NavButton')
            b.clicked.connect(lambda _,x=i:self.pages.setCurrentIndex(x))
            self.nav_buttons.append(b)
            side.addWidget(b)
        side.addStretch()
        self.pages=QStackedWidget()
        self.pages.addWidget(self._build_project_page())
        self.pages.addWidget(self._simple_page('运行中心'))
        self.pages.addWidget(self._simple_page('结果分析'))
        self.pages.addWidget(self._simple_page('工具设置'))
        layout.addWidget(sidebar)
        layout.addWidget(self.pages,1)
        self.setCentralWidget(root)

    def _simple_page(self,title):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(QLabel(title)); return w

    def _build_project_page(self):
        page=QWidget(); outer=QVBoxLayout(page)
        splitter=QSplitter(Qt.Horizontal)
        left=QFrame(objectName='Card'); ll=QVBoxLayout(left)
        self.structure_input=QLineEdit(); self.structure_input.setAcceptDrops(True); self.structure_input.installEventFilter(self)
        self.structure_input.setPlaceholderText('输入PDB ID或拖入PDB文件')
        ll.addWidget(QLabel('受体结构')); ll.addWidget(self.structure_input)
        self.chain_list=QListWidget(); ll.addWidget(self.chain_list)
        splitter.addWidget(left)
        right=QFrame(objectName='Card'); rl=QVBoxLayout(right)
        self.ligand_files=QListWidget(); rl.addWidget(self.ligand_files)
        splitter.addWidget(right)
        splitter.setSizes([500,500])
        outer.addWidget(splitter)
        return page

    def eventFilter(self,obj,event):
        if obj is self.structure_input and event.type()==QEvent.Drop:
            urls=event.mimeData().urls()
            if urls:
                self.structure_input.setText(urls[0].toLocalFile())
                return True
        if obj is self.structure_input and event.type()==QEvent.DragEnter:
            if event.mimeData().hasUrls():
                event.acceptProposedAction(); return True
        return super().eventFilter(obj,event)
