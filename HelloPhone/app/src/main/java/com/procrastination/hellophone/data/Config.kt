package com.procrastination.hellophone.data

object Config {
    // Apps to block (package names)
    val BLOCKED_APPS = listOf(
        "com.discord",
        "org.telegram.messenger",
        "com.valvesoftware.android.steam.community",
        "com.slack",
        "com.reddit.frontpage",
        "com.twitter.android",
        "com.instagram.android",
        "com.facebook.katana",
        "com.zhiliaoapp.musically", // TikTok
        "tv.twitch.android.app",
        "com.linkedin.android",
        "com.google.android.youtube"
    )

    // Websites to block (for DNS filtering if implemented)
    val BLOCKED_SITES = listOf(
        "reddit.com",
        "youtube.com",
        "twitter.com",
        "x.com",
        "discord.com",
        "news.ycombinator.com",
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "tiktok.com",
        "twitch.tv"
    )

    // Confirmation phrase required to disable
    const val CONFIRMATION_PHRASE = "I will not stop cool deepwork session"

    // Monitoring settings
    const val CAPTURE_INTERVAL_SECONDS = 60
    const val CAPTURES_BEFORE_ANALYSIS = 5

    // App blocker polling interval
    const val APP_CHECK_INTERVAL_MS = 500L
}
