from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QFileDialog
from PyQt6.QtCore import pyqtSignal

class FileWidget(QWidget):
    """
    A customizable and reusable widget for handling file dialogs.
    Emits a `files_selected` signal containing a list of chosen file paths.
    """
    files_selected = pyqtSignal(list)

    def __init__(self, button_text="Browse...", dialog_title="Select File", file_filter="All Files (*)", multiple=False, parent=None):
        super().__init__(parent)
        self.dialog_title = dialog_title
        self.file_filter = file_filter
        self.multiple = multiple

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.button = QPushButton(button_text)
        self.button.clicked.connect(self._open_file_dialog)
        self.layout.addWidget(self.button)

    def _open_file_dialog(self):
        if self.multiple:
            file_names, _ = QFileDialog.getOpenFileNames(
                self,
                self.dialog_title,
                "",
                self.file_filter
            )
            if file_names:
                self.files_selected.emit(file_names)
        else:
            file_name, _ = QFileDialog.getOpenFileName(
                self,
                self.dialog_title,
                "",
                self.file_filter
            )
            if file_name:
                self.files_selected.emit([file_name])
