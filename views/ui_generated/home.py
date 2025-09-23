from PyQt6 import QtCore, QtGui, QtWidgets

class Ui_Home(object):
    def setupUi(self, Home):
        Home.setObjectName("Home")
        Home.setWindowTitle("LandEvolve")
        Home.setMinimumSize(800, 600)
        
        # Central widget with layout
        self.centralwidget = QtWidgets.QWidget(Home)
        self.centralLayout = QtWidgets.QHBoxLayout(self.centralwidget)  # Changed to HBox for side-by-side layout
        self.centralLayout.setContentsMargins(40, 40, 40, 40)  # Increased margins for better spacing
        self.centralLayout.setSpacing(40)
        
        # Left side: Text content with button
        self.leftContainer = QtWidgets.QWidget()
        self.leftLayout = QtWidgets.QVBoxLayout(self.leftContainer)
        self.leftLayout.setContentsMargins(0, 0, 0, 0)
        self.leftLayout.setSpacing(30)
        
        # Title
        self.titleLabel = QtWidgets.QLabel("LandEvolve")
        self.titleLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        titleFont = QtGui.QFont()
        titleFont.setPointSize(36)  # Slightly larger
        titleFont.setBold(True)
        self.titleLabel.setFont(titleFont)
        self.leftLayout.addWidget(self.titleLabel)
        
        # Description - expanded with more content
        self.descriptionLabel = QtWidgets.QLabel(
            "<h2>About LandEvolve</h2>"
            "<p>LandEvolve is a research-oriented landscape evolution modelling tool developed on top of the Python-based Landlab library. "
            "It allows researchers to simulate, analyze, and visualize Earth surface processes, with a focus on scenario-based forecasting "
            "and long-term terrain change analysis.</p>"
            "<p>Key features include:</p>"
            "<ul>"
            "<li>Advanced terrain modeling and analysis</li>"
            "<li>Multiple simulation components and scenarios</li>"
            "<li>Interactive visualization tools</li>"
            "<li>Export capabilities for research data</li>"
            "</ul>"
            "<p>Start your landscape evolution journey by creating a new simulation or exploring existing models.</p>"
        )
        self.descriptionLabel.setWordWrap(True)
        self.descriptionLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.descriptionLabel.setStyleSheet("QLabel { font-size: 14px; }")
        self.leftLayout.addWidget(self.descriptionLabel, 1)  # Allow description to expand
        
        # Button container to center the button
        self.buttonContainer = QtWidgets.QWidget()
        self.buttonLayout = QtWidgets.QHBoxLayout(self.buttonContainer)
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)
        
        # Start button - centered under the description
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
        
        # Add stretches on both sides to center the button
        self.buttonLayout.addStretch()
        self.buttonLayout.addWidget(self.startSimulationBtn)
        self.buttonLayout.addStretch()
        
        self.leftLayout.addWidget(self.buttonContainer)
        
        # Add left container to main layout
        self.centralLayout.addWidget(self.leftContainer, 1)  # Takes 50% of space
        
        # Right side: Image
        self.rightContainer = QtWidgets.QWidget()
        self.rightLayout = QtWidgets.QVBoxLayout(self.rightContainer)
        self.rightLayout.setContentsMargins(0, 0, 0, 0)
        
        # Image label with proper scaling
        self.imageLabel = QtWidgets.QLabel()
        self.imageLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.imageLabel.setStyleSheet("""
            QLabel {
                border: none;
                background-color: transparent;
                min-height: 400px;
            }
        """)
        self.imageLabel.setScaledContents(True)  # Allow image to scale with container
        self.rightLayout.addWidget(self.imageLabel)
        
        # Add right container to main layout
        self.centralLayout.addWidget(self.rightContainer, 1)  # Takes 50% of space
        
        # Set stretch factors to balance the layout
        self.centralLayout.setStretchFactor(self.leftContainer, 1)
        self.centralLayout.setStretchFactor(self.rightContainer, 1)
        
        Home.setCentralWidget(self.centralwidget)