from __future__ import annotations

from math import cos, sin
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QWidget

from .structure_scene import StructureScene, load_structure_scene


_ELEMENT_COLORS = {
    "H": QColor("#f8fafc"),
    "C": QColor("#64748b"),
    "N": QColor("#2563eb"),
    "O": QColor("#dc2626"),
    "S": QColor("#eab308"),
    "P": QColor("#f97316"),
    "F": QColor("#22c55e"),
    "CL": QColor("#16a34a"),
    "BR": QColor("#92400e"),
    "I": QColor("#7e22ce"),
    "FE": QColor("#b45309"),
    "ZN": QColor("#0f766e"),
    "MG": QColor("#65a30d"),
    "CA": QColor("#84cc16"),
}


class NativeMoleculeCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene: StructureScene | None = None
        self.title = ""
        self.yaw = -0.55
        self.pitch = 0.35
        self.zoom = 1.0
        self._last_pos = None
        self._interacting = False
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self.setStyleSheet("background:#f8fafc;border:1px solid #dbe3ef;")

    def set_structure(self, path: Path, *, title: str, ligand_only: bool = False):
        self.scene = load_structure_scene(path, ligand_only=ligand_only)
        self.title = title
        self.yaw = -0.55
        self.pitch = 0.35
        self.zoom = 1.0
        self.update()

    def reset_view(self):
        self.yaw = -0.55
        self.pitch = 0.35
        self.zoom = 1.0
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self.zoom *= 1.12 if delta > 0 else 1 / 1.12
        self.zoom = max(0.15, min(8.0, self.zoom))
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._last_pos = event.position()
            self._interacting = True

    def mouseMoveEvent(self, event):
        if self._last_pos is None or not (event.buttons() & Qt.LeftButton):
            return
        delta = event.position() - self._last_pos
        self._last_pos = event.position()
        self.yaw += delta.x() * 0.01
        self.pitch += delta.y() * 0.01
        self.update()

    def mouseReleaseEvent(self, event):
        self._last_pos = None
        self._interacting = False
        self.update()

    def _project(self, atom, center, scale):
        x = atom.x - center[0]
        y = atom.y - center[1]
        z = atom.z - center[2]
        cy, sy = cos(self.yaw), sin(self.yaw)
        cp, sp = cos(self.pitch), sin(self.pitch)
        x1 = cy * x + sy * z
        z1 = -sy * x + cy * z
        y2 = cp * y - sp * z1
        z2 = sp * y + cp * z1
        return QPointF(self.width() / 2 + x1 * scale, self.height() / 2 - y2 * scale), z2

    def paintEvent(self, event):
        painter = QPainter(self)
        scene_size = len(self.scene.atoms) if self.scene else 0
        if not self._interacting and scene_size <= 1600:
            painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8fafc"))
        if not self.scene:
            painter.setPen(QColor("#64748b"))
            painter.drawText(self.rect(), Qt.AlignCenter, "拖入或选择结构文件后将在此处离线显示")
            return

        radius = max(self.scene.radius, 1.0)
        scale = min(self.width(), self.height()) * 0.42 / radius * self.zoom
        projected = [self._project(atom, self.scene.center, scale) for atom in self.scene.atoms]

        painter.setPen(QPen(QColor("#94a3b8"), 1.2 if scene_size < 1200 else 0.8))
        for first, second in self.scene.bonds:
            if first >= len(projected) or second >= len(projected):
                continue
            painter.drawLine(projected[first][0], projected[second][0])

        order = sorted(range(len(projected)), key=lambda index: projected[index][1])
        protein_stride = max(1, scene_size // 700)
        for index in order:
            atom = self.scene.atoms[index]
            if not atom.hetero and scene_size > 900 and index % protein_stride:
                continue
            point, depth = projected[index]
            color = _ELEMENT_COLORS.get(atom.element.upper(), QColor("#64748b"))
            if atom.hetero:
                radius_px = max(3.0, min(8.0, 5.0 * self.zoom))
            else:
                radius_px = max(1.2, min(3.8, 2.4 * self.zoom))
            painter.setPen(QPen(QColor("#334155"), 0.5))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(point, radius_px, radius_px)

        painter.setPen(QColor("#0f172a"))
        painter.drawText(14, 22, self.title)
        painter.setPen(QColor("#64748b"))
        painter.drawText(
            14,
            42,
            f"{len(self.scene.atoms)} atoms · {len(self.scene.bonds)} bonds · {self.scene.representation}",
        )


class NativePreviewPane(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.current_path: Path | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = NativeMoleculeCanvas()
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color:#64748b;padding:4px 8px;")
        controls = QHBoxLayout()
        reset = QPushButton("重置视角")
        reset.clicked.connect(self.canvas.reset_view)
        controls.addWidget(reset)
        controls.addStretch(1)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.message)
        layout.addLayout(controls)

    def load_structure(self, path: Path, *, ligand_only: bool = False):
        self.current_path = Path(path)
        try:
            self.canvas.set_structure(self.current_path, title=self.title, ligand_only=ligand_only)
            self.message.setText("左键拖动旋转，滚轮缩放。大蛋白将自动抽稀显示以保持流畅。")
        except Exception as error:
            self.canvas.scene = None
            self.canvas.update()
            self.message.setText(str(error))
