from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings

from app.core.logging.manager import LogManager
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

    def load_map(self, latitude: float, longitude: float):
        """Renders the interactive MapLibre Map for the given coordinates."""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>MapLibre Map</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <link rel="stylesheet" href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css"/>
            <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"/>
            <style>
                #map {{ width: 100%; height: 100%; }}
                body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; }}
                #toggle-3d-btn {{
                    position: absolute;
                    top: 10px;
                    left: 10px;
                    z-index: 1000;
                    background: white;
                    border: 2px solid rgba(0,0,0,0.2);
                    border-radius: 4px;
                    padding: 8px 12px;
                    font-family: Arial, sans-serif;
                    font-weight: bold;
                    color: #333;
                    cursor: pointer;
                    box-shadow: 0 1px 5px rgba(0,0,0,0.4);
                }}
                #toggle-3d-btn:hover {{ background: #f4f4f4; }}
            </style>
        </head>
        <body>
            <div id="map"></div>
            <button id="toggle-3d-btn" onclick="toggle3D()"><i class="fas fa-cube"></i> 3D View</button>
            <script>
                var map;
                var shapefileCount = 0;
                var is3D = false;
                
                window.onload = function() {{
                    if (typeof maplibregl === 'undefined') {{
                        console.error('MapLibre failed to load!');
                        return;
                    }}
                    
                    map = new maplibregl.Map({{
                        container: 'map',
                        style: {{
                            'version': 8,
                            'sources': {{
                                'esri-imagery': {{
                                    'type': 'raster',
                                    'tiles': [
                                        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'
                                    ],
                                    'tileSize': 256,
                                    'attribution': 'Tiles &copy; Esri'
                                }}
                            }},
                            'layers': [{{
                                'id': 'satellite',
                                'type': 'raster',
                                'source': 'esri-imagery',
                                'minzoom': 0,
                                'maxzoom': 22
                            }}]
                        }},
                        center: [{longitude}, {latitude}],
                        zoom: 14,
                        pitch: 0,
                        dragPitch: true // re-enable manual right-click pitch
                    }});
                    
                    // Add zoom and rotation controls to the map.
                    map.addControl(new maplibregl.NavigationControl({{
                        visualizePitch: true // enable 3D compass behavior 
                    }}));
                    
                    // Add a marker
                    new maplibregl.Marker()
                        .setLngLat([{longitude}, {latitude}])
                        .addTo(map);
                }};

                function toggle3D() {{
                    if (!map) return;
                    is3D = !is3D;
                    var btn = document.getElementById('toggle-3d-btn');
                    
                    if (is3D) {{
                        map.easeTo({{pitch: 60, bearing: map.getBearing() || -30, duration: 1000}});
                        btn.innerHTML = '<i class="fas fa-map"></i> 2D View';
                    }} else {{
                        map.easeTo({{pitch: 0, bearing: 0, duration: 1000}});
                        btn.innerHTML = '<i class="fas fa-cube"></i> 3D View';
                    }}
                }}
                
                function setGeoJsonLayer(layerId, geoJsonData, color, fillColor, fillOpacity) {{
                    if (!map) return;
                    if (map.getSource(layerId)) {{
                        map.getSource(layerId).setData(geoJsonData);
                    }} else {{
                        map.addSource(layerId, {{ 'type': 'geojson', 'data': geoJsonData }});
                        map.addLayer({{
                            'id': layerId + '-fill',
                            'type': 'fill',
                            'source': layerId,
                            'paint': {{ 
                                'fill-color': fillColor || color, 
                                'fill-opacity': fillOpacity !== undefined ? fillOpacity : 0.1 
                            }}
                        }});
                        map.addLayer({{
                            'id': layerId + '-line',
                            'type': 'line',
                            'source': layerId,
                            'paint': {{ 
                                'line-color': color, 
                                'line-width': 4, 
                                'line-opacity': 1.0 
                            }}
                        }});
                    }}
                }}

                function removeGeoJsonLayer(layerId) {{
                    if (!map) return;
                    if (map.getLayer(layerId + '-line')) map.removeLayer(layerId + '-line');
                    if (map.getLayer(layerId + '-fill')) map.removeLayer(layerId + '-fill');
                    if (map.getSource(layerId)) map.removeSource(layerId);
                }}
            </script>
        </body>
        </html>
        """
        self.web_view.setHtml(html_content)
        
    def set_overlay(self, layer_id: str, geojson_str: str, line_color: str, fill_color: str = None, fill_opacity: float = 0.0):
        """Adds or updates a GeoJSON overlay on the map."""
        if fill_color is None:
            fill_color = line_color
        script = f"if (typeof setGeoJsonLayer !== 'undefined') setGeoJsonLayer('{layer_id}', {geojson_str}, '{line_color}', '{fill_color}', {fill_opacity});"
        self.web_view.page().runJavaScript(script)

    def remove_overlay(self, layer_id: str):
        """Removes a specific GeoJSON overlay from the map."""
        script = f"if (typeof removeGeoJsonLayer !== 'undefined') removeGeoJsonLayer('{layer_id}');"
        self.web_view.page().runJavaScript(script)

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
