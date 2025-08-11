from PyQt6 import QtCore, QtGui, QtWidgets

class Ui_Home(object):
    def setupUi(self, Home):
        Home.setObjectName("Home")
        Home.setWindowTitle("LandEvolve")
        Home.setMinimumSize(800, 600)
        
        # Central widget with layout
        self.centralwidget = QtWidgets.QWidget(Home)
        self.centralLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.centralLayout.setContentsMargins(20, 20, 20, 20)
        self.centralLayout.setSpacing(20)
        
        # Title
        self.titleLabel = QtWidgets.QLabel("LandEvolve")
        self.titleLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        titleFont = QtGui.QFont()
        titleFont.setPointSize(32)
        titleFont.setBold(True)
        self.titleLabel.setFont(titleFont)
        self.centralLayout.addWidget(self.titleLabel)
        
        # Main content area
        self.contentFrame = QtWidgets.QFrame()
        self.contentLayout = QtWidgets.QHBoxLayout(self.contentFrame)
        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setSpacing(30)
        
        # Description
        self.descriptionLabel = QtWidgets.QLabel(
            "<h2>About LandEvolve</h2>"
            "<p>LandEvolve is a professional landscape evolution modeling tool that enables researchers "
            "to simulate, analyze, and visualize Earth surface processes. It supports scenario-based "
            "forecasting and long-term terrain change analysis.</p>"
        )
        self.descriptionLabel.setWordWrap(True)
        self.descriptionLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.contentLayout.addWidget(self.descriptionLabel, 1)
        
        # Image
        self.imageLabel = QtWidgets.QLabel()
        self.imageLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.contentLayout.addWidget(self.imageLabel, 1)
        
        self.centralLayout.addWidget(self.contentFrame, 1)
        
        # Start button
        self.buttonLayout = QtWidgets.QHBoxLayout()
        self.buttonLayout.addStretch()
        self.startSimulationBtn = QtWidgets.QPushButton("Start Simulation")
        self.startSimulationBtn.setMinimumSize(200, 50)
        self.buttonLayout.addWidget(self.startSimulationBtn)
        self.buttonLayout.addStretch()
        self.centralLayout.addLayout(self.buttonLayout)
        
        Home.setCentralWidget(self.centralwidget)
        
