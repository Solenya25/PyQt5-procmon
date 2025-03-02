import os
import json
import logging

class AppConfig:
    def __init__(self):
        # Application state variables
        self.logging_enabled = False  # Logging is disabled by default
        self.notifications_enabled = True  # Notifications are enabled by default
        self.expanded_view = False  # Notifications start in collapsed view
        self.blocking_enabled = True  # Blocking is enabled by default

        # Define paths for resources and configuration files
        self.resources_path = os.path.join(os.getcwd(), "resources")
        self.block_list_file = os.path.join(self.resources_path, "block_list.txt")
        self.allow_list_file = os.path.join(self.resources_path, "allow_list.txt")
        self.custom_icons_file = os.path.join(self.resources_path, "custom_icons.txt")
        self.settings_file = os.path.join(self.resources_path, "settings.json")  # New settings file

        # Configuration settings
        self.settings = {
            'poll_interval': 0.5,  # Interval for process monitoring (in seconds)
            'raise_interval': 2.0,  # Interval for raising notifications (in seconds)
            'max_notifications': 20,  # Maximum number of notifications to display
            'fade_duration': 2000,  # Duration for notification fade-out (in ms)
            'display_time': 5000,  # Time to display notifications before fading (in ms)
            'margin_right': 4,  # Distance from right edge of screen (in pixels)
            'margin_bottom': 50,  # Distance from bottom edge of screen (in pixels)
        }

        # Notification styling
        self.notification_style = {
            "background_color": "#282828",
            "border_radius": "10px",
            "font_size_name": "14px",
            "font_size_path": "12px",
            "font_size_pid": "12px",
            "fade_duration": 2000,
            "display_time": 5000,
            "hover_background_color": "#3C3C3C",
            "elevated_background_color": "#DC641E",  # Dark orange for elevated processes
            "elevated_hover_background_color": "#E67828",  # Lighter orange for elevated hover

            # Add default border color
            "border_color": "#505050",  # Dark gray border
            "pin_border_color": "#FFD700",  # Gold color for pinned notifications

            # Status indicator options
            "status_dot_size": 8,  # Size for status indicator dots in pixels
            "blocked_dot_color": "#FF0000",  # Bright red for blocked status
            "allowed_dot_color": "#00CC00",  # Bright green for allowed status
            "show_status_indicators": True,  # Show status indicators by default
            "text_color": "#FFFFFF",  # White text
        }

        # Load saved settings if available
        self.load_settings()
        
    def load_settings(self):
        """Load settings from the settings.json file if it exists."""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    saved_settings = json.load(f)

                # Update settings if they exist in the saved file
                if 'settings' in saved_settings:
                    self.settings.update(saved_settings['settings'])

                # Update notification style if it exists in the saved file
                if 'notification_style' in saved_settings:
                    self.notification_style.update(saved_settings['notification_style'])

                logging.info(f"Loaded settings from {self.settings_file}")
            else:
                logging.info("No settings file found, using defaults")

        except Exception as e:
            logging.error(f"Error loading settings: {e}")

    def save_settings(self):
        """Save current settings to the settings.json file."""
        try:
            # Ensure resources directory exists
            os.makedirs(self.resources_path, exist_ok=True)

            # Create settings object
            settings_data = {
                'settings': self.settings,
                'notification_style': self.notification_style,
            }

            # Write to file using a temporary file first to prevent corruption
            temp_file = self.settings_file + ".tmp"
            try:
                with open(temp_file, 'w') as f:
                    json.dump(settings_data, f, indent=4)

                # If writing succeeded, replace the original file
                if os.path.exists(self.settings_file):
                    os.replace(temp_file, self.settings_file)
                else:
                    os.rename(temp_file, self.settings_file)

                logging.info(f"Settings saved to {self.settings_file}")
                return True
        
            except Exception as file_error:
                logging.error(f"Error writing settings file: {file_error}")
                # Clean up temp file if it exists
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                return False
        
        except Exception as e:
            logging.error(f"Error saving settings: {e}")
            return False
            
    def apply_settings_to_components(self, parent_app):
        """Apply current settings to running application components."""
        try:
            # Update monitor poll interval if it changed
            if hasattr(parent_app, 'monitor'):
                parent_app.monitor.poll_interval = self.settings['poll_interval']

            # Update notification manager max notifications
            if hasattr(parent_app, 'notification_manager'):
                parent_app.notification_manager.max_notifications = self.settings['max_notifications']
                parent_app.notification_manager.margin_right = self.settings['margin_right']
                parent_app.notification_manager.margin_bottom = self.settings['margin_bottom']

            # Update active notifications with new styles
            if hasattr(parent_app, 'notification_manager') and hasattr(parent_app.notification_manager, 'notifications'):
                for notification in parent_app.notification_manager.notifications:
                    if notification.isVisible():
                        # Update customization settings
                        notification.customization = self.notification_style.copy()

                        # Update style
                        notification.setStyleSheet(notification.get_style(notification.is_hovered))

                        # Update status indicators
                        notification.update_status_indicators()

                # Update positions after changing margin settings
                parent_app.notification_manager.update_positions()

            return True

        except Exception as e:
            logging.error(f"Error applying settings to components: {e}")
            return False
        
    def load_allow_list(self):
        """Load the allow list from the file."""
        try:
            if not os.path.exists(self.allow_list_file):
                with open(self.allow_list_file, "w") as f:
                    f.write(
                        "# Add entries to allow specific processes (overrides block list)\n"
                        "# Add full path to allow specific processes\n"
                        "# Example: C:\\Program Files\\MyApp\\MyApp.exe\n"
                        "# Add folder path to allow all processes in a directory\n"
                        "# Example: C:\\Program Files\\\n"
                        "# Add process name for blanket allowing\n"
                        "# Example: MyApp.exe\n"
                        "# --------------------------------------------------------------------\n"
                    )

            # In load_allow_list function
            allow_list = []
            with open(self.allow_list_file, "r") as f:
                for line in f:
                    entry = line.strip()
                    if entry and not entry.startswith("#"):  # Ignore commented lines
                        # Preserve original capitalization for display
                        allow_list.append(entry)

            return allow_list
        except Exception as e:
            logging.error(f"Failed to load allow list: {e}")
            return []    
        
    def load_block_list(self):
        """Load the block list from the file."""
        try:
            if not os.path.exists(self.block_list_file):
                with open(self.block_list_file, "w") as f:
                    f.write(
                        "# Add/remove entries automatically by right-clicking notifications\n"
                        "# Add full path to block specific processes\n"
                        "# Example: C:\\Program Files\\MyApp\\MyApp.exe\n"
                        "# Add folder path to block all processes in a directory\n"
                        "# Example: C:\\Program Files\\\n"
                        "# Add process name for blanket blocking\n"
                        "# Example: MyApp.exe\n"
                        "# --------------------------------------------------------------------\n"
                    )

            # In load_block_list function
            block_list = []
            with open(self.block_list_file, "r") as f:
                for line in f:
                    entry = line.strip()
                    if entry and not entry.startswith("#"):  # Ignore commented lines
                        # Preserve original capitalization for display
                        block_list.append(entry)

            return block_list
        except Exception as e:
            logging.error(f"Failed to load block list: {e}")
            return []
            
    def load_custom_icon_mappings(self):
        """Load custom icon mappings from custom_icons.txt."""
        try:
            logging.debug("Loading custom icon mappings...")
            icon_mappings = {}
            with open(self.custom_icons_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):  # Ignore empty lines and comments
                        continue

                    parts = line.split(",")
                    if len(parts) == 2:
                        key = parts[0].strip().strip('"').lower()  # Normalize (remove quotes, lowercase)
                        icon_name = parts[1].strip().strip('"')

                        if key and icon_name:
                            icon_mappings[key] = icon_name  # Store mapping

            logging.debug(f"Loaded custom icon mappings: {icon_mappings}")
            return icon_mappings
        except Exception as e:
            logging.error(f"Failed to load custom icon mappings: {e}")
            return {}