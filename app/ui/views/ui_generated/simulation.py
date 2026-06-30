from PyQt6 import QtCore, QtWidgets
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
        
        self.locationGroup = QtWidgets.QGroupBox("Input Setup")
        left_layout.addWidget(self.locationGroup)

        location_form = QtWidgets.QFormLayout(self.locationGroup)
        location_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        location_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        # Input DEM: browsed from the user's own filesystem (no longer a DB list).
        self.inputDemLabel = QtWidgets.QLabel("Input DEM:")
        self.inputDemWidget = QtWidgets.QWidget()
        input_dem_layout = QtWidgets.QHBoxLayout(self.inputDemWidget)
        input_dem_layout.setContentsMargins(0, 0, 0, 0)
        self.inputDemLineEdit = QtWidgets.QLineEdit()
        self.inputDemLineEdit.setPlaceholderText("Select a GeoTIFF DEM (.tif)")
        self.inputDemLineEdit.setReadOnly(True)
        self.inputDemBtn = QtWidgets.QPushButton("Browse...")
        input_dem_layout.addWidget(self.inputDemLineEdit)
        input_dem_layout.addWidget(self.inputDemBtn)
        location_form.addRow(self.inputDemLabel, self.inputDemWidget)

        self.periodLabel = QtWidgets.QLabel("Total Duration:")
        self.simulationPeriodLineEdit = QtWidgets.QLineEdit()
        location_form.addRow(self.periodLabel, self.simulationPeriodLineEdit)

        self.timeStepLabel = QtWidgets.QLabel("Time Step:")
        self.timeStepLineEdit = QtWidgets.QLineEdit()
        location_form.addRow(self.timeStepLabel, self.timeStepLineEdit)

        self.trackFeatureCheckBox = QtWidgets.QCheckBox("Track Interested Landscape Feature")
        location_form.addRow(self.trackFeatureCheckBox)
        
        self.featureShapefileWidget = QtWidgets.QWidget()
        feature_shp_layout = QtWidgets.QHBoxLayout(self.featureShapefileWidget)
        feature_shp_layout.setContentsMargins(0, 0, 0, 0)
        self.featureShapefileLineEdit = QtWidgets.QLineEdit()
        self.featureShapefileLineEdit.setPlaceholderText("Upload shapefile (.shp)")
        self.featureShapefileLineEdit.setReadOnly(True)
        self.featureShapefileBtn = QtWidgets.QPushButton("Browse...")
        feature_shp_layout.addWidget(self.featureShapefileLineEdit)
        feature_shp_layout.addWidget(self.featureShapefileBtn)
        
        self.featureShapefileLabel = QtWidgets.QLabel("Feature Shapefile:")
        location_form.addRow(self.featureShapefileLabel, self.featureShapefileWidget)

        # First-effect detection threshold (metres of geomorphic change at which
        # the tracked feature is considered "first affected").
        self.firstEffectThresholdLineEdit = QtWidgets.QLineEdit()
        self.firstEffectThresholdLineEdit.setText("0.01")
        self.firstEffectThresholdLineEdit.setPlaceholderText("e.g. 0.01")
        self.firstEffectThresholdLineEdit.setToolTip(
            "Change (in metres) the tracked feature must reach for the app to report\n"
            "its 'first effect' time. Tectonic uplift is excluded from this measure."
        )
        self.firstEffectThresholdLabel = QtWidgets.QLabel("First-Effect Threshold (m):")
        location_form.addRow(self.firstEffectThresholdLabel, self.firstEffectThresholdLineEdit)

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
        # Stretch factor 1 so the map absorbs all extra vertical space; the
        # toggle and DEM info line then hug directly beneath it.
        self.webView = QWebEngineView()
        earth_layout.addWidget(self.webView, 1)

        self.showDemBoundaryToggle = QtWidgets.QCheckBox("Show DEM Boundary (Yellow)")
        earth_layout.addWidget(self.showDemBoundaryToggle, 0)

        self.demInfoLabel = QtWidgets.QLabel("")
        self.demInfoLabel.setWordWrap(True)
        self.demInfoLabel.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.demInfoLabel.setStyleSheet("color: #d8d8d8; font-size: 11px; padding: 1px 2px;")
        self.demInfoLabel.hide()
        earth_layout.addWidget(self.demInfoLabel, 0)
        
        self.splitter.addWidget(right_container)
        self.splitter.setSizes([300, 500])

        SimulationSetup.setCentralWidget(self.centralwidget)
