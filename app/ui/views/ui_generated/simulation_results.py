from PyQt6 import QtCore, QtWidgets

class Ui_SimulationResults(object):
    def setupUi(self, SimulationResults):
        SimulationResults.setObjectName("SimulationResults")
        SimulationResults.setWindowTitle("Simulation Results")
        SimulationResults.resize(1400, 900)
        
        self.centralwidget = QtWidgets.QWidget(SimulationResults)
        self.verticalLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.verticalLayout.setContentsMargins(20, 20, 20, 20)
        self.verticalLayout.setSpacing(15)
        
        self.topBarLayout = QtWidgets.QHBoxLayout()
        
        self.statsIconButton = QtWidgets.QPushButton()
        self.statsIconButton.setFixedSize(32, 32)
        self.statsIconButton.setVisible(False)
        self.statsIconButton.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-radius: 3px;
            }
        """)
        
        self.statsIconButton.setText("📊")
        self.statsIconButton.setToolTip("View Simulation Statistics")
        
        self.topBarLayout.addWidget(self.statsIconButton)
        self.topBarLayout.addStretch()
        
        self.verticalLayout.addLayout(self.topBarLayout)
        
        self.statusGroup = QtWidgets.QGroupBox("Simulation Status")
        self.statusLayout = QtWidgets.QVBoxLayout(self.statusGroup)
        
        self.statusLabel = QtWidgets.QLabel("Initializing simulation...")
        self.statusLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.statusLabel.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px;")
        self.statusLayout.addWidget(self.statusLabel)
        
        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressBar.setMinimumHeight(25)
        self.statusLayout.addWidget(self.progressBar)
        
        self.liveStatsLayout = QtWidgets.QHBoxLayout()
        
        self.timeLabel = QtWidgets.QLabel("Time: 00:00:00")
        self.timeLabel.setStyleSheet("font-size: 12px; color: #666;")
        
        self.ramLabel = QtWidgets.QLabel("RAM: 0 MB")
        self.ramLabel.setStyleSheet("font-size: 12px; color: #666;")
        
        self.liveStatsLayout.addWidget(self.timeLabel)
        self.liveStatsLayout.addStretch()
        self.liveStatsLayout.addWidget(self.ramLabel)
        
        self.statusLayout.addLayout(self.liveStatsLayout)
        
        self.verticalLayout.addWidget(self.statusGroup)
        
        self.imagesGroup = QtWidgets.QGroupBox("Simulation Results")
        self.imagesGroup.setVisible(False)
        self.imagesLayout = QtWidgets.QVBoxLayout(self.imagesGroup)
        
        self.scrollArea = QtWidgets.QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setMinimumHeight(600)
        
        self.imagesContainer = QtWidgets.QWidget()
        self.gridLayout = QtWidgets.QGridLayout(self.imagesContainer)
        self.gridLayout.setContentsMargins(10, 10, 10, 10)
        self.gridLayout.setSpacing(15)
        
        self.inputImageLabel = QtWidgets.QLabel("Input DEM")
        self.inputImageLabel.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.outputImageLabel = QtWidgets.QLabel("Output Topography")
        self.outputImageLabel.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.changeImageLabel = QtWidgets.QLabel("Topographic Change")
        self.changeImageLabel.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.soilImageLabel = QtWidgets.QLabel("Soil Transport")
        self.soilImageLabel.setStyleSheet("font-size: 14px; font-weight: bold;")
        
        self.inputImageView = QtWidgets.QLabel()
        self.inputImageView.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.inputImageView.setMinimumSize(500, 400)
        self.inputImageView.setStyleSheet("QLabel { border: 2px solid #ccc; background-color: #f8f8f8; border-radius: 5px; }")
        
        self.outputImageView = QtWidgets.QLabel()
        self.outputImageView.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.outputImageView.setMinimumSize(500, 400)
        self.outputImageView.setStyleSheet("QLabel { border: 2px solid #ccc; background-color: #f8f8f8; border-radius: 5px; }")
        
        self.changeImageView = QtWidgets.QLabel()
        self.changeImageView.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.changeImageView.setMinimumSize(500, 400)
        self.changeImageView.setStyleSheet("QLabel { border: 2px solid #ccc; background-color: #f8f8f8; border-radius: 5px; }")
        
        self.soilImageView = QtWidgets.QLabel()
        self.soilImageView.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.soilImageView.setMinimumSize(500, 400)
        self.soilImageView.setStyleSheet("QLabel { border: 2px solid #ccc; background-color: #f8f8f8; border-radius: 5px; }")
        
        self.gridLayout.addWidget(self.inputImageLabel, 0, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
        self.gridLayout.addWidget(self.inputImageView, 1, 0)
        self.gridLayout.addWidget(self.outputImageLabel, 0, 1, QtCore.Qt.AlignmentFlag.AlignCenter)
        self.gridLayout.addWidget(self.outputImageView, 1, 1)
        self.gridLayout.addWidget(self.changeImageLabel, 2, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
        self.gridLayout.addWidget(self.changeImageView, 3, 0)
        self.gridLayout.addWidget(self.soilImageLabel, 2, 1, QtCore.Qt.AlignmentFlag.AlignCenter)
        self.gridLayout.addWidget(self.soilImageView, 3, 1)
        
        self.gridLayout.setRowStretch(1, 1)
        self.gridLayout.setRowStretch(3, 1)
        self.gridLayout.setColumnStretch(0, 1)
        self.gridLayout.setColumnStretch(1, 1)
        
        self.scrollArea.setWidget(self.imagesContainer)
        self.imagesLayout.addWidget(self.scrollArea)
        
        self.verticalLayout.addWidget(self.imagesGroup, 1)
        
        self.buttonLayout = QtWidgets.QHBoxLayout()
        self.view3DButton = QtWidgets.QPushButton("View in 3D (ArcGIS)")
        self.view3DButton.setMinimumHeight(45)
        self.view3DButton.setMinimumWidth(200)
        self.view3DButton.setVisible(False)
        self.view3DButton.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                font-weight: bold;
                padding: 12px 24px;
                background-color: #2E8B57;
                color: white;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #3CB371;
            }
            QPushButton:pressed {
                background-color: #228B22;
            }
        """)
        self.buttonLayout.addStretch()
        self.buttonLayout.addWidget(self.view3DButton)
        self.buttonLayout.addStretch()
        self.verticalLayout.addLayout(self.buttonLayout)
        
        SimulationResults.setCentralWidget(self.centralwidget)
