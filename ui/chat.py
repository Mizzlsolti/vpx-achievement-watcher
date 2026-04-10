"""Tournament Chat widget for the Score Duels – Tournament sub-tab.

Firebase Realtime Database rules (apply in Firebase console):

.. code-block:: json

    {
      "rules": {
        "tournament_chat": {
          "messages": {
            ".read": "auth != null",
            "$messageId": {
              ".write": "auth != null
                && !root.child('tournament_chat/banned').child(auth.uid).exists()
                && (!root.child('tournament_chat/timeouts').child(auth.uid).exists()
                    || root.child('tournament_chat/timeouts').child(auth.uid).child('until').val() < now)
                && newData.child('senderId').val() === auth.uid"
            }
          },
          "banned": {
            ".read": "auth != null",
            ".write": "root.child('tournament_chat/admin/uid').val() === auth.uid"
          },
          "timeouts": {
            ".read": "auth != null",
            ".write": "root.child('tournament_chat/admin/uid').val() === auth.uid"
          },
          "admin": {
            ".read": "auth != null",
            ".write": false
          }
        }
      }
    }

Database structure::

    /tournament_chat/
      /messages/
        /<messageId>/
          senderId:   "player-uid"
          senderName: "Spielername"
          text:       "Nachricht..."
          timestamp:  1712750000000
      /banned/
        /<playerId>: true
      /timeouts/
        /<playerId>/
          until: 1712750300000    <- unix timestamp (ms) when timeout expires
      /admin/
        uid: "admin-cloud-id"    <- set manually by repo owner; never written by client
"""
from __future__ import annotations

import json
import ssl
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime
from html import escape as _esc

from PyQt6.QtCore import QMetaObject, Qt, Q_ARG, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QPushButton, QVBoxLayout, QWidget,
)

from .widgets import HazardStripeOverlay

# ── Module-level admin session (NEVER persisted to disk) ───────────────────────
# The admin UID is loaded from Firebase on login and kept only in memory.
_admin_uid: str | None = None
ADMIN_NICKNAME = "Solters"  # Only this hardcoded nickname can log in as admin


def get_admin_uid() -> str | None:
    """Return the in-memory admin UID, or None when not logged in."""
    return _admin_uid


def set_admin_session(uid: str | None) -> None:
    """Store (or clear) the admin UID in memory – never touches disk."""
    global _admin_uid
    _admin_uid = uid


# ── Firebase path constants ────────────────────────────────────────────────────
_CHAT_PATH    = "tournament_chat/messages"
_BANNED_PATH  = "tournament_chat/banned"
_TIMEOUT_PATH = "tournament_chat/timeouts"
_ADMIN_PATH   = "tournament_chat/admin/uid"

# ── UI constants ───────────────────────────────────────────────────────────────
_MAX_DISPLAY = 100           # Number of messages kept in the list
_RECONNECT_DELAY_S = 5       # Seconds between SSE reconnect attempts
_MSG_ROLE = Qt.ItemDataRole.UserRole  # QListWidgetItem data role for sender info

_BTN_STYLE = (
    "QPushButton { background-color:#005c99; color:#FFFFFF; font-weight:bold;"
    " border:none; border-radius:5px; padding:0 14px; }"
    "QPushButton:hover { background-color:#0070bb; }"
    "QPushButton:disabled { background-color:#333; color:#666; }"
)
_GRP_STYLE = (
    "QGroupBox { color:#FF7F00; font-weight:bold; border:1px solid #333;"
    " border-radius:5px; margin-top:6px; padding-top:6px; }"
    "QGroupBox::title { subcontrol-origin:margin; left:8px; }"
)


class _ChatLockedOverlay(HazardStripeOverlay):
    """Hazard-stripe overlay shown when participation requirements are not met."""

    _TEXT = "⚠️ Chat locked – set VPSID, enable Cloud Sync, set Player Name & ID"

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, text=self._TEXT)


