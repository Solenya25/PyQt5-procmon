import sys
import logging
import traceback
from PyQt5.QtWidgets import QApplication
from utils.resources import create_system_icon, create_resource_files
from system_tray import SystemTrayApp

if __name__ == "__main__":
    try:
        # Ensure resources folder and files are created before logging        
        create_resource_files()

        # Initialize logging (off by default)        
        logging.basicConfig(
            level=logging.CRITICAL,  # Default to CRITICAL to suppress most logs
            format="%(asctime)s - %(levelname)s - %(message)s",
            filename="resources/process_monitor.log",
        )        

        # Create the system tray icon        
        create_system_icon()

        # Start the application        
        logging.debug("Starting PyQt5 application...")
        app = QApplication(sys.argv)
        window = SystemTrayApp()
        logging.debug("PyQt5 application started successfully.")
        sys.exit(app.exec_())
    except Exception as e:
        # Log critical errors
        logging.critical(f"Critical error: {e}\n{traceback.format_exc()}")
        print(f"Critical error: {e}\n{traceback.format_exc()}")
        sys.exit(1)