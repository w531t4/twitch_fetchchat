# SPDX-FileCopyrightText: 2025 Aaron White <w531t4@gmail.com>
# SPDX-License-Identifier: MIT

from __future__ import annotations
from typing import TYPE_CHECKING
import time
from twitch_fetchchat.base_transport import _TransportBase

if TYPE_CHECKING:
    from twitch_fetchchat.twitch_ircbridge import TwitchIrcBridge


class HAAttrTransport(_TransportBase):
    def __init__(
        self, hass_app: TwitchIrcBridge, entity_id: str = "sensor.twitch_chat_bridge"
    ):
        self.hass = hass_app
        self.entity_id = entity_id

    def send(self, lines):
        # lines = [line1, line2, line3] oldest->newest (strings)
        attrs = {
            "updated": int(time.time()),
            "friendly_name": "Twitch Chat Bridge",
            "icon": "mdi:chat",
        }
        for i, line in enumerate(lines):
            attrs.update({f"line{i + 1}": line or ""})

        # Keep state constant to reduce churn; attributes carry the payload
        self.hass.set_state(self.entity_id, state="ok", attributes=attrs)
