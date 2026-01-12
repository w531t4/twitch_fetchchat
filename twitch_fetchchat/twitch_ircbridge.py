# SPDX-FileCopyrightText: 2025 Aaron White <w531t4@gmail.com>
# SPDX-License-Identifier: MIT
from dataclasses import fields
from typing import Any, List
import appdaemon.plugins.hass.hassapi as hass


from twitch_fetchchat.mqtt_transport import MQTTTransport
from twitch_fetchchat.udp_transport import UDPTransport
from twitch_fetchchat.ha_transport import HAAttrTransport
from twitch_fetchchat.config import IrcBridgeConfig
from twitch_fetchchat.irc_agent import IRCAgent


class TwitchIrcBridge(hass.Hass):
    """
    Bridge between HASS and Twitch IRC Agent
    - Watches an HA entity for the channel name
    """

    config: IrcBridgeConfig
    _transports: List[UDPTransport | MQTTTransport | HAAttrTransport]
    irc_agent: IRCAgent

    def initialize(self) -> None:
        """appdaemon init section"""
        self.args.update({"entity_id": self.args.get("channel_entity_id")})
        self.args.pop("channel_entity_id")
        self.config = IrcBridgeConfig(
            **{
                f.name: self.args[f.name]
                for f in fields(IrcBridgeConfig)
                if f.name in self.args
            }
        )

        # -------- Build transports --------
        self._transports = []
        if self.config.transport_mode == "udp":
            if not self.config.udp_hosts:
                self.error("transport=udp requires udp_host", level="ERROR")
            else:
                self._transports.append(
                    UDPTransport(
                        self,
                        self.config.udp_hosts,
                        self.config.udp_port,
                        self.config.udp_line_max_chars,
                    )
                )
        elif self.config.transport_mode == "mqtt":
            self._transports.append(
                MQTTTransport(
                    self, self.config.mqtt_base_topic, self.config.mqtt_retain
                )
            )
        elif self.config.transport_mode == "ha":
            self._transports.append(HAAttrTransport(self, self.config.ha_entity_id))
        if not self._transports:
            self.error("No valid transport configured (use udp/mqtt/ha)", level="ERROR")

        self.irc_agent = IRCAgent(
            logger=self.log, config=self.config, emit_target=self._transports[0].send
        )

        # Drive from entity
        # subscribe for future changes
        self.listen_state(self._on_channel_change, self.config.entity_id)

        # apply current value once at startup
        cur = self.get_state(self.config.entity_id)  # None if entity missing
        self.log(f"initial entity_id={self.config.entity_id} cur={cur}")
        self._on_channel_change(self.config.entity_id, "state", None, cur)
        self.log(f"TwitchIrcBridge ready (transport={self.config.transport_mode})")

        self.irc_agent.start()

    # -------------------- Entity handling --------------------
    def _on_channel_change(
        self,  # pylint: disable=unused-argument
        entity: str,
        attribute: str,  # pylint: disable=unused-argument
        old: Any,  # pylint: disable=unused-argument
        new: Any,
        **kwargs: Any,
    ) -> None:
        """React to channel-entity changes and (dis)connect accordingly."""
        if entity != self.config.entity_id:
            self.log(
                f"this shouldn't happen. found entity={entity} != "
                f"self.config.entity_id=self.config.entity_id"
            )
        new_channel: str = (new or "").strip().lstrip("#").lower()
        if new in (None, "") or new_channel in ("unknown", "unavailable", "none"):
            self.log(f"{self.config.entity_id} unknown/unavailable -> disconnect IRC")
            self.irc_agent.switch_channel(None)
        else:
            self.irc_agent.switch_channel(new_channel)
