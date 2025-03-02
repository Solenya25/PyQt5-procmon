import os
import traceback
import time
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QDesktopWidget, QHBoxLayout, QApplication, QGridLayout,
    QMenu, QAction, QSizePolicy
)
from PyQt5.QtCore import QTimer, QPropertyAnimation, pyqtSignal, Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap, QColor, QPainter
from datetime import datetime
import weakref

class StatusDotLabel(QLabel):
    """A custom label that displays a colored dot indicator."""
    def __init__(self, parent=None, color=None, size=8):
        super().__init__(parent)
        self.dot_color = color
        self.dot_size = size
        self.setFixedSize(size, size)
        self.setVisible(color is not None)
        
    def paintEvent(self, event):
        """Paint the colored dot."""
        if self.dot_color:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(self.dot_color)
            painter.setPen(Qt.NoPen)
            # Draw ellipse from 0,0 to dot_size,dot_size (filling the entire label)
            painter.drawEllipse(0, 0, self.dot_size-1, self.dot_size-1)
            painter.end()
        
    def setColor(self, color):
        """Set the dot color and make visible if color is provided."""
        self.dot_color = color
        self.setVisible(color is not None)
        self.update()

class NotificationWidget(QWidget):
    removal_requested = pyqtSignal(object) 
    
    def __init__(self, icon, message, parent=None, expanded=False, is_elevated=False, notification_style=None):
        super().__init__(parent)        
        self.expanded = expanded    # Initialize expanded state first
        self.is_elevated = is_elevated  # Set elevation status directly from parameter
        self.context_menu_active = False
        self.is_blocked = False     # Track if process is in block list
        self.is_allowed = False     # Track if process is in allow list
        self.is_pinned = False
         
        # Set window flags
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.Tool | 
            Qt.WindowStaysOnTopHint
        )
        
        # Set attributes to handle transparency
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
                        
        # Store original path
        self.original_path = None
        
        # Parse message
        lines = message.split('\n')
        self.name = lines[0]
        self.path = lines[1]
        self.original_path = self.path  # Store original path
        self.pid = lines[2] if len(lines) > 2 else "PID: Unknown"
        
        # Use provided notification_style or set default values
        self.customization = {            
            "border_radius": "10px",
            "font_size": "14px",
            "fade_duration": 2000,
            "display_time": 5000,
            "background_color": "rgba(40, 40, 40, 255)", #Notification Background
            "hover_background_color": "rgba(60, 60, 60, 255)", #Notification Background Hovered           
            "elevated_background_color": "rgba(220, 100, 30, 255)",  # Dark orange for elevated processes
            "elevated_hover_background_color": "rgba(230, 120, 40, 255)",  # Lighter orange for elevated hover
            
            # Status indicator options
            "status_dot_size": 8,  # Size for status indicator dots in pixels
            "blocked_dot_color": "#FF0000",  # Bright red for blocked status
            "allowed_dot_color": "#00CC00",  # Bright green for allowed status
        }
        
        # Update with provided notification style if available
        if notification_style:
            self.customization.update(notification_style)
        
        self.is_hovered = False
        
        # Setup fade animation
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(self.customization['fade_duration'])
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.finished.connect(self.request_removal)

        # Setup fade timer
        self.fade_timer = QTimer(self)
        self.fade_timer.setSingleShot(True)  
        self.fade_timer.timeout.connect(self.start_fade)        

        # Main layout 
        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)  

        # Create a container widget for the entire content
        self.content_container = QWidget()
        self.content_container.setObjectName("content_container")
        
        content_layout = QGridLayout(self.content_container)
        content_layout.setSpacing(5)
        content_layout.setContentsMargins(10, 5, 10, 5)  

        # Add icon if available
        icon_size = 32
        if icon and not icon.isNull():
            self.icon_label = QLabel()
            self.icon_label.setFixedSize(icon_size, icon_size)
            icon_pixmap = icon.pixmap(icon_size, icon_size)
            self.icon_label.setPixmap(icon_pixmap)
            content_layout.addWidget(self.icon_label, 0, 0, 2, 1)

        # Message layout for text
        self.text_container = QWidget()
        self.text_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # Allow horizontal expansion
        text_container_layout = QVBoxLayout(self.text_container)
        text_container_layout.setContentsMargins(0, 0, 0, 0)
        text_container_layout.setSpacing(3)

        # When setting up the labels, update to:
        # Name label
        self.name_label = QLabel(self.name)
        self.name_label.setObjectName("name_label")  # Add object name for CSS targeting
        self.name_label.setWordWrap(False)
        self.name_label.setTextFormat(Qt.PlainText)  # Ensure plain text rendering
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # Allow horizontal expansion
        text_container_layout.addWidget(self.name_label)

        # Path label
        self.path_label = QLabel(self.original_path)
        self.path_label.setObjectName("path_label")  # Add object name for CSS targeting
        self.path_label.setWordWrap(False)
        self.path_label.setTextFormat(Qt.PlainText)  # Ensure plain text rendering
        self.path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # Allow horizontal expansion
        text_container_layout.addWidget(self.path_label)

        # PID label
        pid_text = self.pid
        if self.is_elevated:
            pid_text += " (Admin)"

        self.pid_label = QLabel(pid_text)
        self.pid_label.setObjectName("pid_label")  # Add object name for CSS targeting
        self.pid_label.setWordWrap(False)
        self.pid_label.setTextFormat(Qt.PlainText)  # Ensure plain text rendering
        self.pid_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # Allow horizontal expansion
        text_container_layout.addWidget(self.pid_label)

        # Optional: Add tooltips to show full text when hovered
        self.name_label.setToolTip(self.name)
        self.path_label.setToolTip(self.original_path)
        self.pid_label.setToolTip(pid_text)

        # Add the text container to the grid
        content_layout.addWidget(self.text_container, 0, 1, 2, 1)
        
        # Create status dots container at the bottom-left corner
        self.status_dots_container = QWidget()
        status_dots_layout = QHBoxLayout(self.status_dots_container)
        status_dots_layout.setContentsMargins(0, 0, 0, 0)
        status_dots_layout.setSpacing(2)
        
        # Create the status dot indicators
        dot_size = self.customization.get("status_dot_size", 8)
        
        # Blocked status dot (red)
        self.blocked_dot = StatusDotLabel(
            parent=self,
            color=None,  # Start with no color (hidden)
            size=dot_size
        )
        status_dots_layout.addWidget(self.blocked_dot)
        
        # Allowed status dot (green)
        self.allowed_dot = StatusDotLabel(
            parent=self,
            color=None,  # Start with no color (hidden)
            size=dot_size
        )
        status_dots_layout.addWidget(self.allowed_dot)
        
        # Add the status dots container to the bottom-left of the content grid
        content_layout.addWidget(self.status_dots_container, 1, 0, 1, 1, Qt.AlignBottom | Qt.AlignLeft)
        
        layout.addWidget(self.content_container)  
        self.setLayout(layout)

        # Set initial style
        self.setStyleSheet(self.get_style(False))        
        
        # Calculate sizes
        self.collapsed_width = 52  # Width for icon + margins
        self.full_width = self.calculate_required_width()
        
        # Set initial state
        if self.expanded:
            self.text_container.show()
            self.setFixedWidth(self.full_width)
        else:
            self.text_container.hide()
            self.setFixedWidth(self.collapsed_width)
        
        # Calculate and set fixed height
        self.text_container.show()  # Temporarily show to get proper height
        self.updateGeometry()
        self.adjustSize()
        self.fixed_height = self.sizeHint().height()
        
        # Set fixed dimensions
        self.setFixedSize(self.collapsed_width, self.fixed_height)
        self.text_container.hide()  # Hide again for initial state

        # Ensure opacity is set to 1.0 initially
        self.setWindowOpacity(1.0)
        
        # Install event filters to capture mouse events
        self.content_container.installEventFilter(self)
        self.text_container.installEventFilter(self)
        self.icon_label.installEventFilter(self)
        self.name_label.installEventFilter(self)
        self.path_label.installEventFilter(self)
        self.pid_label.installEventFilter(self)
        self.status_dots_container.installEventFilter(self)
        
        # Creation time
        self.creation_time = datetime.now()
        self._parent_ref = weakref.ref(parent) if parent else None        
        
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.on_single_click)
        self.last_click_time = None
        self.click_position = None        
        
        # Update block/allow status indicators
        self.update_status_indicators()
        
    def eventFilter(self, obj, event):
        """Filter events for child widgets to handle mouse clicks."""
        if event.type() == event.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                # Handle left-click
                self.click_position = event.pos()
                current_time = time.time()
                if self.last_click_time is not None and current_time - self.last_click_time < 0.5:
                    # Double-click
                    self.on_double_click()
                    self.click_timer.stop()
                    self.last_click_time = None
                else:
                    # Single click or first click of double-click
                    self.last_click_time = current_time
                    self.click_timer.start(250)
                return True
                
            elif event.button() == Qt.RightButton:
                # Handle right-click - call the existing method
                self.handle_right_click(event)
                return True
                
        # Let the widget handle other events
        return super().eventFilter(obj, event)

    def update_status_indicators(self):
        """
        Update the status dot indicators based on rules that could affect this process.
        Shows indicators based on potential rules, not just active blocking/allowing.
        Respects the show_status_indicators setting.
        """
        try:
            # Check if status indicators are enabled
            show_indicators = self.customization.get("show_status_indicators", True)
            if not show_indicators:
                self.blocked_dot.setColor(None)  # Hide dot
                self.allowed_dot.setColor(None)  # Hide dot
                return
        
            # Get parent app to access rules
            parent_manager = self.parent()
            parent_app = parent_manager.parent() if parent_manager else None
    
            if not parent_app or not hasattr(parent_app, 'block_list') or not hasattr(parent_app, 'allow_list'):
                # Can't determine status without parent app
                logging.debug("Cannot update status indicators: parent app or lists not available")
                return
    
            # Normalize path for comparison - ensure consistent formatting
            path_lower = self.original_path.lower().replace("/", "\\")
            process_name_lower = os.path.basename(path_lower)
    
            # Debug logging for troubleshooting
            logging.debug(f"Checking rules for: {path_lower}")
    
            # Check block list for ANY matching rule
            block_matched = False
            for entry in parent_app.block_list:
                if not entry or entry.startswith("#"):  # Skip empty lines and comments
                    continue
            
                entry_lower = entry.lower().replace("/", "\\")
        
                # Check exact path match
                if entry_lower == path_lower:
                    logging.debug(f"Block match: exact path with {entry_lower}")
                    block_matched = True
                    break
            
                # Check process name match
                if entry_lower == process_name_lower:
                    logging.debug(f"Block match: process name with {entry_lower}")
                    block_matched = True
                    break
            
                # Check directory match - make sure entry ends with backslash for directory rules
                if entry_lower.endswith("\\"):
                    if path_lower.startswith(entry_lower):
                        logging.debug(f"Block match: directory with {entry_lower}")
                        block_matched = True
                        break
                
                # Check for all keyword
                if entry_lower == "all":
                    logging.debug("Block match: ALL rule")
                    block_matched = True
                    break
    
            # Check allow list for ANY matching rule 
            allow_matched = False
            for entry in parent_app.allow_list:
                if not entry or entry.startswith("#"):  # Skip empty lines and comments
                    continue
            
                entry_lower = entry.lower().replace("/", "\\")
        
                # Check exact path match
                if entry_lower == path_lower:
                    logging.debug(f"Allow match: exact path with {entry_lower}")
                    allow_matched = True
                    break
            
                # Check process name match
                if entry_lower == process_name_lower:
                    logging.debug(f"Allow match: process name with {entry_lower}")
                    allow_matched = True
                    break
            
                # Check directory match - make sure entry ends with backslash for directory rules
                if entry_lower.endswith("\\"):
                    if path_lower.startswith(entry_lower):
                        logging.debug(f"Allow match: directory with {entry_lower}")
                        allow_matched = True
                        break
    
            # Update internal state
            self.is_blocked = block_matched
            self.is_allowed = allow_matched
    
            logging.debug(f"Status indicators for {path_lower}: block={block_matched}, allow={allow_matched}")
        
            # Get dot size from customization
            dot_size = self.customization.get("status_dot_size", 8)
            if hasattr(self.blocked_dot, 'dot_size') and self.blocked_dot.dot_size != dot_size:
                # Update dot size if changed
                self.blocked_dot.dot_size = dot_size
                self.allowed_dot.dot_size = dot_size
                self.blocked_dot.setFixedSize(dot_size, dot_size)
                self.allowed_dot.setFixedSize(dot_size, dot_size)
        
            # Update blocked status dot
            if self.is_blocked:
                # Get color from customization or use default red
                color_str = self.customization.get("blocked_dot_color", "#FF0000")
                blocked_color = QColor(color_str)
                if not blocked_color.isValid():
                    blocked_color = QColor(255, 0, 0)  # Default to red
                self.blocked_dot.setColor(blocked_color)
            else:
                self.blocked_dot.setColor(None)  # Hide dot
        
            # Update allowed status dot
            if self.is_allowed:
                # Get color from customization or use default green
                color_str = self.customization.get("allowed_dot_color", "#00CC00")
                allowed_color = QColor(color_str)
                if not allowed_color.isValid():
                    allowed_color = QColor(0, 204, 0)  # Default to green
                self.allowed_dot.setColor(allowed_color)
            else:
                self.allowed_dot.setColor(None)  # Hide dot
            
        except Exception as e:
            logging.error(f"Error updating status indicators: {e}") 
            
    def mousePressEvent(self, event):
        """Handle mouse press events with context menu support."""
        try:
            if event.button() == Qt.LeftButton:
                # Store click position for validating double-click
                self.click_position = event.pos()
            
                # Check for double-click
                current_time = time.time()
                if self.last_click_time is not None and current_time - self.last_click_time < 0.5:
                    # This is a double-click
                    self.on_double_click()
                    self.click_timer.stop()  # Stop the single-click timer
                    self.last_click_time = None  # Reset click time
                else:
                    # This might be a single click or first click of double-click
                    self.last_click_time = current_time
                    # Start timer to wait for possible second click
                    self.click_timer.start(250)  # 250ms window for double-click
                
            elif event.button() == Qt.RightButton:
                # Show context menu
                self.handle_right_click(event)
            
            # Make sure to call the parent class implementation
            super().mousePressEvent(event)
            
        except Exception as e:
            logging.error(f"Error in mousePressEvent: {e}")
            
    def handle_right_click(self, event):
        """Handle right-click context menu."""
        try:
            # Create context menu
            menu = QMenu()
            menu.setWindowFlags(menu.windowFlags() | Qt.WindowStaysOnTopHint)

            # FORCE highlight - store old style first
            self._old_stylesheet = self.styleSheet()
            self.context_menu_active = True
            self.is_hovered = True  # Force hover state
            hover_style = self.get_style(True)
            self.setStyleSheet(hover_style)

            # Set expanded state during menu
            if not self.expanded:
                self.expand()

            # Force notification to stay on top
            self.raise_()

            # Get parent references
            parent_manager = self.parent()
            parent_app = parent_manager.parent() if parent_manager else None

            # Collections to store all matching entries - with original capitalization
            path_block_entry = None
            name_block_entry = None
            dir_block_entries = []  # Will store original entries with capitalization
            original_dir_block_entries = {}  # Maps lowercase path to original entry

            path_allow_entry = None
            name_allow_entry = None
            dir_allow_entries = []  # Will store original entries with capitalization
            original_dir_allow_entries = {}  # Maps lowercase path to original entry

            # Track which directory paths are already in block and allow lists
            # to grey out options that already exist
            existing_block_dirs = set()
            existing_allow_dirs = set()

            # When no parent app, show basic menu
            if not parent_app or not hasattr(parent_app, 'block_list') or not hasattr(parent_app, 'allow_list'):
                # Basic menu with open option
                open_action = menu.addAction("Open File Location")
                open_action.triggered.connect(self.open_path)
                menu.exec_(event.globalPos())
                return

            # Use original path to preserve proper capitalization
            # Use original path to preserve proper capitalization
            original_path = self.original_path

            # Normalize paths for comparison but preserve original
            path_lower = original_path.lower().replace("/", "\\")  # Don't strip trailing backslashes
            process_name_lower = os.path.basename(path_lower)

            # Create path components for directory options
            # Keep original capitalization for display
            path_components = []
            path_components_lower = []  # Lowercase versions for comparison
            current_path = ""
            current_path_original = ""

            # Split path into components for directory menu
            # Example: C:\Program Files\App\app.exe becomes:
            # C:\, Program Files\, App\
            path_parts = original_path.split("\\")
            path_parts_lower = path_lower.split("\\")

            for i, part in enumerate(path_parts[:-1]):  # Skip the file name
                if i == 0:
                    # Handle drive letter
                    current_path_lower = path_parts_lower[i] + "\\"
                    current_path_original = path_parts[i] + "\\"
                else:
                    current_path_lower = current_path_lower + path_parts_lower[i] + "\\"
                    current_path_original = current_path_original + path_parts[i] + "\\"

                path_components.append(current_path_original)
                path_components_lower.append(current_path_lower)

            # Store entries from both block and allow lists for menu creation
            # Check block list - preserve original entries for display
            for entry in parent_app.block_list:
                # Store original entry
                original_entry = entry
                # Convert for comparison
                entry_lower = entry.lower().replace("/", "\\")  # Don't strip trailing backslashes

                # Check for ALL rule - just track it, status will be calculated later
                if entry_lower == "all":
                    continue

                # Check exact path match
                if entry_lower == path_lower:
                    path_block_entry = original_entry  # Store original entry
                    continue

                # Check process name match
                if entry_lower == process_name_lower:
                    name_block_entry = original_entry  # Store original entry
                    continue

                # Check directory match - keep original form
                for i, path_component_lower in enumerate(path_components_lower):
                    if entry_lower == path_component_lower:  # Compare with trailing slashes preserved
                        dir_block_entries.append(original_entry)  # Add original entry with proper capitalization
                        existing_block_dirs.add(path_component_lower)
                        # Store mapping of lowercase to original
                        original_dir_block_entries[entry_lower] = original_entry
                        break

            # Check allow list - preserve original entries for display
            for entry in parent_app.allow_list:
                # Store original entry
                original_entry = entry
                # Convert for comparison
                entry_lower = entry.lower().replace("/", "\\")  # Don't strip trailing backslashes

                # Check exact path match
                if entry_lower == path_lower:
                    path_allow_entry = original_entry  # Store original entry
                    continue

                # Check process name match
                if entry_lower == process_name_lower:
                    name_allow_entry = original_entry  # Store original entry
                    continue

                # Check directory match - keep original form
                for i, path_component_lower in enumerate(path_components_lower):
                    if entry_lower == path_component_lower:  # Compare with trailing slashes preserved
                        dir_allow_entries.append(original_entry)  # Add original entry with proper capitalization
                        existing_allow_dirs.add(path_component_lower)
                        # Store mapping of lowercase to original
                        original_dir_allow_entries[entry_lower] = original_entry
                        break

            # Now determine final status using the parent app's unified function
            final_status, rule_type, _ = parent_app.determine_process_status(
                original_path, parent_app.block_list, parent_app.allow_list
            )
        
            # Set status flags based on determination
            is_blocked = (final_status is False)
            is_allowed = (final_status is True)

            # Update instance variables for indicators
            self.is_blocked = is_blocked
            self.is_allowed = is_allowed
            self.update_status_indicators()

            # Create the tree structure menu

            # 1. Block List Add submenu
            block_add_menu = menu.addMenu("Block List Add")

            # Path option - with description in the text
            path_add_action = QAction("Path (blocks this exact exe)", block_add_menu)
            path_add_action.setEnabled(not path_block_entry)  # Disable if already exists
            path_add_action.triggered.connect(lambda: self.add_to_blocklist('path'))
            block_add_menu.addAction(path_add_action)

            # Name option - with description in the text
            name_add_action = QAction("Name (blocks all exe's with this name)", block_add_menu)
            name_add_action.setEnabled(not name_block_entry)  # Disable if already exists
            name_add_action.triggered.connect(lambda: self.add_to_blocklist('name'))
            block_add_menu.addAction(name_add_action)

            # Directory submenu - with description in the parent menu
            dir_add_menu = block_add_menu.addMenu("Directory (blocks all in selected dir)")
            for i, path_component in enumerate(path_components):
                # Create action for each directory level - without description
                path_component_lower = path_components_lower[i]  # Keep trailing slash
                dir_action = QAction(path_component, dir_add_menu)
                dir_action.setEnabled(path_component_lower not in existing_block_dirs)
                dir_action.triggered.connect(lambda checked, p=path_component: self.add_to_blocklist('dir', p))
                dir_add_menu.addAction(dir_action)

            # 2. Block List Remove submenu
            block_remove_menu = menu.addMenu("Block List Remove")

            # Path remove option
            path_remove_action = QAction("Path", block_remove_menu)
            path_remove_action.setEnabled(path_block_entry is not None)
            path_remove_action.triggered.connect(lambda: self.remove_from_blocklist('path'))
            block_remove_menu.addAction(path_remove_action)

            # Name remove option
            name_remove_action = QAction("Name", block_remove_menu)
            name_remove_action.setEnabled(name_block_entry is not None)
            name_remove_action.triggered.connect(lambda: self.remove_from_blocklist('name'))
            block_remove_menu.addAction(name_remove_action)

            # Directory remove submenu - only if directory entries exist
            if dir_block_entries:
                dir_remove_menu = block_remove_menu.addMenu("Directory")
                for dir_entry in dir_block_entries:
                    # Use original entry with proper capitalization and trailing slash
                    dir_action = QAction(dir_entry, dir_remove_menu)
                    # Use explicit parameter binding to ensure capitalization is preserved
                    dir_action.triggered.connect(lambda checked, directory_entry=dir_entry: self.remove_from_blocklist('dir', directory_entry))
                    dir_remove_menu.addAction(dir_action)
            else:
                # Add disabled Directory option if no entries
                dir_remove_action = QAction("Directory", block_remove_menu)
                dir_remove_action.setEnabled(False)
                block_remove_menu.addAction(dir_remove_action)

            # 3. Allow List Add submenu
            allow_add_menu = menu.addMenu("Allow List Add")

            # Path option - with description in the text
            path_add_action = QAction("Path (allows this exact exe)", allow_add_menu)
            path_add_action.setEnabled(not path_allow_entry)  # Disable if already exists
            path_add_action.triggered.connect(lambda: self.add_to_allowlist('path'))
            allow_add_menu.addAction(path_add_action)

            # Name option - with description in the text
            name_add_action = QAction("Name (allows all exe's with this name)", allow_add_menu)
            name_add_action.setEnabled(not name_allow_entry)  # Disable if already exists
            name_add_action.triggered.connect(lambda: self.add_to_allowlist('name'))
            allow_add_menu.addAction(name_add_action)

            # Directory submenu - with description in the parent menu
            dir_add_menu = allow_add_menu.addMenu("Directory (allows all in selected dir)")
            for i, path_component in enumerate(path_components):
                # Create action for each directory level - without description
                path_component_lower = path_components_lower[i]  # Keep trailing slash
                dir_action = QAction(path_component, dir_add_menu)
                dir_action.setEnabled(path_component_lower not in existing_allow_dirs)
                dir_action.triggered.connect(lambda checked, p=path_component: self.add_to_allowlist('dir', p))
                dir_add_menu.addAction(dir_action)

            # 4. Allow List Remove submenu
            allow_remove_menu = menu.addMenu("Allow List Remove")

            # Path remove option
            path_remove_action = QAction("Path", allow_remove_menu)
            path_remove_action.setEnabled(path_allow_entry is not None)
            path_remove_action.triggered.connect(lambda: self.remove_from_allowlist('path'))
            allow_remove_menu.addAction(path_remove_action)

            # Name remove option
            name_remove_action = QAction("Name", allow_remove_menu)
            name_remove_action.setEnabled(name_allow_entry is not None)
            name_remove_action.triggered.connect(lambda: self.remove_from_allowlist('name'))
            allow_remove_menu.addAction(name_remove_action)

            # Directory remove submenu - only if directory entries exist
            if dir_allow_entries:
                dir_remove_menu = allow_remove_menu.addMenu("Directory")
                for dir_entry in dir_allow_entries:
                    # Use original entry with proper capitalization and trailing slash
                    dir_action = QAction(dir_entry, dir_remove_menu)
                    # Use explicit parameter binding to ensure capitalization is preserved
                    dir_action.triggered.connect(lambda checked, directory_entry=dir_entry: self.remove_from_allowlist('dir', directory_entry))
                    dir_remove_menu.addAction(dir_action)
            else:
                # Add disabled Directory option if no entries
                dir_remove_action = QAction("Directory", allow_remove_menu)
                dir_remove_action.setEnabled(False)
                allow_remove_menu.addAction(dir_remove_action)

            # 5. Status indicator (no children) with rule explanation
            status_text = ""
            
            # Check for rules that exist in both lists
            same_path_in_both = path_block_entry is not None and path_allow_entry is not None
            same_name_in_both = name_block_entry is not None and name_allow_entry is not None
            
            # Check for directory matches in both lists - this is more complex
            same_dir_in_both = False
            matching_dirs = []
            for dir_path_lower in existing_block_dirs:
                if dir_path_lower in existing_allow_dirs:
                    same_dir_in_both = True
                    matching_dirs.append(dir_path_lower)
            
            # Now determine the status text
            if same_path_in_both:
                status_text = "Status: ALLOWED (exact path in both lists)"
            elif same_name_in_both:
                status_text = "Status: ALLOWED (exe name in both lists)"
            elif same_dir_in_both:
                status_text = "Status: ALLOWED (directory rule in both lists)"
            # If not in both lists, use the original rule_type determination
            elif rule_type == "exact_path_allow":
                status_text = "Status: ALLOWED (by exact path)"
            elif rule_type == "exact_path_block":
                status_text = "Status: BLOCKED (by exact path)"
            elif rule_type == "process_name_allow":
                status_text = "Status: ALLOWED (by executable name)"
            elif rule_type == "process_name_block":
                status_text = "Status: BLOCKED (by executable name)"
            elif rule_type and rule_type.startswith("directory_allow"):
                status_text = "Status: ALLOWED (by directory rule)"
            elif rule_type and rule_type.startswith("directory_block"):
                status_text = "Status: BLOCKED (by directory rule)"
            elif rule_type == "all_keyword":
                status_text = "Status: BLOCKED (by ALL rule)"
            else:
                status_text = "Status: No Rules Applied"
            
            status_action = menu.addAction(status_text)
            status_action.setEnabled(False)  # Make it non-clickable

            # Handle menu closing
            def actual_on_close():
                QTimer.singleShot(100, self.on_context_menu_closed)

            menu.aboutToHide.connect(actual_on_close)

            # Show the menu
            menu.exec_(event.globalPos())

        except Exception as e:
            logging.error(f"Error in handle_right_click: {e}")
            self.context_menu_active = False
            self.is_hovered = False
            self.setStyleSheet(self.get_style(False))

    def get_style(self, hovered):
        """Get the appropriate style based on the state."""
        # For elevated processes, hover is lighter than normal
        if self.is_elevated:
            if hovered:
                bg_color = self.customization['elevated_hover_background_color']
            else:
                bg_color = self.customization['elevated_background_color']
        else:
            # For normal notifications, hover is slightly lighter
            if hovered:
                bg_color = self.customization['hover_background_color']
            else:
                bg_color = self.customization['background_color']

        # Define border style based on pin state
        border_color = self.customization.get("border_color", "#505050")  # Default border color

        # Use pin border color when pinned
        if self.is_pinned:
            border_color = self.customization.get("pin_border_color", "#FFD700")  # Gold/yellow color

        border_style = f"border: 2px solid {border_color};"

        # Get font sizes for different elements
        font_size_name = self.customization.get('font_size_name', '14px')
        font_size_path = self.customization.get('font_size_path', '12px')
        font_size_pid = self.customization.get('font_size_pid', '12px')
        text_color = self.customization.get('text_color', '#FFFFFF')

        return f"""
            QWidget {{
                background-color: transparent;
            }}
            QWidget#content_container {{
                background-color: {bg_color};
                border-radius: {self.customization['border_radius']};
                {border_style}
            }}
            QLabel {{
                background-color: transparent;
                color: {text_color};
            }}
            #name_label {{
                font-size: {font_size_name};
                font-weight: bold;
            }}
            #path_label {{
                font-size: {font_size_path};
            }}
            #pid_label {{
                font-size: {font_size_pid};
            }}
        """

    def toggle_blocklist(self):
        """Toggle the block state of the process using the full executable path."""
        try:
            # Get the SystemTrayApp instance
            parent_manager = self.parent()
            if parent_manager is None:
                logging.error("Cannot access parent notification manager")
                return
            
            parent_app = parent_manager.parent()
            if parent_app is None:
                logging.error("Cannot access parent SystemTrayApp")
                return
            
            # Get the block_list_file from config
            if not hasattr(parent_app, 'config') or parent_app.config is None:
                logging.error("Cannot access config to toggle block list")
                return
            
            block_list_file = parent_app.config.block_list_file

            # Normalize the path for consistent comparison
            path_lower = self.original_path.lower().replace("/", "\\").rstrip("\\")
            process_name_lower = os.path.basename(path_lower)
        
            # Check for direct blocks in the block list
            direct_blocks = []
            directory_block = None
            has_all_rule = False
        
            # Scan block list to find matches
            for entry in parent_app.block_list:
                entry_lower = entry.lower().replace("/", "\\").rstrip("\\")
            
                # Check for "ALL" rule
                if entry_lower == "all":
                    has_all_rule = True
                    continue
            
                # Check exact path match
                if entry_lower == path_lower:
                    direct_blocks.append(entry)
                    continue
            
                # Check process name match (basename)
                if entry_lower == process_name_lower:
                    direct_blocks.append(entry)
                    continue
            
                # Check if it's a directory block
                if path_lower.startswith(entry_lower + "\\"):
                    directory_block = entry

            # Determine if the process has a direct block entry
            has_direct_block = len(direct_blocks) > 0

            if has_direct_block:
                # Remove the process from the block list
                try:
                    with open(block_list_file, "r") as f:
                        lines = f.readlines()
                
                    with open(block_list_file, "w") as f:
                        for line in lines:
                            # Keep the line if it's not in our direct_blocks list
                            keep_line = True
                            line_lower = line.strip().lower()
                            for block in direct_blocks:
                                if line_lower == block.lower():
                                    keep_line = False
                                    break
                        
                            if keep_line:
                                f.write(line)
                
                    # Reload the block list
                    parent_app.reload_block_list()
                    logging.info(f"Removed direct blocks for {self.original_path}: {direct_blocks}")
                
                    # Update status after reload
                    # We'll need to recheck the status because other rules might still apply
                    is_still_blocked = False
                    directory_block_still_applies = False
                    all_rule_still_applies = False
                
                    # Check if the "ALL" rule still exists
                    if "all" in [e.lower() for e in parent_app.block_list]:
                        all_rule_still_applies = True
                        is_still_blocked = True
                    else:
                        # Check if a directory block still applies
                        for entry in parent_app.block_list:
                            entry_lower = entry.lower().replace("/", "\\").rstrip("\\")
                            if path_lower.startswith(entry_lower + "\\"):
                                directory_block_still_applies = True
                                is_still_blocked = True
                                break
                        
                            # Check if there's still a direct match (shouldn't happen, but checking)
                            if entry_lower == path_lower or entry_lower == process_name_lower:
                                is_still_blocked = True
                                break
                
                    # Check allow list (which overrides blocks)
                    is_allowed = False
                    for entry in parent_app.allow_list:
                        entry_lower = entry.lower().replace("/", "\\").rstrip("\\")
                        if entry_lower == path_lower or entry_lower == process_name_lower:
                            is_allowed = True
                            break
                        elif path_lower.startswith(entry_lower + "\\"):
                            is_allowed = True
                            break
                
                    # Update status indicators
                    self.is_blocked = is_still_blocked
                    self.is_allowed = is_allowed
                    self.update_status_indicators()
                        
                except Exception as e:
                    logging.error(f"Failed to remove from block list: {e}")
        
            elif (has_all_rule or directory_block) and not has_direct_block:
                # When blocked by ALL rule or directory, add to allow list to override
                allow_list_file = parent_app.config.allow_list_file
                try:
                    with open(allow_list_file, "a+") as f:
                        f.seek(0)
                        content = f.read()
                        if not content.lower().replace("/", "\\").split("\n").__contains__(self.original_path.lower().replace("/", "\\")):
                            if content and not content.endswith("\n"):
                                f.write("\n")  # Ensure newline before appending
                            f.write(f"{self.original_path}\n")  # Store full path
                
                    # Reload the allow list
                    parent_app.reload_allow_list()
                    logging.info(f"Added {self.original_path} to the allow list to override block.")
                
                    # Update status flags
                    self.is_allowed = True
                    self.update_status_indicators()
                except Exception as e:
                    logging.error(f"Failed to add to allow list: {e}")
        
            else:
                # Not on the block list, so add it
                try:
                    with open(block_list_file, "a+") as f:
                        f.seek(0)
                        content = f.read()
                        if content and not content.endswith("\n"):
                            f.write("\n")  # Ensure newline before appending
                        f.write(f"{self.original_path}\n")  # Store full path
                
                    # Reload the block list
                    parent_app.reload_block_list()
                    logging.info(f"Added {self.original_path} to the block list.")
            
                    # Update status flags
                    self.is_blocked = True
                    self.update_status_indicators()
                except Exception as e:
                    logging.error(f"Failed to add {self.original_path} to the block list: {e}")
        except Exception as e:
            logging.error(f"Error toggling block list: {e}")

    def toggle_allowlist(self):
        """Toggle the allow state of the process using the full executable path."""
        try:
            # Get the SystemTrayApp instance
            parent_manager = self.parent()
            if parent_manager is None:
                logging.error("Cannot access parent notification manager")
                return
        
            parent_app = parent_manager.parent()
            if parent_app is None:
                logging.error("Cannot access parent SystemTrayApp")
                return
        
            # Get the allow_list_file from config
            if not hasattr(parent_app, 'config') or parent_app.config is None:
                logging.error("Cannot access config to toggle allow list")
                return
        
            allow_list_file = parent_app.config.allow_list_file

            # Normalize paths for comparison
            path_lower = self.original_path.lower().replace("/", "\\").rstrip("\\")
            process_name_lower = os.path.basename(path_lower)
        
            # Find which entry in the allow list matches this process
            matched_entry = None
            match_type = None  # 'exact', 'name', or 'directory'
        
            for entry in parent_app.allow_list:
                entry_lower = entry.lower().replace("/", "\\").rstrip("\\")
            
                # Check for exact path match
                if entry_lower == path_lower:
                    matched_entry = entry
                    match_type = 'exact'
                    break
                
                # Check for process name match
                elif entry_lower == process_name_lower:
                    matched_entry = entry
                    match_type = 'name'
                    break
                
                # Check for directory match
                elif path_lower.startswith(entry_lower + "\\"):
                    matched_entry = entry
                    match_type = 'directory'
                    break
        
            # Is the process allowed?
            is_allowed = matched_entry is not None
        
            # If it's a directory match, we don't want to remove it via context menu
            if is_allowed and match_type == 'directory':
                # Show a notification that we can't remove directory entries
                try:
                    parent_app.tray.showMessage(
                        "Information",
                        f"Process is allowed by directory rule: {matched_entry}\nEdit allow list file directly to change."                        
                    )
                except Exception as e:
                    logging.error(f"Failed to show notification: {e}")
                return

            if is_allowed:
                # Remove from allow list - we should remove the exact entry, not the path
                try:
                    with open(allow_list_file, "r") as f:
                        lines = f.readlines()
                    with open(allow_list_file, "w") as f:
                        for line in lines:
                            # Normalize for comparison
                            line_entry = line.strip().lower()
                            matched_lower = matched_entry.lower()
                            if line_entry != matched_lower:
                                f.write(line)
                
                    # Reload the allow list
                    parent_app.reload_allow_list()
                    logging.info(f"Removed {matched_entry} from the allow list.")
                
                    # Update status flags
                    self.is_allowed = False
                
                    # Check if it should now be blocked
                    is_blocked = False
                    # Check for "ALL" rule
                    if "all" in [e.lower() for e in parent_app.block_list]:
                        is_blocked = True
                    else:
                        # Check by path or name
                        for entry in parent_app.block_list:
                            entry_lower = entry.lower().replace("/", "\\").rstrip("\\")
                            if entry_lower == path_lower or entry_lower == process_name_lower:
                                is_blocked = True
                                break
                            # Check directory match
                            if path_lower.startswith(entry_lower + "\\"):
                                is_blocked = True
                                break
                
                    self.is_blocked = is_blocked
                
                    # Update indicators
                    self.update_status_indicators()
                except Exception as e:
                    logging.error(f"Failed to remove {matched_entry} from the allow list: {e}")
            else:
                # Add to allow list
                try:
                    with open(allow_list_file, "a+") as f:
                        f.seek(0)
                        content = f.read()
                        if content and not content.endswith("\n"):
                            f.write("\n")  # Ensure newline before appending
                        f.write(f"{self.original_path}\n")  # Store full path
                
                    # Reload the allow list
                    parent_app.reload_allow_list()
                    logging.info(f"Added {self.original_path} to the allow list.")
                
                    # Update status flags
                    self.is_allowed = True
                
                    # Update indicators
                    self.update_status_indicators()
                except Exception as e:
                    logging.error(f"Failed to add {self.original_path} to the allow list: {e}")
        except Exception as e:
            logging.error(f"Error toggling allow list: {e}")
            
    def on_single_click(self):
        """Handle single-click event after timeout."""
        try:
            # Open the file location on single-click
            self.open_path()
        except Exception as e:
            logging.error(f"Error handling single click: {e}")
            
    def on_double_click(self):
        """Handle double-click event for pinning/unpinning."""
        try:
            # Toggle pin state
            self.is_pinned = not self.is_pinned
        
            # Update style immediately based on current hover state
            self.setStyleSheet(self.get_style(self.is_hovered))
    
            # Update behavior based on pin state
            if self.is_pinned:
                # Stop fade animation and timer if pinned
                self.fade_animation.stop()
                self.fade_timer.stop()
                self.setWindowOpacity(1.0)
        
                # Always stay expanded when pinned, even in collapsed mode
                self.expand()
                # Show brief notification about pinned state
                self.show_pin_status(True)
            else:
                # Restart fade timer if not hovered
                if not self.is_hovered and not self.context_menu_active:
                    self.fade_timer.start(self.customization['display_time'])
        
                # Get parent app's expanded view setting
                expanded_view = False
                parent_manager = self.parent()
                if parent_manager:
                    parent_app = parent_manager.parent()
                    if parent_app and hasattr(parent_app, 'config'):
                        expanded_view = getattr(parent_app.config, 'expanded_view', False)
        
                # If not in expanded view mode, collapse
                if not expanded_view:
                    self.collapse()
            
                # Show brief notification about unpinned state
                self.show_pin_status(False)
        except Exception as e:
            logging.error(f"Error handling double click: {e}")
            
    def show_pin_status(self, is_pinned):
        """Handle pin status change without showing Windows notifications."""
        # This function intentionally left empty to remove Windows notifications
        pass   
            
    def add_to_blocklist(self, entry_type, custom_path=None):
        """Add process to block list by path, name, or directory.
        
        Args:
            entry_type: Type of entry to add ('path', 'name', or 'dir')
            custom_path: Custom path for directory entries (used when entry_type is 'dir')
        """
        try:
            # Get the SystemTrayApp instance
            parent_manager = self.parent()
            if parent_manager is None:
                logging.error("Cannot access parent notification manager")
                return
            
            parent_app = parent_manager.parent()
            if parent_app is None:
                logging.error("Cannot access parent SystemTrayApp")
                return
            
            # Get the block_list_file from config
            if not hasattr(parent_app, 'config') or parent_app.config is None:
                logging.error("Cannot access config to update block list")
                return
            
            block_list_file = parent_app.config.block_list_file
            
            # Determine the value to add based on entry_type
            if entry_type == 'path':
                value = self.original_path
            elif entry_type == 'name':
                value = os.path.basename(self.original_path)
            elif entry_type == 'dir':
                value = custom_path  # For directory entries, use the provided path
            else:
                logging.error(f"Unknown entry type: {entry_type}")
                return
                
            # Check if value already exists in the list
            if value.lower() in [entry.lower() for entry in parent_app.block_list]:
                logging.info(f"Entry already exists in block list: {value}")
                return
                
            # Add to block list file
            try:
                # Read existing content
                with open(block_list_file, "r") as f:
                    lines = f.readlines()
                
                # Find the first empty line
                empty_line_index = -1
                for i, line in enumerate(lines):
                    if line.strip() == "":
                        empty_line_index = i
                        break
                
                # If empty line found, insert the entry there
                if empty_line_index != -1:
                    lines[empty_line_index] = f"{value}\n"
                else:
                    # Otherwise add to the end
                    if lines and not lines[-1].endswith("\n"):
                        lines.append("\n")
                    lines.append(f"{value}\n")
                
                # Write back the modified content
                with open(block_list_file, "w") as f:
                    f.writelines(lines)
                
                # Reload the block list
                parent_app.reload_block_list()
                logging.info(f"Added to block list: {value}")
                
                # Update status flags
                self.is_blocked = True
                self.update_status_indicators()
            except Exception as e:
                logging.error(f"Failed to add to block list: {e}")
                
        except Exception as e:
            logging.error(f"Error in add_to_blocklist: {e}")
    
    def remove_from_blocklist(self, entry_type, custom_path=None):
        """Remove process from block list by path, name, or directory.
    
        Args:
            entry_type: Type of entry to remove ('path', 'name', or 'dir')
            custom_path: Custom path for directory entries (used when entry_type is 'dir')
        """
        try:
            # Get the SystemTrayApp instance
            parent_manager = self.parent()
            if parent_manager is None:
                logging.error("Cannot access parent notification manager")
                return
            
            parent_app = parent_manager.parent()
            if parent_app is None:
                logging.error("Cannot access parent SystemTrayApp")
                return
        
            # Get the block_list_file from config
            if not hasattr(parent_app, 'config') or parent_app.config is None:
                logging.error("Cannot access config to update block list")
                return
        
            block_list_file = parent_app.config.block_list_file
        
            # Determine the value to remove based on entry_type
            if entry_type == 'path':
                value = self.original_path
            elif entry_type == 'name':
                value = os.path.basename(self.original_path)
            elif entry_type == 'dir':
                # For directory entries, use the provided path with original capitalization
                value = custom_path  # This should be the original entry from the context menu
            else:
                logging.error(f"Unknown entry type: {entry_type}")
                return
                
            # Remove from block list file
            try:
                with open(block_list_file, "r") as f:
                    lines = f.readlines()
                
                with open(block_list_file, "w") as f:
                    for line in lines:
                        line_entry = line.strip()
                        if line_entry.lower() != value.lower():
                            f.write(line)
                
                # Reload the block list
                parent_app.reload_block_list()
                logging.info(f"Removed from block list: {value}")
                
                # Check if the process is still blocked by other rules
                path_lower = self.original_path.lower().replace("/", "\\").rstrip("\\")
                process_name_lower = os.path.basename(path_lower)
                
                still_blocked = False
                # Check for "ALL" rule
                if "all" in [e.lower() for e in parent_app.block_list]:
                    still_blocked = True
                else:
                    # Check for other matches
                    for entry in parent_app.block_list:
                        entry_lower = entry.lower().replace("/", "\\").rstrip("\\")
                        if entry_lower == path_lower or entry_lower == process_name_lower:
                            still_blocked = True
                            break
                        # Check for directory match
                        if path_lower.startswith(entry_lower + "\\"):
                            still_blocked = True
                            break
                
                # Update status flags
                self.is_blocked = still_blocked
                self.update_status_indicators()
            except Exception as e:
                logging.error(f"Failed to remove from block list: {e}")
                
        except Exception as e:
                    logging.error(f"Error in remove_from_blocklist: {e}")
    def add_to_allowlist(self, entry_type, custom_path=None):
        """Add process to allow list by path, name, or directory.
        
        Args:
            entry_type: Type of entry to add ('path', 'name', or 'dir')
            custom_path: Custom path for directory entries (used when entry_type is 'dir')
        """
        try:
            # Get the SystemTrayApp instance
            parent_manager = self.parent()
            if parent_manager is None:
                logging.error("Cannot access parent notification manager")
                return
            
            parent_app = parent_manager.parent()
            if parent_app is None:
                logging.error("Cannot access parent SystemTrayApp")
                return
            
            # Get the allow_list_file from config
            if not hasattr(parent_app, 'config') or parent_app.config is None:
                logging.error("Cannot access config to update allow list")
                return
            
            allow_list_file = parent_app.config.allow_list_file
            
            # Determine the value to add based on entry_type
            if entry_type == 'path':
                value = self.original_path
            elif entry_type == 'name':
                value = os.path.basename(self.original_path)
            elif entry_type == 'dir':
                value = custom_path  # For directory entries, use the provided path
            else:
                logging.error(f"Unknown entry type: {entry_type}")
                return
                
            # Check if value already exists in the list
            if value.lower() in [entry.lower() for entry in parent_app.allow_list]:
                logging.info(f"Entry already exists in allow list: {value}")
                return
                
            # Add to allow list file
            try:
                # Read existing content
                with open(allow_list_file, "r") as f:
                    lines = f.readlines()
                
                # Find the first empty line
                empty_line_index = -1
                for i, line in enumerate(lines):
                    if line.strip() == "":
                        empty_line_index = i
                        break
                
                # If empty line found, insert the entry there
                if empty_line_index != -1:
                    lines[empty_line_index] = f"{value}\n"
                else:
                    # Otherwise add to the end
                    if lines and not lines[-1].endswith("\n"):
                        lines.append("\n")
                    lines.append(f"{value}\n")
                
                # Write back the modified content
                with open(allow_list_file, "w") as f:
                    f.writelines(lines)
                
                # Reload the allow list
                parent_app.reload_allow_list()
                logging.info(f"Added to allow list: {value}")
                
                # Update status flags
                self.is_allowed = True
                self.update_status_indicators()
            except Exception as e:
                logging.error(f"Failed to add to allow list: {e}")
                
        except Exception as e:
            logging.error(f"Error in add_to_allowlist: {e}")
    
    def remove_from_allowlist(self, entry_type, custom_path=None):
        """Remove process from allow list by path, name, or directory.
        
        Args:
            entry_type: Type of entry to remove ('path', 'name', or 'dir')
            custom_path: Custom path for directory entries (used when entry_type is 'dir')
        """
        try:
            # Get the SystemTrayApp instance
            parent_manager = self.parent()
            if parent_manager is None:
                logging.error("Cannot access parent notification manager")
                return
            
            parent_app = parent_manager.parent()
            if parent_app is None:
                logging.error("Cannot access parent SystemTrayApp")
                return
            
            # Get the allow_list_file from config
            if not hasattr(parent_app, 'config') or parent_app.config is None:
                logging.error("Cannot access config to update allow list")
                return
            
            allow_list_file = parent_app.config.allow_list_file
            
            # Determine the value to remove based on entry_type
            if entry_type == 'path':
                value = self.original_path
            elif entry_type == 'name':
                value = os.path.basename(self.original_path)
            elif entry_type == 'dir':
                value = custom_path  # For directory entries, use the provided path
            else:
                logging.error(f"Unknown entry type: {entry_type}")
                return
                
            # Remove from allow list file
            try:
                with open(allow_list_file, "r") as f:
                    lines = f.readlines()
                
                with open(allow_list_file, "w") as f:
                    for line in lines:
                        line_entry = line.strip()
                        if line_entry.lower() != value.lower():
                            f.write(line)
                
                # Reload the allow list
                parent_app.reload_allow_list()
                logging.info(f"Removed from allow list: {value}")
                
                # Check if the process is still allowed by other rules
                path_lower = self.original_path.lower().replace("/", "\\").rstrip("\\")
                process_name_lower = os.path.basename(path_lower)
                
                still_allowed = False
                for entry in parent_app.allow_list:
                    entry_lower = entry.lower().replace("/", "\\").rstrip("\\")
                    if entry_lower == path_lower or entry_lower == process_name_lower:
                        still_allowed = True
                        break
                    # Check for directory match
                    if path_lower.startswith(entry_lower + "\\"):
                        still_allowed = True
                        break
                
                # Update status flags
                self.is_allowed = still_allowed
                self.update_status_indicators()
            except Exception as e:
                logging.error(f"Failed to remove from allow list: {e}")
                
        except Exception as e:
            logging.error(f"Error in remove_from_allowlist: {e}")
                
    def on_context_menu_closed(self):
        """Handle context menu closing."""
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QRect, QTimer
    
        # Reset context menu active flag
        self.context_menu_active = False
    
        # Check actual hover state using cursor position
        cursor_pos = QApplication.desktop().cursor().pos()
        widget_geometry = self.geometry()
        widget_global_rect = QRect(self.mapToGlobal(widget_geometry.topLeft()), 
                            self.mapToGlobal(widget_geometry.bottomRight()))

        # Update hover state based on whether cursor is actually over the widget
        self.is_hovered = widget_global_rect.contains(cursor_pos)

        # Reset style based on actual hover state
        self.setStyleSheet(self.get_style(self.is_hovered))

        # Handle state based on hover state and expanded mode
        if not self.is_hovered:
            # Only collapse if not in expanded view AND not pinned
            if not self.expanded and not self.is_pinned:
                self.collapse()
    
            # Force fade animation to stop first
            self.fade_animation.stop()
            self.setWindowOpacity(1.0)
    
            # Don't start fade timer if pinned
            if not self.is_pinned:
                # Use a consistent approach for both expanded and collapsed view
                # Define a common delay for both modes
                fade_delay = 3000  # 3 seconds delay
        
                if self.expanded:
                    # In expanded view, we need to start the fade directly
                    def start_expanded_fade():
                        # Only proceed if still not hovered, not in menu, and not pinned
                        if not self.is_hovered and not self.context_menu_active and not self.is_pinned:
                            self.fade_animation.start()
            
                    # Use our consistent delay
                    QTimer.singleShot(fade_delay, start_expanded_fade)
                else:
                    # In collapsed view, manually start the fade after the same delay
                    # instead of using the normal fade timer
                    def start_collapsed_fade():
                        # Only proceed if still not hovered, not in menu, and not pinned
                        if not self.is_hovered and not self.context_menu_active and not self.is_pinned:
                            self.fade_animation.start()
            
                    # Use the same delay for consistency
                    QTimer.singleShot(fade_delay, start_collapsed_fade)

        # Force an immediate update of all notification positions
        if self.parent():
            self.parent().update_positions()
            # Schedule another update after a short delay to ensure proper layout
            QTimer.singleShot(300, self.parent().update_positions)
        
    def open_path(self):
        """Open the file location when clicked."""
        try:
            directory = os.path.dirname(self.original_path)
            os.startfile(directory)
        except Exception as e:
            logging.error(f"Error opening path: {e}")

    def set_expanded_state(self, expanded):
        """Handle changes in expanded state"""
        self.expanded = expanded
        if expanded:
            self.expand()
            # Stop any ongoing fade
            self.fade_animation.stop()
            self.setWindowOpacity(1.0)
            # Don't start the fade timer in expanded view
            self.fade_timer.stop()
        else:
            # Don't collapse if pinned
            if not self.is_pinned:
                self.collapse()
                # Restart the fade timer when going back to collapsed view
                if not self.is_hovered:
                    self.fade_timer.start(self.customization['display_time'])       
    
    def calculate_required_width(self):
        """
        Calculate the width needed to display the full content, considering
        text width, icon size, padding, and screen constraints.
        """
        # Get font metrics for each label accounting for different font sizes
        name_metrics = self.name_label.fontMetrics()
        path_metrics = self.path_label.fontMetrics()
        pid_metrics = self.pid_label.fontMetrics()

        # Calculate the width of each text component
        name_width = name_metrics.horizontalAdvance(self.name or "")
        path_width = path_metrics.horizontalAdvance(self.original_path or "")
        pid_width = pid_metrics.horizontalAdvance(self.pid or "")

        # Determine the maximum content width
        content_width = max(name_width, path_width, pid_width)

        # Get layout margins
        content_layout = self.content_container.layout()
        margins = content_layout.contentsMargins()
        margin_left = margins.left()
        margin_right = margins.right()

        # Calculate total padding including icon, margins, and spacing
        icon_width = 32  # icon width
        layout_spacing = content_layout.spacing()
        total_padding = icon_width + margin_left + margin_right + layout_spacing 

        # Calculate total width needed
        total_width = content_width + total_padding

        # Get screen width
        screen = QApplication.primaryScreen().geometry()
        max_width = screen.width() - 20  # Allow for a small screen margin

        # Ensure the width is within the allowed range
        return min(max(total_width, self.collapsed_width), max_width)
        
    def request_removal(self):
        """Safely request removal from the notification manager"""
        if self.isVisible():  # Only request removal if still visible
            # Force update positions when being removed
            # This ensures spaces are filled properly
            if self.parent():
                self.parent().update_positions()
            self.removal_requested.emit(self)
            self.hide()
        
    def start_fade(self):
        """Start the fade animation if not hovered and not pinned"""
        # Don't fade if pinned
        if self.is_pinned:
            return
    
        # Modified to ignore expanded state - always fade when timer triggers
        if not self.is_hovered and not self.context_menu_active:
            self.fade_timer.stop()
            self.fade_animation.start()

    def closeEvent(self, event):
        # Clean up timers
        if hasattr(self, 'fade_timer'):
            self.fade_timer.stop()
            self.fade_timer.deleteLater()
        if hasattr(self, 'fade_animation'):
            self.fade_animation.stop()
            self.fade_animation.deleteLater()
        if hasattr(self, 'click_timer'):  # Add cleanup for click_timer
            self.click_timer.stop()
            self.click_timer.deleteLater()
        if hasattr(self, 'icon_label'):
            self.icon_label.clear()
            self.icon_label.deleteLater()
        
        self.icon_label = None
        self.name_label = None
        self.path_label = None
        self.pid_label = None
        self.blocked_dot = None
        self.allowed_dot = None
        
        super().closeEvent(event)
            
    def isDestroyed(self):
        try:
            return not self.isVisible() and not self.parent()
        except RuntimeError:
            return True    
    
    def expand(self):
        """Expand the notification without hover."""
        self.text_container.show()
        self.path_label.setText(self.original_path)

        # Force the text container to update its size
        self.text_container.adjustSize()

        # Recalculate required width based on current content
        new_width = self.calculate_required_width()

        # Update the full width if needed
        if new_width > self.full_width:
            self.full_width = new_width

        # Calculate new position for expansion
        current_pos = self.pos()
        screen = QDesktopWidget().screenGeometry()

        # Get margin from parent if available
        margin_right = 4  # Default
        if self.parent() and hasattr(self.parent(), 'margin_right'):
            margin_right = self.parent().margin_right

        new_x = screen.width() - self.full_width - margin_right

        # Update width and position
        self.setFixedWidth(self.full_width)
        self.move(new_x, current_pos.y())

    def collapse(self):
        """Collapse the notification."""
        self.text_container.hide()

        # Calculate new position for collapse
        current_pos = self.pos()
        screen = QDesktopWidget().screenGeometry()

        # Get margin from parent if available
        margin_right = 4  # Default
        if self.parent() and hasattr(self.parent(), 'margin_right'):
            margin_right = self.parent().margin_right

        new_x = screen.width() - self.collapsed_width - margin_right

        # Update width and position
        self.setFixedWidth(self.collapsed_width)
        self.move(new_x, current_pos.y())
        
    def enterEvent(self, event):
        """Handle mouse enter events"""
        # Already highlighted if context menu is active
        if self.context_menu_active:
            event.ignore()
            return
            
        self.is_hovered = True
        self.setStyleSheet(self.get_style(True))
        self.fade_timer.stop()
        self.fade_animation.stop()
        self.setWindowOpacity(1.0)

        # If not in expanded view, expand on hover
        if not self.expanded:
            self.expand()

        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leave events"""
        # If context menu is active, don't change hover state
        if self.context_menu_active:
            event.ignore()
            return
        
        self.is_hovered = False
        self.setStyleSheet(self.get_style(False))

        # Don't collapse if the context menu is active or notification is pinned
        if not self.context_menu_active and not self.is_pinned:
            # If not in expanded view, collapse on mouse leave
            if not self.expanded:
                self.collapse()

            # Restart fade timer if not pinned
            if not self.is_pinned:
                self.fade_timer.start(self.customization['display_time'])

            # Always update positions when mouse leaves, regardless of expanded state
            # This ensures notifications fill empty spaces even in expanded view
            if self.parent():
                # Use a short delay to ensure hover state is fully updated
                QTimer.singleShot(100, self.parent().update_positions)

        super().leaveEvent(event)