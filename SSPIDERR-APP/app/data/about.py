"""Text and screenshots for the About pages.

Edit the wording here - the templates (templates/about/) only lay it out.
Screenshots live in static/img/about/ and are regenerated with
    ..\\.venv\\Scripts\\python tools\\screenshots\\capture.py
Each `cta` is (button label, endpoint name).
"""

SECTIONS = [
    {
        "slug": "overview",
        "label": "Overview",
        "icon": "fa-compass",
        "cover": "home-hero.jpg",
        "tagline": "Everything SSPIDERR does, at a glance",
        "summary": "SSPIDERR brings the world's music charts, your Spotify playlists and your own music files "
                   "together in one place. Find what's hot, hear a preview, and add it to Spotify in one click.",
        "features": [
            {
                "title": "Charts from everywhere, refreshed every day",
                "text": "The home page gathers the hottest albums, songs and artists from Apple Music, Billboard, "
                        "Last.fm and Audiomack. A fresh set is built automatically every night at midnight, so "
                        "the page opens instantly and is never more than a day old.",
                "points": ["Today's top album, song and artist", "Global top 10 and the year's best hits",
                           "Popular artists, one tap away"],
                "shots": [("home-charts.jpg", "This week's top 10 and the best hits of the year")],
                "cta": ("Open the home page", "main.home"),
            },
            {
                "title": "Add any song to Spotify in one click",
                "text": "Every song on SSPIDERR has an Add button. Press it, choose one of your playlists, and the "
                        "song is saved straight to your Spotify account.",
                "points": ["Shows only playlists you can add to", "Create a new playlist on the spot",
                           "Works on every page: charts, artists, albums, suggestions"],
                "shots": [("add-to-playlist.jpg", "The playlist picker")],
                "cta": ("See your playlists", "library.playlist"),
            },
            {
                "title": "Turn your music files into a Spotify playlist",
                "text": "Upload songs saved on your computer. SSPIDERR recognises each one, finds it on Spotify "
                        "and adds it to the playlist you choose, then shows you exactly what happened to every file.",
                "points": ["Drag and drop up to 50 MB per file", "Live progress while it works",
                           "Songs already in the playlist are skipped, never duplicated"],
                "shots": [("upload-3.jpg", "Results of an upload run")],
                "cta": ("Upload songs", "uploads.loader_page"),
                "more": "local_spotify",
            },
            {
                "title": "Go deeper on any artist, album or song",
                "text": "Every name is a link. Artist pages show followers, top tracks, the newest releases, the "
                        "full discography and similar artists. Album and song pages show stats, the story behind "
                        "the music and the full track list.",
                "points": ["Biographies and stories from Last.fm", "30-second previews",
                           "“Fans also like” recommendations"],
                "shots": [("artist.jpg", "An artist page")],
                "more": "discover",
            },
            {
                "title": "Music news, with the conversation",
                "text": "A newsroom of the latest music stories from Billboard and other outlets, updated through "
                        "the day. Read a summary, jump to the full story, and talk about it in the comments.",
                "points": ["Cover images, authors and topics", "Comment, edit and delete your own comments",
                           "Share to WhatsApp, X, Facebook or LinkedIn"],
                "shots": [("article.jpg", "A news article")],
                "more": "newsroom",
            },
            {
                "title": "Made for your phone too",
                "text": "Every page adapts to small screens, so you can discover music and update your playlists "
                        "wherever you are.",
                "points": [],
                "shots": [("home-mobile.jpg", "Home page on a phone"), ("article-mobile.jpg", "An article on a phone")],
                "mobile": True,
            },
        ],
    },
    {
        "slug": "local_spotify",
        "label": "Local → Spotify",
        "icon": "fa-upload",
        "cover": "upload-2.jpg",
        "tagline": "Your music files, recognised and added to Spotify",
        "summary": "Got songs on your computer with messy file names? Upload them and SSPIDERR works out what "
                   "each song is, finds it on Spotify and adds it to your playlist, in three simple steps.",
        "features": [
            {
                "title": "Step 1: upload your songs",
                "text": "Log in, connect Spotify once, then open Upload. Drag your files into the box or click to "
                        "choose them. You can remove a file before you continue.",
                "points": ["MP3, M4A, WAV, FLAC, AAC and OGG", "Up to 50 MB per file",
                           "Your files are private: only you can see them"],
                "shots": [("upload-1.jpg", "Uploading songs")],
                "cta": ("Start uploading", "uploads.loader_page"),
            },
            {
                "title": "Step 2: choose a playlist",
                "text": "Pick one of your Spotify playlists, or create a new one right there. Only playlists you "
                        "own or collaborate on are shown, because Spotify only lets you add to those.",
                "points": [],
                "shots": [("upload-2.jpg", "Choosing a playlist")],
            },
            {
                "title": "Step 3: we do the rest",
                "text": "SSPIDERR listens to each song, recognises it, searches Spotify and adds it to your "
                        "playlist. The page updates live, and you can leave it open or come back later. At the "
                        "end you get a song-by-song report.",
                "points": ["Added: the song is now in your playlist",
                           "Already in playlist: skipped, so there are no duplicates",
                           "Not recognised or not on Spotify: tells you which files to check"],
                "shots": [("upload-3.jpg", "The song-by-song results")],
            },
        ],
        "notes": [
            ("fa-shield", "Your files are deleted as soon as processing finishes. Files you upload but never "
                          "process are removed after 24 hours."),
            ("fa-clock-o", "Results are kept for 30 days so you can check them later, then cleared automatically."),
            ("fa-lightbulb-o", "Best results come from clear recordings of the original song. Voice notes, "
                               "live recordings and heavy remixes are harder to recognise."),
        ],
    },
    {
        "slug": "new_releases",
        "label": "Charts & releases",
        "icon": "fa-bar-chart",
        "cover": "charts.jpg",
        "tagline": "What the world is listening to, this week and any week",
        "summary": "Browse live Billboard charts from the US and over 50 countries, go back to any week since "
                   "1958, and see the year's GRAMMY winners. Every song has a preview and an Add button.",
        "features": [
            {
                "title": "Billboard charts, live",
                "text": "Open See what's new and pick a chart: the Hot 100, the Billboard 200, the Artist 100, "
                        "streaming and radio charts, charts from over 50 countries, all-time greatest lists and "
                        "pop charts. Each song is matched to Spotify so you can play and add it.",
                "points": ["Pick an optional date to see a past week", "Album and artist charts show descriptions",
                           "Results load in place, no page reload"],
                "shots": [("charts.jpg", "The Billboard Hot 100")],
                "cta": ("See what's new", "music.see_whats_new"),
            },
            {
                "title": "Time travel",
                "text": "What was number one on your birthday? Pick any week since August 1958 and see the Hot 100 "
                        "from that week, then add the classics to a playlist.",
                "points": [],
                "shots": [("time-travel.jpg", "The Hot 100 from Christmas 1999")],
                "cta": ("Try time travel", "main.time_travel_hits"),
            },
            {
                "title": "Award-winning music",
                "text": "The big winners of the GRAMMY Awards, year by year: Record, Album and Song of the Year, "
                        "Best New Artist and more, each linked to the music.",
                "points": [],
                "shots": [("awards.jpg", "GRAMMY winners")],
                "cta": ("See the winners", "main.award_winning_songs"),
            },
            {
                "title": "More ways to find new songs",
                "text": "The home page also links straight to the US Top 40, Afrobeats charts and suggestions "
                        "picked for you.",
                "points": [],
                "shots": [("home-cards.jpg", "Ways to discover music on the home page")],
            },
        ],
    },
    {
        "slug": "discover",
        "label": "Discover",
        "icon": "fa-search",
        "cover": "artist.jpg",
        "tagline": "Artists, albums, songs and Afrobeats",
        "summary": "Click any name on SSPIDERR to learn more. Every artist, album and song has its own page "
                   "with stats, stories, previews and one-click adding to Spotify.",
        "features": [
            {
                "title": "Artist pages",
                "text": "Followers, listeners and popularity at a glance, a short biography, top tracks, the newest "
                        "releases, the full album list and similar artists you might like.",
                "points": [],
                "shots": [("artist.jpg", "Artist header"), ("artist-tracks.jpg", "Top tracks and latest releases")],
            },
            {
                "title": "Album and song pages",
                "text": "See the cover, release date, listeners and plays, read about the music, play a preview "
                        "and add tracks to your playlists.",
                "points": [],
                "shots": [("album.jpg", "An album page"), ("song.jpg", "A song page")],
            },
            {
                "title": "Afrobeats charts",
                "text": "The top and trending Afrobeats songs and albums from Audiomack, updated through the day "
                        "and matched to Spotify.",
                "points": ["Top songs and trending now", "Top and trending albums", "Fresh uploads"],
                "shots": [("afro-lists.jpg", "Afrobeats charts")],
                "cta": ("Open Afrobeats", "music.afro_beats"),
            },
            {
                "title": "Suggestions picked for you",
                "text": "Once your playlists are connected, SSPIDERR looks at the artists you already listen to "
                        "and suggests songs by similar artists, telling you why each one was picked.",
                "points": [],
                "shots": [("suggestions.jpg", "Suggestions with “Because you like…”")],
                "cta": ("Get suggestions", "main.AI_suggested_songs"),
            },
        ],
    },
    {
        "slug": "newsroom",
        "label": "Newsroom",
        "icon": "fa-newspaper-o",
        "cover": "article.jpg",
        "tagline": "The latest music stories, and what people think",
        "summary": "Music news from Billboard and outlets around the world, refreshed through the day. Read the "
                   "highlights, follow the link to the full story and join the conversation.",
        "features": [
            {
                "title": "The news feed",
                "text": "The newest stories first, each with a cover image, source and comment count. On the side "
                        "you'll find what's topping the charts right now.",
                "points": [],
                "shots": [("news.jpg", "The news feed")],
                "cta": ("Read the news", "news.news_blog"),
            },
            {
                "title": "Articles",
                "text": "Each article shows the author, date, reading time and topics, a short excerpt, and a "
                        "button to read the full story on the original site. Share it in one click, or jump to "
                        "the next story.",
                "points": [],
                "shots": [("article.jpg", "An article")],
            },
            {
                "title": "Comments",
                "text": "Log in to share your thoughts. You can edit or delete your own comments at any time, "
                        "sort by oldest or newest, and see who said what and when.",
                "points": ["Plain, friendly comment box with a character counter", "Your comments are marked “You”",
                           "Edited comments are labelled"],
                "shots": [("comments.jpg", "The comments section")],
            },
        ],
    },
    {
        "slug": "playlist_hub",
        "label": "Playlist hub",
        "icon": "fa-list",
        "cover": "playlists.jpg",
        "tagline": "All your Spotify playlists in one place",
        "summary": "Connect Spotify once and SSPIDERR shows every playlist you have. Open one to see its songs "
                   "and stats, create new playlists, and fill them from anywhere on the site.",
        "features": [
            {
                "title": "Your playlists",
                "text": "Every playlist with its cover and song count, plus the latest album releases to explore.",
                "points": [],
                "shots": [("playlists.jpg", "Your playlists")],
                "cta": ("Open your playlists", "library.playlist"),
            },
            {
                "title": "Inside a playlist",
                "text": "See how many songs a playlist has, its average popularity and total length, then play "
                        "previews or copy songs into your other playlists.",
                "points": [],
                "shots": [("playlist-page.jpg", "A playlist"), ("playlist-tracks.jpg", "Its songs")],
            },
            {
                "title": "Create a playlist",
                "text": "Give it a name and an optional description and it is created in your Spotify account "
                        "straight away. SSPIDERR warns you if you already have one with the same name.",
                "points": [],
                "shots": [("create-playlist.jpg", "Creating a playlist")],
                "cta": ("Create a playlist", "library.create_playlist"),
            },
        ],
    },
]

