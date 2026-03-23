"""
Pinball Arcade Qt stylesheet – imported by Achievement_watcher.py.
Keeping the CSS in its own file makes the main module easier to read.
"""


def _tint_color(base_hex: str, tint_hex: str, factor: float) -> str:
    """Blend *base_hex* toward *tint_hex* by *factor* (0.0 = base, 1.0 = tint)."""
    def _parse(h: str):
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    br, base_g, bb = _parse(base_hex)
    tr, tg, tb = _parse(tint_hex)
    r = int(br * (1 - factor) + tr * factor)
    g = int(base_g * (1 - factor) + tg * factor)
    b = int(bb * (1 - factor) + tb * factor)
    return f"#{r:02X}{g:02X}{b:02X}"


def pinball_arcade_style(primary: str = "#00E5FF", accent: str = "#FF7F00", bg: str = "#080C16") -> str:
    """Return the application stylesheet with the given theme colors applied.

    *primary* is used for GroupBox titles, focus borders and checked checkboxes.
    *accent*  is used for selected tabs, button hover/pressed, slider fill and
              checkbox hover borders.
    *bg*      is the theme background color; dark base colors are tinted toward
              it by ~12%.  When *bg* is the neon_blue default ``#080C16`` the
              output is pixel-identical to the original hardcoded stylesheet.
    """
    _DEFAULT_BG = "#080C16"
    if bg.upper() == _DEFAULT_BG.upper():
        # Neon-blue default – keep exact original values for pixel-identical output
        c_main = "#121212"
        c_panel = "#181818"
        c_group = "#1A1A1A"
        c_input = "#222222"
        c_text = "#0A0A0A"
    else:
        # Tint base dark colors toward the theme bg for a subtle coordinated look
        _BLEND = 0.12
        c_main = _tint_color("#121212", bg, _BLEND)
        c_panel = _tint_color("#181818", bg, _BLEND)
        c_group = _tint_color("#1A1A1A", bg, _BLEND)
        c_input = _tint_color("#222222", bg, _BLEND)
        c_text = _tint_color("#0A0A0A", bg, _BLEND)

    return f"""
        /* --- Base: Deep Black (Cabinet) --- */
        QMainWindow, QDialog, QWidget {{
            background-color: {c_main};
            color: #E0E0E0;
            font-family: 'Segoe UI', sans-serif;
            font-size: 10pt;
        }}

        /* --- Main Tabs --- */
        QTabWidget::pane {{
            border: 1px solid #333333;
            background-color: {c_panel};
            border-radius: 4px;
        }}
        QTabBar::tab {{
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
        }}
        QTabBar::tab:hover:!selected {{
            background-color: #2A2A2A;
            color: #FFFFFF;
        }}
        QTabBar::tab:selected {{
            background-color: {c_panel};
            color: {accent};
            border-top: 3px solid {accent};
        }}

        /* --- Buttons (Arcade Style with Metallic Gradient) --- */
        QPushButton {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #383838, stop:1 #252525);
            color: #FFFFFF;
            border: 1px solid #555555;
            border-radius: 5px;
            padding: 7px 16px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            border: 1px solid {accent};
            color: {accent};
            background-color: #2C2C2C;
        }}
        QPushButton:pressed {{
            background-color: {accent};
            color: #000000;
            border: 1px solid {accent};
        }}

        /* --- Panels (GroupBoxes for structure) --- */
        QGroupBox {{
            border: 1px solid #444444;
            border-radius: 6px;
            margin-top: 20px;
            background-color: {c_group};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
            left: 15px;
            color: {primary};
            font-weight: bold;
            font-size: 11pt;
        }}

        /* --- Text fields & lists (e.g. for stats) --- */
        QTextBrowser, QTextEdit {{
            background-color: {c_text};
            border: 1px solid #333333;
            border-radius: 4px;
            color: {accent};
        }}

        /* --- Input fields --- */
        QLineEdit, QComboBox, QSpinBox {{
            background-color: {c_input};
            color: #FFFFFF;
            border: 1px solid #555555;
            border-radius: 3px;
            padding: 5px;
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {primary};
        }}

        /* --- Dropdown Menus --- */
        QComboBox QAbstractItemView {{
            background-color: {c_input};
            color: #FFFFFF;
            border: 1px solid {primary};
            selection-background-color: {primary};
            selection-color: #000000;
            outline: none;
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 32px;
            padding: 4px 8px;
        }}

        /* --- Slider (Volume & Scale) --- */
        QSlider::groove:horizontal {{
            border: 1px solid #444;
            height: 8px;
            background: #222;
            border-radius: 4px;
        }}
        QSlider::sub-page:horizontal {{
            background: {accent};
            border-radius: 4px;
        }}
        QSlider::handle:horizontal {{
            background: #FFFFFF;
            border: 2px solid #777;
            width: 14px;
            margin-top: -5px;
            margin-bottom: -5px;
            border-radius: 7px;
        }}

        /* --- Checkboxen --- */
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid #666;
            border-radius: 4px;
            background-color: #222;
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {accent};
        }}
        QCheckBox::indicator:checked {{
            background-color: {primary};
            border: 1px solid {primary};
        }}
        """
