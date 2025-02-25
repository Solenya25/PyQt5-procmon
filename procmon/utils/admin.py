import os
import sys
import time
import ctypes
import logging
import traceback
import win32con
import win32event
import win32process
from win32com.shell.shell import ShellExecuteEx
from win32com.shell import shellcon
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon

def is_admin():
    """Check if the current process has admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def restart_as_admin(app_instance):
    """Restart the application with admin privileges using ShellExecuteEx."""
    try:
        # Check if already running as admin
        if is_admin():
            logging.info("Already running as admin.")
            return

        logging.info("Restarting as admin...")
        
        # Get the current script path
        script_path = os.path.abspath(sys.argv[0])
        
        # Get pythonw.exe path (windowless version of Python)
        # We derive it from the current Python executable path by replacing python.exe with pythonw.exe
        python_dir = os.path.dirname(sys.executable)
        pythonw_exe = os.path.join(python_dir, 'pythonw.exe')
        
        # If pythonw.exe doesn't exist, fall back to the regular executable
        if not os.path.exists(pythonw_exe):
            pythonw_exe = sys.executable
            logging.warning("pythonw.exe not found, using regular Python executable")
        
        # Prepare the command arguments - starting with the script
        args = f'"{script_path}"'
        if len(sys.argv) > 1:
            # Add any additional arguments
            args += ' ' + ' '.join(f'"{arg}"' for arg in sys.argv[1:])
        
        # Execute with elevated privileges using pythonw.exe
        procInfo = ShellExecuteEx(
            nShow=win32con.SW_SHOWNORMAL,
            fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
            lpVerb='runas',  # This is what triggers the UAC prompt
            lpFile=pythonw_exe,  # Use pythonw instead of python
            lpParameters=args
        )
        
        # Wait a moment to ensure the new process started
        if procInfo['hProcess']:
            # Give it a moment to start up
            time.sleep(1)
            
            # Check if the process is running
            if win32process.GetExitCodeProcess(procInfo['hProcess']) == win32con.STILL_ACTIVE:
                logging.info("Admin process started successfully. Exiting current instance.")
                app_instance.cleanup()  # Clean up resources
                QApplication.quit()
                return
        
        logging.warning("Admin process may not have started properly.")
            
    except Exception as e:
        logging.error(f"Failed to restart as admin: {e}")
        logging.error(traceback.format_exc())
        # Show a notification to the user
        try:
            app_instance.tray.showMessage(
                "Error",
                "Failed to restart with admin privileges. See log for details.",
                QSystemTrayIcon.Critical,
                3000  # Display for 3 seconds
            )
        except:
            pass