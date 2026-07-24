from PyQt6 import QtCore, QtWidgets

class Ui_AddComponents(object):
    def setupUi(self, AddComponents):
        AddComponents.setObjectName("AddComponents")
        AddComponents.resize(520, 480)
        AddComponents.setMinimumSize(480, 420)

        self.centralwidget = QtWidgets.QWidget(AddComponents)
        self.mainLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.mainLayout.setContentsMargins(12, 12, 12, 12)
        self.mainLayout.setSpacing(12)

        self.descriptionLabel = QtWidgets.QLabel("Description will appear here.")
        self.descriptionLabel.setWordWrap(True)
        self.descriptionLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.mainLayout.addWidget(self.descriptionLabel)

        self.dynamic_frame = QtWidgets.QGroupBox("Parameter Values")
        self.mainLayout.addWidget(self.dynamic_frame, 1)
        dynamicLayout = QtWidgets.QVBoxLayout(self.dynamic_frame)
        dynamicLayout.addStretch()

        self.statusLabel = QtWidgets.QLabel("")
        self.statusLabel.setWordWrap(True)
        self.statusLabel.setStyleSheet("color: #c62828; font-weight: 600;")
        self.mainLayout.addWidget(self.statusLabel)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        self.addBtn = QtWidgets.QPushButton("Add")
        self.cancelBtn = QtWidgets.QPushButton("Cancel")
        button_layout.addWidget(self.addBtn)
        button_layout.addWidget(self.cancelBtn)
        self.mainLayout.addLayout(button_layout)

        AddComponents.setLayout(self.mainLayout)
