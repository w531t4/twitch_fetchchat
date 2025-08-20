# Copyright (c) 2025 w531t4
#
# This file is licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

import threading
from collections import deque
from datetime import datetime, timezone
import ssl
import random
import string
import socket
import time
from typing import Callable, Any, cast, Dict, Optional, Tuple
import appdaemon.plugins.hass.hassapi as hass
import irc.client
import irc.connection

from twitch_fetchchat.mqtt_transport import MQTTTransport
from twitch_fetchchat.udp_transport import UDPTransport
from twitch_fetchchat.ha_transport import HAAttrTransport

# -------------------- App --------------------
Callback = Callable[[str, str, Any, Any, dict], None]

class TwitchIrcBridge(hass.Hass):
    """
    Anonymous, read-only Twitch IRC bridge with pluggable transports (udp/mqtt/both).
    - Watches an HA entity for the channel name
    - Joins/parts as the entity changes (unknown/empty => part & clear output)
    - Emits rolling last 3 public chat lines through chosen transport(s)
    """

    def initialize(self):
        # -------- Required --------
        self.entity_id = self.args.get("channel_entity_id")              # e.g. sensor.twitch_channel

        # -------- Output / transport config --------
        # transport: "udp" | "mqtt" | "both"
        self.transport_mode = (self.args.get("transport", "udp")).lower()
        self.max_messages = int(self.args.get("max_messages", 3))  # must be >= 3; we emit top 3

        # UDP options
        self.udp_hosts = self.args.get("udp_host", [])           # string or [list]
        self.udp_port = int(self.args.get("udp_port", 7777))
        self.udp_line_max_chars = self.args.get("udp_line_max_chars", 160)  # e.g. 160 or None

        # MQTT options
        self.mqtt_base_topic = self.args.get("mqtt_base_topic", "twitch_chat")
        self.mqtt_retain = bool(self.args.get("mqtt_retain", True))

        # -------- IRC options --------
        self.irc_host = self.args.get("irc_host", "irc.chat.twitch.tv")
        self.irc_port = int(self.args.get("irc_port", 6697))  # TLS
        self.reconnect_delay_s = int(self.args.get("reconnect_delay_s", 5))

        self.ha_entity_id = self.args.get("ha_entity_id", "sensor.twitch_chat_bridge")

        # -------- State --------
        self._last = deque(maxlen=max(self.max_messages, 3))  # we’ll always output top 3
        self._reactor = None
        self._conn = None
        self._current_channel = None
        self._connected = False
        self._stop_flag = False
        self._lock = threading.RLock()
        self._want_connect = False

        # -------- Build transports --------
        self._transports = []
        if self.transport_mode in ("udp", "both"):
            if not self.udp_hosts:
                self.error("transport=udp/both requires udp_host", level="ERROR")
            else:
                self._transports.append(UDPTransport(self, self.udp_hosts, self.udp_port, self.udp_line_max_chars))
        if self.transport_mode in ("mqtt", "both"):
            self._transports.append(MQTTTransport(self, self.mqtt_base_topic, self.mqtt_retain))
        if self.transport_mode in ("ha", "both_ha_udp", "both_ha_mqtt"):  # or just check == "ha"
            self._transports.append(HAAttrTransport(self, self.ha_entity_id))
        if not self._transports:
            self.error("No valid transport configured (use udp/mqtt/both)", level="ERROR")

        # Drive from entity
        # subscribe for future changes
        entity_id: str = self.entity_id
        self.listen_state(self._on_channel_change,
                          entity_id)

        # apply current value once at startup
        cur = self.get_state(self.entity_id)  # None if entity missing
        self.log(f"initial entity_id={self.entity_id} cur={cur}")
        self._on_channel_change(self.entity_id, "state", None, cur, {})

        self.log(f"TwitchIrcBridge ready (transport={self.transport_mode})")

        # -------- Start IRC loop thread --------
        self._irc_thread = threading.Thread(target=self._irc_loop, daemon=True)
        self._irc_thread.start()

    # -------------------- Entity handling --------------------
    def _on_channel_change(self,
                           entity: str,
                           attribute: str,
                           old: Any,
                           new: Any,
                           kwargs: dict[str, Any]) -> None:
        """React to channel-entity changes and (dis)connect accordingly."""
        if entity != self.entity_id:
            self.log("this shouldn't happen. found entity=%s != self.entity_id=%s" % (entity, self.entity_id))
        new_ch: str = (new or "").strip().lstrip("#").lower()
        if new in (None, "") or new_ch in ("unknown", "unavailable", "none"):
            self.log(f"{self.entity_id} unknown/unavailable -> disconnect IRC")
            self._switch_channel(None)
        else:
            self._switch_channel(new_ch)


    def _switch_channel(self, channel: Optional[str]) -> None:
        """Switch to a new channel (or None to disconnect) and clear buffers."""
        with self._lock:
            self.log(f"_switch_channel: channel={channel}")
            self._current_channel = channel
            self._want_connect = channel is not None
            self._last.clear()
        self._emit()  # send blanks on switch/part

        # If no active channel, fully disconnect from IRC and remain offline
        if channel is None:
            try:
                self.log("Tearing down IRC connection (no active channel).")
                self._teardown()
            except Exception:
                pass


    # -------------------- Emission --------------------
    def _emit(self):
        with self._lock:
            items = list(self._last)
        # Build exactly 3 display lines (oldest->newest), empty if missing
        pad = [""] * (3 - len(items)) + [
            f"{i['user']}: {i['msg']}" for i in items[-3:]
        ]
        lines = pad[-3:]
        for t in self._transports:
            try:
                t.send(lines)
            except Exception as e:
                self.log(f"Transport send error: {e}", level="ERROR")

    # -------------------- IRC core --------------------
    def _irc_loop(self):
        backoff = self.reconnect_delay_s
        while not self._stop_flag:
            try:
                if not self._connected:
                    # Only connect when we actually have a target channel
                    with self._lock:
                        want = self._want_connect
                        self.log(f"self._current_channel={self._current_channel}")
                        self.log(f"self._want_connect={self._want_connect}")
                    if not want:
                        time.sleep(self.reconnect_delay_s)
                        continue
                    self._connect()
                    backoff = self.reconnect_delay_s  # reset after success

                self._reactor.process_once(timeout=0.5)

                with self._lock:
                    target = self._current_channel
                    conn = self._conn

                if self._connected and conn:
                    joined = getattr(conn, "_joined", set())
                    want = set([f"#{target}"]) if target else set()
                    # self.log(f"joined={joined} want={want}")
                    for ch in list(joined - want):
                        try:
                            conn.part(ch)
                            joined.discard(ch)
                            self.log(f"Parted {ch}")
                        except Exception as e:
                            self.log(f"PART error: {e}", level="ERROR")

                    for ch in list(want - joined):
                        try:
                            conn.join(ch)
                            joined.add(ch)
                            self.log(f"Joined {ch}")
                        except Exception as e:
                            self.log(f"JOIN error: {e}", level="ERROR")
                continue
            except Exception as e:
                self.log(f"IRC loop error: {e}", level="WARNING")
                self._teardown()
            # optional backoff (if you already use it)
            time.sleep(backoff + random.random() * 0.5 * backoff)
            backoff = min(backoff * 2, 60)

    def _connect(self) -> None:
        self._reactor = irc.client.Reactor()
        nick = "justinfan" + "".join(random.choices(string.digits, k=6))  # anonymous

        self.log(f"Connecting to {self.irc_host}:{self.irc_port} as {nick} (anonymous)")
        self._conn = self._reactor.server().connect(
            self.irc_host,
            self.irc_port,
            nick,
            password=None,
            connect_factory=self._tls_connect_factory,  # <-- key change
        )
        self._conn._joined = set()

        try:
            self._conn.cap("REQ", "twitch.tv/tags")
            self._conn.cap("REQ", "twitch.tv/commands")
            self._conn.cap("REQ", "twitch.tv/membership")
        except Exception:
            pass

        self._conn.add_global_handler("disconnect", self._on_disconnect)
        self._conn.add_global_handler("pubmsg", self._on_pubmsg)
        self._conn.add_global_handler("ping", self._on_ping)

        self._connected = True

    def _teardown(self):
        self._connected = False
        try:
            if self._conn:
                self._conn.disconnect("bye")
        except Exception:
            pass
        self._conn = None
        self._reactor = None

    def terminate(self):
        self._stop_flag = True
        self._teardown()

    # -------------------- IRC events --------------------
    def _on_disconnect(self,
                       conn: irc.client.ServerConnection,
                       event: irc.client.Event) -> None:
        """Handle disconnect events."""
        self._connected = False


    def _on_ping(self,
                 conn: irc.client.ServerConnection,
                 event: irc.client.Event) -> None:
        """Respond to server PINGs to keep the connection alive."""
        try:
            target: Optional[str] = event.target  # may be None
            conn.pong(target or "tmi.twitch.tv")
        except Exception:
            pass

    def _on_pubmsg(self,
                   conn: irc.client.ServerConnection,
                   event: irc.client.Event) -> None:
        """Handle public channel chat messages (PRIVMSG to a channel)."""
        try:
            channel: str = event.target or ""
            nick: str = irc.client.NickMask(event.source).nick if event.source else "unknown"
            msg: str = event.arguments[0] if event.arguments else ""

            item: Dict[str, str | int] = {
                "ch": channel.lstrip("#"),
                "user": nick,
                "msg": msg,
                "ts": int(datetime.now(tz=timezone.utc).timestamp()),
            }

            with self._lock:
                self._last.append(item)
            self._emit()
        except Exception as e:
            self.log(f"pubmsg parse error: {e}", level="ERROR")

    def _tls_connect_factory(self, *args: Any, **kwargs: Any) -> ssl.SSLSocket:
        """
        Robust TLS socket factory for python-irc.
        Accepts (host, port), ( (host, port), ), or host with port in kwargs.
        """
        host: str
        port: int

        # Unpack args in a version-agnostic way
        if len(args) == 1 and isinstance(args[0], tuple):
            host, port = args[0]  # ((host, port),)
        elif len(args) >= 2:
            host, port = args[0], args[1]  # (host, port, ...)
        elif len(args) == 1:
            host = args[0]
            port = int(kwargs.get("port", getattr(self, "irc_port", 6697)))
        else:
            host = kwargs.get("host") or kwargs.get("server")
            if not host:
                raise TypeError("connect_factory: missing host")
            port = int(kwargs.get("port", getattr(self, "irc_port", 6697)))

        # TCP connect
        raw = socket.create_connection((host, port), timeout=15)

        # Verified TLS (hostname check + CA validation)
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED

        return ctx.wrap_socket(raw, server_hostname=host)
