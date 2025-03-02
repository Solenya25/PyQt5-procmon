import os
import json
import logging
import traceback
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QCheckBox, QPushButton, QColorDialog, QFormLayout, QTabWidget,
    QWidget, QGroupBox, QComboBox, QDialogButtonBox, QMessageBox,
    QSlider, QFontComboBox, QDoubleSpinBox, QRadioButton
)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QColor, QFont, QPixmap, QPainter
from utils.config import AppConfig

class ColorButton(QPushButton):
    """Custom button for color selection."""
    def __init__(self, color, parent=None):
        super().__init__(parent)
        # Set a unique object name to target this specific button
        self.setObjectName("colorSelectButton")
        self.setColor(color)
        self.clicked.connect(self.selectColor)
        # Fixed size to make it more consistent
        self.setMinimumWidth(120)
        self.setMinimumHeight(30)
        
    def setColor(self, color):
        """Set the button color and update display."""
        if isinstance(color, str):
            # Handle rgba format strings like "rgba(40, 40, 40, 255)"
            if color.startswith("rgba("):
                try:
                    # Extract values from rgba format
                    values = color.replace("rgba(", "").replace(")", "").split(",")
                    r = int(values[0].strip())
                    g = int(values[1].strip())
                    b = int(values[2].strip())
                    a = int(values[3].strip())
                    self.color = QColor(r, g, b, a)
                except (IndexError, ValueError) as e:
                    logging.error(f"Error parsing rgba color: {color} - {e}")
                    self.color = QColor(color)  # Fallback
            else:
                self.color = QColor(color)
        else:
            self.color = color
            
        # Set background color of button - use RGB for display
        r, g, b, a = self.color.getRgb()
        background_color = f"rgb({r}, {g}, {b})"
        text_color = self.contrastColor(self.color).name()
        
        # Use very specific selector to target only this button
        # First reset any existing styling
        self.setStyleSheet("")
        
        # Apply new styling with highly specific selector
        self.setStyleSheet(f"""
            QPushButton#colorSelectButton {{
                background-color: {background_color}; 
                color: {text_color};
                padding: 5px;
                border: 1px solid #888888;
            }}
        """)
        
        # Show the color value as text in HTML format
        self.setText(self.color.name().upper())
        
    def contrastColor(self, color):
        """Return black or white depending on which provides better contrast."""
        luminance = (0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()) / 255
        return QColor(0, 0, 0) if luminance > 0.5 else QColor(255, 255, 255)
        
    def selectColor(self):
        """Open color dialog and update color if accepted."""
        current_color = self.color
        
        # Use alpha channel if the current color has it
        options = QColorDialog.ColorDialogOption.ShowAlphaChannel if current_color.alpha() < 255 else QColorDialog.ColorDialogOption(0)
        
        color = QColorDialog.getColor(current_color, self, "Select Color", options)
        if color.isValid():
            # If original color had alpha and new one doesn't, preserve alpha
            if current_color.alpha() < 255 and color.alpha() == 255:
                color.setAlpha(current_color.alpha())
            self.setColor(color)
            
    def getColor(self):
        """Return the current color in HTML format."""
        return self.color.name().upper()

