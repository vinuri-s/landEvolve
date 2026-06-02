import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog,
    QFormLayout, QDoubleSpinBox, QLineEdit, QComboBox,
    QButtonGroup, QRadioButton, QGroupBox, QSpinBox,
    QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt

from app.controllers.vegetation_controller import VegetationController


# ──────────────────────────────────────────────────────────────
# Class editor dialog
# ──────────────────────────────────────────────────────────────

class _VegetationClassDialog(QDialog):
    def __init__(self, parent=None, existing=None):
        super().__init__(parent)
        self.setWindowTitle("Vegetation Class" if existing is None else "Edit Vegetation Class")
        self.setMinimumWidth(320)

        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        layout.addRow("Name", self.name_edit)

        def spin(default):
            w = QDoubleSpinBox()
            w.setRange(0.0, 10.0)
            w.setDecimals(3)
            w.setSingleStep(0.1)
            w.setValue(default)
            return w

        self.K_sed = spin(1.0)
        self.K_br = spin(1.0)
        self.D = spin(1.0)
        self.runoff = spin(1.0)

        layout.addRow("K_sed multiplier", self.K_sed)
        layout.addRow("K_br multiplier", self.K_br)
        layout.addRow("Linear diffusivity multiplier", self.D)
        layout.addRow("Runoff multiplier", self.runoff)

        btns = QHBoxLayout()
        ok_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)

        container = QWidget()
        container.setLayout(btns)
        layout.addRow(container)

        if existing:
            self.name_edit.setText(existing.get('name', ''))
            self.K_sed.setValue(existing.get('K_sed_multiplier', 1.0))
            self.K_br.setValue(existing.get('K_br_multiplier', 1.0))
            self.D.setValue(existing.get('linear_diffusivity_multiplier', 1.0))
            self.runoff.setValue(existing.get('runoff_multiplier', 1.0))

    def values(self):
        return {
            'name': self.name_edit.text().strip(),
            'K_sed_multiplier': self.K_sed.value(),
            'K_br_multiplier': self.K_br.value(),
            'linear_diffusivity_multiplier': self.D.value(),
            'runoff_multiplier': self.runoff.value(),
        }


# ──────────────────────────────────────────────────────────────
# Main vegetation configuration widget
# ──────────────────────────────────────────────────────────────

