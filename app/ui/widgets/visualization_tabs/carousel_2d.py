import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QDoubleSpinBox
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
from app.core.constants import SimulationResultKeys, Carousel2DWidgetConsts

class Carousel2DWidget(QWidget):
    """
    Responsibility: Manages the '2D Visualization' tab UI.
    Handles loading images from disk, scaling them smoothly to fit the window,
    and managing the toggle state between Input/Final/Difference maps.
    """
    def __init__(self, image_paths: dict, controller=None, parent=None):
        super().__init__(parent)
        self.image_paths = image_paths
        self.controller = controller
        
        self.current_pixmap = None
        self.current_2d_key = None
        self.current_2d_title = None
        self.current_active_btn = None
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Title Label
        self.lbl_title = QLabel("") # Renamed from lbl_image_title
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(self.lbl_title)
        
        # Image Display Area
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setText(Carousel2DWidgetConsts.LBL_LOADING) # Set initial text
        self.lbl_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding) # Moved setSizePolicy
        self.lbl_image.setMinimumSize(400, 300) # Moved setMinimumSize
        layout.addWidget(self.lbl_image)
        
        # Toggle Controls
        controls = QHBoxLayout() # Kept as controls, not btn_layout
        controls.addStretch()
        
        self.btn_input = QPushButton(Carousel2DWidgetConsts.BTN_INPUT) # Used constant
        self.btn_input.setCheckable(True) # Kept setCheckable
        self.btn_input.clicked.connect(self.show_input)
        controls.addWidget(self.btn_input)
        
        self.btn_final = QPushButton(Carousel2DWidgetConsts.BTN_FINAL) # Used constant
        self.btn_final.setCheckable(True) # Kept setCheckable
        self.btn_final.clicked.connect(self.show_final)
        controls.addWidget(self.btn_final)

        self.btn_diff = QPushButton(Carousel2DWidgetConsts.BTN_DIFF) # Used constant
        self.btn_diff.setCheckable(True) # Kept setCheckable
        self.btn_diff.clicked.connect(self.show_diff)
        controls.addWidget(self.btn_diff)
        
        self.button_group = [self.btn_input, self.btn_final, self.btn_diff]
        
        controls.addStretch()
        layout.addLayout(controls)

        # Scale Controls (Hidden by default, shown for Difference Map)
        self.scale_controls = QWidget()
        scale_layout = QHBoxLayout(self.scale_controls)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_scale = QLabel(Carousel2DWidgetConsts.LBL_SCALE_RANGE)
        scale_layout.addWidget(self.lbl_scale)
        
        diff_max = self.image_paths.get(SimulationResultKeys.DIFF_MAX, 1.0)
        
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(0.01, 10000.0)
        self.spin_scale.setDecimals(2)
        self.spin_scale.setValue(float(diff_max))
        self.spin_scale.setSingleStep(0.1)
        scale_layout.addWidget(self.spin_scale)
        
        self.btn_apply_scale = QPushButton(Carousel2DWidgetConsts.BTN_APPLY_SCALE)
        self.btn_apply_scale.clicked.connect(self.apply_custom_scale)
        scale_layout.addWidget(self.btn_apply_scale)
        
        self.btn_reset_scale = QPushButton(Carousel2DWidgetConsts.BTN_RESET_SCALE)
        self.btn_reset_scale.clicked.connect(self.reset_scale)
        scale_layout.addWidget(self.btn_reset_scale)
        
        self.scale_controls.hide()
        layout.addWidget(self.scale_controls, alignment=Qt.AlignmentFlag.AlignCenter)

    def apply_custom_scale(self):
        val = self.spin_scale.value()
        self._regenerate_diff_map(vmin=-val, vmax=val)
        
    def reset_scale(self):
        self._regenerate_diff_map(vmin=None, vmax=None)
        
    def _regenerate_diff_map(self, vmin, vmax):
        if not self.controller:
            return
            
        output_dir = self.image_paths.get(SimulationResultKeys.OUTPUT_DIR)
        if not output_dir:
            return
            
        diff_tif = os.path.join(output_dir, "diff.tif")
        diff_png = self.image_paths.get(SimulationResultKeys.CHANGE_PLOT)
        
        if diff_tif and diff_png and os.path.exists(diff_tif):
            result = self.controller.regenerate_2d_difference_map(diff_tif, diff_png, vmin=vmin, vmax=vmax)
            if result is not False:
                # Reload the image to show updated scale
                self.current_pixmap = QPixmap(diff_png)
                self._refresh_image_scaling()
                
                # Update spinbox if it was an auto-reset and we got a valid number back
                if vmin is None and vmax is None and isinstance(result, (int, float)):
                    self.spin_scale.blockSignals(True)
                    self.spin_scale.setValue(float(result))
                    self.spin_scale.blockSignals(False)

    def _update_2d_display(self, result_key: str, title: str, active_btn: QPushButton): # Changed key to result_key
        """Helper to switch the currently displayed 2D map.""" # Updated docstring
        # Update buttons state
        for btn in self.button_group:
            btn.setChecked(btn == active_btn)
            
        self.lbl_title.setText(title) # Changed to lbl_title
        
        if result_key == SimulationResultKeys.CHANGE_PLOT:
            self.scale_controls.show()
        else:
            self.scale_controls.hide()
            
        # Find path
        image_path = self.image_paths.get(result_key) # Changed path to image_path, key to result_key
        if image_path and os.path.exists(image_path):
            self.current_pixmap = QPixmap(image_path)
            self._refresh_image_scaling() # Kept original method name
        else:
            self.lbl_image.setText(f"{Carousel2DWidgetConsts.LBL_NOT_FOUND}{image_path}") # Used constant and image_path
            self.current_pixmap = None # Removed duplicate line
            
        self.current_2d_key = result_key # Changed key to result_key
        self.current_2d_title = title
        self.current_active_btn = active_btn
        
    def _refresh_image_scaling(self):
        """Scales the current pixmap to gracefully fit the Qt layout rect."""
        if hasattr(self, 'current_pixmap') and self.current_pixmap and hasattr(self, 'lbl_image'):
            # Ensure label has a valid size, if not (e.g. 0,0), use minimum size or skip
            target_size = self.lbl_image.size()
            if not target_size.isValid() or target_size.width() <= 10 or target_size.height() <= 10:
                 return # Too small to render usefully wait for resize
                 
            scaled = self.current_pixmap.scaled(
                target_size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_image.setPixmap(scaled)

    def show_input(self):
        self._update_2d_display(SimulationResultKeys.INITIAL_PLOT, Carousel2DWidgetConsts.BTN_INPUT, self.btn_input)

    def show_final(self):
        self._update_2d_display(SimulationResultKeys.FINAL_PLOT, Carousel2DWidgetConsts.BTN_FINAL, self.btn_final)

    def show_diff(self):
        self._update_2d_display(SimulationResultKeys.CHANGE_PLOT, Carousel2DWidgetConsts.BTN_DIFF, self.btn_diff)

    def resizeEvent(self, event):
        """Qt lifecycle hook intercept. Redraws the image when the user resizes the window."""
        super().resizeEvent(event)
        self._refresh_image_scaling()
