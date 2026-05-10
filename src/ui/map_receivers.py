from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt5.QtWebEngineWidgets import QWebEnginePage

class CoordinateReceiver(QObject):
    # Emitted when JavaScript sends coordinates: list of [lat, lng] or list of lists
    coordinatesReceived = pyqtSignal(object)

    @pyqtSlot('QVariant')
    def receiveCoordinates(self, coords):
        # coords is expected as a JS array of lat/lng pairs
        self.coordinatesReceived.emit(coords)

class PlaceReceiver(QObject):
    """Receiver for Google Places Autocomplete selections"""
    placeSelected = pyqtSignal(object)
    
    @pyqtSlot('QVariant')
    def receivePlaceData(self, place_data):
        # place_data contains: name, address, lat, lng, bounds
        self.placeSelected.emit(place_data)

class CustomWebPage(QWebEnginePage):
    """Custom WebEnginePage to intercept and log JavaScript console messages"""
    def __init__(self, parent=None, logger=None):
        super().__init__(parent)
        self.logger = logger

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        try:
            # Map log levels to string prefixes
            levels = {
                QWebEnginePage.InfoMessageLevel: "INFO",
                QWebEnginePage.WarningMessageLevel: "WARN",
                QWebEnginePage.ErrorMessageLevel: "ERROR"
            }
            log_level = levels.get(level, "LOG")
            
            # Format message
            formatted_msg = f"[JS {log_level}] {message} (Line {lineNumber})"
            
            # Print to console for immediate feedback
            print(formatted_msg)
            
            # Log to application logger if available
            if self.logger:
                if level == QWebEnginePage.ErrorMessageLevel:
                    self.logger.log_exception(formatted_msg)
                else:
                    self.logger.log_status(formatted_msg)
        except:
            pass # Prevent recursion or errors in logging
