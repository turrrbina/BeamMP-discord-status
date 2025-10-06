# BeamMP-discord-status
display BeamMP server info in discord channel

this makes use of the information packet introduced in beammp server 3.7.0 - you need to run a pre-release server for it to work.


colored information if a server is online / has players on it / is offline:

![server-info](./img/server-info.png)


optionally show host+port and map:

![hostmap](./img/displayhost-map.png)

![server-info](./img/server-info-3.png)


what you need python wise:
`pip install py-cord toml`


# HOW TO USE:
- add bot to your discord server
- put the bot TOKEN in config.toml
- run it
- go to the channel where you want the status to appear, best is to make a dedicated channel for this and make it read only
- type !beambot
- copy the channel id and message id to config.toml
- change firstrun to False
- edit servers.json to add your servers
- restart the bot
