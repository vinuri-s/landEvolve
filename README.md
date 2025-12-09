# LandEvolve

LandEvolve is a desktop application for simulating and visualizing landscape evolution. It is powered by the **Landlab Landscape Evolution Model** to provide accurate geological modeling, combining a robust scientific engine with a modern, user-friendly interface.

## 🏗️ Project Structure

The project follows a strict layered architecture to ensure separation of concerns and maintainability:

*   **`app/ui`**: Handles the user interface (Views & Controllers). Built with PyQt6.
*   **`app/services`**: Business logic layer that orchestrates operations between the UI, Data, and Engine layers.
*   **`app/engine`**: The core simulation engine powered by `landlab`. This layer is pure logic and isolated from the UI and Database.
*   **`app/data`**: Manages data persistence using SQLAlchemy. Handles database models and repositories.
*   **`app/core`**: Contains core configurations, constants, and shared utilities.

## 🛠️ Technologies

*   **Language**: Python 3.9+
*   **GUI Framework**: PyQt6 (with QtWebEngine)
*   **Simulation**: Landlab, NumPy
*   **Visualization**: Matplotlib
*   **Database**: SQLAlchemy (SQLite)
*   **Geospatial**: Rasterio

## 🚀 Getting Started

### Prerequisites
*   Python 3.9 or higher

### Installation & Running

#### macOS / Linux
```bash
# 1. Create a virtual environment
python -m venv qt_env

# 2. Activate the environment
source qt_env/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python main.py
```

#### Windows
```powershell
# 1. Create a virtual environment
python -m venv qt_env

# 2. Activate the environment
qt_env\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python main.py
```