class ChatWidget(QGroupBox):
    """Real-time tournament chat panel backed by Firebase Realtime Database.

    Participation requirements (all must be satisfied for the chat to be active):
    - Cloud Sync is enabled
    - A non-default Player Name is set
    - A Player ID is set (already in cfg.OVERLAY from cloud-sync setup)
    - At least one VPS-ID mapping exists

    When requirements are not met the widget shows yellow-black hazard stripes
    and disables the input controls.  Requirements are re-checked every 5 s.

    Admin moderation is available when :func:`get_admin_uid` returns a non-None
    value (set by the Admin Login dialog in the System tab).  Admin actions
    write to the Firebase paths for bans and timeouts.
    """

    def __init__(self, cfg, parent: QWidget | None = None) -> None:
        super().__init__("💬 Tournament Chat", parent)
        self._cfg = cfg
        self._stream_stop = threading.Event()
        self._stream_running = False
        self._messages: dict[str, dict] = {}  # msgId → message dict
        self._build_ui()

        # Hazard overlay shown when participation requirements are not met.
        # Must be created *after* _build_ui so it is stacked above all children.
        self._locked_overlay = _ChatLockedOverlay(self)

        # Periodically re-check participation requirements.
        self._check_timer = QTimer(self)
        self._check_timer.setInterval(5_000)
        self._check_timer.timeout.connect(self._check_participation_state)
        self._check_timer.start()

        # Trigger an initial check on next event-loop cycle.
        QTimer.singleShot(0, self._check_participation_state)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setStyleSheet(_GRP_STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # Message list
        self._msg_list = QListWidget()
        self._msg_list.setWordWrap(True)
        self._msg_list.setMinimumHeight(120)
        self._msg_list.setStyleSheet(
            "QListWidget { background:#111; color:#DDD; border:1px solid #333; }"
            "QListWidget::item { padding:2px 4px; border-bottom:1px solid #222; }"
            "QListWidget::item:selected { background:#1a1a1a; }"
        )
        self._msg_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._msg_list.customContextMenuRequested.connect(self._on_context_menu)
        root.addWidget(self._msg_list, 1)

        # Input row
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(4)

        self._input_line = QLineEdit()
        self._input_line.setPlaceholderText("Type a message…")
        self._input_line.setMaxLength(300)
        self._input_line.setStyleSheet(
            "QLineEdit { background:#1a1a1a; color:#DDD; border:1px solid #444;"
            " border-radius:4px; padding:4px 8px; }"
        )
        self._input_line.returnPressed.connect(self._on_send)
        input_row.addWidget(self._input_line, 1)

        self._btn_send = QPushButton("Send")
        self._btn_send.setFixedHeight(28)
        self._btn_send.setFixedWidth(60)
        self._btn_send.setStyleSheet(_BTN_STYLE)
        self._btn_send.clicked.connect(self._on_send)
        input_row.addWidget(self._btn_send)

        root.addLayout(input_row)

    # ── Participation requirements ─────────────────────────────────────────────

    def _can_participate(self) -> bool:
        """Return True iff all chat participation requirements are currently met."""
        cfg = self._cfg
        if not getattr(cfg, "CLOUD_ENABLED", False):
            return False
        player_name = cfg.OVERLAY.get("player_name", "").strip()
        if not player_name or player_name.lower() == "player":
            return False
        player_id = cfg.OVERLAY.get("player_id", "").strip()
        if not player_id or player_id.lower() == "unknown":
            return False
        if not self._has_vpsid():
            return False
        return True

    def _has_vpsid(self) -> bool:
        """Return True if the player has at least one VPS-ID mapping."""
        try:
            from .vps import _load_vps_mapping
            return bool(_load_vps_mapping(self._cfg))
        except Exception:
            return False

    @pyqtSlot()
    def _check_participation_state(self) -> None:
        """Update overlay visibility, input state, and stream based on requirements."""
        can = self._can_participate()
        self._input_line.setEnabled(can)
        self._btn_send.setEnabled(can)
        if can:
            self._locked_overlay.hide()
            if not self._stream_running:
                self._start_stream()
        else:
            self._locked_overlay.show()
            self._locked_overlay.raise_()
            if self._stream_running:
                self._stop_stream()

    # ── Firebase SSE stream ────────────────────────────────────────────────────

    def _start_stream(self) -> None:
        """Start the background SSE listener thread."""
        if self._stream_running:
            return
        self._stream_stop.clear()
        self._stream_running = True
        t = threading.Thread(target=self._stream_worker, daemon=True, name="ChatSSE")
        t.start()

    def _stop_stream(self) -> None:
        """Signal the SSE thread to stop."""
        self._stream_stop.set()
        self._stream_running = False

    def _stream_worker(self) -> None:
        """Background thread: open SSE connection and reconnect on error."""
        while not self._stream_stop.is_set():
            try:
                self._run_sse()
            except Exception:
                pass
            # Wait before reconnecting (honour stop-signal in 100 ms steps).
            if not self._stream_stop.is_set():
                for _ in range(_RECONNECT_DELAY_S * 10):
                    if self._stream_stop.is_set():
                        break
                    time.sleep(0.1)
        self._stream_running = False

    def _run_sse(self) -> None:
        """Open an SSE connection to Firebase and dispatch events until closed."""
        cfg = self._cfg
        base_url = getattr(cfg, "CLOUD_URL", None)
        if not base_url:
            return
        url = (
            f"{base_url.rstrip('/')}/{_CHAT_PATH}.json"
            "?orderBy=%22timestamp%22&limitToLast=100"
        )
        req = urllib.request.Request(url, headers={
            "Accept": "text/event-stream",
            "User-Agent": "AchievementWatcher/2.0",
            "Cache-Control": "no-cache",
        })
        try:
            ctx = ssl.create_default_context()
            conn = urllib.request.urlopen(req, context=ctx, timeout=90)
        except ssl.SSLError:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            conn = urllib.request.urlopen(req, context=ctx, timeout=90)

        event_type: str | None = None
        data_parts: list[str] = []
        try:
            while not self._stream_stop.is_set():
                raw = conn.readline()
                if not raw:
                    break  # Server closed the stream
                line = raw.decode("utf-8").rstrip("\r\n")
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_parts.append(line[5:].strip())
                elif line == "":
                    # Dispatch accumulated event
                    if event_type and data_parts:
                        data_str = "".join(data_parts)
                        if data_str not in ("null", ""):
                            try:
                                # Validate JSON before dispatching
                                json.loads(data_str)
                                QMetaObject.invokeMethod(
                                    self,
                                    "_on_sse_event",
                                    Qt.ConnectionType.QueuedConnection,
                                    Q_ARG(str, event_type),
                                    Q_ARG(str, data_str),
                                )
                            except Exception:
                                pass
                    event_type = None
                    data_parts = []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @pyqtSlot(str, str)
    def _on_sse_event(self, event_type: str, data_str: str) -> None:
        """Process an SSE event on the GUI thread."""
        try:
            payload = json.loads(data_str)
        except Exception:
            return

        if event_type == "put":
            path = payload.get("path", "/")
            data = payload.get("data")
            if path == "/" and isinstance(data, dict):
                self._messages = data
                self._rebuild_message_list()
            elif isinstance(data, dict):
                key = path.strip("/")
                if key:
                    self._messages[key] = data
                    self._rebuild_message_list()
            elif data is None and path != "/":
                key = path.strip("/")
                if key in self._messages:
                    del self._messages[key]
                    self._rebuild_message_list()

        elif event_type == "patch":
            data = payload.get("data", {})
            if isinstance(data, dict):
                changed = False
                for key, val in data.items():
                    if val is None:
                        self._messages.pop(key, None)
                    else:
                        self._messages[key] = val
                    changed = True
                if changed:
                    self._rebuild_message_list()

    def _rebuild_message_list(self) -> None:
        """Rebuild the QListWidget from the current in-memory message dict."""
        sorted_msgs = sorted(
            (
                (k, v) for k, v in self._messages.items()
                if isinstance(v, dict)
            ),
            key=lambda kv: kv[1].get("timestamp", 0),
        )
        if len(sorted_msgs) > _MAX_DISPLAY:
            sorted_msgs = sorted_msgs[-_MAX_DISPLAY:]

        sb = self._msg_list.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 30

        self._msg_list.clear()
        for msg_id, msg in sorted_msgs:
            sender_name = str(msg.get("senderName", "?"))
            text        = str(msg.get("text", ""))
            ts          = int(msg.get("timestamp", 0))
            try:
                time_str = datetime.fromtimestamp(ts / 1000).strftime("%H:%M")
            except Exception:
                time_str = "??"

            display = f"[{time_str}] {_esc(sender_name)}: {_esc(text)}"
            item = QListWidgetItem(display)
            item.setData(_MSG_ROLE, {
                "senderId":   str(msg.get("senderId", "")),
                "senderName": sender_name,
            })
            self._msg_list.addItem(item)

        if at_bottom:
            self._msg_list.scrollToBottom()

    # ── Message sending ────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_send(self) -> None:
        text = self._input_line.text().strip()
        if not text or not self._can_participate():
            return
        self._input_line.clear()
        self._btn_send.setEnabled(False)

        cfg        = self._cfg
        player_id  = cfg.OVERLAY.get("player_id", "").strip()
        player_name = cfg.OVERLAY.get("player_name", "Player").strip()
        msg_data   = {
            "senderId":   player_id,
            "senderName": player_name,
            "text":       text,
            "timestamp":  int(time.time() * 1000),
        }
        threading.Thread(
            target=self._post_message,
            args=(msg_data,),
            daemon=True,
            name="ChatPost",
        ).start()

    def _post_message(self, msg_data: dict) -> None:
        """POST a new chat message to Firebase (background thread)."""
        cfg = self._cfg
        base_url = getattr(cfg, "CLOUD_URL", None)
        if not base_url:
            return
        url = f"{base_url.rstrip('/')}/{_CHAT_PATH}.json"
        try:
            payload = json.dumps(msg_data).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload, method="POST",
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "AchievementWatcher/2.0",
                },
            )
            from core.cloud_sync import _urlopen_ssl_aware
            with _urlopen_ssl_aware(cfg, req, 10):
                pass
        except Exception:
            pass
        finally:
            QMetaObject.invokeMethod(
                self, "_on_send_done", Qt.ConnectionType.QueuedConnection,
            )

    @pyqtSlot()
    def _on_send_done(self) -> None:
        self._btn_send.setEnabled(self._can_participate())

    # ── Admin right-click context menu ─────────────────────────────────────────

    @pyqtSlot(object)
    def _on_context_menu(self, pos) -> None:
        """Show admin moderation menu on right-click (admin only)."""
        if not get_admin_uid():
            return
        item = self._msg_list.itemAt(pos)
        if not item:
            return
        data = item.data(_MSG_ROLE)
        if not data:
            return
        sender_id   = data.get("senderId", "")
        sender_name = data.get("senderName", "?")
        # Prevent the admin from moderating themselves.
        if sender_id == self._cfg.OVERLAY.get("player_id", ""):
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#1a1a1a; color:#DDD; border:1px solid #444; }"
            "QMenu::item:selected { background:#FF7F00; color:#000; }"
            "QMenu::item { padding:4px 20px; }"
        )
        kick_action = menu.addAction(f"🚫 Kick {_esc(sender_name)}")
        ban_action  = menu.addAction(f"🔨 Ban {_esc(sender_name)}")

        timeout_menu = menu.addMenu(f"⏱️ Timeout {_esc(sender_name)}")
        timeout_menu.setStyleSheet(menu.styleSheet())
        t1  = timeout_menu.addAction("1 Minute")
        t5  = timeout_menu.addAction("5 Minutes")
        t10 = timeout_menu.addAction("10 Minutes")
        t30 = timeout_menu.addAction("30 Minutes")
        t60 = timeout_menu.addAction("1 Hour")

        chosen = menu.exec(self._msg_list.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == kick_action:
            self._admin_kick(sender_id)
        elif chosen == ban_action:
            self._admin_ban(sender_id)
        elif chosen == t1:
            self._admin_timeout(sender_id, 1)
        elif chosen == t5:
            self._admin_timeout(sender_id, 5)
        elif chosen == t10:
            self._admin_timeout(sender_id, 10)
        elif chosen == t30:
            self._admin_timeout(sender_id, 30)
        elif chosen == t60:
            self._admin_timeout(sender_id, 60)

    def _admin_kick(self, player_id: str) -> None:
        """Kick = short timeout (1 minute); player can rejoin after expiry."""
        self._admin_timeout(player_id, 1)

    def _admin_ban(self, player_id: str) -> None:
        """Write a permanent ban entry to Firebase."""
        def _do() -> None:
            try:
                from core.cloud_sync import CloudSync
                CloudSync.set_node(self._cfg, f"{_BANNED_PATH}/{player_id}", True)
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True, name="ChatBan").start()

    def _admin_timeout(self, player_id: str, minutes: int) -> None:
        """Write a timed-out entry to Firebase (until = now + minutes)."""
        until_ms = int((time.time() + minutes * 60) * 1000)
        def _do() -> None:
            try:
                from core.cloud_sync import CloudSync
                CloudSync.set_node(
                    self._cfg,
                    f"{_TIMEOUT_PATH}/{player_id}",
                    {"until": until_ms},
                )
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True, name="ChatTimeout").start()

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        """Stop background threads; call when the parent widget is closing."""
        self._check_timer.stop()
        self._stop_stream()


