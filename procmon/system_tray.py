import os
import sys
import logging
import traceback
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QWidget, QApplication
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon
from ui.settings_dialog import SettingsDialog 
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
            
            # Set parent reference for unified status determination
            self.config.parent_app = self
        
            # Load block and allow list
            self.block_list = self.config.load_block_list()
            self.allow_list = self.config.load_allow_list() 
        
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
            self.monitor.allow_list = self.allow_list  # Pass the allow list to the monitor
            self.monitor.start()

            # Set up timers for reloading the block list
            self.block_list_reload_timer = QTimer(self)
            self.block_list_reload_timer.timeout.connect(self.reload_block_and_allow_lists)
            self.block_list_reload_timer.start(5000)  # Reload block list every 5 seconds

            logging.debug("SystemTrayApp initialized successfully.")
        except Exception as e:
            logging.critical(f"Error initializing SystemTrayApp: {e}\n{traceback.format_exc()}")
            raise
            
    def open_settings(self):
        """Open the settings dialog."""
        try:
            # Check if dialog already exists and is visible
            if hasattr(self, 'settings_dialog') and self.settings_dialog is not None:
                # If dialog exists but is hidden, show it
                if not self.settings_dialog.isVisible():
                    self.settings_dialog.show()
                    self.settings_dialog.raise_()
                    self.settings_dialog.activateWindow()
                return

            # Create dialog as a child of the main app window
            self.settings_dialog = SettingsDialog(self.config, self)

            # Connect to the destroyed signal to clean up our reference
            self.settings_dialog.destroyed.connect(self.on_settings_dialog_closed)

            # Show the dialog as a non-modal dialog so it doesn't block the application
            self.settings_dialog.setModal(False)
            self.settings_dialog.show()

            logging.info("Settings dialog opened")
        except Exception as e:
            logging.error(f"Error opening settings: {e}")
            try:
                self.tray.showMessage(
                    "Error",
                    "Failed to open settings dialog. See log for details.",
                    QSystemTrayIcon.Critical,
                    3000
                )
            except Exception:
                pass
                
    def on_settings_dialog_closed(self):
        """Clean up settings dialog reference when it's closed."""
        try:
            # Reset the reference to avoid trying to reuse a deleted dialog
            self.settings_dialog = None
            logging.debug("Settings dialog reference cleared")
        except Exception as e:
            logging.error(f"Error cleaning up settings dialog: {e}")
        
    def determine_process_status(self, path, block_list, allow_list):
        """
        Determine if a process is blocked or allowed based on our hierarchical rule system.
    
        Rule Priority (highest to lowest):
        1. Exact path entries (allow overrides block)
        2. Process name entries (allow overrides block)
        3. Directory entries (deeper paths override shallower ones, allow overrides block)
        4. "ALL" rule in block list (lowest priority)
    
        Args:
            path (str): Full path to the executable
            block_list (list): List of block entries
            allow_list (list): List of allow entries
            
        Returns:
            tuple: (final_status, rule_type, match_depth)
                - final_status: None (no rule matched), True (allowed), False (blocked)
                - rule_type: String indicating which rule determined the status
                - match_depth: Depth of directory match if applicable
        """
        # Normalize paths for comparison
        path_lower = path.lower().replace("/", "\\").rstrip("\\")
        process_name_lower = os.path.basename(path_lower)
    
        # Initialize return values
        final_status = None  # None = no rule matched, True = allowed, False = blocked
        rule_type = None     # Type of rule that determined the final status
        match_depth = -1     # Depth of the deepest directory rule that matched

        # Special case: check if exact path is in both lists - allow wins
        exact_path_in_block = path_lower in [entry.lower().replace("/", "\\").rstrip("\\") for entry in block_list]
        exact_path_in_allow = path_lower in [entry.lower().replace("/", "\\").rstrip("\\") for entry in allow_list]
    
        if exact_path_in_block and exact_path_in_allow:
            final_status = True
            rule_type = "exact_path_both_lists"
            logging.info(f"Process path in both lists, allowing by priority: {path}")
            return final_status, rule_type, match_depth

        # 1. Check exact path (highest priority)
        if exact_path_in_allow:
            final_status = True
            rule_type = "exact_path_allow"
            logging.info(f"Process allowed by exact path: {path}")
            return final_status, rule_type, match_depth
        elif exact_path_in_block:
            final_status = False
            rule_type = "exact_path_block"
            logging.info(f"Process blocked by exact path: {path}")
            return final_status, rule_type, match_depth

        # 2. Check process name (second highest priority)
        process_name_in_allow = process_name_lower in [entry.lower() for entry in allow_list]
        process_name_in_block = process_name_lower in [entry.lower() for entry in block_list]
    
        if process_name_in_allow and process_name_in_block:
            final_status = True
            rule_type = "process_name_both_lists"
            logging.info(f"Process name in both lists, allowing by priority: {process_name_lower}")
            return final_status, rule_type, match_depth
        elif process_name_in_allow:
            final_status = True
            rule_type = "process_name_allow"
            logging.info(f"Process allowed by process name: {process_name_lower}")
            return final_status, rule_type, match_depth
        elif process_name_in_block:
            final_status = False
            rule_type = "process_name_block"
            logging.info(f"Process blocked by process name: {process_name_lower}")
            return final_status, rule_type, match_depth

        # 3. Check directory hierarchy (priority increases with path depth)
        # Collect all matching directory rules from both lists
        allow_dir_matches = []
        block_dir_matches = []
    
        # Process allow list directories - make sure they end with backslash
        for entry in allow_list:
            entry_lower = entry.lower().replace("/", "\\")
            # Ensure entry ends with backslash for directory rules
            if not entry_lower.endswith("\\"):
                continue
            
            if path_lower.startswith(entry_lower):
                depth = entry_lower.count("\\")
                allow_dir_matches.append((depth, entry_lower))
    
        # Process block list directories - make sure they end with backslash
        for entry in block_list:
            entry_lower = entry.lower().replace("/", "\\")
            # Ensure entry ends with backslash for directory rules
            if not entry_lower.endswith("\\"):
                continue
            
            if path_lower.startswith(entry_lower):
                depth = entry_lower.count("\\")
                block_dir_matches.append((depth, entry_lower))
    
        # Find deepest directory match in each list
        deepest_allow = max(allow_dir_matches, key=lambda x: x[0], default=None)
        deepest_block = max(block_dir_matches, key=lambda x: x[0], default=None)
    
        # Compare directory rules if we have matches
        if deepest_allow and deepest_block:
            # If allow is deeper or equal depth, it wins
            if deepest_allow[0] >= deepest_block[0]:
                final_status = True
                rule_type = "directory_allow"
                match_depth = deepest_allow[0]
                logging.info(f"Process allowed by deeper directory rule: {deepest_allow[1]} (depth {deepest_allow[0]})")
                return final_status, rule_type, match_depth
            else:
                # Block list has deeper match
                final_status = False
                rule_type = "directory_block"
                match_depth = deepest_block[0]
                logging.info(f"Process blocked by deeper directory rule: {deepest_block[1]} (depth {deepest_block[0]})")
                return final_status, rule_type, match_depth
        elif deepest_allow:
            # Only allow match
            final_status = True
            rule_type = "directory_allow"
            match_depth = deepest_allow[0]
            logging.info(f"Process allowed by directory rule: {deepest_allow[1]} (depth {deepest_allow[0]})")
            return final_status, rule_type, match_depth
        elif deepest_block:
            # Only block match
            final_status = False
            rule_type = "directory_block"
            match_depth = deepest_block[0]
            logging.info(f"Process blocked by directory rule: {deepest_block[1]} (depth {deepest_block[0]})")
            return final_status, rule_type, match_depth

        # 4. Check for "all" keyword in block list (lowest priority)
        if "all" in [entry.lower() for entry in block_list]:
            final_status = False
            rule_type = "all_keyword"
            logging.info(f"Process blocked by ALL rule: {path}")
            return final_status, rule_type, match_depth

        # No rules matched
        return None, None, -1
    
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
            self.menu_active = False

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
            
            # Add "Edit Allow List" option
            edit_allow_list_action = menu.addAction("Edit Allow List")
            edit_allow_list_action.triggered.connect(self.edit_allow_list)
            
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
            
            # Add "Settings" option
            settings_action = menu.addAction("Settings")
            settings_action.triggered.connect(self.open_settings)

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
        
    def is_system_tray_menu_open(self):
        """Check if the system tray context menu is currently open"""
        from PyQt5.QtWidgets import QApplication, QMenu
    
        # Get all top-level widgets
        for widget in QApplication.topLevelWidgets():
            # Check if it's a menu and visible
            if isinstance(widget, QMenu) and widget.isVisible():
                # Check if this menu belongs to the system tray
                # One way to check is if the menu has our custom actions in it
                for action in widget.actions():
                    # Look for typical actions in our system tray menu
                    if (action.text() in ["Clear All Notifications", "Hide Notifications", 
                                        "Show Notifications", "Exit", "Restart as Admin",
                                        "Edit Block List", "Edit Allow List"]):
                        return True
    
        return False
        
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

    def edit_allow_list(self):
        """Open the allow list file in the default text editor."""
        try:
            os.startfile(self.config.allow_list_file)
        except Exception as e:
            logging.error(f"Failed to open allow list file: {e}")

    def edit_block_list(self):
        """Open the block list file in the default text editor."""
        try:
            os.startfile(self.config.block_list_file)
        except Exception as e:
            logging.error(f"Failed to open block list file: {e}")

    def reload_block_and_allow_lists(self):
        """Reload both block and allow lists from files."""
        self.reload_block_list()
        self.reload_allow_list()

    def reload_allow_list(self):
        """Reload the allow list from the file."""
        try:
            new_allow_list = self.config.load_allow_list()
            if new_allow_list != self.allow_list:
                self.allow_list = new_allow_list
                self.monitor.allow_list = self.allow_list  # Update the monitor's allow list
                logging.info("Allow list reloaded.")
        except Exception as e:
            logging.error(f"Failed to reload allow list: {e}")

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
    
            # Check if system tray menu is open before creating notification
            system_menu_open = getattr(self, 'menu_active', False) or self.is_system_tray_menu_open()

            # Determine block/allow status using the unified function
            final_status, rule_type, match_depth = self.determine_process_status(
                path, self.block_list, self.allow_list
            )
    
            # Skip notification if blocked and blocking is enabled
            if final_status is False and self.config.blocking_enabled:
                logging.info(f"Skipping notification for blocked process: {path} (rule: {rule_type})")
                return
    
            # Create notification
            notification = self.notification_manager.add_notification(
                icon, 
                message, 
                is_elevated,
                system_menu_open
            )

            if notification:
                # Set is_blocked and is_allowed flags
                notification.is_blocked = (final_status is False)
                notification.is_allowed = (final_status is True)
                notification.update_status_indicators()
        
                # Log the decision
                if final_status is True:
                    logging.info(f"Showing notification for allowed process: {path} (rule: {rule_type})")
                elif final_status is False:
                    logging.info(f"Process blocked but showing notification due to blocking disabled: {path} (rule: {rule_type})")
                else:
                    logging.info(f"Showing notification for process with no matching rules: {path}")
    
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
                
                    # Restart fade timer regardless of view mode, but only if visible
                    # and not hovered or pinned
                    if notification.isVisible() and not notification.is_hovered and not getattr(notification, 'is_pinned', False):
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
            # Close settings dialog if open
            if hasattr(self, 'settings_dialog') and self.settings_dialog is not None:
                try:
                    self.settings_dialog.hide()
                    self.settings_dialog.cleanup_resources()
                    self.settings_dialog.deleteLater()
                    self.settings_dialog = None
                except Exception as dialog_error:
                    logging.error(f"Error closing settings dialog: {dialog_error}")
        
            # Clean up notification manager queued notifications
            if hasattr(self, 'notification_manager') and self.notification_manager is not None:
                try:
                    # Clear any queued notifications
                    for notification, _ in self.notification_manager.notification_queue:
                        notification.deleteLater()
                    self.notification_manager.notification_queue.clear()
                except Exception as queue_error:
                    logging.error(f"Error clearing notification queue: {queue_error}")
        
            # Hide all notifications first
            for notification in self.notification_manager.notifications[:]:
                try:
                    notification.hide()
                    notification.deleteLater()
                except RuntimeError:
                    pass
                
            self.notification_manager.notifications.clear()
        
            # Stop the process monitor
            self.monitor.running = False
        
            # Wait with timeout to avoid hanging (max 2 seconds)
            self.monitor.wait(2000)
        
            # Make sure we quit the application even if something failed
            QTimer.singleShot(100, QApplication.quit)
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")
            # Ensure application quits even in case of errors
            QApplication.quit()