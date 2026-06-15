"""
╔══════════════════════════════════════════════════════════════════╗
║              AUTOMATED BOT  —  bot.py                           ║
║  Daily digest: Weather + News in ONE email every morning         ║
║  Schedule : 7:00 AM IST  (1:30 AM UTC)  via GitHub Actions      ║
║  Recipient: suma.hempel2007@gmail.com                            ║
╚══════════════════════════════════════════════════════════════════╝

HOW IT WORKS:
  1. Fetch today's weather for Thiruvananthapuram (OpenWeatherMap API)
  2. Pull top headlines from 3 news RSS feeds
  3. Pack everything into one beautiful HTML + plain-text email
  4. Send it via Gmail SMTP using an App Password

SECRETS REQUIRED (GitHub → Repo → Settings → Secrets → Actions):
  • OPENWEATHER_API_KEY  — your OpenWeatherMap API key
  • APP_PASSWORD         — your Gmail App Password (16 chars, no spaces)

LOCAL TESTING:
  Create a file called  .env  next to this file:
      OPENWEATHER_API_KEY=your_key_here
      APP_PASSWORD=your_app_password_here
  Then run:  python bot.py
"""

# ── Standard library imports ───────────────────────────────────────────────────
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text       import MIMEText
from datetime              import datetime

# ── Third-party imports (install with: pip install -r requirements.txt) ────────
import requests            # HTTP calls to OpenWeatherMap API
import feedparser          # Parse RSS news feeds
from dotenv import load_dotenv  # Read .env file (local dev only)

# ── Load .env for local testing ────────────────────────────────────────────────
# In GitHub Actions, secrets are injected as environment variables automatically.
# Locally, put them in a .env file (NEVER commit .env to GitHub!).
load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION  — everything in one place, easy to update
# ══════════════════════════════════════════════════════════════════════════════

# Sender / receiver
SENDER_EMAIL   = os.environ.get("SENDER_EMAIL",   "rahulpradeep2050@gmail.com")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "suma.hempel2007@gmail.com")

# Secrets — NEVER hardcode these; always read from environment
APP_PASSWORD   = os.environ.get("APP_PASSWORD")          # Gmail App Password
OWM_API_KEY    = os.environ.get("OPENWEATHER_API_KEY")   # OpenWeatherMap key

# Weather settings
CITY         = "Thiruvananthapuram"
COUNTRY_CODE = "IN"
ALERT_TEMP   = 35.0   # °C — if temp is above this, trigger an alert banner

# Email subjects
SUBJECT_WEATHER = "🌧️ Weather Alert - Thiruvananthapuram"
SUBJECT_DIGEST  = "📰 Your Daily News Digest"

# Gmail SMTP settings
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587   # TLS port

# RSS feed sources — name, feed URL, and language label for display
RSS_FEEDS = [
    {
        "name": "Manorama Online",
        "url" : "https://www.onmanorama.com/kerala.feeds.onmrss.xml",
        "lang": "Malayalam",
        "emoji": "📰"
    },
    {
        "name": "The Hindu",
        "url" : "https://www.thehindu.com/feeder/default.rss",
        "lang": "English",
        "emoji": "📰"
    },
    {
        "name": "Mathrubhumi",
        "url" : "https://feeds.bbci.co.uk/news/world/rss.xml",
        "lang": "English",
        "emoji": "📰"
    },
]

HEADLINES_PER_SOURCE = 5   # Number of headlines to pull from each RSS feed


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — WEATHER
# ══════════════════════════════════════════════════════════════════════════════

