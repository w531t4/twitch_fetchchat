# Copyright (c) 2025 w531t4
#
# This file is licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

import socket
from twitch_fetchchat.base_transport import _TransportBase


class UDPTransport(_TransportBase):
    def __init__(self, logger, hosts, port, max_chars=None):
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
