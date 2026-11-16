"""Pure functions: artist-name cleaning, chart parsing, dates, sanitising (no network)."""
import pytest

from app.services import charts, scrapers
from app.services.sanitize import clean_html, gravatar_url
from app.utils import safe_next


@pytest.mark.parametrize("raw, expected", [
    ("Alex Warren", "Alex Warren"),                       # B2: the letter x is not a separator
    ("Lil Nas X", "Lil Nas X"),
    ("Tame Impala & JENNIE", "Tame Impala, JENNIE"),
    ("DJ Snake Featuring Selena Gomez", "DJ Snake, Selena Gomez"),
    ("Morgan Wallen With Tate McRae", "Morgan Wallen, Tate McRae"),
    ("Feather Jones x Sam", "Feather Jones, Sam"),
    ("A feat. B", "A, B"),
    ("Zach Bryan FeaturingLana Del Rey", "Zach Bryan, Lana Del Rey"),   # glued by Billboard
    ("DJ SnakeFeaturing Selena", "DJ Snake, Selena"),
])
def test_normalise_artists(raw, expected):
    assert scrapers.normalise_artists(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Brandy & Monica", "Brandy"),                        # 'and' inside a name is not a separator
    ("Sandé", "Sandé"),
    ("Wizkid ft. Tems", "Wizkid"),
    ("Lil Nas X", "Lil Nas X"),
    ("Burna Boy (feat. Ed Sheeran)", "Burna Boy"),
    ("Simon and Garfunkel", "Simon"),
    ("Featherstone", "Featherstone"),
    ("", None),
])
def test_main_artist(raw, expected):
    assert scrapers.main_artist(raw) == expected


BILLBOARD_HTML = """
<ul>
  <li class="o-chart-results-list__item"><h3>Song One</h3><span class="c-label a-no-trucate">Alex Warren</span></li>
  <li class="o-chart-results-list__item"><span>no title here</span></li>
  <li class="o-chart-results-list__item"><h3>Song &amp; Two</h3><span class="c-label a-no-trucate">A Featuring B</span></li>
</ul>"""


def test_parse_billboard_chart():
    rows = scrapers.parse_billboard_chart(BILLBOARD_HTML, limit=10)
    assert rows == [
        {"song": "Song One", "artist": "Alex Warren", "main_artist": "Alex Warren"},
        {"song": "Song & Two", "artist": "A, B", "main_artist": "A"},
    ]


def test_parse_billboard_chart_respects_limit():
    assert len(scrapers.parse_billboard_chart(BILLBOARD_HTML, limit=1)) == 1


@pytest.mark.parametrize("endpoint, kind", [
    ("hot-100", "songs"), ("billboard-200", "albums"), ("artist-100", "artists"),
    ("greece-albums", "albums"), ("top-arabic-artist-100", "artists"),
])
def test_chart_type(endpoint, kind):
    assert scrapers.chart_type(endpoint) == kind


AUDIOMACK_HTML = """
<div class="ChartsItem-content"><div class="ChartsItem-data">
  <h2 class="ChartsItem-artist">Asake &amp; Wizkid</h2><h2 class="ChartsItem-title">MMS</h2></div></div>
<div class="ChartsItem-content"><div>broken</div></div>"""


def test_parse_audiomack_chart():
    assert scrapers.parse_audiomack_chart(AUDIOMACK_HTML) == [
        {"artist": "Asake & Wizkid", "title": "MMS", "main_artist": "Asake"}]


@pytest.mark.parametrize("raw, expected", [
    ("2025-10-18", "2025-10-18"),                         # what <input type=date> sends (B1)
    ("10/18/2025", "2025-10-18"),
    ("1950-01-01", None),                                 # before the Hot 100 existed
    ("2999-01-01", None),                                 # future
    ("not a date", None),
    ("", None),
])
def test_parse_chart_date(raw, expected):
    assert charts.parse_chart_date(raw) == expected


def test_grammy_url():
    assert charts.grammy_url(2025) == "https://www.grammy.com/awards/67th-annual-grammy-awards-2024"
    assert charts.grammy_url(2021) == "https://www.grammy.com/awards/63rd-annual-grammy-awards-2020"
    assert charts.grammy_url(2013) == "https://www.grammy.com/awards/55th-annual-grammy-awards-2012"


GRAMMY_HTML = """
<div class="accordion-item"><button class="accordion-button">Record Of The Year See all</button>
  <div class="winner-heading">Winner</div><p class="fs-xm">Not Like Us</p><p>Kendrick Lamar</p></div>
<div class="accordion-item"><button class="accordion-button">Best New Artist See all</button>
  <div class="winner-heading">Winner</div><p class="fs-xm">Chappell Roan</p><p>Benson Boone</p></div>
<div class="accordion-item"><button>Album Of The Year</button></div>"""


def test_parse_grammy_winners():
    assert charts.parse_grammy_winners(GRAMMY_HTML) == [
        {"category": "Record Of The Year", "title": "Not Like Us", "artist": "Kendrick Lamar", "kind": "song"},
        {"category": "Best New Artist", "title": "Chappell Roan", "artist": None, "kind": "person"},
    ]


# --------------------------------------------------------------------- security helpers
@pytest.mark.parametrize("dirty", [
    '<img src=x onerror="alert(1)">hi',
    "<script>alert(1)</script>hi",
    '<a href="javascript:alert(1)">hi</a>',
    '<p onclick="steal()">hi</p>',
])
def test_clean_html_removes_scripts(dirty):
    cleaned = clean_html(dirty)
    assert "alert" not in cleaned and "onerror" not in cleaned and "onclick" not in cleaned
    assert "hi" in cleaned


def test_clean_html_keeps_formatting():
    assert clean_html("<p><strong>bold</strong> <a href='https://x.com'>link</a></p>").startswith("<p><strong>bold</strong>")


@pytest.mark.parametrize("target, expected", [
    ("/playlist", "/playlist"),
    ("/song-page/1?x=2", "/song-page/1?x=2"),
    ("https://evil.example/", None),                      # S3: open redirect
    ("//evil.example/", None),
    ("javascript:alert(1)", None),
    (None, None),
])
def test_safe_next(target, expected):
    assert safe_next(target) == expected


def test_gravatar_url_is_https():
    assert gravatar_url("A@B.com").startswith("https://www.gravatar.com/avatar/")
    assert gravatar_url("a@b.com") == gravatar_url(" A@B.com ")


def test_http_errors_never_log_urls():
    import requests

    from app.services.http import describe
    response = requests.Response()
    response.status_code = 403
    err = requests.HTTPError("403 for url: https://x/?key=SECRET", response=response)
    assert describe(err) == "HTTP 403" and "SECRET" not in describe(err)


def test_billboard_artist_split_across_tags_keeps_spaces():
    page = ('<li class="o-chart-results-list__item"><h3>BbY WOW</h3>'
            '<span class="c-label a-no-trucate">Karol G<span>With</span>Judeline</span></li>')
    rows = scrapers.parse_billboard_chart(page)
    assert rows[0]["artist"] == "Karol G, Judeline" and rows[0]["main_artist"] == "Karol G"
