from datetime import datetime
import discord  # https://pycord.dev/
from discord.ext import tasks
import json
import toml
import sys
# from random import randint # used this for random embed colors, not needed anymore unless you want it
from re import sub
import socket

###################
# HOW TO USE:
# - this only works with beammp server versions > 3.7.0 !
# - add bot to your discord server
# - put the bot TOKEN in config.toml
# - run it
# - go to the channel where you want the status to appear, best is to make a dedicated channel for this and make it read only
# - type !beambot
# - copy the channel id and message id to config.toml
# - edit servers.json to add your servers
# - change firstrun to False
# - restart the bot

BOT_NAME = "BeamMP Server Status Bot"
BOT_VERSION = "0.0.2"
#with open("config.json", "r") as f:
#    config = json.load(f)
config = toml.load("config.toml")

token = config["token"]
channel_id = config["channel_id"]
message_id = config["message_id"]
display_hostport = config["display_hostport"] # for json: .lower() == "true"
display_map = config["display_map"]
firstrun = config["firstrun"] # for json: .lower() == "true"

with open('servers.json', 'r') as file:
    servers = json.load(file)


intents = discord.Intents.default()
intents.message_content = (
    True  # < This may give you `read-only` warning, just ignore it.
)

bot = discord.Bot(intents=intents)

allplayers = 0


def bytes_to_human_readable(num, suffix='B'):
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"
 
 
# fills str with given fillchar to the right until width is reached:
def ljust_custom(s: str, width: int, fillchar: str = "-"):
    # calculate the number of fill characters needed
    fill_length = width - len(s)
    # ensure fill_length is not negative
    if fill_length > 0:
        # create the padded string
        return s + fill_length * fillchar
    return s


def get_server_info_json(host: str, port: int):
    # returns json server info. if empty (probably older beammp server version) or connection error, returns json["error"]=Errormsg

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


def make_embed(server, server_info):
    # this creates one embed that we use in update_serverinfo to create the whole experience..

    global allplayers
    if "error" in server_info:
        title = f"{server['ip']}:{str(server['port'])} error:"
        description = server_info['error']
        # give the embed a red'ish color to indicate there was an error:
        color = 0xb71c1c
    else:
        players = int(server_info['players'])
        # we make the embed dark green if the server is online with 0 players and bright green if there are players:
        if players == 0:
            color = 0x375427
        else:
            color = 0x0fdd24
        
        # playercount on all servers. this is used in the footer in update_serverinfo at the bottom:
        allplayers += players

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
    return embed


@bot.event
async def on_ready():
    update_serverinfo.start()
    print(f"{bot.user} is ready and online.")


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

    global allplayers
    allplayers = 0
    
    embeds = []

    # loop through the servers and update the embeds
    for _, server in enumerate(servers):
        server_info = get_server_info_json(server["ip"], server["port"])
        embed = make_embed(server, server_info)
        embeds.append(embed)

    embed_info = discord.Embed(
        color=discord.Colour.dark_green()
    )
    embed_info.set_footer(text=f"{len(servers)} servers / {allplayers} players total / last update: {current_time}")
    embeds.append(embed_info)
    await message.edit(embeds=embeds, content="")


print(f"Starting {BOT_NAME} v{BOT_VERSION}... https://github.com/turrrbina/BeamMP-discord-status")
try:
    bot.run(token)
except Exception as e:
    print(f"ERROR: SOMETHING WENT WRONT (NO TOKEN IN CONFIG.TOML?) {e}")
    sys.exit(1)
