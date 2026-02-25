class ui:
    WIDGET_TAB_HEIGHT = 400
    FULLSCREEN = True

class startup_ui:
    HEIGHT = 500
    WIDTH = 350

class performance:
    FPS = 120

# This acts as the central hub
class Config:
    ui = ui()
    performance = performance()
    startup_ui = startup_ui()
    
# Instantiate it once
config = Config()