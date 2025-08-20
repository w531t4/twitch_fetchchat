# Copyright (c) 2025 w531t4
#
# This file is licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

import time
from twitch_fetchchat.base_transport import _TransportBase


class HAAttrTransport(_TransportBase):
    def __init__(self, hass_app, entity_id="sensor.twitch_chat_bridge"):
        self.hass = hass_app
        self.entity_id = entity_id

    def send(self, lines):
        # lines = [line1, line2, line3] oldest->newest (strings)
        attrs = {
            "line1": lines[0] or "",
            "line2": lines[1] or "",
            "line3": lines[2] or "",
            "updated": int(time.time()),
            "friendly_name": "Twitch Chat Bridge",
            "icon": "mdi:chat",
        }
        # Keep state constant to reduce churn; attributes carry the payload
        self.hass.set_state(self.entity_id, state="ok", attributes=attrs)
