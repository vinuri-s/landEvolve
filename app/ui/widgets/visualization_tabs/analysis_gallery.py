import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QSizePolicy
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt


class AnalysisGalleryWidget(QWidget):
    """Single-view gallery of scientific analysis plots. Shows one plot at a
    time, scaled to fill the tab, with Prev/Next navigation and a dropdown to
    jump directly to any plot. Only successfully-generated plots are listed."""

    def __init__(self, plots, parent=None):
        """plots: list of (title, image_path) tuples."""
        super().__init__(parent)
        self.items = [(t, p) for (t, p) in plots if p and os.path.exists(p)]
        self.index = 0
        self.current_pixmap = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)

        if not self.items:
            from app.core.constants import SimulationResultsWindowConsts
            lbl = QLabel(SimulationResultsWindowConsts.LBL_ANALYSIS_NOT_AVAILABLE)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)
            return

        # Top bar: Prev | selector | Next
        bar = QHBoxLayout()

        self.btn_prev = QPushButton("◀ Previous")
        self.btn_prev.clicked.connect(self.show_prev)
        bar.addWidget(self.btn_prev)

        self.selector = QComboBox()
        self.selector.addItems([t for (t, _) in self.items])
        self.selector.currentIndexChanged.connect(self.jump_to)
        bar.addWidget(self.selector, stretch=1)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self.show_next)
        bar.addWidget(self.btn_next)

        layout.addLayout(bar)

        # Title
        self.lbl_title = QLabel()
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; margin: 6px;")
        layout.addWidget(self.lbl_title)

        # Image
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.lbl_image.setMinimumSize(400, 300)
        layout.addWidget(self.lbl_image, stretch=1)

        self._load_current()

    def _load_current(self):
        title, path = self.items[self.index]
        self.lbl_title.setText(f"{title}  ({self.index + 1}/{len(self.items)})")
        self.current_pixmap = QPixmap(path)
        self._refresh_scaling()

        # Keep selector in sync without re-triggering jump
        self.selector.blockSignals(True)
        self.selector.setCurrentIndex(self.index)
        self.selector.blockSignals(False)

        self.btn_prev.setEnabled(self.index > 0)
        self.btn_next.setEnabled(self.index < len(self.items) - 1)

    def _refresh_scaling(self):
        if not self.current_pixmap:
            return
        size = self.lbl_image.size()
        if not size.isValid() or size.width() <= 10 or size.height() <= 10:
            return
        self.lbl_image.setPixmap(
            self.current_pixmap.scaled(
                size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )

    def show_prev(self):
        if self.index > 0:
            self.index -= 1
            self._load_current()

    def show_next(self):
        if self.index < len(self.items) - 1:
            self.index += 1
            self._load_current()

    def jump_to(self, idx):
        if 0 <= idx < len(self.items):
            self.index = idx
            self._load_current()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.items:
            self._refresh_scaling()
