from PyQt6 import QtCore, QtWidgets

class Ui_AddComponents(object):
    def setupUi(self, AddComponents):
        AddComponents.setObjectName("AddComponents")
        AddComponents.resize(600, 590)
        AddComponents.setMinimumSize(500, 480)
        
        self.centralwidget = QtWidgets.QWidget(AddComponents)
        self.mainLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.mainLayout.setContentsMargins(12, 12, 12, 12)
        self.mainLayout.setSpacing(12)

        # Persistent, visible record of what's been added this session --
        # placed first/at the top so it's the first thing seen, and stays on
        # screen (not a status line that gets overwritten and can be missed)
        # as the list grows with each Add click.
        self.addedGroup = QtWidgets.QGroupBox("Added This Session (0)")
        added_layout = QtWidgets.QVBoxLayout(self.addedGroup)
        self.addedListWidget = QtWidgets.QListWidget()
        self.addedListWidget.setMaximumHeight(90)
        self.addedListWidget.setStyleSheet(
            "QListWidget { color: #2e7d32; font-weight: bold; border: none; }"
        )
        added_layout.addWidget(self.addedListWidget)
        self.mainLayout.addWidget(self.addedGroup)

        selection_layout = QtWidgets.QHBoxLayout()
        self.componentLabel = QtWidgets.QLabel("Component:")
        self.selectComponentComboBox = QtWidgets.QComboBox()
        selection_layout.addWidget(self.componentLabel)
        selection_layout.addWidget(self.selectComponentComboBox, 1)
        self.mainLayout.addLayout(selection_layout)
        
        self.descriptionLabel = QtWidgets.QLabel("Description will appear here.")
        self.descriptionLabel.setWordWrap(True)
        self.descriptionLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.mainLayout.addWidget(self.descriptionLabel)
        
        self.dynamic_frame = QtWidgets.QGroupBox("Parameter Values")
        self.dynamic_frame.setMinimumHeight(370)
        self.mainLayout.addWidget(self.dynamic_frame)
        dynamicLayout = QtWidgets.QVBoxLayout(self.dynamic_frame)
        dynamicLayout.addStretch()

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        self.addBtn = QtWidgets.QPushButton("Add Component")
        self.cancelBtn = QtWidgets.QPushButton("Done")
        button_layout.addWidget(self.addBtn)
        button_layout.addWidget(self.cancelBtn)
        self.mainLayout.addLayout(button_layout)

        AddComponents.setLayout(self.mainLayout)