class VegetationConfigWidget(QWidget):
    """
    Custom configuration widget for the VegetationComponent.
    Replaces the generic DynamicFormWidget for this component.

    Exposes get_form_data() / set_form_data() matching the DynamicFormWidget interface.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.controller = VegetationController()
        self._build_ui()
        self._load_classes()

    # ── UI construction ──────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Vegetation class library ──────────────────────────
        class_group = QGroupBox("Vegetation Classes")
        class_layout = QVBoxLayout(class_group)

        self._class_table = QTableWidget(0, 5)
        self._class_table.setHorizontalHeaderLabels([
            "ID", "Name", "K_sed ×", "K_br ×", "Diffusivity ×", # runoff shown via tooltip
        ])
        # Actually show 6 columns including runoff
        self._class_table.setColumnCount(6)
        self._class_table.setHorizontalHeaderLabels([
            "ID", "Name", "K_sed ×", "K_br ×", "Diffusivity ×", "Runoff ×",
        ])
        self._class_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._class_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._class_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._class_table.setColumnHidden(0, True)  # hide ID column

        class_btn_row = QHBoxLayout()
        self._add_class_btn = QPushButton("Add Class")
        self._edit_class_btn = QPushButton("Edit Class")
        self._del_class_btn = QPushButton("Delete Class")
        for b in (self._add_class_btn, self._edit_class_btn, self._del_class_btn):
            class_btn_row.addWidget(b)

        self._add_class_btn.clicked.connect(self._on_add_class)
        self._edit_class_btn.clicked.connect(self._on_edit_class)
        self._del_class_btn.clicked.connect(self._on_delete_class)

        class_layout.addWidget(self._class_table)
        class_layout.addLayout(class_btn_row)
        root.addWidget(class_group)

        # ── Mode selection ────────────────────────────────────
        mode_group = QGroupBox("Vegetation Mode")
        mode_layout = QVBoxLayout(mode_group)

        self._static_radio = QRadioButton("Static – one class for entire simulation")
        self._transition_radio = QRadioButton("Transition – scheduled class changes over time")
        self._static_radio.setChecked(True)

        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self._static_radio)
        self._mode_group.addButton(self._transition_radio)

        self._static_radio.toggled.connect(self._update_mode_visibility)

        mode_layout.addWidget(self._static_radio)
        mode_layout.addWidget(self._transition_radio)
        root.addWidget(mode_group)

        # ── Static config ─────────────────────────────────────
        self._static_group = QGroupBox("Static Configuration")
        static_layout = QFormLayout(self._static_group)
        self._static_class_combo = QComboBox()
        static_layout.addRow("Vegetation class:", self._static_class_combo)
        root.addWidget(self._static_group)

        # ── Transition config ─────────────────────────────────
        self._transition_group = QGroupBox("Transition Schedule")
        trans_layout = QVBoxLayout(self._transition_group)

        self._trans_table = QTableWidget(0, 3)
        self._trans_table.setHorizontalHeaderLabels(["Timestep", "From Class", "To Class"])
        self._trans_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._trans_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._trans_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        trans_btn_row = QHBoxLayout()
        self._add_trans_btn = QPushButton("Add Transition")
        self._del_trans_btn = QPushButton("Remove Transition")
        trans_btn_row.addWidget(self._add_trans_btn)
        trans_btn_row.addWidget(self._del_trans_btn)

        self._add_trans_btn.clicked.connect(self._on_add_transition)
        self._del_trans_btn.clicked.connect(self._on_delete_transition)

        trans_layout.addWidget(self._trans_table)
        trans_layout.addLayout(trans_btn_row)
        root.addWidget(self._transition_group)

        self._transition_group.setVisible(False)

    # ── Class library helpers ─────────────────────────────────

    def _load_classes(self):
        classes = self.controller.get_classes()
        self._populate_class_table(classes)
        self._populate_class_combos(classes)

    def _populate_class_table(self, classes):
        self._class_table.setRowCount(0)
        for vc in classes:
            row = self._class_table.rowCount()
            self._class_table.insertRow(row)
            self._class_table.setItem(row, 0, QTableWidgetItem(str(vc["id"])))
            self._class_table.setItem(row, 1, QTableWidgetItem(vc["name"]))
            self._class_table.setItem(row, 2, QTableWidgetItem(f"{vc['K_sed_multiplier']:.3f}"))
            self._class_table.setItem(row, 3, QTableWidgetItem(f"{vc['K_br_multiplier']:.3f}"))
            self._class_table.setItem(row, 4, QTableWidgetItem(f"{vc['linear_diffusivity_multiplier']:.3f}"))
            self._class_table.setItem(row, 5, QTableWidgetItem(f"{vc['runoff_multiplier']:.3f}"))

    def _populate_class_combos(self, classes):
        prev_static = self._static_class_combo.currentData()

        self._static_class_combo.clear()
        for vc in classes:
            self._static_class_combo.addItem(vc["name"], vc["id"])

        if prev_static is not None:
            idx = self._static_class_combo.findData(prev_static)
            if idx >= 0:
                self._static_class_combo.setCurrentIndex(idx)

        # Refresh combos inside transition rows
        self._refresh_transition_combos(classes)

    def _refresh_transition_combos(self, classes):
        for row in range(self._trans_table.rowCount()):
            for col in (1, 2):
                cell_widget = self._trans_table.cellWidget(row, col)
                if isinstance(cell_widget, QComboBox):
                    current = cell_widget.currentData()
                    cell_widget.clear()
                    for vc in classes:
                        cell_widget.addItem(vc["name"], vc["id"])
                    if current is not None:
                        idx = cell_widget.findData(current)
                        if idx >= 0:
                            cell_widget.setCurrentIndex(idx)

    def _get_class_names(self):
        return self.controller.get_classes()

    def _selected_class_id(self):
        row = self._class_table.currentRow()
        if row < 0:
            return None
        item = self._class_table.item(row, 0)
        return int(item.text()) if item else None

    # ── Class CRUD handlers ───────────────────────────────────

    def _on_add_class(self):
        dlg = _VegetationClassDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.values()
            if not vals['name']:
                QMessageBox.warning(self, "Validation", "Class name cannot be empty.")
                return
            self.controller.create_class(**vals)
            self._load_classes()

    def _on_edit_class(self):
        cls_id = self._selected_class_id()
        if cls_id is None:
            QMessageBox.information(self, "Edit Class", "Select a class to edit.")
            return
        existing = self.controller.get_class(cls_id)

        dlg = _VegetationClassDialog(self, existing=existing)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.values()
            if not vals['name']:
                QMessageBox.warning(self, "Validation", "Class name cannot be empty.")
                return
            self.controller.update_class(cls_id, **vals)
            self._load_classes()

    def _on_delete_class(self):
        cls_id = self._selected_class_id()
        if cls_id is None:
            QMessageBox.information(self, "Delete Class", "Select a class to delete.")
            return
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            "Delete this vegetation class? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.controller.delete_class(cls_id)
            self._load_classes()

    # ── Mode visibility ───────────────────────────────────────

    def _update_mode_visibility(self):
        is_static = self._static_radio.isChecked()
        self._static_group.setVisible(is_static)
        self._transition_group.setVisible(not is_static)

    # ── Transition CRUD ───────────────────────────────────────

    def _make_class_combo(self, classes, selected_id=None):
        combo = QComboBox()
        for vc in classes:
            combo.addItem(vc["name"], vc["id"])
        if selected_id is not None:
            idx = combo.findData(selected_id)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        return combo

    def _on_add_transition(self):
        classes = self._get_class_names()
        if not classes:
            QMessageBox.warning(self, "No Classes", "Add at least one vegetation class first.")
            return

        row = self._trans_table.rowCount()
        self._trans_table.insertRow(row)

        step_spin = QSpinBox()
        step_spin.setRange(1, 9_999_999)
        step_spin.setValue(100)
        self._trans_table.setCellWidget(row, 0, step_spin)
        self._trans_table.setCellWidget(row, 1, self._make_class_combo(classes))
        self._trans_table.setCellWidget(row, 2, self._make_class_combo(classes))

    def _on_delete_transition(self):
        row = self._trans_table.currentRow()
        if row >= 0:
            self._trans_table.removeRow(row)

    # ── Form data interface ───────────────────────────────────

    def get_form_data(self):
        mode = 'Static' if self._static_radio.isChecked() else 'Transition'
        static_class_id = self._static_class_combo.currentData()

        transitions = []
        for row in range(self._trans_table.rowCount()):
            step_w = self._trans_table.cellWidget(row, 0)
            src_w = self._trans_table.cellWidget(row, 1)
            tgt_w = self._trans_table.cellWidget(row, 2)
            if step_w and src_w and tgt_w:
                transitions.append({
                    'timestep': step_w.value(),
                    'source_class_id': src_w.currentData(),
                    'target_class_id': tgt_w.currentData(),
                })

        return {
            'vegetation_mode': mode,
            'static_class_id': static_class_id if static_class_id is not None else 0,
            'transitions': json.dumps(transitions),
        }

    def set_form_data(self, data):
        if not data:
            return

        mode = data.get('vegetation_mode', 'Static')
        if mode == 'Transition':
            self._transition_radio.setChecked(True)
        else:
            self._static_radio.setChecked(True)
        self._update_mode_visibility()

        static_id = data.get('static_class_id')
        if static_id is not None:
            idx = self._static_class_combo.findData(int(static_id))
            if idx >= 0:
                self._static_class_combo.setCurrentIndex(idx)

        transitions_raw = data.get('transitions', '[]')
        if isinstance(transitions_raw, str):
            try:
                transitions_raw = json.loads(transitions_raw)
            except (json.JSONDecodeError, TypeError):
                transitions_raw = []

        self._trans_table.setRowCount(0)
        classes = self._get_class_names()
        for t in transitions_raw:
            row = self._trans_table.rowCount()
            self._trans_table.insertRow(row)

            step_spin = QSpinBox()
            step_spin.setRange(1, 9_999_999)
            step_spin.setValue(int(t.get('timestep', 1)))
            self._trans_table.setCellWidget(row, 0, step_spin)
            self._trans_table.setCellWidget(
                row, 1,
                self._make_class_combo(classes, t.get('source_class_id'))
            )
            self._trans_table.setCellWidget(
                row, 2,
                self._make_class_combo(classes, t.get('target_class_id'))
            )
