# SPDX-FileCopyrightText: 2025 Aaron White <w531t4@gmail.com>
# SPDX-License-Identifier: MIT
from typing import List, Any
from dataclasses import dataclass, field

# Strings
def validate_is_str(field_name: str, data: Any) -> None:
    """ is data a string """
    if not isinstance(data, str):
        raise ValueError(f"{field_name} expects type=str. observed={type(data)}")

def validate_strlen_gt_zero(field_name: str, data: str) -> None:
    """ is len(data) > 0 """
    if len(data) == 0:
        raise ValueError(f"{field_name} expects string of length > 0. observed length=0")

# Ints
def validate_is_int(field_name: str, data: Any) -> None:
    """ is data a int """
    if not isinstance(data, int):
        raise ValueError(f"{field_name} expects type=int. observed={type(data)}")

def validate_positive(field_name: str, data: int) -> None:
    """ is data positive """
    if data < 0:
        raise ValueError(f"{field_name} expects positive integer. observed={data}")

def validate_port(field_name: str, data: int) -> None:
    """ is data a port """
    if data < 0 or data > 65555:
        raise ValueError(f"{field_name} value must be 0 <= x <= 65555. observed={data}")

# Bools
def validate_is_bool(field_name: str, data: Any) -> None:
    """ is data a bool """
    if not isinstance(data, bool):
        raise ValueError(f"{field_name} expects type=bool. observed={type(data)}")


@dataclass(kw_only=True)
class IrcBridgeConfig:
    """ Config for IrcBridge """
    entity_id: str
    transport_mode: str = field(default="ha")
    max_messages: int = field(default=3)
    irc_host: str = field(default="irc.chat.twitch.tv")
    irc_port: int = field(default=6697)
    reconnect_delay_s: int = field(default=5)
    udp_hosts: List[str] = field(default_factory=list)
    udp_port: int = field(default=7777)
    udp_line_max_chars: int = field(default=160)
    mqtt_base_topic: str = field(default="twitch_chat")
    mqtt_retain: bool = field(default=True)
    ha_entity_id: str = field(default="sensor.twitch_chat_bridge")

    def __post_init__(self):
        # entity_id
        validate_is_str("entity_id", self.entity_id)
        validate_strlen_gt_zero("entity_id", self.entity_id)

        # transport_mode
        validate_is_str("transport_mode", self.transport_mode)
        self.transport_mode = self.transport_mode.lower()
        if not self.transport_mode in ["ha", "udp", "mqtt"]:
            raise ValueError(f"transport_mode expects one of [ha, udp, mqtt]. "
                             f"observed={self.transport_mode}")

        # max_messages
        validate_is_int("max_messages", self.max_messages)
        validate_positive("max_messages", self.max_messages)

        # irc_host
        validate_is_str("irc_host", self.irc_host)
        validate_strlen_gt_zero("irc_host", self.irc_host)

        # irc_port
        validate_is_int("irc_port", self.irc_port)
        validate_port("irc_port", self.irc_port)

        # reconnect_delay_s
        validate_is_int("reconnect_delay_s", self.reconnect_delay_s)
        validate_positive("reconnect_delay_s", self.reconnect_delay_s)

        # udp_hosts
        if not isinstance(self.udp_hosts, (list, str)):
            raise TypeError(f"udp_hosts must be of type list or str. "
                            f"observed={type(self.udp_hosts)}")
        if isinstance(self.udp_hosts, str):
            self.udp_hosts = [self.udp_hosts]
        for i, item in enumerate(self.udp_hosts):
            validate_is_str(f"udp_hosts[{i}]", item)
            validate_strlen_gt_zero(f"irc_hosts[{i}]", item)

        # udp_port
        validate_is_int("udp_port", self.udp_port)
        validate_port("udp_port", self.udp_port)

        # udp_line_max_chars
        validate_is_int("udp_line_max_chars", self.udp_line_max_chars)
        validate_positive("udp_line_max_chars", self.udp_line_max_chars)

        # mqtt_base_topic
        validate_is_str("mqtt_base_topic", self.mqtt_base_topic)
        validate_strlen_gt_zero("mqtt_base_topic", self.mqtt_base_topic)

        # mqtt_retain
        validate_is_bool("mqtt_retain", self.mqtt_retain)

        # ha_entity_id
        validate_is_str("ha_entity_id", self.ha_entity_id)
        validate_strlen_gt_zero("ha_entity_id", self.ha_entity_id)
