# landEvolve

## Steps to run qt app windows:

python -m venv qt_env  
 
qt_env\Scripts\activate

pip install sqlalchemy

pip install -r requirements.txt

pip install PyQt6 PyQt6-WebEngine

optional:
pip uninstall PyQt6 PyQt6-Qt6 PyQt6-sip pyqt6-tools pyqt6-plugins -y
 
pip install PyQt6==6.6.1 PyQt6-Qt6==6.6.1 PyQt6-sip==13.6.0

##  Steps to run qt app mac:

python -m venv qt_env  
 
source qt_env/bin/activate

pip install sqlalchemy

pip install -r requirements.txt

pip install PyQt6 PyQt6-WebEngine
