# Copyright (c) 2025 w531t4
#
# This file is licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

from __future__ import annotations
from typing import TYPE_CHECKING
from datetime import datetime, timezone
import json

from twitch_fetchchat.base_transport import _TransportBase

if TYPE_CHECKING:
    from twitch_fetchchat.twitch_ircbridge import TwitchIrcBridge


class MQTTTransport(_TransportBase):
    def __init__(self,
                 hass_app: TwitchIrcBridge,
                 base_topic: str = "twitch_chat",
                 retain: bool = True):
        self.hass = hass_app
        self.base = base_topic.rstrip("/")
        self.retain = bool(retain)

    def send(self, lines):
        # lines: exactly 3 strings, oldest->newest
        # Publish JSON array as canonical
        payload = json.dumps(
            [{"text": (l or ""),
              "ts": int(datetime.now(tz=timezone.utc).timestamp())} for l in lines],
            ensure_ascii=False
        )
        self.hass.call_service(
            "mqtt/publish",
            topic=f"{self.base}/last3",
            payload=payload,
            retain=self.retain,
        )
        # Convenience line topics
        for i in range(3):
            self.hass.call_service(
                "mqtt/publish",
                topic=f"{self.base}/line{i+1}",
                payload=lines[i] or "",
                retain=self.retain,
            )
