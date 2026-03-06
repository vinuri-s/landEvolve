from app.ui.widgets.file_widget import FileWidget
from app.services.shapefile_service import ShapefileService
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import pyqtSignal

class ShapefileLoader(FileWidget):
    """
    A specialized widget component for loading shapefiles.
    It encapsulates the configuration of the file dialog and handles the
    service logic, adhering to the Single Responsibility Principle.
    """
    geojson_loaded = pyqtSignal(str) # Emits each processed GeoJSON string
    
    def __init__(self, parent=None):
        super().__init__(
            button_text="Load Shapefile", # Not strictly used if launched headless
            dialog_title="Select Shapefile(s)",
            file_filter="Shapefiles (*.shp);;All Files (*)",
            multiple=True,
            parent=parent
        )
        # Connect the base class signal to our internal processing logic
        self.files_selected.connect(self._process_files)
        
    def _process_files(self, file_names):
        if file_names:
            try:
                # Delegate business logic (reading, CRS transformation, GeoJSON conversion) to the Service layer
                geojson_results = ShapefileService.load_shapefiles_as_geojson(file_names)
                
                for file_name, geojson_str in geojson_results:
                    self.geojson_loaded.emit(geojson_str)
                    
            except Exception as e:
                # Display error relative to parent
                parent_widget = self.parentWidget() if hasattr(self, 'parentWidget') else self
                QMessageBox.critical(parent_widget, "Error", f"Failed to load shapefile(s):\n{str(e)}")

    def open_dialog(self):
        """Programmatically triggers the file selection dialog."""
        self._open_file_dialog()
