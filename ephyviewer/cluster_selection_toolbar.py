"""
Cluster Selection Toolbar for ephyviewer
"""

from ephyviewer.myqt import QT
import json
import os


class ClusterSelectionToolbar(QT.QWidget):
    """
    BUTTON_COLORS = {
        1: ('#9B59B6', 'purple'),
        2: ('#3498DB', 'blue'),
        3: ('#2ECC71', 'green'),
        4: ('#E67E22', 'orange'),
        5: ('#E74C3C', 'red')
    }
    
    BUTTON_COLORS = {
        1: ("#8000ffff", 'purple'),
        2: ("#00b4ebff", 'blue'),
        3: ("#80ffb5ff", 'green'),
        4: ("#ffb260ff", 'orange'),
        5: ("#ff0000ff", 'red')
    }
    """
    def __init__(self, channel_names, nb_clusters, button_colors, save_file='cluster_selection.json', parent=None):
        super().__init__(parent)
        
        self.channel_names = list(channel_names)  # Ensure it's a list
        self.save_file = str(save_file)  # Ensure it's a string
        self.button_states = {}
        self.all_buttons = {}
        self.button_colors= button_colors
        self.nb_clusters=nb_clusters
        
        """Load button states from JSON file"""
        
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file, 'r') as f:
                    self.button_states = json.load(f)
                if self.button_states:
                    first_ch = list(self.button_states.keys())[0]
            except Exception as e:
                self._initialize_states()
        else:
            self._initialize_states()

        
        # Build UI AFTER loading
        self._setup_ui()
                
    def _setup_ui(self):
        """Build the user interface"""
        main_layout = QT.QVBoxLayout()
        self.setLayout(main_layout)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(2)
        
        scroll = QT.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QT.Qt.ScrollBarAlwaysOff)
        
        scroll_widget = QT.QWidget()
        scroll_layout = QT.QVBoxLayout()
        scroll_layout.setSpacing(2)
        scroll_layout.setContentsMargins(1, 1, 1, 1)
        scroll_widget.setLayout(scroll_layout)
        scroll.setWidget(scroll_widget)
        
        # Create button rows for each channel
        for ch_name in self.channel_names:
            ch_widget = self._create_channel_widget(ch_name)
            scroll_layout.addWidget(ch_widget)
        
        scroll_layout.addStretch()
        main_layout.addWidget(scroll)
        
        self.setSizePolicy(QT.QSizePolicy.Preferred, QT.QSizePolicy.Expanding)
        self.setMinimumWidth(100)
        self.setMaximumWidth(200)

    def _create_channel_widget(self, ch_name):
        """Create widget for a single channel with 5 buttons"""
        ch_widget = QT.QWidget()
        ch_layout = QT.QVBoxLayout()
        ch_widget.setLayout(ch_layout)
        ch_layout.setContentsMargins(1, 1, 1, 1)
        ch_layout.setSpacing(2)
        
        # Channel name label
        ch_label = QT.QLabel(ch_name)
        ch_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        ch_layout.addWidget(ch_label)
        
        # Button row
        btn_row = QT.QHBoxLayout()
        btn_row.setSpacing(2)
        btn_row.setContentsMargins(1, 1, 1, 1)
        
        self.all_buttons[ch_name] = {}
        
        for btn_num in range(1, self.nb_clusters+1):
            btn = self._create_cluster_button(ch_name, btn_num)
            btn_row.addWidget(btn)
            self.all_buttons[ch_name][btn_num] = btn
        
        ch_layout.addLayout(btn_row)
        
        # Separator
        separator = QT.QFrame()
        separator.setFrameShape(QT.QFrame.HLine)
        separator.setFrameShadow(QT.QFrame.Sunken)
        separator.setFixedHeight(1)
        ch_layout.addWidget(separator)
        
        return ch_widget
    
    def _create_cluster_button(self, ch_name, btn_num):
        """Create a single cluster selection button"""
        btn = QT.QPushButton(str(btn_num))
        btn.setFixedSize(15, 15)
        btn.setCheckable(True)
        
        # Get saved state for this channel and button
        saved_state = self.button_states.get(ch_name, {}).get(f'{btn_num}', False)
                
        # Block signals while setting initial state
        btn.blockSignals(True)
        btn.setChecked(saved_state)
        btn.blockSignals(False)
        
        #color_hex, _ = self.button_colors[btn_num]
        color_hex = self.button_colors[btn_num]
        
        # Apply style
        self._update_button_style(btn, color_hex, saved_state)
        
        # Connect signal AFTER setting initial state
        btn.toggled.connect(lambda checked: self._on_button_toggled(ch_name, btn_num, btn, color_hex, checked))
        
        return btn
    
    def _on_button_toggled(self, ch_name, btn_num, button, color, checked):
        """Handle button toggle event"""        
        if ch_name not in self.button_states:
            self.button_states[ch_name] = {}
        
        self.button_states[ch_name][f'{btn_num}'] = checked
        self._update_button_style(button, color, checked)
        self._save_states()
    
    def _update_button_style(self, button, color, is_checked):
        """Update button appearance"""
        if is_checked:
            button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: white;
                    border: 2px solid {color};
                    border-radius: 2px;
                    font-weight: bold;
                    font-size: 9px;
                }}
            """)
        else:
            button.setStyleSheet(f"""
                QPushButton {{
                    background-color: white;
                    color: {color};
                    border: 2px solid {color};
                    border-radius: 2px;
                    font-size: 9px;
                }}
            """)
        
    
    def _initialize_states(self):
        """Initialize default button states"""
        for ch_name in self.channel_names:
            self.button_states[ch_name] = dict.fromkeys(range(1, self.nb_clusters+1), False) #{1: False, 2: False, 3: False, 4: False, 5: False}
    
    def _save_states(self):
        """Save button states to JSON file"""
        try:
            with open(self.save_file, 'w') as f:
                json.dump(self.button_states, f, indent=2)
        except Exception as e:
            print('JSON file not saved')
    
    def get_channel_clusters(self, ch_name):
        return self.button_states.get(ch_name, {})
    
    def get_all_clusters(self):
        return self.button_states.copy()
    
    def get_settings(self):
        return {}
    
    def set_settings(self, settings):
        pass