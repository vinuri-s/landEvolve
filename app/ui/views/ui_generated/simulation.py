from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWebEngineWidgets import QWebEngineView

class Ui_SimulationSetup(object):
    def setupUi(self, SimulationSetup):
        SimulationSetup.setObjectName("SimulationSetup")
        SimulationSetup.setWindowTitle("Simulation Setup")
        SimulationSetup.setMinimumSize(800, 600)
        
        self.centralwidget = QtWidgets.QWidget(SimulationSetup)
        self.mainLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.mainLayout.setContentsMargins(12, 12, 12, 12)
        self.mainLayout.setSpacing(12)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.mainLayout.addWidget(self.splitter, 1)

        left_container = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        
        self.locationGroup = QtWidgets.QGroupBox("Location Setup")
        left_layout.addWidget(self.locationGroup)
        
        location_form = QtWidgets.QFormLayout(self.locationGroup)
        location_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        location_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        
        self.locationLabel = QtWidgets.QLabel("Location:")
        self.locationComboBox = QtWidgets.QComboBox()
        location_form.addRow(self.locationLabel, self.locationComboBox)
        
        self.resolutionLabel = QtWidgets.QLabel("Resolution:")
        self.resolutionComboBox = QtWidgets.QComboBox()
        location_form.addRow(self.resolutionLabel, self.resolutionComboBox)
        
        self.periodLabel = QtWidgets.QLabel("Simulation Period:")
        self.simulationPeriodLineEdit = QtWidgets.QLineEdit()
        location_form.addRow(self.periodLabel, self.simulationPeriodLineEdit)
        
        self.timeStepLabel = QtWidgets.QLabel("Time Step:")
        self.timeStepLineEdit = QtWidgets.QLineEdit()
        location_form.addRow(self.timeStepLabel, self.timeStepLineEdit)
        
        self.descriptionLabel = QtWidgets.QLabel("Description:")
        self.descriptionTextEdit = QtWidgets.QTextEdit()
        self.descriptionTextEdit.setReadOnly(True)
        self.descriptionTextEdit.setMinimumHeight(80)
        self.descriptionTextEdit.setMaximumHeight(120)
        location_form.addRow(self.descriptionLabel, self.descriptionTextEdit)
        
        self.componentsGroup = QtWidgets.QGroupBox("Simulation Components")
        left_layout.addWidget(self.componentsGroup, 1)
        
        components_layout = QtWidgets.QVBoxLayout(self.componentsGroup)
        
        self.compTableWidget = QtWidgets.QTableWidget()
        self.compTableWidget.setColumnCount(3)
        self.compTableWidget.setHorizontalHeaderLabels(["Component", "Description", "Actions"])
        self.compTableWidget.horizontalHeader().setStretchLastSection(True)
        components_layout.addWidget(self.compTableWidget, 1)
        
        self.addComponentBtn = QtWidgets.QPushButton("Add Component")
        components_layout.addWidget(self.addComponentBtn)
        
        self.viewSimulationBtn = QtWidgets.QPushButton("Run Simulation")
        self.viewSimulationBtn.setMinimumHeight(40)
        self.viewSimulationBtn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                background-color: #006400;  /* Dark green */
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #008000;  /* Slightly lighter dark green on hover */
            }
            QPushButton:pressed {
                background-color: #004d00;  /* Even darker when pressed */
            }
        """)
        left_layout.addWidget(self.viewSimulationBtn)
        
        self.splitter.addWidget(left_container)

        right_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.earthGroup = QtWidgets.QGroupBox("Location Preview")
        right_layout.addWidget(self.earthGroup)
        
        earth_layout = QtWidgets.QVBoxLayout(self.earthGroup)
        self.webView = QWebEngineView()
        earth_layout.addWidget(self.webView)
        
        self.splitter.addWidget(right_container)
        self.splitter.setSizes([300, 500])

        SimulationSetup.setCentralWidget(self.centralwidget)
