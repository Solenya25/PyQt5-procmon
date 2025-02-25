import os
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
        self.custom_icons_file = os.path.join(self.resources_path, "custom_icons.txt")
        
        # Configuration settings
        self.settings = {
            'poll_interval': 0.5,  # Interval for process monitoring (in seconds)
            'raise_interval': 2.0,  # Interval for raising notifications (in seconds)
            'max_notifications': 20,  # Maximum number of notifications to display
            'fade_duration': 2000,  # Duration for notification fade-out (in ms)
            'display_time': 5000,  # Time to display notifications before fading (in ms)
        }
        
        # Notification styling
        self.notification_style = {
            "background_color": "rgba(40, 40, 40, 255)",
            "border_radius": "10px",
            "font_size": "14px",
            "fade_duration": 2000,
            "display_time": 5000,
            "hover_background_color": "rgba(60, 60, 60, 255)",
            "blocked_background_color": "rgba(139, 0, 0, 255)",  # Dark red for blocked notifications
            "elevated_background_color": "rgba(230, 125, 40, 255)",  # Dark orange for elevated processes
            "elevated_hover_background_color": "rgba(255, 160, 60, 255)",  # Lighter orange for elevated hover
        }
        
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

            block_list = []
            with open(self.block_list_file, "r") as f:
                for line in f:
                    entry = line.strip()
                    if entry and not entry.startswith("#"):  # Ignore commented lines
                        block_list.append(entry.lower())  # Store as lowercase for consistency

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