def fetch_weather():
    """
    Calls the OpenWeatherMap 'current weather' endpoint for Thiruvananthapuram.

    Returns:
        dict  — weather data fields + an 'alert' boolean
        None  — if the API call fails (network error, bad key, etc.)
    """
    if not OWM_API_KEY:
        # This will happen if the secret is not set — warn and continue.
        print("[ERROR] OPENWEATHER_API_KEY secret is not set.")
        return None

    # Build the API URL — units=metric gives temperature in Celsius
    api_url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={CITY},{COUNTRY_CODE}"
        f"&appid={OWM_API_KEY}"
        f"&units=metric"
    )

    try:
        print(f"[INFO] Calling OpenWeatherMap API for '{CITY}'...")
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()   # Raises an error for 4xx / 5xx responses
        data = response.json()

        # Pull the fields we need from the nested JSON
        weather = {
            "city"       : data["name"],
            "temp"       : round(data["main"]["temp"], 1),
            "feels_like" : round(data["main"]["feels_like"], 1),
            "humidity"   : data["main"]["humidity"],
            "description": data["weather"][0]["description"].capitalize(),
            "main"       : data["weather"][0]["main"],   # e.g. "Rain", "Clear"
            "wind_speed" : data["wind"]["speed"],
            "icon_code"  : data["weather"][0]["icon"],
        }

        # ── Alert condition check ─────────────────────────────────────────────
        # Alert = True if temperature is high OR rain is mentioned anywhere
        rain_keywords = {"rain", "drizzle", "thunderstorm"}
        weather["alert"] = (
            weather["temp"] > ALERT_TEMP
            or weather["main"].lower() in rain_keywords
            or any(kw in weather["description"].lower() for kw in rain_keywords)
        )

        print(
            f"[INFO] Weather OK — {weather['temp']}°C, "
            f"{weather['description']}, "
            f"Alert={weather['alert']}"
        )
        return weather

    except requests.exceptions.ConnectionError:
        print("[ERROR] No internet connection. Weather fetch skipped.")
    except requests.exceptions.Timeout:
        print("[ERROR] OpenWeatherMap timed out. Weather fetch skipped.")
    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] OpenWeatherMap HTTP error: {e}")
    except (KeyError, ValueError) as e:
        print(f"[ERROR] Could not parse weather response: {e}")

    return None   # Any failure returns None — email still sends without weather


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — NEWS
# ══════════════════════════════════════════════════════════════════════════════

def fetch_news():
    """
    Reads each RSS feed and grabs the top headlines.

    Returns:
        list of dicts — one dict per source with 'name', 'lang', 'articles' list.
        Each article has 'title', 'link', 'published'.
    """
    all_news = []

    for source in RSS_FEEDS:
        print(f"[INFO] Fetching RSS: {source['name']} ({source['lang']})...")
        try:
            # feedparser handles all the XML parsing for us
            feed = feedparser.parse(source["url"])

            articles = []
            for entry in feed.entries[:HEADLINES_PER_SOURCE]:
                # Some feeds don't have a published field — handle gracefully
                published_raw = entry.get("published", "")
                # Trim to first 16 chars to get "Wed, 13 Jun 2026" style
                published = published_raw[:16] if published_raw else ""

                articles.append({
                    "title"    : entry.get("title", "No title"),
                    "link"     : entry.get("link", "#"),
                    "published": published,
                })

            all_news.append({
                "name"    : source["name"],
                "lang"    : source["lang"],
                "emoji"   : source["emoji"],
                "articles": articles,
                "error"   : None,
            })
            print(f"[INFO] Got {len(articles)} headlines from {source['name']}")

        except Exception as e:
            # Don't crash the whole bot if one feed fails
            print(f"[WARNING] Failed to fetch {source['name']}: {e}")
            all_news.append({
                "name"    : source["name"],
                "lang"    : source["lang"],
                "emoji"   : source["emoji"],
                "articles": [],
                "error"   : str(e),
            })

    return all_news


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — BUILD EMAIL BODIES
# ══════════════════════════════════════════════════════════════════════════════

