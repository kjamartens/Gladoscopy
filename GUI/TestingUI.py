import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dynamic Interface Example")
        
        # Create a central widget and set a vertical layout
        self.central_widget = QWidget()
        self.layout = QVBoxLayout(self.central_widget)
        self.setCentralWidget(self.central_widget)
        
        # Initialize the field count
        self.field_count = 0
        
        # Create buttons
        self.add_button = QPushButton("Add Field")
        self.remove_button = QPushButton("Remove Field")
        
        # Connect button signals to slots
        self.add_button.clicked.connect(self.add_field)
        self.remove_button.clicked.connect(self.remove_field)
        
        # Add buttons to the layout
        self.layout.addWidget(self.add_button)
        self.layout.addWidget(self.remove_button)
        
    def add_field(self):
        # Increase the field count
        self.field_count += 1
        
        # Create a new field (label) with a unique name
        field_label = QLabel(f"Field {self.field_count}")
        
        # Add the field to the layout
        self.layout.addWidget(field_label)
        
    def remove_field(self):
        if self.field_count > 0:
            # Remove the last field from the layout
            field_label = self.layout.itemAt(self.field_count+1).widget()
            self.layout.removeWidget(field_label)
            field_label.deleteLater()
            
            # Decrease the field count
            self.field_count -= 1
            
    def moveEvent(self, event):
        # Adjust the size of the central widget when the window is resized
        self.central_widget.resize(self.width(), self.height())
        
        event.accept()
            

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
