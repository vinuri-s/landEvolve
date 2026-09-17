from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWebEngineWidgets import QWebEngineView

class Ui_SimulationSetup(object):

    @staticmethod
    def _info_icon(tooltip_text):
        """A tiny 'ⓘ' badge that shows `tooltip_text` on hover -- used next to
        form labels/sections so the user gets a quick explanation without
        cluttering the layout with permanent help text."""
        icon = QtWidgets.QLabel("ⓘ")
        icon.setToolTip(tooltip_text)
        icon.setCursor(QtCore.Qt.CursorShape.WhatsThisCursor)
        icon.setStyleSheet("color: #8a8a8a; font-size: 12px;")
        icon.setFixedWidth(14)
        return icon

    @classmethod
    def _label_with_info(cls, text, tooltip_text):
        """A form-row label followed by an info icon, wrapped in one widget so
        it can be passed straight to QFormLayout.addRow()."""
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(QtWidgets.QLabel(text))
        layout.addWidget(cls._info_icon(tooltip_text))
        return container

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
        self.inputDemLabel = self._label_with_info(
            "Input DEM:",
            "Browse for a GeoTIFF (.tif) elevation model of the area you want to "
            "simulate. This is the starting terrain the simulation will evolve."
        )
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

        self.periodLabel = self._label_with_info(
            "Total Duration:",
            "How long the simulation should run, in years. This is the total "
            "simulated time span, from start to finish."
        )
        self.simulationPeriodLineEdit = QtWidgets.QLineEdit()
        location_form.addRow(self.periodLabel, self.simulationPeriodLineEdit)

        self.timeStepLabel = self._label_with_info(
            "Time Step:",
            "The size of each simulation step, in years. Smaller steps are more "
            "accurate but take longer to compute."
        )
        self.timeStepLineEdit = QtWidgets.QLineEdit()
        location_form.addRow(self.timeStepLabel, self.timeStepLineEdit)

        track_feature_row = QtWidgets.QWidget()
        track_feature_layout = QtWidgets.QHBoxLayout(track_feature_row)
        track_feature_layout.setContentsMargins(0, 0, 0, 0)
        track_feature_layout.setSpacing(4)
        self.trackFeatureCheckBox = QtWidgets.QCheckBox("Track Interested Landscape Feature")
        track_feature_layout.addWidget(self.trackFeatureCheckBox)
        track_feature_layout.addWidget(self._info_icon(
            "Enable to monitor a specific feature (e.g. a river, ridge, or "
            "structure) and see when it's first affected by landscape change."
        ))
        track_feature_layout.addStretch()
        location_form.addRow(track_feature_row)
        
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

        # No native title -- the heading below sits inline with the info icon,
        # which a QGroupBox's built-in title bar can't host.
        self.componentsGroup = QtWidgets.QGroupBox()
        left_layout.addWidget(self.componentsGroup, 1)

        components_layout = QtWidgets.QVBoxLayout(self.componentsGroup)

        components_header_layout = QtWidgets.QHBoxLayout()
        components_header_layout.setSpacing(4)
        self.componentsTitleLabel = QtWidgets.QLabel("Select earth surface processes you want to simulate")
        self.componentsTitleLabel.setStyleSheet("font-weight: 600; font-size: 13px;")
        components_header_layout.addWidget(self.componentsTitleLabel)
        components_header_layout.addWidget(self._info_icon(
            "Add the geomorphic processes (e.g. erosion, diffusion) that should "
            "drive this simulation. At least one process is required."
        ))
        components_header_layout.addStretch()
        components_layout.addLayout(components_header_layout)

        # A small labelled "+" affordance above the table, right-aligned,
        # instead of a full-width button -- the standard "add a row" pattern,
        # with text so its purpose isn't left to guesswork.
        add_btn_layout = QtWidgets.QHBoxLayout()
        add_btn_layout.addStretch()
        self.addComponentBtn = QtWidgets.QPushButton("+ Add Process")
        self.addComponentBtn.setStyleSheet("QPushButton { font-weight: 600; padding: 4px 10px; }")
        add_btn_layout.addWidget(self.addComponentBtn)
        components_layout.addLayout(add_btn_layout)

        self.compTableWidget = QtWidgets.QTableWidget()
        self.compTableWidget.setColumnCount(3)
        self.compTableWidget.setHorizontalHeaderLabels(["Process", "Description", "Actions"])
        comp_header = self.compTableWidget.horizontalHeader()
        # Process needs room for its name plus the occasional "Required"
        # badge; Description absorbs whatever space is left.
        comp_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Interactive)
        comp_header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        comp_header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.compTableWidget.setColumnWidth(0, 215)
        self.compTableWidget.setColumnWidth(2, 130)
        components_layout.addWidget(self.compTableWidget, 1)

        # Output folder is its own step at the end of setup, separate from the
        # input parameters above -- it's about where results land, not about
        # configuring the simulation itself.
        self.outputGroup = QtWidgets.QGroupBox("Output")
        left_layout.addWidget(self.outputGroup)

        output_form = QtWidgets.QFormLayout(self.outputGroup)
        output_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        output_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        # Output folder: where this simulation's results are written. Pre-filled
        # with the app's default outputs location (or the last folder the user
        # picked), overridable via Browse.
        self.outputFolderLabel = self._label_with_info(
            "Output Folder:",
            "Choose where this simulation's results (maps, logs, data) will be "
            "saved. Defaults to the last folder you used."
        )
        self.outputFolderWidget = QtWidgets.QWidget()
        output_folder_layout = QtWidgets.QHBoxLayout(self.outputFolderWidget)
        output_folder_layout.setContentsMargins(0, 0, 0, 0)
        self.outputFolderLineEdit = QtWidgets.QLineEdit()
        self.outputFolderLineEdit.setPlaceholderText("Select a folder to store simulation outputs")
        self.outputFolderLineEdit.setReadOnly(True)
        self.outputFolderBtn = QtWidgets.QPushButton("Browse...")
        output_folder_layout.addWidget(self.outputFolderLineEdit)
        output_folder_layout.addWidget(self.outputFolderBtn)
        output_form.addRow(self.outputFolderLabel, self.outputFolderWidget)

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
