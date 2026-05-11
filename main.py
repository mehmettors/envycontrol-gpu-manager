#!/usr/bin/env python3
import sys
from PySide6.QtWidgets import QApplication
from gpu_manager import GPUManagerWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GPU Manager")
    app.setOrganizationName("gpu-manager")

    window = GPUManagerWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
