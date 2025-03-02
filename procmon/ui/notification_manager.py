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
        
        # Add notification queue for pending notifications
        self.notification_queue = []
        
        # Add timer to process queued notifications
        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self.process_notification_queue)
        self.queue_timer.start(1000)  # Check queue every second
        
        # Store configuration if parent is valid
        self.config = None
        try:
            if parent is not None and hasattr(parent, 'config'):
                self.config = parent.config
                
                # Override defaults with config values if available
                if hasattr(self.config, 'settings'):
                    self.max_notifications = self.config.settings.get('max_notifications', self.max_notifications)
                    self.margin_right = self.config.settings.get('margin_right', self.margin_right)
                    self.margin_bottom = self.config.settings.get('margin_bottom', self.margin_bottom)
                    
            logging.debug("NotificationManager initialized successfully.")
        except Exception as e:
            logging.warning(f"Error accessing parent config: {e}")
            

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

        # Check for gaps between notifications from bottom up
        expected_y = bottom_y

        for i, notification in enumerate(reversed(visible_notifications)):
            current_y = notification.y()
            expected_position = expected_y - notification.height()
    
            # Rule 3, 4, 7: If the current notification is hovered or has open context menu,
            # don't consider spaces below it for filling
            if notification.is_hovered or getattr(notification, 'context_menu_active', False):
                # Rule 5: Notifications above a hovered/context menu one don't fill spaces below it
                break
                
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

        # Find the lowest notification that's above the empty space
        # Sort by Y position (bottom to top)
        above_notifications = [n for n in visible_notifications if n.y() < empty_space['y']]
        above_notifications.sort(key=lambda n: n.y(), reverse=True)  # Lowest first

        # Find the lowest eligible notification
        candidate = None
        for notification in above_notifications:
            # Rule 4: If the lowest notification above an empty space is being hovered 
            # or has context menu open, don't fill empty spaces below it
            if notification.is_hovered or getattr(notification, 'context_menu_active', False):
                return False

            # Rule 6: Pinned notifications can move but not collapse
            # Skip pinned notifications as candidates to fill spaces
            if getattr(notification, 'is_pinned', False):
                continue
                
            # This is our candidate - the lowest non-special notification above the space
            candidate = notification
            break

        if candidate:
            # Get the appropriate width based on expanded state
            width = candidate.full_width if candidate.expanded else candidate.collapsed_width

            # Calculate the new position
            x_position = QDesktopWidget().screenGeometry().width() - width - self.margin_right

            # Move the notification to fill the empty space
            candidate.move(x_position, empty_space['y'])

            # Log the fill operation for debugging
            logging.debug(f"Filled empty space at y={empty_space['y']} with notification")

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
        """Raise notifications, but only when not interfering with menus"""
        from PyQt5.QtWidgets import QApplication, QMenu
    
        # Skip raising if any popup (like a menu) is active
        active_popup = QApplication.activePopupWidget()
        if active_popup is not None:
            return
    
        # Skip raising if any notification has an active context menu
        for notification in self.notifications:
            if notification.isVisible() and hasattr(notification, 'context_menu_active') and notification.context_menu_active:
                return
            
        # Only if no popups are active, we can safely raise notifications
        for notification in self.notifications:
            if notification.isVisible():
                notification.raise_()
                    
        
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
        
        # Ensure proper state handling based on expanded mode and hover state
        if not self.is_hovered:
            # Only collapse if not in expanded view mode
            if not self.expanded:
                self.collapse()
            
            # Stop any existing fade animation first
            self.fade_animation.stop()
            # Reset opacity to full
            self.setWindowOpacity(1.0)
            # Restart fade timer (in both expanded and collapsed view)
            self.fade_timer.start(self.customization['display_time'])
        
        # Force an immediate update of all notification positions
        if self.parent():
            self.parent().update_positions()
            # Schedule another update after a short delay to ensure proper layout
            QTimer.singleShot(300, self.parent().update_positions)

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
            
                # Force immediate position update, then another after short delay
                self.update_positions()
                QTimer.singleShot(200, self.update_positions)
            
                # Process queued notifications since we've made space
                QTimer.singleShot(300, self.process_notification_queue)
        
        except RuntimeError as e:
            logging.warning(f"RuntimeError during notification removal: {e}")
        except Exception as e:
            logging.error(f"Error removing notification: {e}")
            
    def show_notification(self, notification, system_menu_open=False):
        """Display a notification that's been created"""
        try:
            # Add to list
            if notification not in self.notifications:
                self.notifications.append(notification)

            # Get the screen dimensions
            screen = QDesktopWidget().screenGeometry()

            # Get width based on expansion state
            is_expanded = getattr(notification, 'expanded', False)
            width = notification.full_width if is_expanded else notification.collapsed_width

            # Calculate X position using the configured margin_right
            x_position = screen.width() - width - self.margin_right

            # Rule 1: Find the highest notification (closest to top of screen)
            visible_notifications = [n for n in self.notifications if n != notification and n.isVisible()]

            if visible_notifications:
                # Get the highest (minimal y coordinate) notification
                highest_notification = min(visible_notifications, key=lambda n: n.y())
                highest_y = highest_notification.y()

                # Position the new notification above it
                y_position = highest_y - self.spacing - notification.height()
            else:
                # If no existing notifications, start from the bottom using the configured margin_bottom
                y_position = screen.height() - self.margin_bottom - notification.height()

            # Ensure position is not above the top of the screen
            if y_position < 10:  # 10px minimum margin from top
                y_position = 10

            # Position the notification at the new position
            notification.move(x_position, y_position)

            # If in expanded view, make sure it's expanded before showing
            if getattr(notification, 'expanded', False):
                notification.expand()

            # Show the notification but don't raise it yet
            notification.show()

            # Start the fade timer now that it's being shown
            # but only if it's not pinned
            if not getattr(notification, 'is_pinned', False) and not notification.is_hovered:
                notification.fade_timer.start(notification.customization['display_time'])
    
            # Check for active system tray menu or popups before raising
            from PyQt5.QtWidgets import QApplication, QMenu
    
            active_popup = QApplication.activePopupWidget()
    
            # If system tray menu is open or another popup is active, keep notification below
            if system_menu_open or active_popup is not None:
                # Keep it below all menus - use QApplication.processEvents() to ensure 
                # any pending operations complete before we lower the window
                QApplication.processEvents()
                notification.lower()
        
                # Make sure all active menus stay on top
                for widget in QApplication.topLevelWidgets():
                    if isinstance(widget, QMenu) and widget.isVisible():
                        widget.raise_()
            else:
                # Check for active context menus on notifications
                context_menu_active = False
                for notif in self.notifications:
                    if hasattr(notif, 'context_menu_active') and notif.context_menu_active:
                        context_menu_active = True
                        break
                
                # Only raise if no context menus are active
                if not context_menu_active:
                    notification.raise_()

            # Update positions after adding the new notification
            QTimer.singleShot(50, self.update_positions)

            return notification

        except Exception as e:
            logging.error(f"Error showing notification: {e}")
            if notification and notification in self.notifications:
                self.notifications.remove(notification)
                notification.deleteLater()
            return None

    def add_notification(self, icon, message, is_elevated=False, system_menu_open=False):
        try:
            # Rate limiting check
            current_time = time.time()
            self.notification_times = [t for t in self.notification_times 
                                    if current_time - t < 1.0]

            if len(self.notification_times) >= self.rate_limit:
                logging.warning("Notification rate limit exceeded")
                return None

            self.notification_times.append(current_time)

            # Determine expanded view setting 
            expanded_view = False
            if self.config is not None:
                expanded_view = getattr(self.config, 'expanded_view', False)

            # Create notification style
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

            # Check if we have room to display this notification based on available slots
            # This accounts for both pinned and non-pinned notifications
            available_slots = self.calculate_available_slots()
            if available_slots <= 0:
                # No room - add to queue instead
                logging.info(f"No available slots, queueing notification for: {message.split()[0]}")
                self.notification_queue.append((notification, system_menu_open))

                # Start/restart queue processing timer
                if not self.queue_timer.isActive():
                    self.queue_timer.start(1000)

                return notification
        
            # We have room - display the notification now
            return self.show_notification(notification, system_menu_open)
    
        except Exception as e:
            logging.error(f"Error creating notification: {e}")
            return None
        
    def calculate_available_slots(self):
        """
        Calculate how many more notifications can be displayed based on height constraints.
        Maximum notifications designates a height on the display above which no notifications
        should appear, expressed as a number of notifications.
        """
        try:
            # Get screen dimensions
            screen = QDesktopWidget().screenGeometry()
            top_margin = 10  # Minimum margin from top of screen

            # Get all visible notifications
            visible_notifications = [n for n in self.notifications if n.isVisible()]

            if not visible_notifications:
                return self.max_notifications

            # Get notification height for calculations (height of first notification + spacing)
            notification_height = visible_notifications[0].height() + self.spacing

            # Calculate maximum allowed height from bottom of screen
            max_allowed_height = notification_height * self.max_notifications
            max_y_position = screen.height() - self.margin_bottom - max_allowed_height

            # Ensure max_y_position is not less than top_margin
            max_y_position = max(max_y_position, top_margin)

            # Find hovered or pinned notifications
            special_notifications = [n for n in visible_notifications if 
                                n.is_hovered or 
                                getattr(n, 'is_pinned', False) or
                                getattr(n, 'context_menu_active', False)]

            # If there are special notifications, we need to respect their positions
            if special_notifications:
                # Find the highest (top-most) special notification
                highest_special = min(special_notifications, key=lambda n: n.y())

                # The available space is above the highest special notification
                # No notifications can appear above the max_y_position
                available_height = max(0, highest_special.y() - max_y_position)

                # Count notifications already above the highest special notification
                notifications_above = [n for n in visible_notifications if n.y() < highest_special.y()]
                height_used_above = len(notifications_above) * notification_height

                # Available height after accounting for notifications already above
                remaining_height = max(0, available_height - height_used_above)

                # How many more notifications can fit in the remaining height
                available_slots = remaining_height // notification_height

                return int(available_slots)
            else:
                # Without special notifications, calculate based on total visible
                # Calculate current used height from bottom
                lowest_y = screen.height() - self.margin_bottom
                highest_y = min([n.y() for n in visible_notifications]) if visible_notifications else lowest_y
                total_used_height = lowest_y - highest_y

                # Calculate how much more height is available until max_y_position
                available_height = max(0, highest_y - max_y_position)

                # How many more notifications can fit in the available height
                available_slots = available_height // notification_height

                return int(available_slots)

        except Exception as e:
            logging.error(f"Error calculating available slots: {e}")
            # Conservative fallback
            return 0

    def process_notification_queue(self):
        """Process pending notifications in the queue when space becomes available."""
        try:
            if not self.notification_queue:
                # Stop the timer if there's nothing in the queue
                self.queue_timer.stop()
                return

            # Calculate available slots based on height constraints
            available_slots = self.calculate_available_slots()

            if available_slots <= 0:
                # No slots available, try again later
                return

            # Process as many queued notifications as we have slots for
            for _ in range(min(available_slots, len(self.notification_queue))):
                if not self.notification_queue:
                    break
                    
                # Get the next notification from the queue
                notification, system_menu_open = self.notification_queue.pop(0)

                # If the notification was already destroyed, skip it
                if hasattr(notification, 'isDestroyed') and notification.isDestroyed():
                    continue
                    
                # Show the notification (which will also start the timer)
                self.show_notification(notification, system_menu_open)

                # Recalculate available slots after adding each notification
                available_slots = self.calculate_available_slots()
                if available_slots <= 0:
                    break
                    
            # If queue is now empty, stop the timer
            if not self.notification_queue:
                self.queue_timer.stop()

        except Exception as e:
            logging.error(f"Error processing notification queue: {e}")

    def update_positions(self):
        """Update positions of all notifications from bottom to top."""
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

            # Identify notifications with special status (hovered, context menu open)
            # Rule 3 & 7: These notifications don't move
            special_notifications = [n for n in visible_notifications if 
                        n.is_hovered or 
                        getattr(n, 'context_menu_active', False)]

            # Find the highest position of special notifications
            special_highest_y = None
            if special_notifications:
                special_highest_y = min([n.y() for n in special_notifications])

            # Track the current expected Y position, using the configured margin_bottom
            expected_y = screen.height() - self.margin_bottom

            # Process notifications from bottom to top
            for notification in visible_notifications:
                # Rule 3 & 7: Skip repositioning if context menu is active or being hovered
                if notification.is_hovered or getattr(notification, 'context_menu_active', False):
                    # Update the expected_y for the next notification
                    expected_y = notification.y() - self.spacing
                    continue
                    
                # Calculate the expected position for this notification
                expected_position = expected_y - notification.height()

                # Rule 5: Check if moving this notification would make it pass above a special notification
                # Only applies if notification is below a special one but would move above it
                skip_repositioning = False
                if special_highest_y is not None:
                    for special in special_notifications:
                        if notification.y() > special.y() and expected_position < special.y():
                            skip_repositioning = True
                            break
                            
                if skip_repositioning:
                    # Skip repositioning this notification
                    expected_y = notification.y() - self.spacing
                    continue
                    
                # Rule 6: Pinned notifications can move but stay expanded
                is_pinned = getattr(notification, 'is_pinned', False)
                width = notification.full_width if (notification.expanded or is_pinned) else notification.collapsed_width

                # Use the configured margin_right
                x_position = screen.width() - width - self.margin_right

                # Only move if the position difference is significant
                if (abs(notification.y() - expected_position) > 2 or
                    abs(notification.x() - x_position) > 2):
                    notification.move(x_position, expected_position)

                # Update the expected_y for the next notification
                expected_y = notification.y() - self.spacing

        except Exception as e:
            logging.error(f"Error updating positions: {e}\n{traceback.format_exc()}")