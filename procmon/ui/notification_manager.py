import logging
import time
import traceback
from PyQt5.QtWidgets import QWidget, QDesktopWidget
from PyQt5.QtCore import QTimer
from ui.notification import NotificationWidget

class NotificationManager(QWidget):
    def __init__(self, parent=None):
        """Initialize the NotificationManager with defaults and parent configuration if available."""
        super().__init__(parent)
        logging.debug("Initializing NotificationManager...")
        
        # Initialize default values
        self.notifications = []
        self.spacing = 2
        self.margin_right = 4
        self.margin_bottom = 50
        self.max_notifications = 30
        self.notification_times = []
        self.rate_limit = 10
        
        # Store configuration if parent is valid
        self.config = None
        try:
            if parent is not None and hasattr(parent, 'config'):
                self.config = parent.config
                
                # Override defaults with config values if available
                if hasattr(self.config, 'settings'):
                    self.max_notifications = self.config.settings.get('max_notifications', self.max_notifications)
                    
            logging.debug("NotificationManager initialized successfully.")
        except Exception as e:
            logging.warning(f"Error accessing parent config: {e}")
            # Continue with default values

    def find_empty_spaces(self):
        """Find all empty spaces between notifications"""
        if not self.notifications:
            return []

        screen = QDesktopWidget().screenGeometry()
        bottom_y = screen.height() - self.margin_bottom
        empty_spaces = []
        
        # Get visible notifications sorted by Y position (top to bottom)
        visible_notifications = sorted(
            [n for n in self.notifications if n.isVisible()],
            key=lambda n: n.y()
        )
        
        if not visible_notifications:
            return []

        # Check for gaps between notifications
        expected_y = bottom_y
        for notification in reversed(visible_notifications):
            current_y = notification.y()
            expected_position = expected_y - notification.height()
            
            if current_y > expected_position:
                # Found a gap
                empty_spaces.append({
                    'y': expected_position,
                    'height': notification.height(),
                    'size': current_y - expected_position
                })
            
            expected_y = current_y - self.spacing

        return empty_spaces

    def fill_empty_space(self, empty_space):
        """Fill an empty space with the lowest non-hovered notification above it"""
        visible_notifications = [n for n in self.notifications if n.isVisible()]
        
        # Find the lowest non-hovered notification above the empty space
        candidate = None
        for notification in visible_notifications:
            if (not notification.is_hovered and 
                notification.y() < empty_space['y'] and
                (candidate is None or notification.y() > candidate.y())):
                candidate = notification

        if candidate:
            width = (candidate.full_width if candidate.expanded 
                    else candidate.collapsed_width)
            x_position = QDesktopWidget().screenGeometry().width() - width - self.margin_right
            candidate.move(x_position, empty_space['y'])
            return True
            
        return False

    def get_occupied_spaces(self):
        """Get all spaces occupied by visible notifications, including hovered ones"""
        occupied_spaces = []
        for notification in self.notifications:
            if notification.isVisible():
                occupied_spaces.append({
                    'y': notification.y(),
                    'height': notification.height(),
                    'is_hovered': notification.is_hovered
                })
        return occupied_spaces

    def raise_notifications(self):
        """Ensure all notifications stay on top"""
        for notification in self.notifications:
            if notification.isVisible():
                notification.raise_()

    def remove_notification(self, notification):
        """Safely remove a notification with additional checks"""
        try:
            if notification in self.notifications:
                # First hide the notification if it's still visible
                if notification.isVisible():
                    notification.hide()
            
                # Remove from our list
                self.notifications.remove(notification)
            
                # Schedule deletion for the next event loop iteration
                notification.deleteLater()
                
                # Update positions after a short delay
                QTimer.singleShot(200, self.update_positions)
            
        except RuntimeError as e:
            logging.warning(f"RuntimeError during notification removal: {e}")
        except Exception as e:
            logging.error(f"Error removing notification: {e}")

    def add_notification(self, icon, message, is_elevated=False):
        try:
            # Rate limiting check
            current_time = time.time()
            self.notification_times = [t for t in self.notification_times 
                                    if current_time - t < 1.0]

            if len(self.notification_times) >= self.rate_limit:
                logging.warning("Notification rate limit exceeded")
                return
    
            self.notification_times.append(current_time)

            # Remove oldest notifications if we exceed the maximum
            while len(self.notifications) >= self.max_notifications:
                oldest = min(self.notifications, key=lambda n: n.creation_time)
                self.remove_notification(oldest)
    
            # Determine expanded view setting 
            expanded_view = False
            if self.config is not None:
                expanded_view = getattr(self.config, 'expanded_view', False)
            
            # Create new notification without relying on parent's config
            notification_style = {}
            if self.config is not None:
                notification_style = getattr(self.config, 'notification_style', {})
            
            # Create the notification with all necessary info
            notification = NotificationWidget(
                icon, 
                message, 
                parent=self, 
                expanded=expanded_view,
                is_elevated=is_elevated,
                notification_style=notification_style
            )
    
            # Connect the removal signal
            notification.removal_requested.connect(self.remove_notification)

            # Add to list and position
            self.notifications.append(notification)

            # Get the screen dimensions
            screen = QDesktopWidget().screenGeometry()

            # Get width based on expansion state
            width = notification.full_width if expanded_view else notification.collapsed_width

            # Calculate X position
            x_position = screen.width() - width - self.margin_right

            # Initially position off-screen at the top
            notification.move(x_position, -notification.height())
        
            # If in expanded view, make sure it's expanded before showing
            if expanded_view:
                notification.expand()

            notification.show()
            notification.raise_()
        
            # Update positions after adding the new notification
            QTimer.singleShot(50, self.update_positions)
        
            return notification
        
        except Exception as e:
            logging.error(f"Error creating notification: {e}")
            return None

    def update_positions(self):
        """Update positions of remaining notifications with smoother transitions"""
        try:
            if not self.notifications:
                return

            screen = QDesktopWidget().screenGeometry()
            bottom_y = screen.height() - self.margin_bottom
        
            # Get all visible notifications sorted by Y position (bottom to top)
            visible_notifications = sorted(
                [n for n in self.notifications if n.isVisible()],
                key=lambda n: n.y(),
                reverse=True  # Sort from bottom to top
            )
        
            if not visible_notifications:
                return

            # Track the current expected Y position
            expected_y = screen.height() - self.margin_bottom
        
            # Process notifications from bottom to top
            for notification in visible_notifications:
                # Calculate the expected position for this notification
                expected_position = expected_y - notification.height()
            
                # Get the current width based on expanded state
                width = (notification.full_width if notification.expanded 
                        else notification.collapsed_width)
                x_position = screen.width() - width - self.margin_right
            
                # Only move if not hovered and the position difference is significant
                # This prevents small adjustments that cause visual jumpiness
                if (not notification.is_hovered and 
                    (abs(notification.y() - expected_position) > 2 or
                    abs(notification.x() - x_position) > 2)):
                    notification.move(x_position, expected_position)
            
                # Update the expected_y for the next notification, using the actual position
                # of the current notification to maintain correct spacing
                expected_y = notification.y() - self.spacing
    
        except Exception as e:
            logging.error(f"Error updating positions: {e}")