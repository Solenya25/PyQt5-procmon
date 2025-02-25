import os
import traceback
import time
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QDesktopWidget, QHBoxLayout, QApplication
)
from PyQt5.QtCore import QTimer, QPropertyAnimation, pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QPixmap, QColor
from datetime import datetime
import weakref

class NotificationWidget(QWidget):
    removal_requested = pyqtSignal(object) 
    
    def __init__(self, icon, message, parent=None, expanded=False, is_elevated=False, notification_style=None):
        super().__init__(parent)        
        self.expanded = expanded    # Initialize expanded state first
        self.is_elevated = is_elevated  # Set elevation status directly from parameter
                
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
            "background_color": "rgba(40, 40, 40, 255)",
            "border_radius": "10px",
            "font_size": "14px",
            "fade_duration": 2000,
            "display_time": 5000,
            "hover_background_color": "rgba(60, 60, 60, 255)",
            "blocked_background_color": "rgba(139, 0, 0, 255)",  # Dark red for blocked notifications
            "elevated_background_color": "rgba(180, 80, 20, 255)",  # Dark orange for elevated processes
            "elevated_hover_background_color": "rgba(210, 100, 20, 255)",  # Lighter orange for elevated hover
        }
        
        # Update with provided notification style if available
        if notification_style:
            self.customization.update(notification_style)
        
        self.is_hovered = False
        self.is_blocked = False  # Track if the notification is blocked    
        
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
        
        # Start the fade timer regardless of expanded state
        self.fade_timer.start(self.customization['display_time'])

        # Main layout 
        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)  

        # Create a container widget for the entire content
        self.content_container = QWidget()
        self.content_container.setObjectName("content_container")
        
        content_layout = QHBoxLayout(self.content_container)
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(10, 5, 10, 5)  

        # Add icon if available
        icon_size = 32
        if icon and not icon.isNull():
            self.icon_label = QLabel()
            self.icon_label.setFixedSize(icon_size, icon_size)
            icon_pixmap = icon.pixmap(icon_size, icon_size)
            self.icon_label.setPixmap(icon_pixmap)
            content_layout.addWidget(self.icon_label)

        # Message layout
        self.message_layout = QVBoxLayout()
        self.message_layout.setContentsMargins(0, 2, 0, 2)
        self.message_layout.setSpacing(1)

        # Create labels with a container widget
        self.text_container = QWidget()
        text_container_layout = QVBoxLayout(self.text_container)
        text_container_layout.setContentsMargins(0, 0, 0, 0)
        text_container_layout.setSpacing(3)
        
        # Name label
        self.name_label = QLabel(self.name)
        self.name_label.setStyleSheet(f"""
            font-size: {self.customization['font_size']};
            color: white;
            font-weight: bold;
        """)
        self.name_label.setWordWrap(False)
        text_container_layout.addWidget(self.name_label)

        # Path label
        self.path_label = QLabel(self.original_path)
        self.path_label.setStyleSheet("""
            font-size: 12px;
            color: white;
        """)
        self.path_label.setWordWrap(False)
        text_container_layout.addWidget(self.path_label)

        # PID label
        pid_text = self.pid
        if self.is_elevated:
            pid_text += " (Admin)"
        
        self.pid_label = QLabel(pid_text)
        self.pid_label.setStyleSheet(f"""
            font-size: 12px;
            color: white;
        """)
        self.pid_label.setWordWrap(False)
        text_container_layout.addWidget(self.pid_label)

        # Add the text container to the message layout
        self.message_layout.addWidget(self.text_container)
        content_layout.addLayout(self.message_layout)
        content_layout.addStretch()
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
        
        #Creation time
        self.creation_time = datetime.now()
        self._parent_ref = weakref.ref(parent) if parent else None
        
         # Connect mouse press event to handle clicks
        self.content_container.mousePressEvent = self.handle_mouse_press
        
    def handle_mouse_press(self, event):
        """Handle mouse press events."""
        try:
            if event.button() == Qt.LeftButton:
                # Open the file path on left-click
                self.open_path()
            elif event.button() == Qt.RightButton:
                # Add to block list on right-click
                self.toggle_blocklist()
        except Exception as e:
            logging.error(f"Error in handle_mouse_press: {e}")
            
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

            if self.is_blocked:
                # Unblock the process
                try:
                    with open(block_list_file, "r") as f:
                        lines = f.readlines()
                    with open(block_list_file, "w") as f:
                        for line in lines:
                            if line.strip().lower() != self.original_path.lower():
                                f.write(line)
                
                    # Reload the block list
                    parent_app.reload_block_list()
                    logging.info(f"Removed {self.original_path} from the block list.")
                
                    # Change the background color back to normal
                    self.is_blocked = False
                    self.setStyleSheet(self.get_style(self.is_hovered))
                except Exception as e:
                    logging.error(f"Failed to remove {self.original_path} from the block list: {e}")
            else:
                # Block the process by full path
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
                
                    # Change the background color to indicate blocking
                    self.is_blocked = True
                    self.setStyleSheet(self.get_style(self.is_hovered))
                except Exception as e:
                    logging.error(f"Failed to add {self.original_path} to the block list: {e}")
        except Exception as e:
            logging.error(f"Error toggling block list: {e}")

    def open_path(self):
        """Open the file location when clicked."""
        try:
            directory = os.path.dirname(self.original_path)
            os.startfile(directory)
        except Exception as e:
            logging.error(f"Error opening path: {e}")
            
    def get_style(self, hovered):
        """Get the appropriate style based on the state."""
        if self.is_blocked:
            # Blocked notifications are always dark red
            bg_color = self.customization['blocked_background_color']
        elif self.is_elevated:
            # For elevated processes, ensure hover is lighter than normal
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
            
        return f"""
            QWidget {{
                background-color: transparent;
            }}
            QWidget#content_container {{
                background-color: {bg_color};
                border-radius: {self.customization['border_radius']};
            }}
            QLabel {{
                background-color: transparent;
            }}
        """

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
            self.collapse()
            # Restart the fade timer when going back to collapsed view
            if not self.is_hovered:
                self.fade_timer.start(self.customization['display_time'])       
    
    def calculate_required_width(self):
        """
        Calculate the width needed to display the full content, considering
        text width, icon size, padding, and screen constraints.
        """
        # Get font metrics for the label
        metrics = self.path_label.fontMetrics()

        # Calculate the width of each text component
        name_width = metrics.horizontalAdvance(self.name or "")
        path_width = metrics.horizontalAdvance(self.original_path or "")
        pid_width = metrics.horizontalAdvance(self.pid or "")

        # Determine the maximum content width
        content_width = max(name_width, path_width, pid_width)

        # Add icon width and padding (icon: 32px, margins: 20px, spacing: 18px)
        padding = 70
        total_width = content_width + padding

        # Get screen width (using QApplication for PyQt5)
        screen = QApplication.primaryScreen().geometry()
        max_width = screen.width() - 20  # Allow for a small screen margin

        # Ensure the width is within the allowed range
        return min(max(total_width, self.collapsed_width), max_width)
        
    def request_removal(self):
        """Safely request removal from the notification manager"""
        if self.isVisible():  # Only request removal if still visible
            # Update positions before removing to handle any gaps
            self.parent().update_positions()
            self.removal_requested.emit(self)
            self.hide()
        
    def start_fade(self):
        """Start the fade animation if not hovered"""
        if not self.is_hovered:  # Remove the expanded_view check that was preventing fade
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
        if hasattr(self, 'icon_label'):
            self.icon_label.clear()
            self.icon_label.deleteLater()
            
        self.icon_label = None
        self.name_label = None
        self.path_label = None
        self.pid_label = None   
            
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
        
        # Calculate new position for expansion
        current_pos = self.pos()
        screen = QDesktopWidget().screenGeometry()
        new_x = screen.width() - self.full_width - 4
        
        # Update width and position
        self.setFixedWidth(self.full_width)
        self.move(new_x, current_pos.y())
        
    def collapse(self):
        """Collapse the notification."""
        self.text_container.hide()
        
        # Calculate new position for collapse
        current_pos = self.pos()
        screen = QDesktopWidget().screenGeometry()
        new_x = screen.width() - self.collapsed_width - 4
        
        # Update width and position
        self.setFixedWidth(self.collapsed_width)
        self.move(new_x, current_pos.y())

        
    def enterEvent(self, event):
        """Handle mouse enter events"""
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
        self.is_hovered = False
        self.setStyleSheet(self.get_style(False))

        # If not in expanded view, collapse on mouse leave
        if not self.expanded:
            self.collapse()

        # Restart fade timer
        self.fade_timer.start(self.customization['display_time'])

        # Trigger immediate position update only if necessary
        # This reduces unnecessary position updates
        if self.parent() and not self.expanded:
            QTimer.singleShot(100, self.parent().update_positions)

        super().leaveEvent(event)