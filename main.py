# main.py
import sys
from qtpy.QtWidgets import QApplication
from src.ui.windows.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()