# ── Admin login dialog (used from System tab) ──────────────────────────────────

class AdminLoginDialog(QDialog):
    """Small dialog that verifies the admin identity against Firebase.

    The admin enters the hardcoded nickname ``ADMIN_NICKNAME`` ("Solters") and
    their cloud UID.  The UID is compared against the value stored at
    ``/tournament_chat/admin/uid`` in Firebase Realtime Database.

    The UID is **never** written to any local config file; it lives only in the
    module-level ``_admin_uid`` variable for the lifetime of the process.
    """

    def __init__(self, cfg, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._result_ok = False
        self.setWindowTitle("🔑 Admin Login")
        self.setFixedWidth(380)

        lay = QVBoxLayout(self)

        info = QLabel(
            "Enter the admin nickname and your cloud ID to activate moderation."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#888; font-size:9pt;")
        lay.addWidget(info)

        form = QVBoxLayout()
        form.setSpacing(4)

        form.addWidget(QLabel("Nickname:"))
        self._edit_nick = QLineEdit(ADMIN_NICKNAME)
        self._edit_nick.setReadOnly(True)
        self._edit_nick.setStyleSheet(
            "QLineEdit { background:#1a1a1a; color:#888; border:1px solid #333;"
            " border-radius:4px; padding:4px 8px; }"
        )
        form.addWidget(self._edit_nick)

        form.addWidget(QLabel("Cloud ID:"))
        self._edit_id = QLineEdit()
        self._edit_id.setPlaceholderText("Enter your cloud ID…")
        self._edit_id.setStyleSheet(
            "QLineEdit { background:#1a1a1a; color:#DDD; border:1px solid #444;"
            " border-radius:4px; padding:4px 8px; }"
        )
        form.addWidget(self._edit_id)
        lay.addLayout(form)

        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("color:#FF4444; font-size:9pt;")
        self._lbl_status.hide()
        lay.addWidget(self._lbl_status)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

        self._ok_btn = btn_box.button(QDialogButtonBox.StandardButton.Ok)

    def _on_ok(self) -> None:
        entered_id = self._edit_id.text().strip()
        if not entered_id:
            self._show_error("Please enter a cloud ID.")
            return
        if not getattr(self._cfg, "CLOUD_URL", None) or not getattr(self._cfg, "CLOUD_ENABLED", False):
            self._show_error("Cloud Sync must be enabled to verify admin identity.")
            return
        self._ok_btn.setEnabled(False)
        self._ok_btn.setText("Verifying…")
        threading.Thread(
            target=self._verify_in_background,
            args=(entered_id,),
            daemon=True,
            name="AdminVerify",
        ).start()

    def _verify_in_background(self, entered_id: str) -> None:
        """Fetch the stored admin UID and compare (background thread)."""
        try:
            from core.cloud_sync import CloudSync
            stored = CloudSync.fetch_node(self._cfg, _ADMIN_PATH)
            ok = isinstance(stored, str) and stored.strip() == entered_id
        except Exception:
            ok = False
        QMetaObject.invokeMethod(
            self, "_on_verify_done",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(bool, ok),
            Q_ARG(str, entered_id),
        )

    @pyqtSlot(bool, str)
    def _on_verify_done(self, ok: bool, entered_id: str) -> None:
        self._ok_btn.setEnabled(True)
        self._ok_btn.setText("OK")
        if ok:
            set_admin_session(entered_id)
            self._result_ok = True
            self.accept()
        else:
            self._show_error("⛔ Invalid ID – admin identity could not be verified.")

    def _show_error(self, msg: str) -> None:
        self._lbl_status.setText(msg)
        self._lbl_status.show()

    def was_successful(self) -> bool:
        return self._result_ok
