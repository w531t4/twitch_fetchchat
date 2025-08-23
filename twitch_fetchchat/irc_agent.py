# Copyright (c) 2025 w531t4
#
# This file is licensed under the MIT License.
# See the LICENSE file in the project root for full license text.
from datetime import datetime, timezone
import ssl
import random
import string
import socket
import time
from collections import deque
import threading
from functools import partial
from typing import Optional, Callable, List, Dict

import irc.client
from irc.connection import Factory

from twitch_fetchchat.config import IrcBridgeConfig
from twitch_fetchchat.hasslog import HassLog


class IRCAgent():
    """
    Anonymous, read-only Twitch IRC Agent
    - Joins/parts as the entity changes (unknown/empty => part & clear output)
    - Emits rolling last 3 public chat lines through chosen transport(s)
    """
    def __init__(self,
                 config: IrcBridgeConfig,
                 logger: HassLog,
                 emit_target: Callable[[List[str]], None]) -> None:
        self.log = logger
        self.config = config
        self.send = emit_target
        self._irc_thread: threading.Thread | None = None

        # -------- State --------
        self._last: deque[Dict[str, str | int]] = deque(maxlen=max(self.config.max_messages, 3))
        self._reactor: irc.client.Reactor | None = None
        self._conn: irc.client.ServerConnection | None = None
        self._current_channel = None
        self._connected = False
        self._stop_flag = False
        self._lock = threading.RLock()

    def start(self) -> None:
        """ start the agent """
        if not self._irc_thread:
            self._irc_thread = threading.Thread(target=self._irc_loop, daemon=True)
            self._irc_thread.start()

    def switch_channel(self, channel: Optional[str]) -> None:
        """Switch to a new channel (or None to disconnect) and clear buffers."""
        with self._lock:
            self.log(f"switch_channel: channel={channel}")
            self._current_channel = channel
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
    def _emit(self) -> None:
        with self._lock:
            items = list(self._last)[(-1 * self.config.max_messages):]
        # Build exactly 3 display lines (oldest->newest), empty if missing
        lines = [""] * (self.config.max_messages - len(items)) + [
            f"{i['user']}: {i['msg']}" for i in items
        ]
        try:
            self.send(lines)
        except Exception as e:
            self.log(f"Transport send error: {e}", level="ERROR")

    # -------------------- IRC core --------------------
    def _irc_loop(self) -> None:
        joined: set[str] = set()
        backoff = self.config.reconnect_delay_s
        while not self._stop_flag:
            try:
                if not self._connected:
                    # Only connect when we actually have a target channel
                    with self._lock:
                        self.log(f"self._current_channel={self._current_channel}")
                    if self._current_channel is None:
                        time.sleep(self.config.reconnect_delay_s)
                        continue
                    self._connect()
                    joined = set()
                    backoff = self.config.reconnect_delay_s  # reset after success

                if not self._reactor:
                    raise NotImplementedError("_reactor should be defined here, but isn't.")
                self._reactor.process_once(timeout=0.5) # pyright: ignore[reportArgumentType]

                with self._lock:
                    target = self._current_channel
                    conn = self._conn

                if self._connected and conn:
                    want: set[str] = set([f"#{target}"]) if target else set()
                    # self.log(f"joined={joined} want={want}")
                    for ch in list(joined.difference(want)):
                        try:
                            conn.part(ch)
                            joined.discard(ch)
                            self.log(f"Parted {ch}")
                        except Exception as e:
                            self.log(f"PART error: {e}", level="ERROR")

                    for ch in list(want.difference(joined)):
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

        self.log(f"Connecting to {self.config.irc_host}:{self.config.irc_port} "
                 f"as {nick} (anonymous)")
        wrapper = self._tls_connect_wrapper(self.config.irc_host)
        self._conn = self._reactor.server().connect(
            self.config.irc_host,
            self.config.irc_port,
            nick,
            password=None,
            connect_factory=Factory(wrapper=wrapper),
        )

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

    def _teardown(self) -> None:
        self._connected = False
        try:
            if self._conn:
                self._conn.disconnect("bye")
        except Exception:
            pass
        self._conn = None
        self._reactor = None

    def terminate(self) -> None:
        """ stop irc session """
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

    def _tls_connect_wrapper(self, server_address: str) -> Callable[[socket.socket], ssl.SSLSocket]:
        """
        TLS socket wrapper for python-irc.
        """
        # Verified TLS (hostname check + CA validation)
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        return partial(ctx.wrap_socket, server_hostname=server_address)