BY_SLUG = {s["slug"]: s for s in SECTIONS}

STEPS = [
    ("fa-headphones", "Discover", "Browse charts, artists and news. Press play to hear a 30-second preview."),
    ("fa-spotify", "Connect", "Create a free account and connect Spotify once, so SSPIDERR can add songs for you."),
    ("fa-plus-circle", "Add", "Press Add on any song, or upload your own files, and it lands in your playlist."),
]

FAQ = [
    ("Is SSPIDERR free?", "Yes. You only need a free SSPIDERR account, and a Spotify account (free or Premium) "
                          "for the playlist features."),
    ("Do I need Spotify?", "Not to browse. Charts, artist pages, previews and news work without logging in. "
                           "Spotify is only needed to add songs to playlists or upload your own music."),
    ("What does SSPIDERR do with my Spotify account?", "It only reads your playlists and adds the songs you ask it "
                                                       "to. It never posts anything, follows anyone or changes your "
                                                       "account. You can disconnect it in your Spotify settings."),
    ("What happens to the music files I upload?", "They are stored privately while they are processed and deleted "
                                                  "as soon as processing finishes. The results list is kept for "
                                                  "30 days, then removed."),
    ("Why wasn't one of my songs recognised?", "Recognition works best with clear recordings of the original "
                                               "song. Voice notes, live versions, very short clips and heavy "
                                               "remixes are harder to identify."),
    ("How often is the music updated?", "The home page refreshes every day at midnight, the news through the "
                                        "day, and charts are fetched live when you open them."),
]
