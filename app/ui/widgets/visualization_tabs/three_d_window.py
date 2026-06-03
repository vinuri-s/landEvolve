import os
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QLabel, QDoubleSpinBox, QPushButton
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtCore import QUrl
from app.core.constants import Carousel2DWidgetConsts

class ThreeDView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Scale Controls (similar to 2D view)
        self.scale_controls = QWidget()
        scale_layout = QHBoxLayout(self.scale_controls)
        
        self.lbl_scale = QLabel(Carousel2DWidgetConsts.LBL_SCALE_RANGE)
        scale_layout.addWidget(self.lbl_scale)
        
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(0.01, 10000.0)
        self.spin_scale.setDecimals(2)
        self.spin_scale.setValue(1.0)
        self.spin_scale.setSingleStep(0.1)
        scale_layout.addWidget(self.spin_scale)
        
        self.btn_apply_scale = QPushButton(Carousel2DWidgetConsts.BTN_APPLY_SCALE)
        self.btn_apply_scale.clicked.connect(self.apply_custom_scale)
        scale_layout.addWidget(self.btn_apply_scale)
        
        self.btn_reset_scale = QPushButton(Carousel2DWidgetConsts.BTN_RESET_SCALE)
        self.btn_reset_scale.clicked.connect(self.reset_scale)
        scale_layout.addWidget(self.btn_reset_scale)
        
        from PyQt6.QtWidgets import QSizePolicy
        self.scale_controls.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.scale_controls.hide()
        
        scale_layout.addStretch()
        self.layout.addWidget(self.scale_controls, stretch=0)
        
        # Web View
        self.web_view = QWebEngineView()
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        
        self.web_view.titleChanged.connect(self.on_title_changed)
        self.web_view.loadFinished.connect(self.on_load_finished)
        
        self.web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.layout.addWidget(self.web_view, stretch=1)
        
        # Keep track of last params to regenerate
        self.last_sim_params = None
        self.last_output_data = None
        self.last_controller = None

    def apply_custom_scale(self):
        val = self.spin_scale.value()
        self._regenerate_and_reload(vmin=-val, vmax=val)
        
    def reset_scale(self):
        self._regenerate_and_reload(vmin=None, vmax=None, force_diff_mode=True)
        
    def _regenerate_and_reload(self, vmin, vmax, force_diff_mode=False):
        if self.last_sim_params and self.last_output_data and self.last_controller:
            if vmin is not None or vmax is not None or force_diff_mode:
                self.scale_controls.show()
            else:
                self.scale_controls.hide()

            result = self.generate_and_load(self.last_sim_params, self.last_output_data, self.last_controller, vmin=vmin, vmax=vmax, force_diff_mode=force_diff_mode)

            # Update spinbox after auto-reset with the computed scale
            if vmin is None and vmax is None and isinstance(result, (int, float)):
                self.spin_scale.blockSignals(True)
                self.spin_scale.setValue(float(result))
                self.spin_scale.blockSignals(False)

    def on_title_changed(self, title):
        if title == "SHOW_SCALE_CONTROLS":
            self.scale_controls.show()
        elif title == "HIDE_SCALE_CONTROLS":
            self.scale_controls.hide()

    def on_load_finished(self, ok):
        if not ok:
            return
        js = """
        document.addEventListener('click', function(e) {
            var text = e.target.textContent;
            if (text === 'Difference Map') {
                window.document.title = 'SHOW_SCALE_CONTROLS';
            } else if (text === 'Final Elevation' || text === 'Input Elevation') {
                window.document.title = 'HIDE_SCALE_CONTROLS';
            }
        });
        """
        self.web_view.page().runJavaScript(js)
        
    def load_plot(self, html_path):
        from app.core.constants import ThreeDViewConsts
        if not html_path or not os.path.exists(html_path):
            print(ThreeDViewConsts.LOG_FILE_NOT_FOUND.format(html_path))
            return
            
        self.web_view.setUrl(QUrl.fromLocalFile(html_path))

    def generate_and_load(self, sim_params: dict, output_data: dict, controller, vmin=None, vmax=None, force_diff_mode=False):
        """Generates the 3D HTML comparison and loads it into the view."""
        self.last_sim_params = sim_params
        self.last_output_data = output_data
        self.last_controller = controller
        
        from app.core.constants import SimulationParamKeys, SimulationResultKeys, ThreeDViewConsts
        
        output_dir = output_data.get(SimulationResultKeys.OUTPUT_DIR)
        if not output_dir or not os.path.exists(output_dir):
            return

        # Locate Tiffs
        potential_tiffs = [f for f in os.listdir(output_dir) if f.endswith(ThreeDViewConsts.EXT_TIFF) and ThreeDViewConsts.STR_ELEVATION_SUBSTRING in f]
        # Fallback to any TIF if specific name lookup fails
        tiff_name = ThreeDViewConsts.FILE_FALLBACK_TIFF 
        if tiff_name not in potential_tiffs and potential_tiffs:
            tiff_name = potential_tiffs[0]
            
        final_tiff_path = os.path.join(output_dir, tiff_name)
        
        input_tiff = sim_params.get(SimulationParamKeys.INPUT_TIFF_PATH)
        if not os.path.isabs(input_tiff):
            input_tiff = os.path.abspath(input_tiff)
            
        html_output = os.path.join(output_dir, ThreeDViewConsts.FILE_HTML_COMPARISON)
        
        result = controller.generate_3d_model(input_tiff, final_tiff_path, html_output, vmin=vmin, vmax=vmax, force_diff_mode=force_diff_mode)

        if result is not False and result:
            self.load_plot(html_output)
        else:
            print(ThreeDViewConsts.LOG_GENERATION_FAILED)
            return False

        return result
