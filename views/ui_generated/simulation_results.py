from PyQt6 import QtCore, QtGui, QtWidgets

class Ui_SimulationResults(object):
    def setupUi(self, SimulationResults):
        SimulationResults.setObjectName("SimulationResults")
        SimulationResults.setWindowTitle("Simulation Results")
        SimulationResults.resize(1200, 800)
        
        self.centralwidget = QtWidgets.QWidget(SimulationResults)
        self.gridLayout = QtWidgets.QGridLayout(self.centralwidget)
        
        # Create image labels
        self.inputImageLabel = QtWidgets.QLabel("Input DEM")
        self.outputImageLabel = QtWidgets.QLabel("Output Topography")
        self.changeImageLabel = QtWidgets.QLabel("Topographic Change")
        self.soilImageLabel = QtWidgets.QLabel("Soil Transport")
        
        # Create image displays
        self.inputImageView = QtWidgets.QLabel()
        self.inputImageView.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.inputImageView.setMinimumSize(400, 300)
        
        self.outputImageView = QtWidgets.QLabel()
        self.outputImageView.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.outputImageView.setMinimumSize(400, 300)
        
        self.changeImageView = QtWidgets.QLabel()
        self.changeImageView.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.changeImageView.setMinimumSize(400, 300)
        
        self.soilImageView = QtWidgets.QLabel()
        self.soilImageView.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.soilImageView.setMinimumSize(400, 300)
        
        # Add to grid layout
        self.gridLayout.addWidget(self.inputImageLabel, 0, 0)
        self.gridLayout.addWidget(self.inputImageView, 1, 0)
        self.gridLayout.addWidget(self.outputImageLabel, 0, 1)
        self.gridLayout.addWidget(self.outputImageView, 1, 1)
        self.gridLayout.addWidget(self.changeImageLabel, 2, 0)
        self.gridLayout.addWidget(self.changeImageView, 3, 0)
        self.gridLayout.addWidget(self.soilImageLabel, 2, 1)
        self.gridLayout.addWidget(self.soilImageView, 3, 1)
        
        SimulationResults.setCentralWidget(self.centralwidget)