def build_html_email(weather, news_list):
    """
    Builds the HTML version of the daily digest email.
    Uses inline CSS so it works across all email clients (Gmail, Outlook, etc.)

    Args:
        weather   (dict | None): weather data from fetch_weather()
        news_list (list)       : news data from fetch_news()

    Returns:
        str — complete HTML document as a string
    """
    today = datetime.now().strftime("%A, %d %B %Y")

    # ── Weather block ─────────────────────────────────────────────────────────
    if weather:
        # Show a red alert banner only if conditions are triggered
        alert_html = ""
        if weather["alert"]:
            alert_html = """
            <div style="background:#ffe0e0;border-left:4px solid #e53935;
                        padding:12px 18px;border-radius:8px;margin-bottom:16px;
                        font-size:14px;">
              <strong>⚠️ Alert!</strong>
              High temperature or rain expected today in Thiruvananthapuram.
              Please carry an umbrella or plan accordingly!
            </div>
            """

        # OpenWeatherMap icon image URL
        icon_url = (
            f"https://openweathermap.org/img/wn/{weather['icon_code']}@2x.png"
        )

        weather_block = f"""
        <div style="background:linear-gradient(135deg,#e3f2fd,#bbdefb);
                    border-radius:14px;padding:22px 24px;margin-bottom:26px;">
          <h2 style="margin:0 0 4px;color:#1565c0;font-size:18px;font-weight:700;">
            🌤️ Weather — {weather['city']}
          </h2>
          <p style="margin:0 0 14px;font-size:13px;color:#555;">{today}</p>
          {alert_html}
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">
            <img src="{icon_url}" alt="{weather['description']}"
                 width="60" height="60" style="border-radius:50%;
                 background:#fff;padding:4px;">
            <div>
              <p style="margin:0;font-size:28px;font-weight:800;color:#1565c0;">
                {weather['temp']}°C
              </p>
              <p style="margin:2px 0 0;font-size:14px;color:#555;">
                {weather['description']}
              </p>
            </div>
          </div>
          <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <tr>
              <td style="padding:5px 0;color:#555;width:50%;">
                🤔 Feels like
              </td>
              <td style="padding:5px 0;font-weight:600;color:#333;">
                {weather['feels_like']}°C
              </td>
            </tr>
            <tr>
              <td style="padding:5px 0;color:#555;">💧 Humidity</td>
              <td style="padding:5px 0;font-weight:600;color:#333;">
                {weather['humidity']}%
              </td>
            </tr>
            <tr>
              <td style="padding:5px 0;color:#555;">💨 Wind Speed</td>
              <td style="padding:5px 0;font-weight:600;color:#333;">
                {weather['wind_speed']} m/s
              </td>
            </tr>
          </table>
        </div>
        """
    else:
        # Graceful fallback if weather fetch failed
        weather_block = """
        <div style="background:#fff3cd;border-radius:14px;padding:18px 22px;
                    margin-bottom:26px;font-size:14px;">
          <strong>⚠️ Weather data unavailable.</strong>
          Could not fetch weather for Thiruvananthapuram today.
          Please check that OPENWEATHER_API_KEY is set correctly.
        </div>
        """

    # ── News blocks ───────────────────────────────────────────────────────────
    # Alternating color schemes for each source
    source_styles = [
        {"bg": "#e8f5e9", "border": "#43a047", "heading": "#2e7d32"},
        {"bg": "#f3e5f5", "border": "#8e24aa", "heading": "#6a1b9a"},
        {"bg": "#fff8e1", "border": "#ffa000", "heading": "#e65100"},
    ]

    news_blocks = ""
    for i, source in enumerate(news_list):
        style = source_styles[i % len(source_styles)]

        # Build article list items
        articles_html = ""
        if source["articles"]:
            for article in source["articles"]:
                pub = (
                    f'<br><small style="color:#888;font-size:11px;">'
                    f'{article["published"]}</small>'
                    if article["published"] else ""
                )
                articles_html += f"""
                <li style="margin-bottom:10px;line-height:1.5;">
                  <a href="{article['link']}"
                     style="color:#1a73e8;text-decoration:none;
                            font-weight:500;font-size:14px;"
                     target="_blank">
                    {article['title']}
                  </a>
                  {pub}
                </li>
                """
        elif source.get("error"):
            articles_html = (
                f"<li style='color:#e53935;font-size:13px;'>"
                f"⚠️ Feed unavailable: {source['error']}"
                f"</li>"
            )
        else:
            articles_html = (
                "<li style='color:#999;font-size:13px;'>No headlines found.</li>"
            )

        lang_badge = (
            f'<span style="font-size:11px;background:#ddd;padding:2px 8px;'
            f'border-radius:20px;margin-left:8px;font-weight:500;">'
            f'{source["lang"]}</span>'
        )

        news_blocks += f"""
        <div style="background:{style['bg']};border-left:4px solid {style['border']};
                    border-radius:12px;padding:20px 22px;margin-bottom:20px;">
          <h2 style="margin:0 0 14px;color:{style['heading']};font-size:17px;
                     font-weight:700;">
            {source['emoji']} {source['name']}{lang_badge}
          </h2>
          <ul style="padding-left:18px;margin:0;list-style:disc;">
            {articles_html}
          </ul>
        </div>
        """

    # ── Full HTML document ────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Automated Bot — Daily Digest</title>
