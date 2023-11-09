import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QLabel, QPushButton, QWidget

## This example creates just a single input and a single output.
## Flowcharts may define any number of terminals, though.
import pyqtgraph as pg
from pyqtgraph.flowchart import FlowchartCtrlWidget,Flowchart
# from pyqtgraph.flowchart.library import CtrlNode


# Create the main application
app = QApplication(sys.argv)

# Create a main window
window = QMainWindow()
window.setWindowTitle("PyQt Layout Example")

# Create a central widget
central_widget = QWidget(window)
window.setCentralWidget(central_widget)

# Create a vertical layout
layout = QVBoxLayout(central_widget)

# Create a label and add it to the layout
label = QLabel("Hello, PyQt!")
layout.addWidget(label)

# Create a button and add it to the layout
button = QPushButton("Click Me!")
layout.addWidget(button)

global fc
fc = Flowchart(terminals={
    'InputTerminal': {'io': 'in'},
    'OutputTerminal': {'io': 'out'}
})
fc_ctrl_widget = FlowchartCtrlWidget(chart=fc)

# fc_ctrl_widget.setFlowchart(fc)

# Create a GraphicsView widget and add it to the layout
view = pg.GraphicsView()
fc_ctrl_widget.setCentralItem(view)
layout.addWidget(view)
# Set the Flowchart as the top-level widget of the GraphicsView
# view.setCentralItem(fc.widget())

ctrl = fc.widget()
layout.addWidget(ctrl)  ## read Qt docs on QWidget and layouts for more information

fc.setInput(InputTerminal='Value')

#On button press, print the output:
def on_click():
    print("Clicked!")
    print(fc.output())
button.clicked.connect(on_click)

# Show the main window
window.show()

# Run the application
sys.exit(app.exec_())