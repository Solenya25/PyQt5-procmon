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
            self.block_list = []  # Initialize block list
            self.allow_list = []  # Initialize allow list
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
    
    def check_process_block_status(self, path, block_list, allow_list):
        """
        Determine if a process should be blocked or allowed.
    
        This is a fallback method used when the parent's unified function is not available.
        Follows the same rule priority as defined in Rules.txt.
    
        Args:
            path (str): Process executable path
            block_list (list): Block list entries
            allow_list (list): Allow list entries
    
        Returns:
            tuple: (is_blocked, is_allowed)
        """
        # Normalize paths for comparison
        path_lower = path.lower().replace("/", "\\").rstrip("\\")
        process_name_lower = os.path.basename(path_lower)
    
        block_list_lower = [entry.lower().replace("/", "\\").rstrip("\\") for entry in block_list]
        allow_list_lower = [entry.lower().replace("/", "\\").rstrip("\\") for entry in allow_list]
    
        # 1. Check exact path (highest priority)
        # If path is in both lists, allow overrides block
        if path_lower in allow_list_lower and path_lower in block_list_lower:
            return False, True  # Not blocked, allowed
        
        # If path is in allow list, it's allowed
        if path_lower in allow_list_lower:
            return False, True  # Not blocked, allowed
    
        # If path is in block list, it's blocked
        if path_lower in block_list_lower:
            return True, False  # Blocked, not allowed
    
        # 2. Check process name (second priority)
        # If name is in both lists, allow overrides block
        if process_name_lower in allow_list_lower and process_name_lower in block_list_lower:
            return False, True  # Not blocked, allowed
        
        # If name is in allow list, it's allowed
        if process_name_lower in allow_list_lower:
            return False, True  # Not blocked, allowed
    
        # If name is in block list, it's blocked
        if process_name_lower in block_list_lower:
            return True, False  # Blocked, not allowed
    
        # 3. Check directory hierarchy (third priority)
        # Collect all directory rules (both allow and block)
        allow_dir_matches = []
        block_dir_matches = []
    
        # Gather allow list directory matches
        for entry in allow_list_lower:
            if entry.endswith("\\") and path_lower.startswith(entry):
                depth = entry.count("\\")
                allow_dir_matches.append((depth, entry))
            
        # Gather block list directory matches        
        for entry in block_list_lower:
            if entry.endswith("\\") and path_lower.startswith(entry):
                depth = entry.count("\\")
                block_dir_matches.append((depth, entry))
    
        # Find deepest directory match in each list
        deepest_allow = max(allow_dir_matches, key=lambda x: x[0], default=None)
        deepest_block = max(block_dir_matches, key=lambda x: x[0], default=None)
    
        # If we have matches in both lists, compare their depths
        if deepest_allow and deepest_block:
            if deepest_allow[0] >= deepest_block[0]:
                # Allow list has equal or deeper match - it wins
                return False, True  # Not blocked, allowed
            else:
                # Block list has deeper match - it wins
                return True, False  # Blocked, not allowed
        elif deepest_allow:
            # Only have allow match
            return False, True  # Not blocked, allowed
        elif deepest_block:
            # Only have block match
            return True, False  # Blocked, not allowed
    
        # 4. Check for "all" keyword in block list (lowest priority)
        if "all" in block_list_lower:
            return True, False  # Blocked, not allowed
    
        # No rules matched
        return False, False  # Not blocked, not allowed (default)

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
                current_processes = set(p.pid for p in psutil.process_iter(["pid"]))
                new_pids = current_processes - self.previous_processes

                for pid in new_pids:
                    try:
                        process = psutil.Process(pid)
                        if process.is_running():
                            exe_path_original = process.exe()  # Keep correct capitalization for display
                            process_name_original = process.name()  # Correct capitalization

                            # Get the parent app reference to use the unified function
                            parent_app = getattr(self.config, 'parent_app', None)
                        
                            # Determine block/allow status
                            should_block = False
                            rule_type = None
                        
                            if self.blocking_enabled:
                                if parent_app and hasattr(parent_app, 'determine_process_status'):
                                    # Use parent's unified determination function
                                    final_status, rule_type, _ = parent_app.determine_process_status(
                                        exe_path_original, self.block_list, self.allow_list
                                    )
                                    should_block = (final_status is False)
                                else:
                                    # Fallback: use local function to determine status
                                    is_blocked, is_allowed = self.check_process_block_status(
                                        exe_path_original, self.block_list, self.allow_list
                                    )
                                    should_block = is_blocked and not is_allowed
                                    rule_type = "local_determination"

                            # Skip notification if blocked AND blocking is enabled
                            if should_block and self.blocking_enabled:
                                logging.info(f"Skipping notification for blocked process: {exe_path_original} (rule: {rule_type})")
                                continue

                            # Rest of process notification code only runs if not blocked
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

                # Sleep for the poll interval
                time.sleep(self.poll_interval)

            except Exception as e:
                logging.error(f"Error in process monitoring: {e}")
                time.sleep(1)  # Use a longer sleep on errors to avoid spamming

