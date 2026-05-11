from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSizePolicy,
    QStatusBar,
    QMessageBox,
)
from PySide6.QtCore import Qt, QDateTime
from PySide6.QtGui import QFont

from gpu_detector import detect_gpus, get_current_opengl_renderer, get_current_mode, GPUInfo
from envycontrol_backend import query_mode, switch_mode, SWITCH_MODES

MODE_COLORS = {
    "integrated": ("#a6e3a1", "#1e1e2e"),
    "hybrid": ("#89b4fa", "#1e1e2e"),
    "nvidia": ("#f38ba8", "#1e1e2e"),
    "unknown": ("#6c7086", "#1e1e2e"),
}

VENDOR_COLORS = {
    "NVIDIA": ("#76b900", "#ffffff"),
    "Intel": ("#0071c5", "#ffffff"),
    "AMD": ("#ff6900", "#ffffff"),
}


class GPUCard(QFrame):
    def __init__(self, gpu_info: GPUInfo, active: bool = False):
        super().__init__()
        self.gpu = gpu_info
        self.setup_ui(active)

    def setup_ui(self, active):
        self.setMinimumSize(240, 160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        is_offline = self.gpu.power_state == "offline"
        if is_offline:
            border_color = "#6c7086"
            text_color = "#6c7086"
        else:
            border_color = VENDOR_COLORS.get(self.gpu.vendor, ("#6c7086", "#ffffff"))[0]
            text_color = VENDOR_COLORS.get(self.gpu.vendor, ("#6c7086", "#ffffff"))[1]

        border_width = 3 if active else 2
        self.setStyleSheet(f"""
            GPUCard {{
                background-color: rgba(128, 128, 128, {40 if is_offline else 0});
                border: {border_width}px solid {border_color};
                border-radius: 12px;
                padding: 4px;
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        badge_frame = QFrame()
        badge_frame.setFixedHeight(28)
        badge_color = "#6c7086" if is_offline else border_color
        badge_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {badge_color};
                border-radius: 14px;
            }}
        """)
        badge_layout = QHBoxLayout(badge_frame)
        badge_layout.setContentsMargins(12, 0, 12, 0)
        vendor_label = QLabel(self.gpu.vendor)
        vendor_label.setStyleSheet(
            f"color: {text_color}; font-weight: bold; font-size: 12px;"
        )
        badge_layout.addWidget(vendor_label)
        if is_offline:
            off = QLabel("OFFLINE")
            off.setStyleSheet("color: #cdd6f4; font-weight: bold; font-size: 10px;")
            badge_layout.addWidget(off)
        elif active:
            dot = QLabel("\u25cf ACTIVE")
            dot.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 10px;")
            badge_layout.addWidget(dot)
        badge_layout.addStretch()
        layout.addWidget(badge_frame)

        name_label = QLabel(self.gpu.name if self.gpu.name else "Unknown")
        name_label.setWordWrap(True)
        nf = QFont()
        nf.setPointSize(11)
        name_label.setFont(nf)
        name_style = "color: #6c7086;" if is_offline else "color: palette(text);"
        name_label.setStyleSheet(name_style)
        layout.addWidget(name_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: palette(mid);")
        layout.addWidget(sep)

        if is_offline:
            na = QLabel("GPU is powered off")
            na.setStyleSheet("color: #6c7086; font-style: italic;")
            layout.addWidget(na)
        else:
            if self.gpu.temp is not None:
                row = QHBoxLayout()
                row.setSpacing(8)
                row.addWidget(QLabel("Temperature:"))
                tv = QLabel(f"{self.gpu.temp}\u00b0C")
                tv.setStyleSheet("font-weight: bold;")
                row.addWidget(tv)
                row.addStretch()
                layout.addLayout(row)

            if self.gpu.utilization is not None:
                row = QHBoxLayout()
                row.setSpacing(8)
                row.addWidget(QLabel("Utilization:"))
                uv = QLabel(self.gpu.utilization)
                uv.setStyleSheet("font-weight: bold;")
                row.addWidget(uv)
                row.addStretch()
                layout.addLayout(row)

            if self.gpu.temp is None and self.gpu.utilization is None:
                na = QLabel("No runtime data")
                na.setStyleSheet("color: palette(placeholder-text); font-style: italic;")
                layout.addWidget(na)

        layout.addStretch()
        self.setLayout(layout)


class GPUManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GPU Manager")
        self.setMinimumSize(720, 480)
        self.resize(720, 520)
        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        title = QLabel("GPU Manager")
        tf = QFont()
        tf.setPointSize(20)
        tf.setBold(True)
        title.setFont(tf)
        outer.addWidget(title)

        self.mode_frame = QFrame()
        self.mode_frame.setFixedHeight(36)
        self.mode_frame.setStyleSheet("background-color: palette(midlight); border-radius: 8px;")
        ml = QHBoxLayout(self.mode_frame)
        ml.setContentsMargins(16, 0, 16, 0)

        ml.addWidget(QLabel("Current Mode:"))
        self.mode_badge = QLabel("unknown")
        self.mode_badge.setFixedHeight(26)
        self.mode_badge.setAlignment(Qt.AlignCenter)
        self.mode_badge.setStyleSheet("""
            QLabel {
                padding: 2px 16px;
                border-radius: 13px;
                font-weight: bold;
                color: white;
            }
        """)
        self._update_badge("unknown")
        ml.addWidget(self.mode_badge)
        ml.addStretch()
        outer.addWidget(self.mode_frame)

        self.cards_widget = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_widget)
        self.cards_layout.setSpacing(16)
        outer.addWidget(self.cards_widget)

        self.gl_frame = QFrame()
        self.gl_frame.setStyleSheet("""
            QFrame {
                background-color: palette(midlight);
                border-radius: 8px;
            }
        """)
        gl_layout = QHBoxLayout(self.gl_frame)
        gl_layout.setContentsMargins(16, 12, 16, 12)
        gl_label = QLabel("OpenGL Renderer:")
        gl_label.setStyleSheet("font-weight: bold;")
        self.gl_value = QLabel("...")
        self.gl_value.setWordWrap(True)
        gl_layout.addWidget(gl_label)
        gl_layout.addWidget(self.gl_value, 1)
        outer.addWidget(self.gl_frame)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        self.switch_buttons = {}
        for mode in SWITCH_MODES:
            btn = QPushButton(mode.capitalize())
            btn.setFixedHeight(40)
            btn.clicked.connect(lambda checked, m=mode: self.do_switch(m))
            self.switch_buttons[mode] = btn
            btn_layout.addWidget(btn)
        outer.addLayout(btn_layout)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(36)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: palette(button);
                border: 1px solid palette(mid);
                border-radius: 8px;
                padding: 8px 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: palette(light);
            }
            QPushButton:pressed {
                background-color: palette(midlight);
            }
        """)
        refresh_btn.clicked.connect(self.refresh_data)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        outer.addWidget(refresh_btn, alignment=Qt.AlignCenter)

        outer.addStretch()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _update_badge(self, mode):
        color = MODE_COLORS.get(mode, MODE_COLORS["unknown"])[0]
        self.mode_badge.setText(mode.capitalize())
        self.mode_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                padding: 2px 16px;
                border-radius: 13px;
                font-weight: bold;
                color: white;
            }}
        """)

    def refresh_data(self):
        self.status_bar.showMessage("Refreshing...")

        gpus = detect_gpus()
        if not gpus:
            self.status_bar.showMessage("No GPUs detected", 5000)
            return

        gl_renderer = get_current_opengl_renderer()
        self.gl_value.setText(gl_renderer)

        gl_lower = gl_renderer.lower()
        for gpu in gpus:
            if gpu.power_state == "offline":
                gpu.is_active = False
            else:
                gpu.is_active = gpu.vendor.lower() in gl_lower

        self._rebuild_cards(gpus)

        mode = query_mode()
        self._update_badge(mode)

        for m, btn in self.switch_buttons.items():
            is_current = m == mode
            btn.setEnabled(not is_current)
            if is_current:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: palette(mid);
                        color: palette(dark);
                        border: none;
                        border-radius: 8px;
                        font-weight: bold;
                        padding: 8px 24px;
                        font-size: 13px;
                    }
                """)
            else:
                c = MODE_COLORS.get(m, ("#6c7086", "#1e1e2e"))[0]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: palette(window);
                        color: palette(text);
                        border: 2px solid {c};
                        border-radius: 8px;
                        font-weight: bold;
                        padding: 8px 24px;
                        font-size: 13px;
                    }}
                    QPushButton:hover {{
                        background-color: {c}33;
                    }}
                    QPushButton:pressed {{
                        background-color: {c}66;
                    }}
                """)

        now = QDateTime.currentDateTime().toString("hh:mm:ss")
        self.status_bar.showMessage(f"Last refreshed: {now}")

    def _rebuild_cards(self, gpus):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for gpu in gpus:
            card = GPUCard(gpu, active=gpu.is_active)
            self.cards_layout.addWidget(card)

        if not gpus:
            lbl = QLabel("No GPUs detected")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: palette(placeholder-text); font-size: 14px;")
            self.cards_layout.addWidget(lbl)

    def do_switch(self, mode):
        reply = QMessageBox.question(
            self,
            "Switch Graphics Mode",
            f"Switch to {mode.capitalize()} mode?\n\n"
            "You will need to log out and back in for changes to take effect.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.status_bar.showMessage(f"Switching to {mode} mode...")
        self.setEnabled(False)

        success, msg = switch_mode(mode)

        self.setEnabled(True)

        if success:
            QMessageBox.information(
                self,
                "Success",
                f"Switched to {mode.capitalize()} mode.\n\n"
                "Please log out and log back in (or reboot) for changes to take effect.\n\n"
                f"Output: {msg}",
            )
            self.refresh_data()
        else:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to switch to {mode.capitalize()} mode:\n\n{msg}",
            )
            self.status_bar.showMessage("Switch failed", 5000)
