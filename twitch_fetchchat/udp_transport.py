# SPDX-FileCopyrightText: 2025 Aaron White <w531t4@gmail.com>
# SPDX-License-Identifier: MIT

from __future__ import annotations
import socket
from typing import Sequence, TYPE_CHECKING
from twitch_fetchchat.base_transport import _TransportBase

if TYPE_CHECKING:
    from twitch_fetchchat.twitch_ircbridge import TwitchIrcBridge


class UDPTransport(_TransportBase):
    def __init__(self,
                 logger: TwitchIrcBridge,
                 hosts: Sequence[str],
                 port: int,
                 max_chars: int | None = None):
        self.log = logger.log
        self.hosts = hosts if isinstance(hosts, (list, tuple)) else [hosts]
        self.port = int(port)
        self.max_chars = max_chars
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, lines):
        out = []
        for s in lines:
            if s is None:
                s = ""
            if self.max_chars:
                s = s[: self.max_chars]
            out.append(s)
        payload = ("\n".join(out)).encode("utf-8", errors="replace")
        for host in self.hosts:
            try:
                self.sock.sendto(payload, (host, self.port))
            except Exception as e:
                self.log(f"UDP send to {host}:{self.port} failed: {e}", level="ERROR")
