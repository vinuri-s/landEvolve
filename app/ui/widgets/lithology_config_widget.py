import ast

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QDoubleSpinBox, QAbstractItemView, QMessageBox, QGroupBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from app.controllers.lithology_controller import LithologyController

_BASE_DEPTH_PADDING = 10_000.0   # extra depth added to the base layer
_BASE_ROW_COLOR     = "#2a2a3a"  # slightly different shade for the base row


class LithologyConfigWidget(QWidget):
    """
    Intuitive layer-stack editor for LithoLayersComponent.

    The user builds a stack of rock layers from surface to depth.
    Each non-base row has a rock type and a thickness.
    The base (bottom) row has a rock type but no thickness — it extends
    indefinitely.

    get_form_data() serialises the stack into the z0s / ids / attrs format
    expected by LithoLayersComponent.__init__.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.controller = LithologyController()
        self._lithologies = self.controller.get_lithologies()
        self._build_ui()
        self._add_default_stack()

    # ── UI construction ──────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        group = QGroupBox("Rock Layer Stack  (surface → base)")
        group_layout = QVBoxLayout(group)

        # Instruction label
        info = QLabel(
            "Define rock layers from the surface downward.\n"
            "The bottom row is the base layer — it extends indefinitely."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: grey; font-size: 11px;")
        group_layout.addWidget(info)

        # Layer table
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Rock Type", "Thickness (m)", "K_sp"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setMinimumHeight(160)
        group_layout.addWidget(self._table)

        # Buttons
        btn_row = QHBoxLayout()
        self._add_btn    = QPushButton("Add Layer Above Base")
        self._remove_btn = QPushButton("Remove Selected Layer")
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        group_layout.addLayout(btn_row)

        self._add_btn.clicked.connect(self._on_add_layer)
        self._remove_btn.clicked.connect(self._on_remove_layer)

        root.addWidget(group)

    # ── helpers ──────────────────────────────────────────────

    def _make_rock_combo(self, selected_id=None):
        combo = QComboBox()
        for lith in self._lithologies:
            combo.addItem(f"{lith['name']}  (K={lith['erodibility']:.2e})", lith)
        if selected_id is not None:
            for i in range(combo.count()):
                data = combo.itemData(i)
                if data is not None and data["id"] == selected_id:
                    combo.setCurrentIndex(i)
                    break
        combo.currentIndexChanged.connect(self._on_rock_changed)
        return combo

    def _make_thickness_spin(self, value=10.0):
        spin = QDoubleSpinBox()
        spin.setRange(0.1, 99_999.0)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setValue(value)
        spin.setSuffix(" m")
        spin.valueChanged.connect(self._refresh_ksp_column)
        return spin

    def _on_rock_changed(self):
        self._refresh_ksp_column()

    def _refresh_ksp_column(self):
        """Sync the read-only K_sp column with the chosen rock's erodibility."""
        for row in range(self._table.rowCount()):
            combo = self._table.cellWidget(row, 0)
            if combo is None:
                continue
            lith = combo.currentData()
            if lith is not None:
                item = QTableWidgetItem(f"{lith['erodibility']:.3e}")
                item.setForeground(QColor("#aaaaaa"))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row, 2, item)

    def _insert_row(self, is_base: bool, rock_id=None, thickness=10.0):
        row = self._table.rowCount()
        self._table.insertRow(row)

        combo = self._make_rock_combo(rock_id)
        self._table.setCellWidget(row, 0, combo)

        if is_base:
            base_item = QTableWidgetItem("∞  (base)")
            base_item.setFlags(base_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            base_item.setForeground(QColor("#666688"))
            self._table.setItem(row, 1, base_item)
            # Shade the entire row slightly
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(QColor(_BASE_ROW_COLOR))
        else:
            spin = self._make_thickness_spin(thickness)
            self._table.setCellWidget(row, 1, spin)

        self._refresh_ksp_column()

    def _add_default_stack(self):
        """Seed with a two-layer default (first lithology on top, second as base)."""
        if len(self._lithologies) >= 2:
            top_id  = self._lithologies[0]["id"]
            base_id = self._lithologies[1]["id"]
        elif len(self._lithologies) == 1:
            top_id = base_id = self._lithologies[0]["id"]
        else:
            top_id = base_id = None

        self._insert_row(is_base=False, rock_id=top_id, thickness=10.0)
        self._insert_row(is_base=True,  rock_id=base_id)

    def _is_base_row(self, row: int) -> bool:
        return self._table.cellWidget(row, 1) is None  # base has no spin

    # ── button handlers ──────────────────────────────────────

    def _on_add_layer(self):
        """Insert a new layer just before the base row."""
        n = self._table.rowCount()
        if n == 0:
            self._insert_row(is_base=False)
            return

        base_row = n - 1   # base is always the last row

        # Build new layer
        self._table.insertRow(base_row)
        rock_id = self._lithologies[0]["id"] if self._lithologies else None
        combo = self._make_rock_combo(rock_id)
        self._table.setCellWidget(base_row, 0, combo)
        spin = self._make_thickness_spin(10.0)
        self._table.setCellWidget(base_row, 1, spin)
        self._refresh_ksp_column()

    def _on_remove_layer(self):
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Remove Layer", "Select a layer to remove.")
            return
        if self._is_base_row(row):
            QMessageBox.warning(self, "Remove Layer",
                                "The base layer cannot be removed.")
            return
        if self._table.rowCount() <= 2:
            QMessageBox.warning(self, "Remove Layer",
                                "At least one layer above the base is required.")
            return
        self._table.removeRow(row)

    # ── form data interface ───────────────────────────────────

    def get_form_data(self) -> dict:
        """
        Returns the dict that LithoLayersComponent.__init__ expects:
          z0s  — list of cumulative depths (positive, metres)
          ids  — list of rock-type IDs
          attrs — {'K_sp': {id: value}}
        """
        z0s  = []
        ids  = []
        ksp_map = {}
        cumulative = 0.0

        n = self._table.rowCount()
        for row in range(n):
            combo = self._table.cellWidget(row, 0)
            lith  = combo.currentData() if combo else None
            if lith is None:
                continue

            rock_id = lith["id"]
            ids.append(rock_id)
            ksp_map[rock_id] = lith["erodibility"]

            if self._is_base_row(row):
                # Base layer: pad depth so it extends well below any erosion
                cumulative += _BASE_DEPTH_PADDING
            else:
                spin = self._table.cellWidget(row, 1)
                cumulative += spin.value() if spin else 10.0

            z0s.append(cumulative)

        attrs = {"K_sp": ksp_map}

        return {
            "z0s":   repr(z0s),
            "ids":   repr(ids),
            "attrs": repr(attrs),
        }

    def set_form_data(self, data: dict):
        """Restore layer stack from a previously saved form_data dict."""
        if not data:
            return

        try:
            z0s = list(ast.literal_eval(str(data.get("z0s", "[10000.0]"))))
            ids = list(ast.literal_eval(str(data.get("ids", "[1]"))))
        except Exception:
            return

        if not z0s or not ids or len(z0s) != len(ids):
            return

        # Clear existing rows. K_sp values are driven by the selected rock type
        # (from the lithology DB), so only the layer geometry + rock ids are restored.
        self._table.setRowCount(0)

        prev_depth = 0.0

        for i, (depth, rock_id) in enumerate(zip(z0s, ids)):
            is_base = (i == len(z0s) - 1)
            thickness = depth - prev_depth
            if not is_base:
                prev_depth = depth

            # Find matching lithology
            matched_id = None
            for lith in self._lithologies:
                if lith["id"] == rock_id:
                    matched_id = rock_id
                    break

            self._insert_row(
                is_base=is_base,
                rock_id=matched_id,
                thickness=min(thickness, 99_999.0) if not is_base else 10.0,
            )
