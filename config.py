"""Configuration constants for the productivity enforcement app."""

# Blocked websites (will be redirected to 0.0.0.0 in hosts file)
BLOCKED_SITES = [
    "reddit.com",
    "www.reddit.com",
    "old.reddit.com",
    "youtube.com",
    "www.youtube.com",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
    "discord.com",
    "www.discord.com",
    "discord.gg",
    "news.ycombinator.com",
    "linkedin.com",
    "www.linkedin.com",
    "facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "tiktok.com",
    "www.tiktok.com",
    "twitch.tv",
    "www.twitch.tv",
]

# Apps to kill (process names)
BLOCKED_APPS = [
    "Discord.exe",
    "Telegram.exe",
    "Steam.exe",
    "steamwebhelper.exe",
    "slack.exe",
]

# Confirmation phrase to disable blocking
CONFIRMATION_PHRASE = "I will not stop cool deepwork session"

# Monitoring settings
CAPTURE_INTERVAL_SECONDS = 60
CAPTURES_BEFORE_ANALYSIS = 5

# Hosts file path (Windows)
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"

# Marker for our entries in hosts file
HOSTS_MARKER_START = "# PRODUCTIVITY_BLOCKER_START"
HOSTS_MARKER_END = "# PRODUCTIVITY_BLOCKER_END"
