import logging
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings

from app.logging.manager import LogManager
logger = LogManager.get_logger("ui")

class MapViewWidget:
    """
    Responsibility: Manages the QWebEngineView for rendering Leaflet maps.
    Handles browser security configurations, HTML string generation, and JS console logging.
    """
    
    def __init__(self, web_view: QWebEngineView):
        self.web_view = web_view
        self.configure_web_engine()
        
    def configure_web_engine(self):
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowGeolocationOnInsecureOrigins, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        
        self.web_view.page().javaScriptConsoleMessage = self.on_js_console_message
        
    def on_js_console_message(self, level, message, line, source):
        # We route Javascript errors straight into the Python Logging Architecture
        logger.debug(f"JS {level.name}: {message} (Line {line} in {source})")
        
    def clear(self):
        """Clears the map by setting an empty HTML document."""
        self.web_view.setHtml("")

    def load_leaflet_map(self, latitude: float, longitude: float):
        """Renders the interactive Leaflet Map for the given coordinates."""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Leaflet Map</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <style>
                #map {{ width: 100%; height: 100%; }}
                body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; }}
            </style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                window.onload = function() {{
                    if (typeof L === 'undefined') {{
                        console.error('Leaflet failed to load!');
                        return;
                    }}
                    const map = L.map('map').setView([{latitude}, {longitude}], 14);
                    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                        attribution: 'Tiles &copy; Esri',
                        maxZoom: 18
                    }}).addTo(map);
                    L.marker([{latitude}, {longitude}]).addTo(map);
                }};
            </script>
        </body>
        </html>
        """
        self.web_view.setHtml(html_content)

    def show_placeholder(self, message: str):
        """Renders a simple placeholder message when no valid coordinates are provided."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin:0;padding:0;background-color:#f0f0f0;">
            <div style="display:flex;justify-content:center;align-items:center;height:100%;">
                <p style="font-family:Arial;color:#666;">{message}</p>
            </div>
        </body>
        </html>
        """
        self.web_view.setHtml(html)
