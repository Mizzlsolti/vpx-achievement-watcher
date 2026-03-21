"""
Pinball Arcade Qt stylesheet – imported by Achievement_watcher.py.
Keeping the CSS in its own file makes the main module easier to read.
"""

pinball_arcade_style = """
        /* --- Basis: Tiefschwarz (Cabinet) --- */
        QMainWindow, QDialog, QWidget {
            background-color: #121212;
            color: #E0E0E0;
            font-family: 'Segoe UI', sans-serif;
            font-size: 10pt;
        }

        /* --- Die Haupt-Tabs --- */
        QTabWidget::pane {
            border: 1px solid #333333;
            background-color: #181818;
            border-radius: 4px;
        }
        QTabBar::tab {
            background-color: #222222;
            color: #777777;
            padding: 10px 22px;
            border: 1px solid #333333;
            border-bottom: none;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 3px;
            font-weight: bold;
            font-size: 11pt;
        }
        QTabBar::tab:hover:!selected {
            background-color: #2A2A2A;
            color: #FFFFFF;
        }
        QTabBar::tab:selected {
            background-color: #181818;
            color: #FF7F00; /* Williams DMD Orange! */
            border-top: 3px solid #FF7F00;
        }

        /* --- Buttons (Arcade Style mit Metallic-Gradient) --- */
        QPushButton {
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #383838, stop:1 #252525);
            color: #FFFFFF;
            border: 1px solid #555555;
            border-radius: 5px;
            padding: 7px 16px;
            font-weight: bold;
        }
        QPushButton:hover {
            border: 1px solid #FF7F00; /* DMD Orange Glow */
            color: #FF7F00;
            background-color: #2C2C2C;
        }
        QPushButton:pressed {
            background-color: #FF7F00;
            color: #000000;
            border: 1px solid #FF7F00;
        }

        /* --- Panels (Groupboxen für die Struktur) --- */
        QGroupBox {
            border: 1px solid #444444;
            border-radius: 6px;
            margin-top: 20px;
            background-color: #1A1A1A;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
            left: 15px;
            color: #00E5FF; /* LED Eisblau! */
            font-weight: bold;
            font-size: 11pt;
        }

        /* --- Textfelder & Listen (z.B. für Stats) --- */
        QTextBrowser, QTextEdit {
            background-color: #0A0A0A; /* Noch dunkler für Kontrast */
            border: 1px solid #333333;
            border-radius: 4px;
            color: #FFB000; /* Leichtes Orange/Amber für Stats */
        }
        
        /* --- Eingabefelder --- */
        QLineEdit, QComboBox, QSpinBox {
            background-color: #222222;
            color: #FFFFFF;
            border: 1px solid #555555;
            border-radius: 3px;
            padding: 5px;
        }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
            border: 1px solid #00E5FF; /* Blauer Fokus-Glow */
        }

        /* --- Slider (Für Volume & Skalierung) --- */
        QSlider::groove:horizontal {
            border: 1px solid #444;
            height: 8px;
            background: #222;
            border-radius: 4px;
        }
        QSlider::sub-page:horizontal {
            background: #FF7F00; /* DMD Orange Füllung */
            border-radius: 4px;
        }
        QSlider::handle:horizontal {
            background: #FFFFFF;
            border: 2px solid #777;
            width: 14px;
            margin-top: -5px;
            margin-bottom: -5px;
            border-radius: 7px;
        }

        /* --- Checkboxen --- */
        QCheckBox::indicator {
            width: 18px; 
            height: 18px;
            border: 1px solid #666;
            border-radius: 4px;
            background-color: #222;
        }
        QCheckBox::indicator:hover {
            border: 1px solid #FF7F00;
        }
        QCheckBox::indicator:checked {
            background-color: #00E5FF; /* Eisblauer Haken */
            border: 1px solid #00E5FF;
        }
        """
