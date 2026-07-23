import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QSizePolicy
)
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import Qt
from app.ui.widgets.zoomable_image_view import ZoomableImageView


class AnalysisGalleryWidget(QWidget):
    """Single-view gallery of scientific analysis plots. Shows one plot at a
    time, scaled to fill the tab, with Prev/Next navigation and a dropdown to
    jump directly to any plot. Only successfully-generated plots are listed.

    Layout deliberately separates the two distinct ways to navigate instead
    of putting them in one ambiguous row: a labelled "Jump to plot" dropdown
    on its own row up top (pick any plot directly), and Previous/Next arrows
    immediately flanking the current plot's title (browse one at a time,
    visually tied to what they act on). Left/Right arrow keys do the same as
    the Previous/Next buttons.
    """

    def __init__(self, plots, parent=None):
        """plots: list of (title, image_path) tuples."""
        super().__init__(parent)
        self.items = [(t, p) for (t, p) in plots if p and os.path.exists(p)]
        self.index = 0
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)

        if not self.items:
            from app.core.constants import SimulationResultsWindowConsts
            lbl = QLabel(SimulationResultsWindowConsts.LBL_ANALYSIS_NOT_AVAILABLE)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)
            return

        # Row 1: "Jump to plot" -- a clearly-labelled shortcut to any plot
        # directly, kept visually separate from the Previous/Next pair below
        # so the two different ways to navigate don't read as one confusing
        # cluster of controls.
        jump_bar = QHBoxLayout()
        jump_label = QLabel("Jump to plot:")
        jump_bar.addWidget(jump_label)
        self.selector = QComboBox()
        self.selector.addItems([t for (t, _) in self.items])
        self.selector.currentIndexChanged.connect(self.jump_to)
        jump_bar.addWidget(self.selector, stretch=1)
        layout.addLayout(jump_bar)

        # Row 2: Previous | Title (n/N) | Next -- arrows sit right next to
        # the title they browse, rather than floating in a generic toolbar,
        # so their effect (moving to the previous/next plot) is obvious.
        nav_bar = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Previous")
        self.btn_prev.setToolTip("Previous plot (Left arrow key)")
        self.btn_prev.clicked.connect(self.show_prev)
        nav_bar.addWidget(self.btn_prev)

        self.lbl_title = QLabel()
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        nav_bar.addWidget(self.lbl_title, stretch=1)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.setToolTip("Next plot (Right arrow key)")
        self.btn_next.clicked.connect(self.show_next)
        nav_bar.addWidget(self.btn_next)

        layout.addLayout(nav_bar)

        # Image -- fits the panel by default; Ctrl+wheel zooms in to native
        # resolution and click-drag pans, so a viewer isn't stuck only ever
        # seeing the plot downsampled to the panel size.
        self.lbl_image = ZoomableImageView()
        self.lbl_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.lbl_image.setMinimumSize(400, 300)
        layout.addWidget(self.lbl_image, stretch=1)

        # Left/Right arrow keys mirror the Previous/Next buttons.
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.show_prev)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self.show_next)

        self._load_current()

    def _load_current(self):
        title, path = self.items[self.index]
        self.lbl_title.setText(f"{title}  ({self.index + 1}/{len(self.items)})")
        self.lbl_image.load(path)

        # Keep selector in sync without re-triggering jump
        self.selector.blockSignals(True)
        self.selector.setCurrentIndex(self.index)
        self.selector.blockSignals(False)

        self.btn_prev.setEnabled(self.index > 0)
        self.btn_next.setEnabled(self.index < len(self.items) - 1)

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