</head>
<body style="margin:0;padding:0;background:#f0f2f5;
             font-family:'Segoe UI',Arial,Helvetica,sans-serif;">

  <div style="max-width:640px;margin:30px auto;background:#ffffff;
              border-radius:18px;overflow:hidden;
              box-shadow:0 6px 30px rgba(0,0,0,0.12);">

    <!-- ── Header ──────────────────────────────────────────────────── -->
    <div style="background:linear-gradient(135deg,#1a237e 0%,#283593 60%,#3949ab 100%);
                padding:30px 32px;">
      <h1 style="color:#ffffff;margin:0;font-size:26px;font-weight:800;
                 letter-spacing:-0.5px;">
        🤖 Automated Bot
      </h1>
      <p style="color:#c5cae9;margin:6px 0 0;font-size:14px;">
        Daily Digest &nbsp;·&nbsp; {today}
      </p>
    </div>

    <!-- ── Body ────────────────────────────────────────────────────── -->
    <div style="padding:30px 32px;">

      {weather_block}

      <h2 style="font-size:19px;color:#212121;font-weight:700;
                 border-bottom:2px solid #e0e0e0;padding-bottom:10px;
                 margin:0 0 20px;">
        📰 Today's Headlines
      </h2>

      {news_blocks}

    </div>

    <!-- ── Footer ───────────────────────────────────────────────────── -->
    <div style="background:#f5f5f5;padding:16px 32px;text-align:center;
                font-size:12px;color:#9e9e9e;border-top:1px solid #e0e0e0;">
      <p style="margin:0;">
        Generated by <strong>Automated Bot</strong> &nbsp;·&nbsp; {today}
      </p>
      <p style="margin:5px 0 0;">
        Powered by OpenWeatherMap &amp; RSS &nbsp;·&nbsp;
        <a href="https://github.com/r4hulee/automated-email-bot"
           style="color:#1a73e8;text-decoration:none;">
          View on GitHub ↗
        </a>
      </p>
    </div>

  </div>