class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.resize(500, 500)  # Reasonable starting size

        # Flag to track if we've applied settings
        self.settings_applied = False
        self.settings_changed = False

        # Ensure dialog is deleted when closed
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        # Create main layout
        main_layout = QVBoxLayout(self)

        # Create tab widget for better organization
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Create tabs - with better naming and structure
        self.appearance_tab = QWidget()
        self.behavior_tab = QWidget()
        self.status_tab = QWidget()

        self.tab_widget.addTab(self.appearance_tab, "Colors & Appearance")
        self.tab_widget.addTab(self.behavior_tab, "Behavior & Timing")
        self.tab_widget.addTab(self.status_tab, "Status Indicators")

        # Set up each tab
        self.setup_appearance_tab()
        self.setup_behavior_tab()
        self.setup_status_tab()

        # Add custom buttons instead of using QDialogButtonBox
        button_layout = QHBoxLayout()

        # Create buttons manually for better control
        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Cancel")
        self.apply_button = QPushButton("Apply")
        self.reset_button = QPushButton("Reset")

        # Connect signals
        self.ok_button.clicked.connect(self.on_ok_clicked)
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        self.apply_button.clicked.connect(self.apply_settings)
        self.reset_button.clicked.connect(self.reset_settings)

        # Add buttons to layout
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.reset_button)

        main_layout.addLayout(button_layout)

        # Initialize fields with current config
        self.load_current_settings()

        # Setup change tracking
        self.track_changes()

        # Prevent dialog from accepting the enter key as OK
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setModal(True)  # Make dialog modal
    
    def setup_appearance_tab(self):
        """Setup the appearance tab with color settings and text options."""
        layout = QVBoxLayout(self.appearance_tab)

        # Colors group
        colors_group = QGroupBox("Colors")
        colors_layout = QFormLayout()

        self.bg_color_btn = ColorButton(self.config.notification_style.get("background_color", "#282828"))
        self.hover_bg_color_btn = ColorButton(self.config.notification_style.get("hover_background_color", "#3C3C3C"))
        self.elevated_bg_color_btn = ColorButton(self.config.notification_style.get("elevated_background_color", "#DC641E"))
        self.elevated_hover_bg_color_btn = ColorButton(self.config.notification_style.get("elevated_hover_background_color", "#E67828"))
        self.border_color_btn = ColorButton(self.config.notification_style.get("border_color", "#505050"))
        self.pin_border_color_btn = ColorButton(self.config.notification_style.get("pin_border_color", "#FFD700"))
        self.text_color_btn = ColorButton(self.config.notification_style.get("text_color", "#FFFFFF"))

        colors_layout.addRow("Background Color:", self.bg_color_btn)
        colors_layout.addRow("Hover Background Color:", self.hover_bg_color_btn)
        colors_layout.addRow("Elevated Background Color:", self.elevated_bg_color_btn)
        colors_layout.addRow("Elevated Hover Background Color:", self.elevated_hover_bg_color_btn)
        colors_layout.addRow("Border Color:", self.border_color_btn)
        colors_layout.addRow("Pinned Border Color:", self.pin_border_color_btn)
        colors_layout.addRow("Text Color:", self.text_color_btn)

        colors_group.setLayout(colors_layout)
        layout.addWidget(colors_group)

        # Text options group
        text_group = QGroupBox("Text Options")
        text_layout = QFormLayout()

        # Create font size controls for different elements
        self.font_size_name_spin = QSpinBox()
        self.font_size_name_spin.setRange(8, 24)
        self.font_size_name_spin.setValue(int(self.config.notification_style.get("font_size_name", "14px").replace("px", "")))

        self.font_size_path_spin = QSpinBox()
        self.font_size_path_spin.setRange(8, 24)
        self.font_size_path_spin.setValue(int(self.config.notification_style.get("font_size_path", "12px").replace("px", "")))

        self.font_size_pid_spin = QSpinBox()
        self.font_size_pid_spin.setRange(8, 24)
        self.font_size_pid_spin.setValue(int(self.config.notification_style.get("font_size_pid", "12px").replace("px", "")))

        self.border_radius_spin = QSpinBox()
        self.border_radius_spin.setRange(0, 20)
        self.border_radius_spin.setValue(int(self.config.notification_style.get("border_radius", "10px").replace("px", "")))

        text_layout.addRow("Process Name Font Size (px):", self.font_size_name_spin)
        text_layout.addRow("Path Font Size (px):", self.font_size_path_spin)
        text_layout.addRow("PID Font Size (px):", self.font_size_pid_spin)
        text_layout.addRow("Border Radius (px):", self.border_radius_spin)

        text_group.setLayout(text_layout)
        layout.addWidget(text_group)

        # Prevent stretching
        layout.addStretch()
    
    def setup_behavior_tab(self):
        """Setup the behavior tab with timing and notification count settings."""
        layout = QVBoxLayout(self.behavior_tab)

        # Timing group
        timing_group = QGroupBox("Timing")
        timing_layout = QFormLayout()

        self.display_time_spin = QSpinBox()
        self.display_time_spin.setRange(1000, 30000)
        self.display_time_spin.setSingleStep(500)
        self.display_time_spin.setSuffix(" ms")
        self.display_time_spin.setValue(self.config.notification_style.get("display_time", 5000))

        self.fade_duration_spin = QSpinBox()
        self.fade_duration_spin.setRange(500, 10000)
        self.fade_duration_spin.setSingleStep(100)
        self.fade_duration_spin.setSuffix(" ms")
        self.fade_duration_spin.setValue(self.config.notification_style.get("fade_duration", 2000))

        self.poll_interval_spin = QDoubleSpinBox()
        self.poll_interval_spin.setRange(0.1, 5.0)
        self.poll_interval_spin.setSingleStep(0.1)
        self.poll_interval_spin.setSuffix(" sec")
        self.poll_interval_spin.setValue(self.config.settings.get("poll_interval", 0.5))

        timing_layout.addRow("Display Time:", self.display_time_spin)
        timing_layout.addRow("Fade Duration:", self.fade_duration_spin)
        timing_layout.addRow("Poll Interval:", self.poll_interval_spin)

        timing_group.setLayout(timing_layout)
        layout.addWidget(timing_group)

        # Notification limits group
        limits_group = QGroupBox("Notification Limits")
        limits_layout = QFormLayout()

        self.max_notifications_spin = QSpinBox()
        self.max_notifications_spin.setRange(5, 100)
        self.max_notifications_spin.setValue(self.config.settings.get("max_notifications", 20))

        limits_layout.addRow("Maximum Notifications:", self.max_notifications_spin)

        limits_group.setLayout(limits_layout)
        layout.addWidget(limits_group)

        # Position group
        position_group = QGroupBox("Screen Position")
        position_layout = QFormLayout()

        self.margin_right_spin = QSpinBox()
        self.margin_right_spin.setRange(0, 500)
        self.margin_right_spin.setSuffix(" px")
        self.margin_right_spin.setValue(self.config.settings.get("margin_right", 4))

        self.margin_bottom_spin = QSpinBox()
        self.margin_bottom_spin.setRange(0, 500)
        self.margin_bottom_spin.setSuffix(" px")
        self.margin_bottom_spin.setValue(self.config.settings.get("margin_bottom", 50))

        position_layout.addRow("Distance from Right:", self.margin_right_spin)
        position_layout.addRow("Distance from Bottom:", self.margin_bottom_spin)

        position_group.setLayout(position_layout)
        layout.addWidget(position_group)

        # Prevent stretching
        layout.addStretch()
        
    def setup_status_tab(self):
        """Setup the status indicators tab."""
        layout = QVBoxLayout(self.status_tab)
        
        # Status indicators group
        indicators_group = QGroupBox("Status Indicators")
        indicators_layout = QFormLayout()
        
        self.show_indicators_check = QCheckBox("Show Status Indicators")
        self.show_indicators_check.setChecked(self.config.notification_style.get("show_status_indicators", True))
        
        self.status_dot_size_spin = QSpinBox()
        self.status_dot_size_spin.setRange(4, 16)
        self.status_dot_size_spin.setValue(self.config.notification_style.get("status_dot_size", 8))
        
        self.blocked_dot_color_btn = ColorButton(self.config.notification_style.get("blocked_dot_color", "#FF0000"))
        self.allowed_dot_color_btn = ColorButton(self.config.notification_style.get("allowed_dot_color", "#00CC00"))
        
        indicators_layout.addRow("", self.show_indicators_check)
        indicators_layout.addRow("Dot Size (px):", self.status_dot_size_spin)
        indicators_layout.addRow("Blocked Indicator Color:", self.blocked_dot_color_btn)
        indicators_layout.addRow("Allowed Indicator Color:", self.allowed_dot_color_btn)
        
        indicators_group.setLayout(indicators_layout)
        layout.addWidget(indicators_group)
        
        # Prevent stretching
        layout.addStretch()

    def track_changes(self):
        """Connect to change signals to track when settings are modified."""
        # Color buttons
        self.bg_color_btn.clicked.connect(self.mark_settings_changed)
        self.hover_bg_color_btn.clicked.connect(self.mark_settings_changed)
        self.elevated_bg_color_btn.clicked.connect(self.mark_settings_changed)
        self.elevated_hover_bg_color_btn.clicked.connect(self.mark_settings_changed)
        self.border_color_btn.clicked.connect(self.mark_settings_changed)
        self.pin_border_color_btn.clicked.connect(self.mark_settings_changed)
        self.text_color_btn.clicked.connect(self.mark_settings_changed)
        self.blocked_dot_color_btn.clicked.connect(self.mark_settings_changed)
        self.allowed_dot_color_btn.clicked.connect(self.mark_settings_changed)

        # Spinboxes
        self.font_size_name_spin.valueChanged.connect(self.mark_settings_changed)
        self.font_size_path_spin.valueChanged.connect(self.mark_settings_changed)
        self.font_size_pid_spin.valueChanged.connect(self.mark_settings_changed)
        self.border_radius_spin.valueChanged.connect(self.mark_settings_changed)
        self.display_time_spin.valueChanged.connect(self.mark_settings_changed)
        self.fade_duration_spin.valueChanged.connect(self.mark_settings_changed)
        self.poll_interval_spin.valueChanged.connect(self.mark_settings_changed)
        self.max_notifications_spin.valueChanged.connect(self.mark_settings_changed)
        self.status_dot_size_spin.valueChanged.connect(self.mark_settings_changed)
        self.margin_right_spin.valueChanged.connect(self.mark_settings_changed)
        self.margin_bottom_spin.valueChanged.connect(self.mark_settings_changed)

        # Checkboxes
        self.show_indicators_check.stateChanged.connect(self.mark_settings_changed)

    def mark_settings_changed(self):
        """Mark that settings have been changed but not yet applied."""
        self.settings_changed = True

    def load_current_settings(self):
        """Load current settings into the UI components."""
        try:
            # Load appearance settings
            self.bg_color_btn.setColor(self.config.notification_style.get("background_color", "#282828"))
            self.hover_bg_color_btn.setColor(self.config.notification_style.get("hover_background_color", "#3C3C3C"))
            self.elevated_bg_color_btn.setColor(self.config.notification_style.get("elevated_background_color", "#DC641E"))
            self.elevated_hover_bg_color_btn.setColor(self.config.notification_style.get("elevated_hover_background_color", "#E67828"))
            self.border_color_btn.setColor(self.config.notification_style.get("border_color", "#505050"))
            self.pin_border_color_btn.setColor(self.config.notification_style.get("pin_border_color", "#FFD700"))
            self.text_color_btn.setColor(self.config.notification_style.get("text_color", "#FFFFFF"))

            # Load font settings for different elements
            font_size_name = self.config.notification_style.get("font_size_name", "14px")
            if isinstance(font_size_name, str) and font_size_name.endswith("px"):
                font_size_name = font_size_name.replace("px", "")
            self.font_size_name_spin.setValue(int(font_size_name))

            font_size_path = self.config.notification_style.get("font_size_path", "12px")
            if isinstance(font_size_path, str) and font_size_path.endswith("px"):
                font_size_path = font_size_path.replace("px", "")
            self.font_size_path_spin.setValue(int(font_size_path))

            font_size_pid = self.config.notification_style.get("font_size_pid", "12px")
            if isinstance(font_size_pid, str) and font_size_pid.endswith("px"):
                font_size_pid = font_size_pid.replace("px", "")
            self.font_size_pid_spin.setValue(int(font_size_pid))

            border_radius = self.config.notification_style.get("border_radius", "10px")
            if isinstance(border_radius, str) and border_radius.endswith("px"):
                border_radius = border_radius.replace("px", "")
            self.border_radius_spin.setValue(int(border_radius))

            # Load timing settings
            self.display_time_spin.setValue(self.config.notification_style.get("display_time", 5000))
            self.fade_duration_spin.setValue(self.config.notification_style.get("fade_duration", 2000))
            self.poll_interval_spin.setValue(self.config.settings.get("poll_interval", 0.5))

            # Load margins settings
            self.margin_right_spin.setValue(self.config.settings.get("margin_right", 4))
            self.margin_bottom_spin.setValue(self.config.settings.get("margin_bottom", 50))

            # Load notification limits
            self.max_notifications_spin.setValue(self.config.settings.get("max_notifications", 20))

            # Load status indicator settings
            self.show_indicators_check.setChecked(self.config.notification_style.get("show_status_indicators", True))
            self.status_dot_size_spin.setValue(self.config.notification_style.get("status_dot_size", 8))
            self.blocked_dot_color_btn.setColor(self.config.notification_style.get("blocked_dot_color", "#FF0000"))
            self.allowed_dot_color_btn.setColor(self.config.notification_style.get("allowed_dot_color", "#00CC00"))

            # Reset change tracking
            self.settings_changed = False
            self.settings_applied = False   

            logging.debug("Current settings loaded into dialog")
        except Exception as e:
            logging.error(f"Error loading current settings: {e}")
            QMessageBox.warning(self, "Warning", "Could not load all current settings. Default values will be used.")

    def apply_settings(self):
        """Apply the current settings from the dialog to the config."""
        try:
            logging.debug("Applying settings from dialog")

            # Update appearance settings
            self.config.notification_style["background_color"] = self.bg_color_btn.getColor()
            self.config.notification_style["hover_background_color"] = self.hover_bg_color_btn.getColor()
            self.config.notification_style["elevated_background_color"] = self.elevated_bg_color_btn.getColor()
            self.config.notification_style["elevated_hover_background_color"] = self.elevated_hover_bg_color_btn.getColor()
            self.config.notification_style["border_color"] = self.border_color_btn.getColor()
            self.config.notification_style["pin_border_color"] = self.pin_border_color_btn.getColor()
            self.config.notification_style["text_color"] = self.text_color_btn.getColor()

            # Update font settings for different elements
            self.config.notification_style["font_size_name"] = f"{self.font_size_name_spin.value()}px"
            self.config.notification_style["font_size_path"] = f"{self.font_size_path_spin.value()}px"
            self.config.notification_style["font_size_pid"] = f"{self.font_size_pid_spin.value()}px"
            self.config.notification_style["border_radius"] = f"{self.border_radius_spin.value()}px"

            # Margins 
            self.config.settings["margin_right"] = self.margin_right_spin.value()
            self.config.settings["margin_bottom"] = self.margin_bottom_spin.value()

            # Update timing settings
            self.config.notification_style["display_time"] = self.display_time_spin.value()
            self.config.notification_style["fade_duration"] = self.fade_duration_spin.value()
            self.config.settings["poll_interval"] = self.poll_interval_spin.value()

            # Update notification limits
            self.config.settings["max_notifications"] = self.max_notifications_spin.value()

            # Update status indicator settings
            self.config.notification_style["show_status_indicators"] = self.show_indicators_check.isChecked()
            self.config.notification_style["status_dot_size"] = self.status_dot_size_spin.value()
            self.config.notification_style["blocked_dot_color"] = self.blocked_dot_color_btn.getColor()
            self.config.notification_style["allowed_dot_color"] = self.allowed_dot_color_btn.getColor()

            # Apply settings to running components
            if self.parent():
                self.config.apply_settings_to_components(self.parent())

            # Mark that settings have been applied
            self.settings_applied = True
            self.settings_changed = False

            logging.info("Settings applied successfully")
            return True
        except Exception as e:
            logging.error(f"Error applying settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to apply settings: {str(e)}")
            return False

    def on_ok_clicked(self):
        """Apply settings, save, and close dialog."""
        try:
            if self.apply_settings():
                # Save settings to file
                if self.config.save_settings():
                    logging.info("Settings saved successfully")
                else:
                    # Show a warning but still close the dialog
                    logging.warning("Failed to save settings to file")
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "Settings were applied but could not be saved to file.\n"
                        "Changes may be lost when the application restarts."
                    )
                
                # Safely close the dialog without terminating the application
                self.hide()
                self.deleteLater()
        except Exception as e:
            logging.error(f"Error in on_ok_clicked: {e}")
            QMessageBox.critical(self, "Error", f"Failed to apply settings: {str(e)}")

    def on_cancel_clicked(self):
        """Close dialog without applying settings."""
        try:
            # Check if there are unsaved changes
            if self.settings_changed and not self.settings_applied:
                confirm = QMessageBox.question(
                    self, 
                    "Unsaved Changes", 
                    "You have made changes that haven't been applied. Do you want to apply them before closing?",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes
                )

                if confirm == QMessageBox.Yes:
                    # Apply settings but don't save to file
                    if not self.apply_settings():
                        # If apply fails, let user decide whether to continue
                        retry = QMessageBox.question(
                            self,
                            "Apply Failed",
                            "Failed to apply settings. Close anyway?",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.No
                        )
                        if retry == QMessageBox.No:
                            return
                elif confirm == QMessageBox.Cancel:
                    return

            # Safely close the dialog without terminating the application
            self.hide()
            self.deleteLater()
        except Exception as e:
            logging.error(f"Error in on_cancel_clicked: {e}")
            # Make sure we close even if there's an error
            self.hide()
            self.deleteLater()
            
    def closeEvent(self, event):
        """Handle window close button events."""
        try:
            # Check if there are unsaved changes
            if self.settings_changed and not self.settings_applied:
                confirm = QMessageBox.question(
                    self, 
                    "Unsaved Changes", 
                    "You have made changes that haven't been applied. Do you want to apply them before closing?",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes
                )

                if confirm == QMessageBox.Yes:
                    # Apply the changes
                    if not self.apply_settings():
                        # If apply fails, let user decide whether to continue
                        retry = QMessageBox.question(
                            self,
                            "Apply Failed",
                            "Failed to apply settings. Close anyway?",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.No
                        )
                        if retry == QMessageBox.No:
                            # Don't close - ignore the event
                            event.ignore()
                            return
                elif confirm == QMessageBox.Cancel:
                    # Don't close - ignore the event
                    event.ignore()
                    return

            # CRITICAL FIX: We need to ignore the event to prevent propagation
            # Instead, we'll manually hide and schedule deletion
            event.ignore()

            # Hide first, then schedule deletion
            self.hide()
            self.deleteLater()
        except Exception as e:
            logging.error(f"Error in closeEvent: {e}\n{traceback.format_exc()}")
            # In case of error, still hide the dialog
            event.ignore()
            self.hide()
            self.deleteLater()
            
    def reset_settings(self):
        """Reset the dialog to default settings."""
        try:
            confirm = QMessageBox.question(
                self, 
                "Reset Settings", 
                "Are you sure you want to reset all settings to defaults?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
        
            if confirm == QMessageBox.Yes:
                # Create a new AppConfig that will initialize with default values
                default_config = AppConfig()
            
                # Skip loading from file to get true defaults
                default_config.load_settings = lambda: None
            
                # Call init again to set defaults after preventing file loading
                default_config.__init__()
            
                # Copy default values to our actual config
                self.config.settings = default_config.settings.copy()
                self.config.notification_style = default_config.notification_style.copy()
            
                # Re-initialize fields with default settings
                self.load_current_settings()

                # Setup change tracking
                self.track_changes()

                # Prevent dialog from accepting the enter key as OK
                self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
                self.setModal(True)  # Make dialog modal
            
                # Apply default settings to the application immediately
                if self.parent():
                    self.config.apply_settings_to_components(self.parent())
            
                logging.info("Settings reset to defaults")
                QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")
                return True
            return False
        except Exception as e:
            logging.error(f"Error resetting settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to reset settings: {str(e)}")
            return False

    def reset_to_original(self):
        """Reset to the original settings that were loaded when the dialog opened."""
        try:
            # This just reloads the settings from the file
            self.config.load_settings()
        
            # Apply the loaded settings to running application
            if self.parent():
                self.config.apply_settings_to_components(self.parent())
        except Exception as e:
            logging.error(f"Error resetting to original settings: {e}")
            QMessageBox.warning(self, "Warning", "Could not reset to original settings. Some changes may persist.")
            
    def cleanup_resources(self):
        """Clean up all resources to prevent memory leaks."""
        try:
            # Clean up color buttons
            if hasattr(self, 'bg_color_btn'):
                self.bg_color_btn.deleteLater()
            if hasattr(self, 'hover_bg_color_btn'):
                self.hover_bg_color_btn.deleteLater()
            if hasattr(self, 'elevated_bg_color_btn'):
                self.elevated_bg_color_btn.deleteLater()
            if hasattr(self, 'elevated_hover_bg_color_btn'):
                self.elevated_hover_bg_color_btn.deleteLater()
            if hasattr(self, 'border_color_btn'):
                self.border_color_btn.deleteLater()
            if hasattr(self, 'pin_border_color_btn'):
                self.pin_border_color_btn.deleteLater()
            if hasattr(self, 'blocked_dot_color_btn'):
                self.blocked_dot_color_btn.deleteLater()
            if hasattr(self, 'allowed_dot_color_btn'):
                self.allowed_dot_color_btn.deleteLater()

            # Set all references to None to help garbage collection
            self.bg_color_btn = None
            self.hover_bg_color_btn = None
            self.elevated_bg_color_btn = None
            self.elevated_hover_bg_color_btn = None
            self.border_color_btn = None
            self.pin_border_color_btn = None
            self.blocked_dot_color_btn = None
            self.allowed_dot_color_btn = None

            logging.debug("Settings dialog resources cleaned up")
        except Exception as e:
            logging.error(f"Error cleaning up settings dialog resources: {e}")