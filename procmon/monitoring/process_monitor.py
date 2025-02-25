import os
import time
import psutil
import logging
import traceback
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QIcon
from icons.extractor import extract_regular_icon, create_default_icon
from icons.uwp import extract_windowsapps_icon
from icons.cache import IconCache
from monitoring.elevation import is_process_elevated

class ProcessMonitor(QThread):
    process_started = pyqtSignal(str, str, str, QIcon, bool)  # Added boolean for is_elevated

    def __init__(self, config, logging_enabled=False):
        try:
            super().__init__()
            logging.debug("Initializing ProcessMonitor...")
            self.running = True
            self.previous_processes = None
            self.icon_cache = IconCache()
            self.poll_interval = 0.5
            self.logging_enabled = logging_enabled
            self.block_list = []
            self.blocking_enabled = True
            self.config = config

            # Set the path for the custom_icons folder and file
            self.resources_path = os.path.join(os.getcwd(), "resources")
            self.custom_icons_path = os.path.join(self.resources_path, "custom_icons")
            self.custom_icons_file = os.path.join(self.resources_path, "custom_icons.txt")
            os.makedirs(self.custom_icons_path, exist_ok=True)  # Ensure the folder exists

            # Track the last modification time of custom_icons.txt
            self.custom_icons_last_modified = os.path.getmtime(self.custom_icons_file)

            # Load custom icon mappings
            self.icon_mappings = self.config.load_custom_icon_mappings()

            # Create default icon on initialization
            self.default_icon = create_default_icon()
            logging.debug("ProcessMonitor initialized successfully.")
        except Exception as e:
            logging.critical(f"Error initializing ProcessMonitor: {e}\n{traceback.format_exc()}")
            raise

    def check_for_custom_icons_update(self):
        """Check if custom_icons.txt has been updated and reload mappings if necessary."""
        try:
            current_mod_time = os.path.getmtime(self.custom_icons_file)
            if current_mod_time > self.custom_icons_last_modified:
                logging.debug("custom_icons.txt has been updated. Reloading mappings...")
                self.custom_icons_last_modified = current_mod_time
                self.icon_mappings = self.config.load_custom_icon_mappings()
                self.icon_cache.clear()  # Clear the cache to ensure updated mappings take effect
                logging.debug("Custom icon mappings reloaded and cache cleared.")
        except Exception as e:
            logging.error(f"Error checking for updates to custom_icons.txt: {e}")

    def get_custom_icon(self, exe_path, process_name):
        """Try to find a matching icon in the custom_icons folder."""
        try:
            # Check if custom_icons.txt has been updated
            self.check_for_custom_icons_update()

            # Define supported formats
            supported_formats = [".ico", ".png", ".jpg", ".jpeg", ".bmp"]

            exe_path_lower = exe_path.lower()
            process_name_lower = process_name.lower()

            def find_icon(icon_name):
                """Helper function to find an icon file with any supported format."""
                for ext in supported_formats:
                    icon_path = os.path.join(self.custom_icons_path, f"{icon_name}{ext}")
                    if os.path.exists(icon_path):
                        return icon_path
                return None

            # Step 1: Check for path-based icon (higher priority)
            if exe_path_lower in self.icon_mappings:
                icon_path = find_icon(self.icon_mappings[exe_path_lower])
                if icon_path:
                    return QIcon(icon_path)

            # Step 2: Check for process name-based icon
            if process_name_lower in self.icon_mappings:
                icon_path = find_icon(self.icon_mappings[process_name_lower])
                if icon_path:
                    return QIcon(icon_path)

            return None  # No custom icon found

        except Exception as e:
            logging.error(f"Error loading custom icon for {process_name}: {e}")
            return None

    def get_process_icon(self, process):
        """Get an icon for a process with multiple fallback methods."""
        try:
            exe_path = process.exe()
            process_name = process.name()
            
            # 1. Try custom icon first (highest priority)
            custom_icon = self.get_custom_icon(exe_path, process_name)
            if custom_icon:
                self.icon_cache.put(exe_path, custom_icon)
                logging.info(f"Using custom icon for {process_name}")
                return custom_icon
            
            # 2. Check cache
            cached_icon = self.icon_cache.get(exe_path)
            if cached_icon:
                return cached_icon            

            # 3. Extraction based on application type
            icon = None
            
            # For WindowsApps (UWP applications)
            if "WindowsApps" in exe_path:
                icon = extract_windowsapps_icon(process)
                
                # Retry once after a short delay if the icon is not retrieved
                if not icon:
                    time.sleep(0.2)  # Reduced delay for better performance
                    icon = extract_windowsapps_icon(process)
            
            # 4. For regular applications
            if not icon:
                icon = extract_regular_icon(exe_path, process_name)
                
            # 5. Cache and return the icon if any extraction method succeeded
            if icon:
                self.icon_cache.put(exe_path, icon)
                return icon

            # 6. If all methods fail, try to find a similar icon for related processes
            # This helps with processes that have multiple instances but different paths
            try:
                base_name = os.path.basename(exe_path).lower()
                # Check for similar process names in the cache
                for cached_path, cached_data in self.icon_cache.cache.items():
                    cached_base = os.path.basename(cached_path).lower()
                    # If the basename matches, use that icon
                    if cached_base == base_name:
                        logging.info(f"Using similar process icon for {process_name}")
                        return cached_data[0]  # [0] is the icon, [1] is the timestamp
            except Exception as similar_error:
                logging.debug(f"Similar icon check failed: {similar_error}")

            # 7. Final fallback - create a process-specific default icon
            logging.info(f"Using default icon for {process_name}")
            process_default_icon = create_default_icon(process_name)
            return process_default_icon

        except Exception as e:
            logging.error(f"Icon extraction failed for {process_name}: {e}")
            return self.default_icon

    def run(self):
        try:
            self.previous_processes = set(p.pid for p in psutil.process_iter(["pid"]))
            logging.info(f"Initial process count: {len(self.previous_processes)}")
        except Exception as e:
            logging.error(f"Error initializing process list: {e}")
            self.previous_processes = set()

        time.sleep(1)

        while self.running:
            try:
                # Use psutil's process_iter with caching to reduce overhead
                current_processes = set(p.pid for p in psutil.process_iter(["pid"]))
                new_pids = current_processes - self.previous_processes

                # Process new PIDs
                for pid in new_pids:
                    try:
                        process = psutil.Process(pid)
                        if process.is_running():
                            exe_path_original = process.exe()  # Keep correct capitalization for display
                            exe_path_lower = exe_path_original.lower().replace("/", "\\").rstrip("\\")  # Normalize slashes
                            process_name_original = process.name()  # Correct capitalization
                            process_name_lower = process_name_original.lower()  # Lowercase for matching

                            # Check if blocking is enabled
                            if self.blocking_enabled:
                                block_list_lower = [
                                    entry.lower().replace("/", "\\").rstrip("\\")
                                    for entry in self.block_list
                                ]

                                # Initialize a flag to track if the process is blocked
                                is_blocked = False

                                # 1. Block by exact file path
                                if exe_path_lower in block_list_lower:
                                    logging.info(f"Blocked process by full path: {exe_path_original}")
                                    is_blocked = True

                                # 2. Block by process name
                                if process_name_lower in block_list_lower:
                                    logging.info(f"Blocked process by name: {process_name_original}")
                                    is_blocked = True

                                # 3. Block by directory (check if exe path starts with any blocked directory)
                                for blocked_entry in block_list_lower:
                                    if exe_path_lower.startswith(blocked_entry + "\\"):  # Ensure it's a directory match
                                        logging.info(f"Blocked process in blocked directory: {exe_path_original}")
                                        is_blocked = True
                                        break  # No need to check further if already blocked

                                # Skip the process if it is blocked
                                if is_blocked:
                                    continue

                            # Check if the process is elevated
                            is_elevated = False
                            try:
                                is_elevated = is_process_elevated(pid)
                            except Exception as e:
                                logging.error(f"Error checking if process is elevated: {e}")
                            
                            # Get the icon
                            icon = self.get_process_icon(process)
                            
                            # Send notification with elevation status
                            self.process_started.emit(
                                process_name_original, 
                                exe_path_original, 
                                str(pid), 
                                icon,
                                is_elevated
                            )

                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
                    except Exception as e:
                        logging.error(f"Error processing PID {pid}: {e}")
                        continue

                # Update the previous process list
                self.previous_processes = current_processes

                # Adjust polling interval dynamically based on system load
                time.sleep(self.poll_interval)

            except Exception as e:
                logging.error(f"Error in process monitoring: {e}")
                time.sleep(1)  # Use a longer sleep on errors to avoid spamming