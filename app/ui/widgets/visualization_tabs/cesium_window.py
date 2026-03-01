import os
from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QMessageBox
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtCore import QUrl

class ThreeDView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Standard settings
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        
    def load_plot(self, html_path):
        from app.ui.constants import ThreeDViewConsts
        if not html_path or not os.path.exists(html_path):
            print(ThreeDViewConsts.LOG_FILE_NOT_FOUND.format(html_path))
            return
            
        self.setUrl(QUrl.fromLocalFile(html_path))

    def generate_and_load(self, sim_params: dict, output_data: dict, controller):
        """Generates the 3D HTML comparison and loads it into the view."""
        from app.ui.constants import SimulationParamKeys, SimulationResultKeys, ThreeDViewConsts
        
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
        
        success = controller.generate_3d_model(input_tiff, final_tiff_path, html_output)
        
        if success:
            self.load_plot(html_output)
        else:
            print(ThreeDViewConsts.LOG_GENERATION_FAILED)
