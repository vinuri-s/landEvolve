import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
from app.ui.constants import SimulationResultKeys, Carousel2DWidgetConsts

class Carousel2DWidget(QWidget):
    """
    Responsibility: Manages the '2D Visualization' tab UI.
    Handles loading images from disk, scaling them smoothly to fit the window,
    and managing the toggle state between Input/Final/Difference maps.
    """
    def __init__(self, image_paths: dict, parent=None):
        super().__init__(parent)
        self.image_paths = image_paths
        
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

    def _update_2d_display(self, result_key: str, title: str, active_btn: QPushButton): # Changed key to result_key
        """Helper to switch the currently displayed 2D map.""" # Updated docstring
        # Update buttons state
        for btn in self.button_group:
            btn.setChecked(btn == active_btn)
            
        self.lbl_title.setText(title) # Changed to lbl_title
        
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
