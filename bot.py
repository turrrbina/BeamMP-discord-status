from datetime import datetime
import discord  # https://pycord.dev/
from discord.ext import tasks
import json
import toml # type: ignore
import sys
# from random import randint # used this for random embed colors, not needed anymore unless you want it
from re import sub
import socket
from typing import List, Dict

###################
# HOW TO USE:
# - this only works with beammp server versions > 3.7.0 !
# - add bot to your discord server
# - put the bot TOKEN in config.toml
# - run it
# - go to the channel where you want the status to appear, best is to make a dedicated channel for this and make it read only
# - type !beambot
# - copy the channel id and message id to config.toml
# - change firstrun to False in config.toml
# - edit servers.json to add your servers
# - restart the bot

BOT_NAME = "BeamMP Server Status Bot"
BOT_VERSION = "0.0.4"
#with open("config.json", "r") as f:
#    config = json.load(f)
config = toml.load("config.toml")

token = config["token"]
channel_id = config["channel_id"]
message_id = config["message_id"]
display_hostport = config["display_hostport"] # for json: .lower() == "true"
display_map = config["display_map"]
hide_errors = config["hide_errors"]
hide_empty = config["hide_empty"]
firstrun = config["firstrun"] # for json: .lower() == "true"

with open('servers.json', 'r') as file:
    servers = json.load(file)


intents = discord.Intents.default()
intents.message_content = (
    True  # < This may give you `read-only` warning, just ignore it.
)

bot = discord.Bot(intents=intents)

allplayers = 0
servers_total = 0


def bytes_to_human_readable(num, suffix='B'):
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"
 

def format_leaderboard_discord(entries: List[Dict]) -> str:
    """ format for discord with monospace code blocks """
    lines = []
    lines.append("```")
    #lines.append(f"{'Rank':<5} {'Owner':<15} {'Model':<10} {'Config':<15} {'Lap Time':<10} {'Penalties':<3}")
    lines.append(f"{'Rank':<5} {'Owner':<15} {'Model':<10} {'Config':<15} {'Lap Time':<10}")
    #lines.append("-" * 70)
    lines.append("-" * 57)
    for idx, entry in enumerate(entries, 1):
        lap_time = entry.get('lapTime', 0)
        lap_time_formatted = seconds_to_mmss(lap_time)
        owner = entry.get('owner', 'N/A')[:15]
        model = entry.get('model', 'N/A')[:10]
        config = entry.get('config', 'N/A')[:15]
        penalties = entry.get('penalties', 0)
        
        #lines.append(f"{idx:<5} {owner:<15} {model:<10} {config:<15} {lap_time_formatted:<10} {penalties:<3}")
        lines.append(f"{idx:<5} {owner:<15} {model:<10} {config:<15} {lap_time_formatted:<10}")
    
    lines.append("```")
    return "\n".join(lines)


