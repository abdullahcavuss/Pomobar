import sys
import json
from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QPainter, QPen, QFont, QColor
from PyQt5.QtWidgets import QApplication, QWidget, QDesktopWidget, QPushButton, QDialog, QLabel, QVBoxLayout, QSpinBox, QHBoxLayout, QColorDialog

class LinearProgressBar(QWidget):
    CONFIG_FILE = "progressbar_config.json"  # Configuration file name

    def __init__(self):
        super().__init__()
        # Initialize work and break durations in minutes
        self.work_min = 25
        self.break_min = 5
        # Convert minutes to seconds
        self.work_seconds = self.work_min * 60  
        self.break_seconds = self.break_min * 60  
        self.total_seconds = self.work_seconds  # Total seconds for current session
        self.elapsed_seconds = 0  # Elapsed seconds
        self.is_work_session = True  # Flag to check if it's a work session
        self.completed_sets = 0  # Number of completed work/break sets
        self.is_paused = False  # Pause state flag
        self.is_animating = False  # Animation state flag
        # Default colors for work and break sessions (RGBA)
        self.work_color = [89, 221, 247, 255]
        self.break_color = [200, 221, 247, 255]

        self.load_config()  # Load configuration from file
        self.init_ui()  # Initialize the user interface

        # Initialize timer to update progress every second
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(1000)  # Timer interval set to 1000 ms (1 second)

    def init_ui(self):
        screen = QDesktopWidget().screenGeometry(0)  # Get screen geometry

        # Set window geometry based on config or default values
        self.setGeometry(
            self.config.get("x", 0),
            self.config.get("y", screen.height() - 30),
            self.config.get("width", screen.width()),
            self.config.get("height", 30)
        )
        # Update work and break durations from config
        self.work_seconds = self.config.get("work_time") * 60
        self.break_seconds = self.config.get("break_time") * 60
        self.work_color = self.config.get("work_color")
        self.break_color = self.config.get("break_color")

        self.total_seconds = self.work_seconds  # Set total seconds to work duration
        # Set window flags to make the window frameless and always on top
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)  # Make background translucent
        self.setWindowTitle("Pomobar")  # Set window title

        # Create reset button
        self.reset_button = QPushButton("o", self)
        self.reset_button.setGeometry(self.width() - self.height(), 0, self.height(), self.height())
        self.reset_button.clicked.connect(self.reset_progress)  # Connect reset action
        self.reset_button.setStyleSheet("background-color: red; color: white; border: none;")  # Style reset button

        # Create pause/resume button
        self.pause_button = QPushButton("-", self)
        self.pause_button.setGeometry(self.width() - (2 * self.height()), 0, self.height(), self.height())
        self.pause_button.clicked.connect(self.toggle_pause)  # Connect pause/resume action
        self.pause_button.setStyleSheet("background-color: orange; color: white; border: none;")  # Style pause button

        self.setMouseTracking(True)  # Enable mouse tracking
        # Initialize double-click handling
        self.double_click_timer = QTimer()
        self.double_click_timer.setSingleShot(True)
        self.double_click_timer.timeout.connect(self.reset_double_click)
        self.double_click = False

    def reset_double_click(self):
        """Reset the double-click flag after a timeout."""
        self.double_click = False

    def mousePressEvent(self, event):
        """Handle mouse press events to detect double-clicks."""
        if event.button() == Qt.LeftButton:
            if self.double_click:
                self.open_geometry_config_dialog()  # Open config dialog on double-click
            else:
                self.double_click = True
                self.double_click_timer.start(250)  # Start timer for double-click detection

    def get_work_color(self):
        """Open color dialog to select work session color."""
        self.color_dialog.exec_()
        self.work_color = self.color_dialog.selectedColor().getRgb()
        # Update the work color display button
        self.work_color_box.setStyleSheet(
            "background-color: rgba" + str(self.work_color).replace("[", "(").replace("]", ")")
        )
    
    def get_break_color(self):
        """Open color dialog to select break session color."""
        self.color_dialog.exec_()
        self.break_color = self.color_dialog.selectedColor().getRgb()
        # Update the break color display button
        self.break_color_box.setStyleSheet(
            "background-color: rgba" + str(self.break_color).replace("[", "(").replace("]", ")")
        )
  
    def open_geometry_config_dialog(self):
        """Open a dialog to configure geometry and other settings."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Config")

        # Create a close button to close the progress bar
        self.close_button = QPushButton("Close Bar")
        self.close_button.clicked.connect(self.close)
        layout = QVBoxLayout()

        # Layout for color settings
        color_layout = QHBoxLayout()
        work_color_label = QLabel("Work color:")
        break_color_label = QLabel("Break color:")

        self.color_dialog = QColorDialog(self)  # Initialize color dialog
        self.work_color_box = QPushButton("")
        # Set initial work color
        self.work_color_box.setStyleSheet(
            "background-color: rgba" + str(self.work_color).replace("[", "(").replace("]", ")")
        )
        self.break_color_box = QPushButton("")
        # Set initial break color
        self.break_color_box.setStyleSheet(
            "background-color: rgba" + str(self.break_color).replace("[", "(").replace("]", ")")
        )

        # Connect color buttons to their respective handlers
        self.work_color_box.clicked.connect(self.get_work_color)
        self.break_color_box.clicked.connect(self.get_break_color)

        # Add color widgets to color layout
        color_layout.addWidget(work_color_label)
        color_layout.addWidget(self.work_color_box)
        color_layout.addWidget(break_color_label)
        color_layout.addWidget(self.break_color_box)

        # Layout for timer settings
        timer_layout = QHBoxLayout()
        work_time_label = QLabel("Work Time:")
        break_time_label = QLabel("Break Time:")

        self.work_time_spinbox = QSpinBox()
        self.work_time_spinbox.setRange(0, 1440)  # Set range from 0 to 1440 minutes
        self.work_time_spinbox.setValue(self.work_min)  # Set initial value

        self.break_time_spinbox = QSpinBox()
        self.break_time_spinbox.setRange(0, 1440)  # Set range from 0 to 1440 minutes
        self.break_time_spinbox.setValue(self.break_min)  # Set initial value

        # Add timer widgets to timer layout
        timer_layout.addWidget(work_time_label)
        timer_layout.addWidget(self.work_time_spinbox)
        timer_layout.addWidget(break_time_label)
        timer_layout.addWidget(self.break_time_spinbox)

        # Layout for position settings
        pos_layout = QHBoxLayout()
        x_pos_label = QLabel("X pos:")
        y_pos_label = QLabel("Y pos:")
        self.x_pos_spinbox = QSpinBox()
        self.x_pos_spinbox.setRange(-5000, 5000)  # Set range for X position
        self.x_pos_spinbox.setValue(self.x())  # Set initial X position
        
        self.y_pos_spinbox = QSpinBox()
        self.y_pos_spinbox.setRange(-5000, 5000)  # Set range for Y position
        self.y_pos_spinbox.setValue(self.y())  # Set initial Y position

        # Add position widgets to position layout
        pos_layout.addWidget(x_pos_label)
        pos_layout.addWidget(self.x_pos_spinbox)
        pos_layout.addWidget(y_pos_label)
        pos_layout.addWidget(self.y_pos_spinbox)

        # Layout for width settings
        width_layout = QHBoxLayout()
        width_label = QLabel("Width:")
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setRange(100, 3000)  # Set range for width
        self.width_spinbox.setValue(self.width())  # Set initial width
        width_layout.addWidget(width_label)
        width_layout.addWidget(self.width_spinbox)

        # Layout for height settings
        height_layout = QHBoxLayout()
        height_label = QLabel("Height:")
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setRange(2, 200)  # Set range for height
        self.height_spinbox.setValue(self.height())  # Set initial height
        height_layout.addWidget(height_label)
        height_layout.addWidget(self.height_spinbox)

        # Layout for OK and Cancel buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)

        # Connect OK and Cancel buttons to their actions
        ok_button.clicked.connect(lambda: self.apply_geometry_changes(dialog))
        cancel_button.clicked.connect(dialog.reject)

        # Connect spinbox value changes to apply geometry changes
        self.x_pos_spinbox.valueChanged.connect(self.apply_geometry_changes)
        self.y_pos_spinbox.valueChanged.connect(self.apply_geometry_changes)
        self.height_spinbox.valueChanged.connect(self.apply_geometry_changes)
        self.width_spinbox.valueChanged.connect(self.apply_geometry_changes)

        # Add all layouts to the main dialog layout
        layout.addLayout(color_layout)
        layout.addLayout(timer_layout)
        layout.addLayout(pos_layout)
        layout.addLayout(width_layout)
        layout.addLayout(height_layout)
        layout.addLayout(button_layout)
        layout.addWidget(self.close_button)
        dialog.setLayout(layout)
        dialog.exec_()  # Execute the dialog

    def apply_geometry_changes(self, dialog):
        """Apply changes made in the configuration dialog."""
        # Get new values from spinboxes
        new_work_time = self.work_time_spinbox.value()
        new_break_time = self.break_time_spinbox.value()
        new_x_pos = self.x_pos_spinbox.value()
        new_y_pos = self.y_pos_spinbox.value()
        new_width = self.width_spinbox.value()
        new_height = self.height_spinbox.value()

        # Update work and break durations
        self.work_min = new_work_time
        self.break_min = new_break_time 
        self.work_seconds = self.work_min * 60
        self.break_seconds = self.break_min * 60
        self.total_seconds = self.work_seconds  # Reset total seconds to new work duration

        # Update window geometry
        self.setGeometry(new_x_pos, new_y_pos, new_width, new_height)
        self.save_config()  # Save the new configuration

        # Update positions of pause and reset buttons based on new height
        self.pause_button.setGeometry(self.width() - (2 * self.height()), 0, self.height(), self.height())
        self.reset_button.setGeometry(self.width() - self.height(), 0, self.height(), self.height())
        
        try:
            dialog.accept()  # Close the dialog if possible
        except:
            pass

    def save_config(self):
        """Save the current configuration to a JSON file."""
        self.config = {
            "work_color": self.work_color,
            "break_color": self.break_color,
            "work_time": self.work_min,
            "break_time": self.break_min,
            "x": self.x(),
            "y": self.y(),
            "width": self.width(),
            "height": self.height()
        }
        with open(self.CONFIG_FILE, "w") as config_file:
            json.dump(self.config, config_file)  # Write config to file

    def load_config(self):
        """Load configuration from a JSON file."""
        try:
            with open(self.CONFIG_FILE, "r") as config_file:
                self.config = json.load(config_file)
        except (FileNotFoundError, json.JSONDecodeError):
            self.config = {}  # Use empty config if file not found or invalid

    def update_progress(self):
        """Update the progress bar based on elapsed time."""
        if not self.is_paused:
            self.elapsed_seconds += 1  # Increment elapsed time
            if self.elapsed_seconds >= self.total_seconds:
                if not self.is_animating:
                    self.start_animation()  # Start transition animation
            self.update()  # Trigger repaint

    def switch_session(self):
        """Switch between work and break sessions."""
        self.elapsed_seconds = 0  # Reset elapsed time
        if self.is_work_session:
            self.completed_sets += 1  # Increment completed sets if it was a work session
        self.is_work_session = not self.is_work_session  # Toggle session type
        # Set total seconds based on the new session type
        self.total_seconds = self.work_seconds if self.is_work_session else self.break_seconds

    def reset_progress(self):
        """Reset the progress bar to initial state."""
        self.timer.stop()  # Stop the timer
        self.is_work_session = True  # Set to work session
        self.total_seconds = self.work_seconds  # Reset total seconds to work duration
        self.elapsed_seconds = 0  # Reset elapsed time
        self.completed_sets = 0  # Reset completed sets
        self.is_paused = False  # Unpause if paused
        self.timer.start(1000)  # Restart the timer
        self.update()  # Trigger repaint

    def toggle_pause(self):
        """Toggle the pause state of the progress bar."""
        self.is_paused = not self.is_paused  # Toggle pause flag
        # Update pause button text based on state
        self.pause_button.setText("Resume" if self.is_paused else "Pause")

    def start_animation(self):
        """Start the transition animation between sessions."""
        self.is_animating = True  # Set animation flag
        self.animation_progress = 0  # Initialize animation progress
        self.animation_timer = QTimer(self)  # Create a timer for animation
        self.animation_timer.timeout.connect(self.animate_transition)  # Connect to animation handler
        self.animation_timer.start(50)  # Set timer interval to 50 ms

    def animate_transition(self):
        """Handle the transition animation."""
        self.animation_progress += 1  # Increment animation progress
        if self.animation_progress >= 60:  # Check if animation duration is complete
            self.animation_timer.stop()  # Stop the animation timer
            self.is_animating = False  # Reset animation flag
            self.switch_session()  # Switch to the next session
        self.update()  # Trigger repaint

    def paintEvent(self, event):
        """Custom paint event to draw the progress bar."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)  # Enable anti-aliasing for smoother graphics

        rect = QRect(0, 0, self.width(), self.height())  # Define the rectangle area

        painter.fillRect(rect, Qt.black)  # Fill the background with black color
        if self.is_animating:
            # Calculate progress width based on animation progress
            progress_width = (self.width() * self.animation_progress) // 40
            # Generate color based on animation progress
            color = QColor.fromHsv((self.animation_progress * 9) % 360, 255, 255)
            painter.fillRect(QRect(0, 0, progress_width, self.height()), color)  # Draw animated progress
        else:
            # Calculate progress width based on elapsed time
            progress_width = self.width() * (self.elapsed_seconds / self.total_seconds)
            progress_rect = QRect(0, 0, int(progress_width), self.height())
            # Choose color based on current session type
            bar_color = QColor(
                self.work_color[0],
                self.work_color[1],
                self.work_color[2],
                self.work_color[3]
            ) if self.is_work_session else QColor(
                self.break_color[0],
                self.break_color[1],
                self.break_color[2],
                self.break_color[3]
            )
            painter.fillRect(progress_rect, bar_color)  # Draw the progress bar

        # Calculate remaining time
        remaining_seconds = self.total_seconds - self.elapsed_seconds
        minutes = remaining_seconds // 60
        seconds = remaining_seconds % 60

        painter.setPen(Qt.white)  # Set text color to white
        # Set font based on widget height
        font = QFont("Courier", int(self.height() / 2), QFont.Bold)
        painter.setFont(font)
        session_type = "Work" if self.is_work_session else "Break"  # Determine session type
        if not self.is_animating:
            # Format time and sets information
            time_text = f"{session_type} {minutes:02}:{seconds:02} | Sets: {self.completed_sets}"
            # Define the area to draw the text
            text_rect = QRect(
                self.width() - int(self.height() * 20),
                0,
                int(self.height() * 17.5),
                self.height()
            )
            # Draw the text aligned to the right and vertically centered
            painter.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter, time_text)

if __name__ == "__main__":
    app = QApplication(sys.argv)  # Create the application instance
    window = LinearProgressBar()  # Create the progress bar window
    window.show()  # Show the window
    sys.exit(app.exec_())  # Execute the application loop