# Example apps.yaml
```
twitch_fetchchat:
  module: twitch_fetchchat
  class: TwitchIrcBridge
  channel_entity_id: sensor.firetv_twitch_playback_channel
  transport: udp/mqtt/ha
  max_messages: 3
  udp_host: localhost
  udp_port: 7777
  udp_line_max_chars: 160
  mqtt_base_topic: twitch_chat
  mqtt_retain: True
  irc_host: irc.chat.twitch.tv
  irc_port: 6697
  reconnect_delay_s: 5
  ha_entity_id: sensor.twitch_chat_bridge
```