</body>
</html>"""

    return html


def build_plain_email(weather, news_list):
    """
    Builds the plain-text fallback version of the email.
    Email clients that cannot render HTML will show this instead.

    Args:
        weather   (dict | None): weather data
        news_list (list)       : news data

    Returns:
        str — plain text email body
    """
    today = datetime.now().strftime("%A, %d %B %Y")
    sep   = "=" * 52
    thin  = "-" * 40

    lines = [
        "AUTOMATED BOT — DAILY DIGEST",
        f"Date: {today}",
        sep,
        "",
    ]

    # Weather section
    if weather:
        lines += [
            f"WEATHER — {weather['city']}",
            thin,
            f"  Temperature : {weather['temp']}°C  (Feels like {weather['feels_like']}°C)",
            f"  Condition   : {weather['description']}",
            f"  Humidity    : {weather['humidity']}%",
            f"  Wind Speed  : {weather['wind_speed']} m/s",
        ]
        if weather["alert"]:
            lines.append(
                "  ⚠️  ALERT: High temperature or rain predicted! "
                "Take precautions."
            )
    else:
        lines += [
            "WEATHER",
            thin,
            "  ⚠️  Weather data unavailable. Check your API key.",
        ]

    lines += ["", sep, ""]

    # News sections
    lines.append("TODAY'S HEADLINES")
    lines.append(sep)

    for source in news_list:
        lines += [
            "",
            f"{source['name']}  [{source['lang']}]",
            thin,
        ]
        if source["articles"]:
            for j, art in enumerate(source["articles"], start=1):
                lines.append(f"  {j}. {art['title']}")
                lines.append(f"     {art['link']}")
        else:
            lines.append("  No headlines available.")

    lines += [
        "",
        sep,
        "Automated Bot  |  github.com/r4hulee/automated-email-bot",
    ]

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 4 — SEND EMAIL
# ══════════════════════════════════════════════════════════════════════════════

def send_email(subject, html_body, plain_body):
    """
    Sends the daily digest as a multipart email via Gmail SMTP.

    The email contains BOTH html_body and plain_body. Email clients prefer HTML;
    they fall back to plain text if HTML is not supported.

    Args:
        subject    (str): email subject line
        html_body  (str): HTML email content
        plain_body (str): plain text email content

    Returns:
        bool — True if sent successfully, False otherwise
    """
    if not APP_PASSWORD:
        print("[ERROR] APP_PASSWORD secret is not set. Cannot send email.")
        print("[TIP]  Add it in: GitHub Repo → Settings → Secrets → Actions")
        return False

    try:
        # Create a MIME multipart message (alternative = HTML or plain text)
        msg               = MIMEMultipart("alternative")
        msg["Subject"]    = subject
        msg["From"]       = SENDER_EMAIL
        msg["To"]         = RECEIVER_EMAIL
        msg["X-Mailer"]   = "Automated Bot / Python smtplib"

        # IMPORTANT: attach plain text FIRST, then HTML.
        # Email clients use the LAST part they can render — so HTML wins.
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body,  "html",  "utf-8"))

        print(f"[INFO] Connecting to Gmail SMTP ({SMTP_HOST}:{SMTP_PORT})...")

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()                          # Upgrade to encrypted TLS
            server.login(SENDER_EMAIL, APP_PASSWORD)   # Use App Password (not gmail pwd)
            server.sendmail(
                from_addr    = SENDER_EMAIL,
                to_addrs     = [RECEIVER_EMAIL],
                msg          = msg.as_string(),
            )

        print(f"[INFO] ✅ Email sent to {RECEIVER_EMAIL}")
        return True

    except smtplib.SMTPAuthenticationError:
        print(
            "[ERROR] Gmail authentication failed!\n"
            "  • Check that APP_PASSWORD is the 16-char App Password\n"
            "  • Make sure SENDER_EMAIL is correct\n"
            "  • Verify 2-Step Verification is enabled on your Google account"
        )
    except smtplib.SMTPConnectError:
        print("[ERROR] Could not connect to Gmail SMTP. Check your internet.")
    except smtplib.SMTPException as e:
        print(f"[ERROR] SMTP error: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected error while sending email: {e}")

    return False


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """
    Orchestrates the four steps:
      1. Fetch weather  2. Fetch news  3. Build email  4. Send email
    """
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("╔══════════════════════════════════════════╗")
    print("║   🤖  Automated Bot  —  Starting...      ║")
    print(f"║   🕐  {run_time}                  ║")
    print("╚══════════════════════════════════════════╝\n")

    # ── Step 1 ────────────────────────────────────────────────────────────────
    print("[STEP 1/4] Fetching weather data...")
    weather = fetch_weather()

    # ── Step 2 ────────────────────────────────────────────────────────────────
    print("\n[STEP 2/4] Fetching news headlines...")
    news = fetch_news()

    # ── Step 3 ────────────────────────────────────────────────────────────────
    print("\n[STEP 3/4] Building email content...")

    # Use the weather alert subject if conditions are triggered; else digest subject
    subject = SUBJECT_WEATHER if (weather and weather.get("alert")) else SUBJECT_DIGEST

    html_body  = build_html_email(weather, news)
    plain_body = build_plain_email(weather, news)
    print(f"[INFO] Subject: {subject}")

    # ── Step 4 ────────────────────────────────────────────────────────────────
    print("\n[STEP 4/4] Sending email...")
    success = send_email(subject, html_body, plain_body)

    print()
    if success:
        print("✅ Automated Bot finished successfully!\n")
    else:
        print("❌ Automated Bot failed — see errors above.\n")
        # Exit with code 1 so GitHub Actions marks the job as FAILED (red ✗)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
