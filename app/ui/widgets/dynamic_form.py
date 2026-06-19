from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QScrollArea,
    QDoubleSpinBox,
    QFileDialog,
    QPushButton,
    QHBoxLayout,
    QLabel,
)
from PyQt6.QtCore import Qt
from app.core.constants import DynamicFormConsts


class LithologyPickerWidget(QWidget):
    """
    Composite widget for K_br: a QComboBox listing all lithologies from the DB
    (showing name and erodibility) plus a 'Custom' option that reveals a
    QDoubleSpinBox for manual entry.
    """

    CUSTOM_LABEL = "Custom value"

    def __init__(self, default_value=None, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._lithologies = []  # list of {"name": str, "erodibility": float}
        self._load_lithologies()

        self.combo = QComboBox()
        self.combo.addItem(self.CUSTOM_LABEL)
        for lith in self._lithologies:
            label = f"{lith['name']}  (K = {lith['erodibility']:.2e})"
            self.combo.addItem(label)

        self.spinbox = QDoubleSpinBox()
        self.spinbox.setDecimals(8)
        self.spinbox.setRange(1e-12, 1.0)
        self.spinbox.setSingleStep(1e-6)
        self.spinbox.setMinimumWidth(120)

        layout.addWidget(self.combo, stretch=2)
        layout.addWidget(self.spinbox, stretch=1)

        self.combo.currentIndexChanged.connect(self._on_combo_changed)

        # Set initial value
        if default_value not in (None, ""):
            self.setValue(float(default_value))
        else:
            self._on_combo_changed(0)

    def _load_lithologies(self):
        try:
            from app.controllers.lithology_controller import LithologyController
            self._lithologies = LithologyController().get_lithologies()
        except Exception:
            self._lithologies = []

    def _on_combo_changed(self, index):
        is_custom = (index == 0)
        self.spinbox.setVisible(is_custom)
        if not is_custom and index - 1 < len(self._lithologies):
            # Sync spinbox to the chosen lithology's erodibility (useful if
            # user later switches back to Custom — they see the last picked value)
            self.spinbox.setValue(self._lithologies[index - 1]["erodibility"])

    def value(self):
        """Returns the effective K_br as a float."""
        idx = self.combo.currentIndex()
        if idx == 0:
            return self.spinbox.value()
        lith_idx = idx - 1
        if lith_idx < len(self._lithologies):
            return self._lithologies[lith_idx]["erodibility"]
        return self.spinbox.value()

    def setValue(self, v: float):
        """Select the lithology whose erodibility matches v, else fall back to Custom."""
        for i, lith in enumerate(self._lithologies):
            if abs(lith["erodibility"] - v) < 1e-15:
                self.combo.setCurrentIndex(i + 1)
                return
        # No exact match — use Custom
        self.combo.setCurrentIndex(0)
        self.spinbox.setValue(v)


class DynamicFormWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.fields = {}

        main_layout = QVBoxLayout(self)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.form_layout = QFormLayout(scroll_content)
        # Keep labels vertically centred against their input widgets so the
        # layman name + key/units line up cleanly with each control.
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        for item in self.config:

            label = item.get("label", "")
            field_type = item.get("type", "QLineEdit")
            validation = item.get("validation", None)
            default_value = item.get("default_value", None)

            # Human-friendly row label: layman name + technical key + units,
            # with a tooltip describing the parameter (all from the DB).
            row_label = self._param_row_label(item)

            if field_type == "QLineEdit":
                widget = QLineEdit()

                if validation == "Optional":
                    widget.setPlaceholderText(DynamicFormConsts.OPTIONAL_TEXT)

                if default_value not in (None, ""):
                    widget.setText(str(default_value))

                self.fields[label] = widget
                self.form_layout.addRow(row_label, widget)

            elif field_type == "QComboBox":
                widget = QComboBox()
                widget.setEditable(False)

                if validation:
                    options = [opt.strip() for opt in validation.split("|")]
                    widget.addItems(options)

                if default_value not in (None, ""):
                    index = widget.findText(str(default_value))
                    if index >= 0:
                        widget.setCurrentIndex(index)

                self.fields[label] = widget
                self.form_layout.addRow(row_label, widget)

            elif field_type == "QDoubleSpinBox":
                widget = QDoubleSpinBox()
                widget.setMinimum(0.0)

                # validation format: min|max|step
                step = None
                if validation:
                    parts = [part.strip() for part in validation.split("|")]
                    try:
                        if len(parts) >= 1 and parts[0] != "":
                            widget.setMinimum(float(parts[0]))
                        if len(parts) >= 2 and parts[1] != "":
                            widget.setMaximum(float(parts[1]))
                        if len(parts) >= 3 and parts[2] != "":
                            step = float(parts[2])
                            widget.setSingleStep(step)
                    except ValueError:
                        pass

                # Show enough decimals to represent the step and default exactly
                # (so e.g. K_sed=1e-4 or uplift_rate=0.001 are usable, while a
                # step-0.1 control isn't padded with trailing zeros).
                widget.setDecimals(self._decimals_for(step, default_value))

                # default_value is the only true default
                if default_value not in (None, ""):
                    try:
                        widget.setValue(float(default_value))
                    except (ValueError, TypeError):
                        pass

                self.fields[label] = widget
                self.form_layout.addRow(row_label, widget)

            elif field_type == "LithologyComboBox":
                widget = LithologyPickerWidget(default_value=default_value)
                self.fields[label] = widget
                self.form_layout.addRow(row_label, widget)

            elif field_type == "QFileEdit":
                file_widget = QWidget()
                file_layout = QHBoxLayout(file_widget)
                file_layout.setContentsMargins(0, 0, 0, 0)

                line_edit = QLineEdit()
                browse_btn = QPushButton(DynamicFormConsts.BTN_BROWSE)

                if default_value not in (None, ""):
                    line_edit.setText(str(default_value))

                def browse_file(le=line_edit):
                    file_path, _ = QFileDialog.getOpenFileName(
                        self,
                        DynamicFormConsts.FILE_DIALOG_TITLE,
                        "",
                        DynamicFormConsts.FILE_DIALOG_FILTER,
                    )
                    if file_path:
                        le.setText(file_path)

                browse_btn.clicked.connect(browse_file)

                file_layout.addWidget(line_edit)
                file_layout.addWidget(browse_btn)

                self.fields[label] = line_edit
                self.form_layout.addRow(row_label, file_widget)

        conditional_fields = [
            DynamicFormConsts.FIELD_GEOLOGY_FILE,
            DynamicFormConsts.FIELD_K_SED,
            DynamicFormConsts.FIELD_K_BR,
        ]

        if DynamicFormConsts.FIELD_LITHOLOGY_TYPE in self.fields:
            lithology_combo = self.fields[DynamicFormConsts.FIELD_LITHOLOGY_TYPE]

            def update_fields_visibility():
                is_heterogeneous = (
                    lithology_combo.currentText()
                    == DynamicFormConsts.LITHOLOGY_HETEROGENEOUS
                )

                for field_name in conditional_fields:
                    if field_name in self.fields:
                        widget = self.fields[field_name]
                        label_item = self.form_layout.labelForField(widget)

                        if field_name in (
                            DynamicFormConsts.FIELD_K_SED,
                            DynamicFormConsts.FIELD_K_BR,
                        ):
                            visible = not is_heterogeneous
                        else:
                            visible = is_heterogeneous

                        widget.setVisible(visible)
                        if label_item:
                            label_item.setVisible(visible)

            lithology_combo.currentTextChanged.connect(update_fields_visibility)
            update_fields_visibility()

        # Precipitation: show only the parameters relevant to the selected mode.
        if DynamicFormConsts.FIELD_PRECIP_MODE in self.fields and \
                DynamicFormConsts.FIELD_PRECIPITATION in self.fields:
            mode_combo = self.fields[DynamicFormConsts.FIELD_PRECIP_MODE]

            def update_precip_visibility():
                mode = mode_combo.currentText()
                spatial = mode == DynamicFormConsts.PRECIP_MODE_SPATIAL
                stochastic = mode == DynamicFormConsts.PRECIP_MODE_STOCHASTIC
                trend = mode == DynamicFormConsts.PRECIP_MODE_TREND

                # `precipitation` is the mean/start value for every mode except Spatial.
                self._set_row_visible(DynamicFormConsts.FIELD_PRECIPITATION, not spatial)
                self._set_row_visible(DynamicFormConsts.FIELD_PRECIP_RASTER, spatial)
                self._set_row_visible(DynamicFormConsts.FIELD_FINAL_PRECIPITATION, trend)
                self._set_row_visible(DynamicFormConsts.FIELD_VARIABILITY, stochastic)
                self._set_row_visible(DynamicFormConsts.FIELD_RANDOM_SEED, stochastic)

            mode_combo.currentTextChanged.connect(update_precip_visibility)
            update_precip_visibility()

        # Tectonics: show the uplift rate (Uniform) or the uplift raster (Spatial).
        if DynamicFormConsts.FIELD_TECT_MODE in self.fields and \
                DynamicFormConsts.FIELD_UPLIFT_RATE in self.fields:
            tect_mode_combo = self.fields[DynamicFormConsts.FIELD_TECT_MODE]

            def update_tect_visibility():
                spatial = tect_mode_combo.currentText() == DynamicFormConsts.TECT_MODE_SPATIAL
                self._set_row_visible(DynamicFormConsts.FIELD_UPLIFT_RATE, not spatial)
                self._set_row_visible(DynamicFormConsts.FIELD_UPLIFT_RASTER, spatial)

            tect_mode_combo.currentTextChanged.connect(update_tect_visibility)
            update_tect_visibility()

    @staticmethod
    def _decimals_for(*values):
        """Decimal places needed to represent the given values exactly (e.g. a
        step of 1e-4 -> 4), floored at 2 and capped at 10."""
        d = 2
        for v in values:
            if v in (None, ""):
                continue
            try:
                f = abs(float(v))
            except (ValueError, TypeError):
                continue
            s = f"{f:.10f}".rstrip("0")
            if "." in s:
                d = max(d, len(s.split(".")[1]))
        return min(d, 10)

    def _param_row_label(self, item):
        """Build a form-row label from DB metadata: layman name on top, the
        technical key + units beneath, and the description as a tooltip."""
        key = item.get("label", "")
        name = item.get("display_name") or key
        units = item.get("units") or ""
        desc = item.get("description") or ""
        sub = key + (f" &middot; {units}" if units else "")
        # Single line so the label height matches single-line input widgets:
        # layman name, then the technical key + units in small grey.
        lbl = QLabel(
            f'{name} &nbsp;<span style="color:#9aa0a6; font-size:10px;">({sub})</span>'
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if desc:
            lbl.setToolTip(desc)
        return lbl

    def _set_row_visible(self, field_key, visible):
        """Show/hide a form row (widget + its label) by field key, handling the
        composite file-edit widget whose row holds a container, not the field."""
        if field_key not in self.fields:
            return
        widget = self.fields[field_key]
        # The row widget is the field itself, except for QFileEdit where the row
        # holds the line-edit's parent container.
        row_widget = widget
        label_item = self.form_layout.labelForField(widget)
        if label_item is None and widget.parentWidget() is not None:
            row_widget = widget.parentWidget()
            label_item = self.form_layout.labelForField(row_widget)

        row_widget.setVisible(visible)
        if label_item:
            label_item.setVisible(visible)

    def get_form_data(self):
        data = {}
        for label, widget in self.fields.items():
            if isinstance(widget, LithologyPickerWidget):
                data[label] = widget.value()
            elif isinstance(widget, QLineEdit):
                data[label] = widget.text()
            elif isinstance(widget, QComboBox):
                data[label] = widget.currentText()
            elif isinstance(widget, QDoubleSpinBox):
                data[label] = widget.value()
        return data

    def set_form_data(self, data):
        """Populate form fields from a data dictionary."""

        if not data:
            return

        for label, value in data.items():
            if label not in self.fields:
                continue

            widget = self.fields[label]

            if isinstance(widget, LithologyPickerWidget):
                try:
                    widget.setValue(float(value))
                except (ValueError, TypeError):
                    pass

            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))

            elif isinstance(widget, QComboBox):
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)

            elif isinstance(widget, QDoubleSpinBox):
                try:
                    widget.setValue(float(value))
                except (ValueError, TypeError):
                    pass
