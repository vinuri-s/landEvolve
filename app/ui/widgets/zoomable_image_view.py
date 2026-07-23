import os
from PyQt6.QtWidgets import QScrollArea, QLabel, QSizePolicy
from PyQt6.QtGui import QPixmap, QCursor
from PyQt6.QtCore import Qt, QPoint
from app.core.constants import ZoomableImageViewConsts


class ZoomableImageView(QScrollArea):
    """Image viewer that fits the panel by default, like a plain QLabel, but
    also supports Ctrl+wheel zoom and click-drag panning so a user can inspect
    a plot at native pixel resolution instead of only ever seeing it
    downsampled to the panel size.
    """

    _ZOOM_STEP = 1.15
    _MIN_ZOOM = 1.0    # 1.0 == fit-to-panel; can't zoom out past fit
    _MAX_ZOOM = 12.0   # cap so a huge source image can't be blown up absurdly

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWidget(self._label)

        self._pixmap = None
        self._zoom = self._MIN_ZOOM
        self._panning = False
        self._pan_start = QPoint()
        self._scroll_start = QPoint()

    def load(self, path: str) -> bool:
        """Load an image from disk at fit-to-panel zoom. Returns False (and
        shows a placeholder message) if the path doesn't exist."""
        if not path or not os.path.exists(path):
            self.set_placeholder(f"{ZoomableImageViewConsts.LBL_NOT_FOUND}{path}")
            return False
        self._pixmap = QPixmap(path)
        self._zoom = self._MIN_ZOOM
        self._render()
        return True

    def set_placeholder(self, text: str):
        self._pixmap = None
        self._label.setPixmap(QPixmap())
        self._label.setText(text)

    def has_image(self) -> bool:
        return self._pixmap is not None and not self._pixmap.isNull()

    def _fit_size(self):
        if not self.has_image():
            return None
        viewport = self.viewport().size()
        pm_size = self._pixmap.size()
        if pm_size.width() == 0 or pm_size.height() == 0:
            return None
        scale = min(viewport.width() / pm_size.width(),
                    viewport.height() / pm_size.height())
        # Fill the available panel by default (matches this app's original,
        # pre-zoom QLabel behavior) -- scale up as well as down. A source
        # image smaller than the panel (a fixed-size matplotlib PNG in a
        # large window) would otherwise render small with the rest of the
        # panel left blank. Ctrl+wheel still zooms further beyond this.
        if scale <= 0:
            scale = 1.0
        return pm_size * scale

    def _render(self):
        if not self.has_image():
            return
        fit = self._fit_size()
        if fit is None or fit.width() <= 0 or fit.height() <= 0:
            return
        target_w = max(1, int(fit.width() * self._zoom))
        target_h = max(1, int(fit.height() * self._zoom))
        scaled = self._pixmap.scaled(
            target_w, target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and self.has_image():
            delta = event.angleDelta().y()
            factor = self._ZOOM_STEP if delta > 0 else 1.0 / self._ZOOM_STEP
            self._zoom = max(self._MIN_ZOOM, min(self._MAX_ZOOM, self._zoom * factor))
            self._render()
            event.accept()
        else:
            super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        # Reset to fit-to-panel.
        self._zoom = self._MIN_ZOOM
        self._render()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._zoom > self._MIN_ZOOM:
            self._panning = True
            self._pan_start = event.pos()
            self._scroll_start = QPoint(self.horizontalScrollBar().value(),
                                         self.verticalScrollBar().value())
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_start
            self.horizontalScrollBar().setValue(self._scroll_start.x() - delta.x())
            self.verticalScrollBar().setValue(self._scroll_start.y() - delta.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.unsetCursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
