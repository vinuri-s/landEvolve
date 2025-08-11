from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWebEngineWidgets import QWebEngineView

class Ui_SimulationSetup(object):
    def setupUi(self, SimulationSetup):
        SimulationSetup.setObjectName("SimulationSetup")
        SimulationSetup.setWindowTitle("Simulation Setup")
        SimulationSetup.setMinimumSize(800, 600)  # More flexible minimum size
        
        # Main layout with margins
        self.centralwidget = QtWidgets.QWidget(SimulationSetup)
        self.mainLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.mainLayout.setContentsMargins(12, 12, 12, 12)
        self.mainLayout.setSpacing(12)

        # Splitter for flexible resizing
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.mainLayout.addWidget(self.splitter, 1)  # Takes available space

        # --- Left Panel (Location Setup) ---
        left_container = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        
        # Location group
        self.locationGroup = QtWidgets.QGroupBox("Location Setup")
        left_layout.addWidget(self.locationGroup)
        
        location_form = QtWidgets.QFormLayout(self.locationGroup)
        location_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        location_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        
        # Location selection
        self.locationLabel = QtWidgets.QLabel("Location:")
        self.locationComboBox = QtWidgets.QComboBox()
        location_form.addRow(self.locationLabel, self.locationComboBox)
        
        # Resolution selection
        self.resolutionLabel = QtWidgets.QLabel("Resolution:")
        self.resolutionComboBox = QtWidgets.QComboBox()
        location_form.addRow(self.resolutionLabel, self.resolutionComboBox)
        
        # Simulation period
        self.periodLabel = QtWidgets.QLabel("Simulation Period:")
        self.simulationPeriodLineEdit = QtWidgets.QLineEdit()
        location_form.addRow(self.periodLabel, self.simulationPeriodLineEdit)
        
        # Time step
        self.timeStepLabel = QtWidgets.QLabel("Time Step:")
        self.timeStepLineEdit = QtWidgets.QLineEdit()
        location_form.addRow(self.timeStepLabel, self.timeStepLineEdit)
        
        # Description
        self.descriptionLabel = QtWidgets.QLabel("Description:")
        self.descriptionTextEdit = QtWidgets.QTextEdit()
        self.descriptionTextEdit.setReadOnly(True)
        self.descriptionTextEdit.setMaximumHeight(30)   # Limit height to 80 pixels
        location_form.addRow(self.descriptionLabel, self.descriptionTextEdit)
        
        # Google Earth view
        self.earthGroup = QtWidgets.QGroupBox("Location Preview")
        left_layout.addWidget(self.earthGroup, 1)  # Takes available space
        
        earth_layout = QtWidgets.QVBoxLayout(self.earthGroup)
        self.webView = QWebEngineView()
        earth_layout.addWidget(self.webView)
        
        # Add to splitter
        self.splitter.addWidget(left_container)

        # --- Right Panel (Component Selection) ---
        right_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        
        # Components group
        self.componentsGroup = QtWidgets.QGroupBox("Simulation Components")
        right_layout.addWidget(self.componentsGroup, 1)  # Takes available space
        
        components_layout = QtWidgets.QVBoxLayout(self.componentsGroup)
        
        # Table for components
        self.compTableWidget = QtWidgets.QTableWidget()
        self.compTableWidget.setColumnCount(3)
        self.compTableWidget.setHorizontalHeaderLabels(["Component", "Description", "Actions"])
        self.compTableWidget.horizontalHeader().setStretchLastSection(True)
        components_layout.addWidget(self.compTableWidget, 1)
        
        # Add component button
        self.addComponentBtn = QtWidgets.QPushButton("Add Component")
        components_layout.addWidget(self.addComponentBtn)
        
        # Add to splitter
        self.splitter.addWidget(right_container)

        # Set initial splitter sizes
        self.splitter.setSizes([400, 400])
        
        # --- Bottom Button ---
        self.viewSimulationBtn = QtWidgets.QPushButton("Run Simulation")
        self.viewSimulationBtn.setMinimumHeight(40)
        self.mainLayout.addWidget(self.viewSimulationBtn)

        # Final setup
        SimulationSetup.setCentralWidget(self.centralwidget)
        
        # Remove hard-coded styling - will use QSS files instead