def get_leaderboard(level: str, track: str, limit: int = 10) -> List[Dict]:
    try:
        with open('nord_leaderboard.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Error: leaderboard.json not found!")
        return []
    except json.JSONDecodeError:
        print("Error: Invalid JSON file!")
        return []

    levels = data.get('levels', {})
    if level not in levels:
        print(f"Error: Level '{level}' not found!")
        return []
    
    # Get the track
    try:
        track_data = levels[level]['tracks'][track]
    except KeyError:
        print(f"Error: Track '{track}' not found in level '{level}'!")
        return []

    # Collect all entries across all vehicle types
    all_entries = []

    for _, vehicle_data in track_data.items():
    #for vehicle_type, vehicle_data in track_data.items():
        # Get entries list (can be a list or dict)
        entries = vehicle_data.get('entries', [])

        if isinstance(entries, list):
            all_entries.extend(entries)
        elif isinstance(entries, dict) and entries:  # Non-empty dict
            all_entries.append(entries)

    # Sort by lap time (ascending - fastest first), then by penalties (ascending)
    all_entries.sort(key=lambda x: (x.get('lapTime', float('inf')), x.get('penalties', 0)))

    # Return top N entries
    return all_entries[:limit]


def get_server_info_json(host: str, port: int) -> dict:
    """ returns json server info. if empty (probably older beammp server version) or connection error, returns json["error"]=Errormsg """

    result = {}
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((host, port))
            s.sendall(b"I")
            data = bytearray()
            while True:
                chunk = s.recv(1024)
                if not chunk:
                    break  # connection closed
                data.extend(chunk)
            if len(data) > 0:
                result = json.loads(data[4:])
            else:
                result["error"] = f"server too old (3.4.1) ?"
        except ConnectionRefusedError:
            result["error"] = f"connection refused (server offline?)"
        except Exception as e:
            result["error"] = f"{host}:{port} - {e}"
    return result


def ljust_custom(s: str, width: int, fillchar: str = "-"):
    """ fills str with given fillchar to the right until width is reached """
    
    # calculate the number of fill characters needed
    fill_length = width - len(s)
    # ensure fill_length is not negative
    if fill_length > 0:
        # create the padded string
        return s + fill_length * fillchar
    return s


def make_embed(server: dict, server_info: dict, leaderboard: bool = False) -> discord.Embed | bool:
    # this creates one embed that we use in update_serverinfo to create the whole experience..

    global players_total
    global servers_total

    if "error" in server_info and hide_errors:
        return False
    
    if "error" in server_info:
        title = f"{server['ip']}:{str(server['port'])} error:"
        description = server_info['error']
        # give the embed a red'ish color to indicate there was an error:
        color = 0xb71c1c
    else:
        players = int(server_info['players'])
        if players == 0 and hide_empty:
            return False
        # we make the embed dark green if the server is online with 0 players and bright green if there are players:
        if players == 0:
            color = 0x375427
        else:
            color = 0x0fdd24
        
        # playercount on all servers. this is used in the footer in update_serverinfo at the bottom:
        players_total += players
        
        # server seems to be online, we did the hide_error and hide_empty checks - so lets add it to the list:
        servers_total += 1


        # replace the semicolon in the playerlist with a comma and space to make it prettier:
        playerslist = sub(r"\;", ", ", server_info["playerslist"])
        playersstring = f"{players}/{server_info['maxplayers']} ({playerslist})"
        
        # if there are players on the server we make it bold so its a little more visible:
        if players > 0:
            playersstring = f"**{playersstring}**"
        
        # get rid of the beammp formatting characters in server name:
        server_name = sub(r"\^.", "", server_info["name"])

        # this is how many mods there are on the server:
        modstotal = server_info['modstotal']

        # same as with playerlist above:
        modlist = sub(r"\;\/", ", ", server_info['modlist'])

        # we truncate the modlist so it doesnt use too much space if its really long:
        if len(modlist) > 300:
            modlist = f"{modlist[:300]} [.....]" # adjust to your needs
        modsize = bytes_to_human_readable(int(server_info['modstotalsize']))
        modstring = f"{modstotal} ({modlist} **{modsize}**)"
        
        mapname = server_info['map']
        # make the servername/title 130 characters long (fill with invisible spaces, Unicode U+200E) if its shorter
        # that way all embeds have the same (maximum) width. might need to play around with the width if discord changes smth:
        title = ljust_custom(server_name, 130, "‎ ")
        
        description = ""
        if display_hostport:
            description  += f"**Host/port: ** {server['ip']}:{str(server['port'])}\n"
        description += f"**Players: **  {playersstring}\n"
        if display_map:
            description += f"**Map: **  {mapname}\n"
        description += f"**Mods: **     {modstring}"
        # some experimenting artifacts, might be useful if you wanna change how the embed looks:
        # description = f"{ljust_custom('**Host/port: **', 25, '‎ ')}{server['ip']}:{str(server['port'])}\n"
        # description += f"{ljust_custom('**Players: **', 25, '‎ ')}{playersstring}\n"
        # description += f"{ljust_custom('**Mods: **', 25, '‎ ')}{modstring}"
    # OLD - used to be a random color for every embed but now it depends on the player count / server status:
    # random_color = randint(0, 0xFFFFFF)
    
    embed = discord.Embed(
            title=title,
            description=description,
            color=color  # discord.Colour.blurple()
        )
    # do we wanna display a leaderbord? lets fetch and add it to the embed:
    if leaderboard:
        embed.add_field(name="Leaderboard:", value="""
                        ```
                        ```
                        """)
        
    return embed


def seconds_to_mmss(seconds: float) -> str:
    """ convert seconds to MM:SS format """
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}:{secs:05.2f}"


@bot.event
async def on_ready():
    print(f"{bot.user} is ready and online.")
    if firstrun:
        print(f"FIRSTRUN IS SET TO TRUE, PLEASE USE !beambot IN A CHANNEL TO GET THE CHANNEL ID AND MESSAGE ID, PUT THEM IN CONFIG.TOML AND CHANGE FIRSTRUN TO FALSE.")
        return
    update_serverinfo.start()



@bot.event
async def on_message(message: discord.Message):
    # this is to setup the bot. make it say something to create a message that will 
    # be edited every time the server info updates

    if not firstrun:
        return
    if message.author.id == bot.user.id: # type: ignore
        return
    if message.content.startswith("!beambot"):
        msg = await message.channel.send("hello there!")
        await msg.edit(content=f"this messages id: {msg.id} - channel id: {msg.channel.id}")


# update the server info every minute:
@tasks.loop(seconds=60)
async def update_serverinfo():
    
    channel = bot.get_channel(channel_id)
    try:
        message = await channel.fetch_message(message_id) # type: ignore
    except Exception as e:
        print(f"COULD NOT FETCH MESSAGE. MAKE SURE THE CHANNEL ID AND MESSAGE ID ARE CORRECT IN CONFIG.TOML. ERROR: {e}")
        await bot.close()
    
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    current_unix_timestamp = int(now.timestamp()) # NEW
    global players_total
    global servers_total
    players_total = 0
    servers_total = 0
    embeds = []

    # loop through the servers and update the embeds
    for _, server in enumerate(servers):
        server_info = get_server_info_json(server["ip"], server["port"])
        embed = make_embed(server, server_info)
        if embed:
            embeds.append(embed)

    embed_info = discord.Embed(
        color=discord.Colour.dark_green(),
        timestamp=now
    )
    embed_info.set_footer(
        text=(
            f"{servers_total} {'server' if servers_total == 1 else 'servers'} online / "
            f"{players_total} {'player' if players_total == 1 else 'players'} total / last update:"
            )
    )
    
    # {current_time}") # <t:{current_unix_timestamp}:T>")
    #embed_info.set_footer(text=f"{len(servers)} servers / {players_total} players total / last update:")# {current_time}") # <t:{current_unix_timestamp}:T>") #
    embeds.append(embed_info)
    await message.edit(embeds=embeds, content="") # type: ignore


print(f"Starting {BOT_NAME} v{BOT_VERSION}... https://github.com/turrrbina/BeamMP-discord-status")
try:
    bot.run(token)
except Exception as e:
    print(f"ERROR: SOMETHING WENT WRONT (NO TOKEN IN CONFIG.TOML?) {e}")
    sys.exit(1)