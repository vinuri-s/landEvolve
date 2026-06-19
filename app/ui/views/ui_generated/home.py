from PyQt6 import QtCore, QtGui, QtWidgets

class Ui_Home(object):
    def setupUi(self, Home):
        Home.setObjectName("Home")
        Home.setWindowTitle("LandEvolve")
        Home.setMinimumSize(800, 600)
        
        self.centralwidget = QtWidgets.QWidget(Home)
        self.centralLayout = QtWidgets.QHBoxLayout(self.centralwidget)
        self.centralLayout.setContentsMargins(40, 40, 40, 40)
        self.centralLayout.setSpacing(40)
        
        self.leftContainer = QtWidgets.QWidget()
        self.leftLayout = QtWidgets.QVBoxLayout(self.leftContainer)
        self.leftLayout.setContentsMargins(0, 0, 0, 0)
        self.leftLayout.setSpacing(30)
        
        self.titleLabel = QtWidgets.QLabel("LandEvolve")
        self.titleLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        titleFont = QtGui.QFont()
        titleFont.setPointSize(36)
        titleFont.setBold(True)
        self.titleLabel.setFont(titleFont)
        self.leftLayout.addWidget(self.titleLabel)
        
        self.descriptionLabel = QtWidgets.QLabel(
            "<h2>About LandEvolve</h2>"
            "<p>LandEvolve is a desktop landscape evolution model built on the Landlab framework. "
            "It runs physics-based simulations on real elevation data (DEMs) to show how terrain reshapes "
            "over decades to millennia under river erosion, hillslope soil creep, climate, vegetation, "
            "rock type, and tectonic uplift.</p>"
            "<p>What you can do:</p>"
            "<ul>"
            "<li>Assemble a simulation from interchangeable process components</li>"
            "<li>Drive erosion with precipitation, vegetation, lithology, and uplift scenarios</li>"
            "<li>Explore results as 2D maps, an interactive 3D surface, and a scrubbable sediment timeline</li>"
            "<li>Analyze drainage, slope&ndash;area, hypsometry, soil thickness, and sediment budgets</li>"
            "<li>Track a chosen landscape feature and export GeoTIFFs for further research</li>"
            "</ul>"
            "<p>Click <b>Start Simulation</b> to configure and run your first model.</p>"
        )
        self.descriptionLabel.setWordWrap(True)
        self.descriptionLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.descriptionLabel.setStyleSheet("QLabel { font-size: 14px; }")
        self.leftLayout.addWidget(self.descriptionLabel, 1)
        
        self.buttonContainer = QtWidgets.QWidget()
        self.buttonLayout = QtWidgets.QHBoxLayout(self.buttonContainer)
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)
        
        self.startSimulationBtn = QtWidgets.QPushButton("Start Simulation")
        self.startSimulationBtn.setMinimumSize(220, 55)
        self.startSimulationBtn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                font-weight: bold;
                padding: 12px 24px;
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
        
        self.buttonLayout.addStretch()
        self.buttonLayout.addWidget(self.startSimulationBtn)
        self.buttonLayout.addStretch()
        
        self.leftLayout.addWidget(self.buttonContainer)
        self.centralLayout.addWidget(self.leftContainer, 1)
        
        self.rightContainer = QtWidgets.QWidget()
        self.rightLayout = QtWidgets.QVBoxLayout(self.rightContainer)
        self.rightLayout.setContentsMargins(0, 0, 0, 0)
        
        self.imageLabel = QtWidgets.QLabel()
        self.imageLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.imageLabel.setStyleSheet("""
            QLabel {
                border: none;
                background-color: transparent;
                min-height: 400px;
            }
        """)
        self.imageLabel.setScaledContents(True)
        self.rightLayout.addWidget(self.imageLabel)
        
        self.centralLayout.addWidget(self.rightContainer, 1)
        self.centralLayout.setStretchFactor(self.leftContainer, 1)
        self.centralLayout.setStretchFactor(self.rightContainer, 1)
        
        Home.setCentralWidget(self.centralwidget)
