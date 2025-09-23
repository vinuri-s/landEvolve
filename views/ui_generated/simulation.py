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

        # --- Left Panel (Location Setup + Simulation Components + Button) ---
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
        
        # Description - with more vertical space
        self.descriptionLabel = QtWidgets.QLabel("Description:")
        self.descriptionTextEdit = QtWidgets.QTextEdit()
        self.descriptionTextEdit.setReadOnly(True)
        self.descriptionTextEdit.setMinimumHeight(80)   # Increased minimum height
        self.descriptionTextEdit.setMaximumHeight(120)  # Increased maximum height
        location_form.addRow(self.descriptionLabel, self.descriptionTextEdit)
        
        # Components group
        self.componentsGroup = QtWidgets.QGroupBox("Simulation Components")
        left_layout.addWidget(self.componentsGroup, 1)  # Takes available space
        
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
        
        # Run Simulation button - in left panel
        self.viewSimulationBtn = QtWidgets.QPushButton("Run Simulation")
        self.viewSimulationBtn.setMinimumHeight(40)
        left_layout.addWidget(self.viewSimulationBtn)
        
        # Add to splitter
        self.splitter.addWidget(left_container)

        # --- Right Panel (Location Preview) ---
        right_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Google Earth view - takes the whole right side
        self.earthGroup = QtWidgets.QGroupBox("Location Preview")
        right_layout.addWidget(self.earthGroup)
        
        earth_layout = QtWidgets.QVBoxLayout(self.earthGroup)
        self.webView = QWebEngineView()
        earth_layout.addWidget(self.webView)
        
        # Add to splitter
        self.splitter.addWidget(right_container)

        # Set initial splitter sizes - give more space to the right side (preview)
        self.splitter.setSizes([300, 500])  # Left: 300, Right: 500

        # Final setup
        SimulationSetup.setCentralWidget(self.centralwidget)
        
       