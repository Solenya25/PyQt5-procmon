import os
import sys
import logging
import traceback
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QWidget, QApplication
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QIcon
from ui.notification_manager import NotificationManager
from monitoring.process_monitor import ProcessMonitor
from utils.admin import restart_as_admin
from utils.config import AppConfig

class SystemTrayApp(QWidget):
    def __init__(self):
        try:
            super().__init__()
            logging.debug("Initializing SystemTrayApp...")

            # Initialize configuration
            self.config = AppConfig()
            
            # Load block list
            self.block_list = self.config.load_block_list()

            # Initialize the NotificationManager
            logging.debug("Creating NotificationManager...")
            self.notification_manager = NotificationManager(self)

            # Set up logging
            logging.debug("Setting up logging...")
            self.setup_logging()

            # Initialize the system tray UI
            logging.debug("Initializing UI...")
            self.init_ui()

            # Start the ProcessMonitor to monitor running processes
            logging.debug("Starting ProcessMonitor...")
            self.monitor = ProcessMonitor(self.config, logging_enabled=self.config.logging_enabled)
            self.monitor.poll_interval = self.config.settings['poll_interval']
            self.monitor.process_started.connect(self.show_notification)  # Connect signal for new processes
            self.monitor.block_list = self.block_list  # Pass the block list to the monitor
            self.monitor.start()

            # Set up timers for raising notifications and reloading the block list
            logging.debug("Setting up timers...")
            self.raise_timer = QTimer(self)
            self.raise_timer.timeout.connect(self.notification_manager.raise_notifications)
            self.raise_timer.start(int(self.config.settings['raise_interval'] * 1000))  # Convert seconds to ms

            self.block_list_reload_timer = QTimer(self)
            self.block_list_reload_timer.timeout.connect(self.reload_block_list)
            self.block_list_reload_timer.start(5000)  # Reload block list every 5 seconds

            logging.debug("SystemTrayApp initialized successfully.")
        except Exception as e:
            logging.critical(f"Error initializing SystemTrayApp: {e}\n{traceback.format_exc()}")
            raise
        
    def setup_logging(self):
        """Set up logging configuration."""
        try:
            log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "process_monitor.log")
            logging.basicConfig(
                level=logging.CRITICAL,  # Logging is off by default
                format="%(asctime)s - %(levelname)s - %(message)s",
                filename=log_file,  # Log only to a file
            )
            logging.getLogger().setLevel(logging.CRITICAL)  # Ensure logging is off by default
        except Exception as e:
            print(f"Failed to initialize logging: {e}")
            sys.exit(1)                
    
    def init_ui(self):
        """Set up the system tray icon and menu."""
        try:
            logging.debug("Setting up system tray icon...")
            self.tray = QSystemTrayIcon(self)
            self.tray.setIcon(QIcon("resources/system.ico"))  # Set the tray icon

            logging.debug("Creating system tray menu...")
            menu = QMenu()            
            
            # Add "Clear All Notifications" option
            clear_action = menu.addAction("Clear All Notifications")
            clear_action.triggered.connect(self.clear_notifications)

            # Add "Hide/Show Notifications" option
            self.toggle_notifications_action = menu.addAction("Hide Notifications")
            self.toggle_notifications_action.triggered.connect(self.toggle_notifications)

            # Add "Collapsed/Expanded View" option
            self.toggle_view_action = menu.addAction("Expanded View")
            self.toggle_view_action.triggered.connect(self.toggle_view)

            # Add "Edit Custom Icons" option
            edit_custom_icons_action = menu.addAction("Edit Custom Icons")
            edit_custom_icons_action.triggered.connect(self.edit_custom_icons)

            # Add "Edit Block List" option
            edit_block_list_action = menu.addAction("Edit Block List")
            edit_block_list_action.triggered.connect(self.edit_block_list)
            
            # Add "Enable/Disable Blocking" option
            self.toggle_blocking_action = menu.addAction("Disable Blocking")
            self.toggle_blocking_action.triggered.connect(self.toggle_blocking)
            
             # Add "Enable/Disable Logging" option
            logging_text = "Enable Logging" if not self.config.logging_enabled else "Disable Logging"
            self.toggle_logging_action = menu.addAction(logging_text)
            self.toggle_logging_action.triggered.connect(self.toggle_logging)

			# Add "Restart as Admin" option
            restart_as_admin_action = menu.addAction("Restart as Admin")
            restart_as_admin_action.triggered.connect(self.restart_as_admin_handler)

            # Add "Exit" option
            exit_action = menu.addAction("Exit")
            exit_action.triggered.connect(self.cleanup)

            # Set the menu for the system tray icon
            self.tray.setContextMenu(menu)
            self.tray.show()
            logging.debug("System tray icon and menu set up successfully.")
        except Exception as e:
            logging.critical(f"Error in init_ui(): {e}\n{traceback.format_exc()}")
            raise
        
    def toggle_blocking(self):
        """Enable or disable blocking."""
        self.config.blocking_enabled = not self.config.blocking_enabled
        self.monitor.blocking_enabled = self.config.blocking_enabled  # Update the monitor's blocking state

        if self.config.blocking_enabled:
            self.toggle_blocking_action.setText("Disable Blocking")
            logging.info("Blocking enabled.")
        else:
            self.toggle_blocking_action.setText("Enable Blocking")
            logging.info("Blocking disabled.")

    def edit_block_list(self):
        """Open the block list file in the default text editor."""
        try:
            os.startfile(self.config.block_list_file)
        except Exception as e:
            logging.error(f"Failed to open block list file: {e}")

    def reload_block_list(self):
        """Reload the block list from the file."""
        try:
            new_block_list = self.config.load_block_list()
            if new_block_list != self.block_list:
                self.block_list = new_block_list
                self.monitor.block_list = self.block_list  # Update the monitor's block list
                logging.info("Block list reloaded.")
        except Exception as e:
            logging.error(f"Failed to reload block list: {e}") 

    def edit_custom_icons(self):
        """Open the custom_icons.txt file in the default text editor."""
        try:
            os.startfile(self.config.custom_icons_file)
        except Exception as e:
            logging.error(f"Failed to open custom_icons.txt: {e}")

    def toggle_logging(self):
        """Enable or disable logging."""
        self.config.logging_enabled = not self.config.logging_enabled

        if self.config.logging_enabled:
            self.toggle_logging_action.setText("Disable Logging")
            logging.getLogger().setLevel(logging.INFO)  # Enable logging
            logging.info("Logging enabled.")
        else:
            self.toggle_logging_action.setText("Enable Logging")
            logging.getLogger().setLevel(logging.CRITICAL)  # Disable most logs
            logging.info("Logging disabled.")  # This won't appear because logging is disabled

    def clear_notifications(self):
        """Clear all current notifications."""
        for notification in self.notification_manager.notifications[:]:
            notification.fade_animation.setDuration(200)  # Faster fade for bulk clear
            notification.start_fade()        

    def toggle_notifications(self):
        """Enable or disable notifications."""
        self.config.notifications_enabled = not self.config.notifications_enabled

        if self.config.notifications_enabled:
            self.toggle_notifications_action.setText("Hide Notifications")
        else:
            self.toggle_notifications_action.setText("Show Notifications")
            # Hide all currently visible notifications
            for notification in self.notification_manager.notifications:
                notification.hide()

    def show_notification(self, name, path, pid, icon, is_elevated=False):
        """Show a notification for a new process."""
        if not self.config.notifications_enabled:
            return
            
        try:
            message = f"{name}\n{path}\nPID: {pid}"
            self.notification_manager.add_notification(
                icon, 
                message, 
                is_elevated
            )
            logging.info(f"Notification shown for process: {name} (PID: {pid}, Elevated: {is_elevated})")
        except Exception as e:
            logging.error(f"Failed to show notification for {name}: {e}")
            try:
                self.tray.showMessage("Error", 
                                    f"Failed to show notification for {name}",
                                    QSystemTrayIcon.Warning)
            except Exception as show_error:
                logging.error(f"Failed to show error message: {show_error}")
    
    def toggle_view(self):
        """Toggle between collapsed and expanded view."""
        self.config.expanded_view = not self.config.expanded_view

        if self.config.expanded_view:
            self.toggle_view_action.setText("Collapsed View")
        else:
            self.toggle_view_action.setText("Expanded View")

        # Update all existing notifications
        for notification in self.notification_manager.notifications[:]:
            try:
                if not notification.isDestroyed():
                    notification.set_expanded_state(self.config.expanded_view)
                    # Reset opacity when switching views
                    notification.setWindowOpacity(1.0)
                    
                    # Stop any ongoing animations
                    notification.fade_animation.stop()
                    notification.fade_timer.stop()
                    
                    # Restart fade timer regardless of view mode
                    if not notification.is_hovered:
                        notification.fade_timer.start(
                            notification.customization['display_time']
                        )
                    
                    if self.config.expanded_view:
                        notification.expand()
                    else:
                        notification.collapse()
                        
            except Exception as e:
                logging.error(f"Error updating notification view state: {e}")
                continue

        # Update positions after changing states
        self.notification_manager.update_positions()
        
    def restart_as_admin_handler(self):
        """Handle the "Restart as Admin" menu action by calling the utility function."""
        restart_as_admin(self)
                
    def cleanup(self):
        """Clean up resources and exit the application."""
        try:
            # Hide all notifications first
            for notification in self.notification_manager.notifications[:]:
                try:
                    notification.hide()
                    notification.deleteLater()
                except RuntimeError:
                    pass
                    
            self.notification_manager.notifications.clear()
            
            self.monitor.running = False
            self.monitor.wait()
            QApplication.quit()
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")
            QApplication.quit()