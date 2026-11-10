"""The demo case "Demo: State v. Mateo Ruiz (synthetic)" (lx-demo): six phones, four bank accounts and the State's
discovery documents of one invented defence investigation, with its answer key in ``planted-truths.json``.

Every person, business, bank, address, number (555-01xx), e-mail (example.com/.org/.net) and plate is invented. The
phones are written by ``fixture_builder`` (UXD-33: no second phone generator) at the structure of catalogue phones;
this module holds the story, the ledgers, and the document writers, which reuse the builder's PDF statement writer.
Deterministic: the same call gives the same bytes. Pillow (photos, the scanned statement) and ffmpeg's flite voice
(the voice note) are used when present; without them the manifest says what was not made.

    python3 fixture_builder.py demo OUT_DIR
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

try:
    from . import fixture_builder as fb
except ImportError:  # pragma: no cover - run as a script
    import fixture_builder as fb

HERE = Path(__file__).resolve().parent
ANSWER_KEY = HERE / "planted-truths.json"
CASE_TITLE = "Demo: State v. Mateo Ruiz (synthetic)"
BANNER = "SYNTHETIC — INVENTED FOR TESTING — NOT EVIDENCE"
EASTERN = ZoneInfo("America/New_York")


def L(y, mo, d, h=0, mi=0) -> dt.datetime:
    """A Baltimore wall-clock time as the naive UTC instant the reports carry."""
    local = dt.datetime(y, mo, d, h, mi, tzinfo=EASTERN)
    return local.astimezone(dt.timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------------------------------------------
# People (invented). Numbers are in the fictional 555-01xx range.
P = fb.Person
PEOPLE = [
    P("mateo", "Mateo Ruiz", ["+14435550112"], {"WhatsApp": "+14435550112"}, "mateo.ruiz@example.com"),
    P("lucia", "Lucía Ruiz", ["+14435550113"], {}, "lucia.ruiz@example.com"),
    P("rosa", "Rosa Ruiz", ["+14105550114"], {}, "rosa.ruiz@example.org"),
    P("shop", "Ruiz Auto & Tire", ["+14105550110"], {}, "office@ruizautotire.example.com"),
    P("kell", "Travis Kell", ["+14105550121"], {"Telegram": "@tk_nights", "WhatsApp": "+14105550121"},
      "travis.kell@example.net"),
    P("burner", "", ["+14435550131"], {}, "no-mail@example.net"),
    P("curtis", "Curtis Fallowby", ["+14435550131"], {}, "c.fallowby@example.org"),
    P("dee", "Desmond Okafor", ["+14105550141", "+14435550142"], {"Telegram": "@dee_o28"}, "d.okafor@example.org"),
    P("dee2", "Desmond Okafor", ["+14435550142"], {}, "d.okafor@example.org"),
    P("brianna", "Brianna Cole", ["+14435550151"], {"WhatsApp": "+14435550151"}, "bri.cole@example.com"),
    P("lena", "Lena Marsh", ["+14105550161"], {}, "lena.marsh@example.net"),
    P("joan", "Joan Marsh", ["+14105550162"], {}, "joan.marsh@example.net"),
    P("gary", "Gary Penn", ["+14105550171"], {}, "penn.tools@example.com"),
    P("garza", "Mateo Garza", ["+14435550181"], {}, "mgarza.mech@example.com"),
    P("vint", "Harold Vint", ["+14105550191"], {}, "h.vint@example.org"),
]
PEOPLE_BY_KEY = {p.key: p for p in PEOPLE}
# Names used anywhere in the case: checked against the live cases (by count only) and the box's Nominatim before loading.
INVENTED_NAMES = sorted({p.name for p in PEOPLE if p.name} | {"Carla Ruiz", "Paula Grennan"})
INVENTED_PLACES = [
    "Brightwater Logistics", "Fenwick Ridge Industrial Park", "Ruiz Auto & Tire", "Penn's Used Tools",
    "Stowell Self Storage", "Larkfield Tradesmen Credit Union", "Kestrel Point Bank", "Old Ferrow Savings Bank",
    "Pocketwire", "Benchyard", "Quillan's Home Supply", "Greenhollow Grocers", "Elkmere Home Lending",
    "Corbel Auto Parts", "Ferrowmere Medical Center", "Larkmont Apartments", "Torvane", "Keldar", "Lumetra",
    "Tessaly Quarry Lane", "Ferrow Avenue", "Tallow Creek Road", "Calder Mill Road", "Wexmoor Court",
    "Hobbet Mill Road", "Cradlemere Lane", "Calder County", "Bramble Cafe", "Elkmere Insurance", "Tessaly Properties",
    "Tallow Creek Mart", "Wexmoor Fuel",
]

# Places (invented addresses; coordinates around the builder's centre)
GARAGE = (39.261512, -76.689034)       # Ruiz Auto & Tire, 4410 Calder Mill Road
KELL_APT = (39.266840, -76.679512)     # Larkmont Apartments 3C, 18 Wexmoor Court (same sector as the garage)
WAREHOUSE = (39.220478, -76.660215)    # Brightwater Logistics Unit 7, Fenwick Ridge Industrial Park
STORAGE = (39.317206, -76.553018)      # Stowell Self Storage unit 212, 900 Tallow Creek Road
PENN_SHOP = (39.339011, -76.541027)    # Penn's Used Tools, 61 Tessaly Quarry Lane
MATEO_HOME = (39.276044, -76.701233)
TOW_N2 = (39.438012, -76.810544)       # Harold Vint's breakdown, 12 Apr, across the county
HOSPITAL = (39.288503, -76.623911)     # Ferrowmere Medical Center emergency department
BIGBOX = (39.310522, -76.744809)       # Quillan's Home Supply
MARSH_HOME = (39.229034, -76.620118)
OKAFOR_HOME = (39.295012, -76.640033)
BREAKDOWN_JUN8 = (39.240210, -76.645522)  # Kell's car, Ferrow Avenue
TOW_JUN10 = (39.252204, -76.712010)
TOW_JUN12 = (39.281533, -76.668420)

# Theft nights: (label, date of the evening). Each 23:00 to 03:30 Baltimore time.
NIGHTS = [("N1", dt.date(2024, 3, 15)), ("N2", dt.date(2024, 4, 12)), ("N3", dt.date(2024, 5, 3)),
          ("N4", dt.date(2024, 5, 17)), ("N5", dt.date(2024, 5, 31))]

# The loss lists (police reports) by night: (item, serial prefix, first serial, count)
LOSSES = {
    "N1": [("Torvane 20V hammer drill", "TVN20-", 118201, 12), ("Keldar 7in circular saw", "KLD-CS7-", 55021, 8)],
    "N2": [("Lumetra 55in television", "LMT55-", 70310, 6), ("Torvane 20V impact driver", "TVN20I-", 30440, 10)],
    "N3": [("Keldar 10in table saw", "KLD-TS10-", 8812, 4), ("Torvane 20V hammer drill", "TVN20-", 118301, 14)],
    "N4": [("Lumetra 65in television", "LMT65-", 41100, 5), ("Keldar 7in circular saw", "KLD-CS7-", 55101, 9)],
    "N5": [("Torvane 20V combo kit", "TVNK-", 6620, 8), ("Lumetra soundbar", "LMTSB-", 2290, 12)],
}


def serials(night: str) -> list[tuple[str, str]]:
    return [(item, f"{prefix}{start + i}") for item, prefix, start, n in LOSSES[night] for i in range(n)]


# Serial numbers the defence's records carry (Brianna's photos in unit 212; Penn's listings)
PHOTO_SERIALS = {"IMG_2041.JPG": ["TVN20-118204", "KLD-CS7-55027"], "IMG_2107.JPG": ["LMT55-70312", "TVN20I-30447"],
                 "IMG_2188.JPG": ["KLD-TS10-8813", "TVN20-118309"], "IMG_2240.JPG": ["TVNK-6624", "LMTSB-2297"]}
LISTED_SERIALS = ["TVN20-118207", "KLD-CS7-55024", "LMT55-70315", "TVN20I-30449", "KLD-TS10-8814", "TVN20-118312",
                  "LMT65-41103", "KLD-CS7-55105", "TVNK-6627", "LMTSB-2293"]
GARAGE_TOOLS = [("Torvane 20V hammer drill", "TVN20-099812"), ("Keldar 7in circular saw", "KLD-CS7-40920")]

# Kell's money after each night (Kestrel Point Bank): cash just under 10,000, then Pocketwire to Marsh and Okafor
DEPOSITS = {"N1": (dt.date(2024, 3, 18), 9800.00, "BR 014 FENWICK"), "N2": (dt.date(2024, 4, 15), 9650.00, "BR 022 TALLOW CREEK"),
            "N3": (dt.date(2024, 5, 6), 9900.00, "BR 031 WEXMOOR"), "N4": (dt.date(2024, 5, 20), 9750.00, "BR 009 MERROW"),
            "N5": (dt.date(2024, 6, 3), 9850.00, "BR 040 HESKETH")}
PENN_CHECKS = [(dt.date(2024, 3, 22), 1043, 3400.00), (dt.date(2024, 4, 19), 1051, 2950.00),
               (dt.date(2024, 5, 10), 1066, 4100.00), (dt.date(2024, 5, 24), 1072, 3600.00),
               (dt.date(2024, 6, 7), 1080, 3900.00)]
MISREAD_AMOUNT = "9800.00"  # N1's deposit on the March statement: printed as "9" and "800.00", two runs


def _night_gap(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    nxt = day + dt.timedelta(days=1)
    return L(day.year, day.month, day.day, 23, 0), L(nxt.year, nxt.month, nxt.day, 4, 0)


def _days(first: dt.date, last: dt.date):
    d = first
    while d <= last:
        yield d
        d += dt.timedelta(days=1)


# ---------------------------------------------------------------------------------------------------------------
# Media made with optional tools


def _photo(lines: list[str], seed: str, size=(480, 360)) -> tuple[bytes, bool]:
    """A small JPEG of stacked boxes with serial-number labels; a tiny PNG when Pillow is absent."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:  # pragma: no cover
        return fb._tiny_png(seed), False
    img = Image.new("RGB", size, (92, 84, 70))
    d = ImageDraw.Draw(img)
    font = _font(20)
    for i, text in enumerate(lines):
        x, y = 30 + (i % 2) * 220, 40 + (i // 2) * 150
        d.rectangle([x, y, x + 200, y + 130], fill=(176, 141, 96), outline=(60, 50, 40), width=3)
        d.rectangle([x + 14, y + 40, x + 186, y + 90], fill=(245, 245, 240))
        d.text((x + 22, y + 52), text, fill=(10, 10, 10), font=font)
    d.text((10, size[1] - 26), "synthetic test image", fill=(230, 230, 230), font=_font(14))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue(), True


def _font(size, italic=False):
    from PIL import ImageFont
    for path in (["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"] if italic else []) + [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


VOICE_NOTE_TEXT = ("Hey T, it's me. They are asking around the warehouse about the badges. "
                   "Do not call the other phone. I will come by tonight.")


def _voice_note() -> bytes | None:
    """Invented speech from ffmpeg's flite voice, as Opus in Ogg; None when ffmpeg or flite is absent."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    with tempfile.TemporaryDirectory(prefix="lx-demo-voice-") as d:
        out = Path(d) / "v.opus"
        src = Path(d) / "t.txt"
        src.write_text(VOICE_NOTE_TEXT)
        r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"flite=textfile={src}:voice=slt",
                            "-c:a", "libopus", "-b:a", "24k", "-map_metadata", "-1", "-fflags", "+bitexact",
                            "-flags:a", "+bitexact", str(out)], capture_output=True)
        return out.read_bytes() if r.returncode == 0 and out.exists() else None


# ---------------------------------------------------------------------------------------------------------------
# Phones


def _fixes(day: dt.date, place, times, acc=10, jitter=0.0) -> list[tuple]:
    out = []
    for k, (h, m) in enumerate(times):
        nxt = day + dt.timedelta(days=1) if h < 12 and times[0][0] >= 12 else day
        out.append((L(nxt.year, nxt.month, nxt.day, h, m), place[0] + jitter * ((k % 3) - 1), place[1] + jitter * ((k % 2) - 0.5), acc))
    return out


def _sms(day: dt.date, h, m, who, text, deleted="Intact", file=None):
    return (L(day.year, day.month, day.day, h, m), who, text, deleted, file)


def mateo_phone() -> fb.PhoneSpec:
    """PH1, Mateo's iPhone, seized 14 June."""
    tracks = []
    night_days = {d for _, d in NIGHTS}
    for day in _days(dt.date(2024, 1, 2), dt.date(2024, 6, 13)):
        if day.weekday() < 5:
            tracks += _fixes(day, GARAGE, [(9, 40), (15, 10)], acc=8, jitter=0.00003)
        if day not in night_days:
            tracks += _fixes(day, MATEO_HOME, [(21, 5)], acc=6, jitter=0.00002)
    for label, day in NIGHTS:
        nxt = day + dt.timedelta(days=1)
        if label == "N2":  # the Vint tow job across the county
            tracks += [(L(2024, 4, 12, 22, 40), *GARAGE, 8)]
            tracks += [(L(2024, 4, 12, 23, 0), 39.3610, -76.7520, 15)]
            tracks += [(L(2024, 4, 12, 23, mi), TOW_N2[0] + 0.00002 * k, TOW_N2[1], 9) for k, mi in enumerate((20, 40))]
            tracks += [(L(2024, 4, 13, 0, mi), TOW_N2[0], TOW_N2[1] + 0.00002 * k, 9) for k, mi in enumerate((0, 20, 40))]
            tracks += [(L(2024, 4, 13, 1, 15), *GARAGE, 8), (L(2024, 4, 13, 1, 50), *MATEO_HOME, 6)]
        elif label == "N3":  # emergency department with Lucía
            tracks += [(L(2024, 5, 3, 22, 40), *MATEO_HOME, 6)]
            tracks += [(L(2024, 5, 3, 23, 10), *HOSPITAL, 12), (L(2024, 5, 3, 23, 40), *HOSPITAL, 12)]
            tracks += [(L(2024, 5, 4, h, m), HOSPITAL[0] + 0.00003 * (h % 2), HOSPITAL[1], 12)
                       for h in (0, 1, 2, 3) for m in (10, 40) if (h, m) != (3, 40)]
            tracks += [(L(2024, 5, 4, 3, 40), *HOSPITAL, 12), (L(2024, 5, 4, 4, 5), *MATEO_HOME, 6)]
        else:
            tracks += [(L(day.year, day.month, day.day, 22, 30), *MATEO_HOME, 6),
                       (L(day.year, day.month, day.day, 23, 30), *MATEO_HOME, 6)]
            tracks += [(L(nxt.year, nxt.month, nxt.day, h, m), *MATEO_HOME, 6) for h, m in ((0, 45), (2, 10), (3, 20))]
    tracks += [(L(2024, 5, 18, 11, m), BIGBOX[0], BIGBOX[1] + 0.00004 * k, 15) for k, m in enumerate((20, 32, 44))]
    tracks += [(L(2024, 6, 8, 14, 10), *BREAKDOWN_JUN8, 9), (L(2024, 6, 8, 14, 25), *BREAKDOWN_JUN8, 9),
               (L(2024, 6, 8, 14, 50), *GARAGE, 8)]
    lucia = [
        _sms(dt.date(2024, 3, 15), 18, 2, "lucia", "¿Vienes a cenar? hice pozole"),
        _sms(dt.date(2024, 3, 15), 18, 5, "owner", "sí, closing up now, 20 min"),
        _sms(dt.date(2024, 4, 12), 22, 33, "owner", "tow call, guy broke down out past the county line. back late, no me esperes"),
        _sms(dt.date(2024, 4, 12), 22, 36, "lucia", "ok be careful. text me when you're back"),
        _sms(dt.date(2024, 4, 13), 1, 52, "owner", "back home"),
        _sms(dt.date(2024, 5, 3), 22, 41, "lucia", "the pain is worse, I think we need to go"),
        _sms(dt.date(2024, 5, 3), 22, 42, "owner", "getting the car, vamos a Ferrowmere"),
        _sms(dt.date(2024, 5, 17), 20, 15, "lucia", "movie tonight? the kids are asleep"),
        _sms(dt.date(2024, 5, 17), 20, 16, "owner", "sí, I'll make popcorn"),
        _sms(dt.date(2024, 5, 31), 21, 30, "owner", "dejé las llaves del camión en la oficina, I'll get them mañana"),
        _sms(dt.date(2024, 6, 8), 13, 58, "owner", "tow job, Travis from bay 4, his car died on Ferrow Ave"),
    ]
    rosa = [
        _sms(dt.date(2024, 5, 3), 23, 25, "owner", "Mamá, estamos en urgencias con Lucía. Está bien, solo dolor. Te llamo mañana", file="er1"),
        _sms(dt.date(2024, 5, 3), 23, 31, "rosa", "Ay mijo, avísame. Rezo por ella"),
        _sms(dt.date(2024, 5, 4), 3, 44, "owner", "ya nos vamos a casa, le dieron medicina. todo bien"),
    ]
    kell = []
    for month in range(1, 7):
        kell += [_sms(dt.date(2024, month, 1), 8, 40, "kell", "sent the bay rent"),
                 _sms(dt.date(2024, month, 1), 9, 2, "owner", "got it, thanks Travis")]
    kell += [_sms(dt.date(2024, 6, 8), 13, 50, "kell", "car died on Ferrow Ave by the light. can you tow it to the shop?"),
             _sms(dt.date(2024, 6, 8), 13, 55, "owner", "on my way, 20 min"),
             _sms(dt.date(2024, 6, 8), 15, 5, "owner", "it's in the lot. probably the alternator, I'll look Monday"),
             _sms(dt.date(2024, 6, 9), 17, 20, "kell", "did you find a phone in the truck? think I left it in the cab"),
             _sms(dt.date(2024, 6, 9), 18, 45, "owner", "didn't see anything, I'll check tomorrow")]
    vint = [_sms(dt.date(2024, 4, 12), 22, 34, "vint", "I'm on Hobbet Mill past the reservoir sign, silver sedan, hazards on"),
            _sms(dt.date(2024, 4, 12), 22, 35, "owner", "ok, 40 minutes")]
    er_photo, made = _photo(["Ferrowmere ED", "waiting room"], "er1")
    script = fb.Script(
        chats=[fb.ScriptChat("WhatsApp", ["lucia"], lucia), fb.ScriptChat("WhatsApp", ["rosa"], rosa),
               fb.ScriptChat("Native Messages", ["kell"], kell), fb.ScriptChat("Native Messages", ["vint"], vint)],
        calls=[(L(2024, 4, 12, 22, 31), "vint", "Incoming", "Established", 140),
               (L(2024, 5, 4, 9, 10), "rosa", "Outgoing", "Established", 610),
               (L(2024, 6, 8, 13, 52), "kell", "Incoming", "Established", 75)],
        tracks=tracks,
        contacts=[("Lucía ❤️", ["+14435550113"], {}), ("Mamá", ["+14105550114"], {}),
                  ("Travis Kell (bay 4)", ["+14105550121"], {}), ("Harold Vint", ["+14105550191"], {}),
                  ("Gary Penn tools", ["+14105550171"], {}), ("Shop", ["+14105550110"], {})],
        saved_names={"lucia": "Lucía ❤️", "rosa": "Mamá", "kell": "Travis Kell (bay 4)"},
        files=[fb.ScriptFile("er1", "IMG_4410.JPG", "/private/var/mobile/Media/DCIM/104APPLE/IMG_4410.JPG", er_photo,
                             L(2024, 5, 3, 23, 24), meta=(("EXIFCameraMaker", "Synthetic"), ("EXIFCameraModel", "iPhone (Phone PH1)"),
                                                          ("ExifEnumGPSLatitude", f"{HOSPITAL[0]:.6f}"),
                                                          ("ExifEnumGPSLongitude", f"{HOSPITAL[1]:.6f}")),
                             position=HOSPITAL)])
    return fb.PhoneSpec("PH1", like="P14", scale=0.003, owner="mateo", extraction_date=dt.date(2024, 6, 18),
                        period_days=180, gap=None, contacts=["lucia", "rosa", "vint"], seed=601, random_locations=False,
                        script=script, device_name="iPhone (Phone PH1)", os_type="iOS")


NIGHT_CREW = []  # the Telegram group "night crew", on Kell's and Okafor's phones alike
for _label, _d in NIGHTS:
    NIGHT_CREW += [_sms(_d, 16, 10, "kell", "tonight. 11. same as before"),
                   _sms(_d, 16, 14, "dee", "ok. dock 3 again?"),
                   _sms(_d, 16, 15, "kell", "dock 3")]
NIGHT_CREW += [_sms(dt.date(2024, 4, 20), 18, 30, "kell", "they let me go today. doesn't change anything, my badge still works"),
               _sms(dt.date(2024, 4, 20), 18, 41, "dee", "for real? ok")]


def kell_phone() -> fb.PhoneSpec:
    """PH2, Travis Kell's Android, seized 10 June. Powered off 23:00 to 04:00 on each theft night; the extraction
    records the zone as America/Chicago though he never left Maryland."""
    tracks = []
    nights = {d for _, d in NIGHTS}
    for day in _days(dt.date(2024, 1, 2), dt.date(2024, 6, 9)):
        tracks += _fixes(day, KELL_APT, [(7, 30)], acc=7, jitter=0.00002)
        tracks += [(L(day.year, day.month, day.day, 22, 30), KELL_APT[0], KELL_APT[1] + 0.00002, 7)]
        if day.weekday() < 5 and day <= dt.date(2024, 4, 19):
            tracks += _fixes(day, WAREHOUSE, [(15, 0)], acc=9)
        if dt.date(2024, 5, 23) <= day <= dt.date(2024, 6, 7):
            tracks += [(L(day.year, day.month, day.day, h, 30), KELL_APT[0] + 0.00001, KELL_APT[1], 6) for h in (20, 21)]
    for _, day in NIGHTS:
        nxt = day + dt.timedelta(days=1)
        tracks += [(L(day.year, day.month, day.day, 22, 40), *KELL_APT, 7),
                   (L(nxt.year, nxt.month, nxt.day, 10, 30), *STORAGE, 10),
                   (L(nxt.year, nxt.month, nxt.day, 11, 40), *PENN_SHOP, 10)]
    tracks += [(L(2024, 2, 2, 11, 15), *STORAGE, 10), (L(2024, 6, 8, 13, 45), *BREAKDOWN_JUN8, 8)]
    notes = []
    for row in KELL_ALERT_ROWS():
        when = row["date"]
        amt = abs(row["amount"])
        if row["desc"].startswith("CASH DEPOSIT"):
            body = f"Kestrel Point Bank: a deposit of ${amt:,.2f} posted to checking ending 4471."
        elif row["desc"].startswith("POCKETWIRE TO"):
            body = f"Pocketwire: you sent ${amt:,.2f} to {row['desc'].split(' TO ', 1)[1].title()}."
        elif row["desc"].startswith("MOBILE DEP"):
            body = f"Kestrel Point Bank: your mobile check deposit of ${amt:,.2f} was accepted."
        else:
            body = f"Kestrel Point Bank: ${amt:,.2f} {'debit' if row['amount'] < 0 else 'credit'} on checking ending 4471: {row['desc'].title()}."
        notes.append((L(when.year, when.month, when.day, 9, 15), "test.kestrelpoint.bank" if "Kestrel" in body else
                      "test.pocketwire.app", "Kestrel Point Bank" if "Kestrel" in body else "Pocketwire", body))
    dee_dm = [_sms(dt.date(2024, 5, 18), 12, 5, "dee", "you good? saw you at Quillan's lol"),
              _sms(dt.date(2024, 6, 9), 19, 42, "owner", "left something in the tow truck, need it back", "Deleted"),
              _sms(dt.date(2024, 6, 9), 19, 50, "dee", "what did you leave?"),
              _sms(dt.date(2024, 6, 9), 19, 51, "owner", "the other one. don't text it")]
    bri = [_sms(dt.date(2024, 2, 1), 19, 0, "owner", "can you rent a unit at Stowell tomorrow, in your name. I'll pay with my card"),
           _sms(dt.date(2024, 2, 1), 19, 6, "brianna", "why my name?"),
           _sms(dt.date(2024, 2, 1), 19, 7, "owner", "just do it babe, it's for the side work")]
    rent = []
    for month in range(1, 7):
        rent += [_sms(dt.date(2024, month, 1), 8, 40, "owner", "sent the bay rent"),
                 _sms(dt.date(2024, month, 1), 9, 2, "mateo", "got it, thanks Travis")]
    rent += [_sms(dt.date(2024, 6, 8), 13, 50, "owner", "car died on Ferrow Ave by the light. can you tow it to the shop?"),
             _sms(dt.date(2024, 6, 8), 13, 55, "mateo", "on my way, 20 min"),
             _sms(dt.date(2024, 6, 8), 15, 5, "mateo", "it's in the lot. probably the alternator, I'll look Monday"),
             _sms(dt.date(2024, 6, 9), 17, 20, "owner", "did you find a phone in the truck? think I left it in the cab"),
             _sms(dt.date(2024, 6, 9), 18, 45, "mateo", "didn't see anything, I'll check tomorrow")]
    crew = [(t, "owner" if w == "kell" else w, x, dl, f) for t, w, x, dl, f in NIGHT_CREW]
    script = fb.Script(
        chats=[fb.ScriptChat("Telegram", ["dee"], crew, name="night crew"), fb.ScriptChat("Telegram", ["dee"], dee_dm),
               fb.ScriptChat("WhatsApp", ["brianna"], bri), fb.ScriptChat("Native Messages", ["mateo"], rent)],
        calls=[(L(2024, 6, 8, 13, 52), "mateo", "Outgoing", "Established", 75)],
        tracks=tracks, notifications=notes,
        emails=[(L(2024, 5, 4, 14, 20), "owner", ["gary"], "price list",
                 "Gary, for Saturday. Torvane 20V hammer drill x14, $85 each. Keldar 10in table saw x4, $240 each. "
                 "Same as last time, check to me. T.", "Sent")],
        contacts=[("Dee", ["+14105550141"], {"Telegram": "@dee_o28"}), ("Bri", ["+14435550151"], {}),
                  ("Mateo garage", ["+14105550110", "+14435550112"], {}), ("Gary P", ["+14105550171"], {})],
        saved_names={"dee": "Dee", "brianna": "Bri", "mateo": "Mateo garage", "gary": "Gary P"})
    return fb.PhoneSpec("PH2", like="P08", scale=0.002, owner="kell", zone="America/Chicago",
                        extraction_date=dt.date(2024, 6, 15), period_days=170, gap=None,
                        gaps=tuple(_night_gap(d) for _, d in NIGHTS), contacts=["brianna", "dee", "gary"], seed=602,
                        random_locations=False, script=script, extraction_type="Logical")


def _burner_lines(partner: str) -> list[tuple]:
    out = []
    for label, d in NIGHTS:
        nxt = d + dt.timedelta(days=1)
        if partner == "dee2":
            out += [_sms(d, 22, 5, "owner", "bay 4 is clear"), _sms(d, 22, 7, "dee2", "ok"),
                    (L(nxt.year, nxt.month, nxt.day, 1, 40), "owner", "unit's open", "Intact", None),
                    (L(nxt.year, nxt.month, nxt.day, 1, 43), "dee2", "on the way", "Intact", None)]
        elif partner == "lena":
            out += [_sms(d, 22, 10, "owner", "be on the gate at 11. same as before"), _sms(d, 22, 12, "lena", "ok")]
        else:
            out += [(L(nxt.year, nxt.month, nxt.day, 9, 30), "owner", "got more for you, saturday", "Intact", None),
                    (L(nxt.year, nxt.month, nxt.day, 9, 41), "gary", "same price. come to the back", "Intact", None)]
    return out


def burner_phone() -> fb.PhoneSpec:
    """PH3, the phone found in the tow truck's glovebox. The State lists it as Mateo's. Three contacts only."""
    tracks = []
    for _, d in NIGHTS:
        nxt = d + dt.timedelta(days=1)
        tracks += [(L(d.year, d.month, d.day, 22, 15), *KELL_APT, 25), (L(nxt.year, nxt.month, nxt.day, 0, 40), *WAREHOUSE, 30),
                   (L(nxt.year, nxt.month, nxt.day, 2, 30), *STORAGE, 30)]
    for day in _days(dt.date(2024, 5, 23), dt.date(2024, 6, 7)):
        if day in (dt.date(2024, 5, 27), dt.date(2024, 6, 2)):
            continue  # 14 of the 16 days
        tracks += [(L(day.year, day.month, day.day, h, 35), KELL_APT[0] + 0.00004, KELL_APT[1] - 0.00003, 20)
                   for h in (20, 21, 22)]
    tracks += [(L(2024, 6, 8, 14, 12), *BREAKDOWN_JUN8, 20), (L(2024, 6, 8, 14, 55), *GARAGE, 20),
               (L(2024, 6, 10, 10, 20), *TOW_JUN10, 25), (L(2024, 6, 10, 11, 30), *GARAGE, 20),
               (L(2024, 6, 12, 15, 5), *TOW_JUN12, 25), (L(2024, 6, 12, 16, 10), *GARAGE, 20),
               (L(2024, 6, 14, 7, 10), *GARAGE, 20)]
    script = fb.Script(
        chats=[fb.ScriptChat("Native Messages", ["dee2"], _burner_lines("dee2")),
               fb.ScriptChat("Native Messages", ["lena"], _burner_lines("lena")),
               fb.ScriptChat("Native Messages", ["gary"], _burner_lines("gary"))],
        tracks=tracks,
        contacts=[("D.O.", ["+14435550142"], {}), ("L", ["+14105550161"], {}), ("G", ["+14105550171"], {})],
        saved_names={"dee2": "D.O.", "lena": "L", "gary": "G"})
    return fb.PhoneSpec("PH3", like="P10", scale=0.001, owner="burner", extraction_date=dt.date(2024, 6, 17),
                        period_days=110, gap=None, contacts=["dee2", "lena", "gary"], seed=603, random_locations=False,
                        script=script, device_name="Phone PH3 (prepaid)")


def okafor_phone(voice: bytes | None) -> fb.PhoneSpec:
    """PH4, Desmond Okafor's phone, consent extraction. Two numbers, Telegram; the glovebox number is still saved
    under its 2022 owner's name; "Mateo \U0001F527" is a different man (Mateo Garza)."""
    tracks = []
    for _, d in NIGHTS:
        nxt = d + dt.timedelta(days=1)
        tracks += [(L(d.year, d.month, d.day, 23, 30), *WAREHOUSE, 20), (L(nxt.year, nxt.month, nxt.day, 1, 30), *WAREHOUSE, 20),
                   (L(nxt.year, nxt.month, nxt.day, 2, 45), *STORAGE, 25)]
    tracks += [(L(2024, 5, 18, 11, 35), *BIGBOX, 25), (L(2024, 5, 18, 11, 50), BIGBOX[0] + 0.00005, BIGBOX[1], 25)]
    tracks += [(L(2024, m, 10, 21, 0), *OKAFOR_HOME, 15) for m in range(1, 7)]
    burner = [(t, "burner" if w == "owner" else "owner", x, dl, f) for t, w, x, dl, f in _burner_lines("dee2")]
    crew = list(NIGHT_CREW)
    crew = [(t, "owner" if w == "dee" else w, x, dl, f) for t, w, x, dl, f in crew]
    kell_dm = [_sms(dt.date(2024, 5, 18), 12, 5, "owner", "you good? saw you at Quillan's lol"),
               _sms(dt.date(2024, 6, 9), 19, 42, "kell", "left something in the tow truck, need it back"),
               _sms(dt.date(2024, 6, 9), 19, 50, "owner", "what did you leave?"),
               _sms(dt.date(2024, 6, 9), 19, 51, "kell", "the other one. don't text it")]
    files = []
    if voice:
        kell_dm.append(_sms(dt.date(2024, 6, 9), 20, 3, "owner", "", file="vn1"))
        files.append(fb.ScriptFile("vn1", "PTT-20240609-0001.opus", "/Telegram/Telegram Audio/PTT-20240609-0001.opus",
                                   voice, L(2024, 6, 9, 20, 3), kind="Audio", content_type="audio/ogg"))
    garza = [_sms(dt.date(2024, 5, 23), 18, 0, "owner", "can you look at my brakes saturday? grinding again"),
             _sms(dt.date(2024, 5, 23), 18, 20, "garza", "bring it by 9. it's me and the lift all morning, Mateo"),
             _sms(dt.date(2024, 5, 25), 12, 10, "garza", "pads and rotors done. $180, pay me whenever")]
    script = fb.Script(
        chats=[fb.ScriptChat("Telegram", ["kell"], crew, name="night crew"), fb.ScriptChat("Telegram", ["kell"], kell_dm),
               fb.ScriptChat("Native Messages", ["burner"], burner, owner_ident="+14435550142"),
               fb.ScriptChat("Native Messages", ["garza"], garza)],
        calls=[(dt.datetime(2022, 3, 4, 22, 10), "curtis", "Outgoing", "Established", 210),
               (dt.datetime(2022, 7, 19, 17, 2), "curtis", "Incoming", "Established", 95),
               (dt.datetime(2022, 11, 2, 23, 40), "curtis", "Incoming", "Missed", 0),
               (L(2024, 5, 23, 17, 55), "garza", "Outgoing", "Established", 48)],
        tracks=tracks, files=files,
        contacts=[("T", ["+14105550121"], {"Telegram": "@tk_nights"}), ("Curtis Fallowby", ["+14435550131"], {}),
                  ("Mateo \U0001F527", ["+14435550181"], {}), ("Lena M", ["+14105550161"], {})],
        saved_names={"kell": "T", "burner": "Curtis Fallowby", "curtis": "Curtis Fallowby", "garza": "Mateo \U0001F527",
                     "lena": "Lena M"})
    return fb.PhoneSpec("PH4", like="P09", scale=0.02, owner="dee", extraction_date=dt.date(2024, 6, 21),
                        period_days=200, gap=None, contacts=["kell", "lena", "garza"], seed=604, random_locations=False,
                        script=script)


def brianna_phone() -> tuple[fb.PhoneSpec, bool]:
    """PH5, Brianna Cole's phone, consent extraction: her own photos inside unit 212 (camera folder, this phone's
    EXIF, GPS at the storage site) and photos received from Kell (his phone's EXIF, GPS at the warehouse)."""
    files, made_all = [], True
    own = [("IMG_2041.JPG", L(2024, 3, 16, 10, 48)), ("IMG_2107.JPG", L(2024, 4, 13, 10, 51)),
           ("IMG_2188.JPG", L(2024, 5, 4, 10, 52)), ("IMG_2240.JPG", L(2024, 6, 1, 11, 5))]
    for name, t in own:
        data, made = _photo(PHOTO_SERIALS[name], name)
        made_all &= made
        files.append(fb.ScriptFile(name, name, f"/storage/emulated/0/DCIM/Camera/{name}", data, t,
                                   meta=(("EXIFCameraMaker", "Synthetic"), ("EXIFCameraModel", "Phone PH5"),
                                         ("ExifEnumGPSLatitude", f"{STORAGE[0]:.6f}"), ("ExifEnumGPSLongitude", f"{STORAGE[1]:.6f}")),
                                   position=STORAGE))
    received = [("IMG-20240316-WA0003.jpg", L(2024, 3, 16, 2, 5)), ("IMG-20240504-WA0001.jpg", L(2024, 5, 4, 1, 58))]
    for name, t in received:
        data, made = _photo(["dock 3", "loaded"], name)
        made_all &= made
        files.append(fb.ScriptFile(name, name, f"/storage/emulated/0/WhatsApp/Media/WhatsApp Images/{name}", data, t,
                                   meta=(("EXIFCameraMaker", "Synthetic"), ("EXIFCameraModel", "Phone PH2"),
                                         ("ExifEnumGPSLatitude", f"{WAREHOUSE[0]:.6f}"),
                                         ("ExifEnumGPSLongitude", f"{WAREHOUSE[1]:.6f}")),
                                   position=WAREHOUSE))
    kell = [_sms(dt.date(2024, 2, 2), 11, 30, "owner", "signed for the unit, 212. it's in my name like you said"),
            _sms(dt.date(2024, 2, 2), 11, 34, "kell", "thanks babe. I paid it on my card"),
            (L(2024, 3, 16, 2, 5), "kell", "loaded", "Intact", "IMG-20240316-WA0003.jpg"),
            _sms(dt.date(2024, 3, 16), 10, 50, "owner", "they're all in 212, took pics", file="IMG_2041.JPG"),
            _sms(dt.date(2024, 4, 13), 10, 53, "owner", "212 again. it's getting full", file="IMG_2107.JPG"),
            (L(2024, 5, 4, 1, 58), "kell", "count these for me tomorrow", "Intact", "IMG-20240504-WA0001.jpg"),
            _sms(dt.date(2024, 5, 4), 10, 55, "owner", "counted. 18 boxes", file="IMG_2188.JPG"),
            _sms(dt.date(2024, 6, 1), 11, 6, "owner", "last ones fit. Gary said he'd take them next week", file="IMG_2240.JPG"),
            _sms(dt.date(2024, 6, 11), 9, 15, "owner", "they arrested you?? what do I do about the unit")]
    script = fb.Script(chats=[fb.ScriptChat("WhatsApp", ["kell"], kell)], files=files,
                       tracks=[(L(2024, 2, 2, 11, 20), *STORAGE, 12)] + [(f.time, *STORAGE, 12) for f in files[:4]],
                       contacts=[("Travis \U0001F499", ["+14105550121"], {}), ("Desmond Okafor", ["+14105550141"], {})],
                       saved_names={"kell": "Travis \U0001F499", "dee": "Desmond Okafor"})
    spec = fb.PhoneSpec("PH5", like="P12", scale=0.03, owner="brianna", extraction_date=dt.date(2024, 6, 24),
                        period_days=180, gap=None, contacts=["kell", "dee"], seed=605, random_locations=False, script=script)
    return spec, made_all


def marsh_phone() -> fb.PhoneSpec:
    """PH6, Lena Marsh's phone, consent extraction: the payments she received, and her texts before her interview."""
    notes = []
    for label, d in NIGHTS:
        when = d + dt.timedelta(days=1)
        notes.append((L(when.year, when.month, when.day, 9, 15), "test.pocketwire.app", "Pocketwire",
                      "You received $500.00 from Travis K."))
    joan = [_sms(dt.date(2024, 6, 11), 19, 10, "owner", "they want me to come in tomorrow about the warehouse"),
            _sms(dt.date(2024, 6, 11), 19, 14, "joan", "just tell them what you saw"),
            _sms(dt.date(2024, 6, 11), 19, 20, "owner", "I'll say I saw a tow truck. white one, with the name on it. that's all I'm saying"),
            _sms(dt.date(2024, 6, 11), 19, 22, "joan", "Lena did you see one or not"),
            _sms(dt.date(2024, 6, 11), 19, 40, "owner", "I saw what I saw")]
    burner = [(t, "burner" if w == "owner" else "owner", x, dl, f) for t, w, x, dl, f in _burner_lines("lena")]
    tracks = []
    for _, d in NIGHTS:
        nxt = d + dt.timedelta(days=1)
        tracks += [(L(d.year, d.month, d.day, 22, 50), *WAREHOUSE, 15), (L(nxt.year, nxt.month, nxt.day, 3, 10), *WAREHOUSE, 15)]
    tracks += [(L(2024, m, 5, 20, 0), *MARSH_HOME, 10) for m in range(1, 7)]
    script = fb.Script(chats=[fb.ScriptChat("Native Messages", ["joan"], joan),
                              fb.ScriptChat("Native Messages", ["burner"], burner)],
                       notifications=notes, tracks=tracks,
                       contacts=[("Joanie", ["+14105550162"], {}), ("T 2", ["+14435550131"], {})],
                       saved_names={"joan": "Joanie", "burner": "T 2"})
    return fb.PhoneSpec("PH6", like="P05", scale=0.006, owner="lena", extraction_date=dt.date(2024, 6, 25),
                        period_days=180, gap=None, contacts=["joan"], seed=606, random_locations=False, script=script)


# ---------------------------------------------------------------------------------------------------------------
# Ledgers


def _month_rows(rows, y, m):
    return [r for r in rows if r["date"].year == y and r["date"].month == m]


def kell_rows() -> list[dict]:
    rows = []
    for m in range(1, 7):
        rows.append({"date": dt.date(2024, m, 1), "desc": "LARKMONT APTS RENT 3C", "amount": -1350.00})
        rows.append({"date": dt.date(2024, m, 1), "desc": "ACH RUIZ AUTO & TIRE BAY 4 RENT", "amount": -650.00})
        if m >= 3:
            rows.append({"date": dt.date(2024, m, 2), "desc": "STOWELL SELF STORAGE U212", "amount": -139.00})
        for d in (6, 13, 20, 27):
            try:
                day = dt.date(2024, m, d)
            except ValueError:  # pragma: no cover
                continue
            rows.append({"date": day, "desc": "GREENHOLLOW GROCERS", "amount": -round(64.10 + d * 1.37 + m * 2.05, 2)})
        rows.append({"date": dt.date(2024, m, 11), "desc": "WEXMOOR FUEL 2291", "amount": -round(48.20 + m * 3.1, 2)})
    rows.append({"date": dt.date(2024, 2, 2), "desc": "STOWELL SELF STORAGE U212", "amount": -139.00})
    pay = dt.date(2024, 1, 5)
    while pay <= dt.date(2024, 4, 19):
        rows.append({"date": pay, "desc": "BRIGHTWATER LOGISTICS PAYROLL", "amount": 1840.00})
        pay += dt.timedelta(days=14)
    rows.append({"date": dt.date(2024, 4, 26), "desc": "BRIGHTWATER LOGISTICS FINAL PAY", "amount": 1210.55})
    for label, d in NIGHTS:
        dep, amount, branch = DEPOSITS[label]
        rows.append({"date": dep, "desc": f"CASH DEPOSIT {branch}", "amount": amount})
        rows.append({"date": d + dt.timedelta(days=1), "desc": "POCKETWIRE TO LENA MARSH", "amount": -500.00})
        rows.append({"date": d + dt.timedelta(days=2), "desc": "POCKETWIRE TO DESMOND OKAFOR", "amount": -1200.00})
    for day, num, amount in PENN_CHECKS:
        rows.append({"date": day, "desc": f"MOBILE DEP CHK {num} PENN'S USED TOOLS", "amount": amount})
    rows.append({"date": dt.date(2024, 5, 14), "desc": "CORBEL AUTO PARTS", "amount": -86.75})
    rows.append({"date": dt.date(2024, 5, 21), "desc": "CORBEL AUTO PARTS", "amount": -42.10})
    rows.append({"date": dt.date(2024, 5, 28), "desc": "ATM WITHDRAWAL BR 022", "amount": -300.00})
    rows.append({"date": dt.date(2024, 5, 29), "desc": "WEXMOOR FUEL 2291", "amount": -51.30})
    for k, day in enumerate((3, 7, 8, 9, 12, 15, 16, 22, 23, 25, 30)):  # May's card spending fills a second page
        rows.append({"date": dt.date(2024, 5, day), "desc": "BRAMBLE CAFE 18" if k % 2 else "TALLOW CREEK MART",
                     "amount": -round(11.40 + 3.15 * k, 2)})
    return sorted(rows, key=lambda r: (r["date"], -r["amount"]))


def KELL_ALERT_ROWS() -> list[dict]:
    """The rows Kell's phone carries a bank or Pocketwire alert for: deposits, payments to Marsh and Okafor, Penn's checks."""
    return [r for r in kell_rows() if r["desc"].startswith(("CASH DEPOSIT", "POCKETWIRE TO", "MOBILE DEP"))]


def shop_rows() -> list[dict]:
    rows = []
    months = [(2023, 10), (2023, 11), (2023, 12)] + [(2024, m) for m in range(1, 7)]
    for y, m in months:
        rows.append({"date": dt.date(y, m, 1), "desc": "KELL T BAY 4 RENT", "amount": 650.00})
        rows.append({"date": dt.date(y, m, 3), "desc": "CORBEL AUTO PARTS", "amount": -round(1210.40 + m * 37.15, 2)})
        for d in (5, 12, 19, 26):
            rows.append({"date": dt.date(y, m, d), "desc": "CARD SETTLEMENT BATCH", "amount": round(2380.00 + d * 21.5 + m * 9.25, 2)})
        rows.append({"date": dt.date(y, m, 15), "desc": "OWNER DRAW TO M RUIZ", "amount": -2500.00})
        rows.append({"date": dt.date(y, m, 28), "desc": "OWNER DRAW TO M RUIZ", "amount": -2500.00})
        rows.append({"date": dt.date(y, m, 20), "desc": "ELKMERE INSURANCE TOW TRUCK", "amount": -312.00})
    rows.append({"date": dt.date(2024, 4, 15), "desc": "VINT H TOW INV 1187", "amount": 185.00})
    return sorted(rows, key=lambda r: (r["date"], -r["amount"]))


def mateo_rows() -> list[dict]:
    rows = []
    for m in range(1, 7):
        rows.append({"date": dt.date(2024, m, 15), "desc": "OWNER DRAW RUIZ AUTO & TIRE", "amount": 2500.00})
        rows.append({"date": dt.date(2024, m, 28), "desc": "OWNER DRAW RUIZ AUTO & TIRE", "amount": 2500.00})
        rows.append({"date": dt.date(2024, m, 2), "desc": "ELKMERE HOME LENDING MORTGAGE", "amount": -1980.00})
        for d in (4, 11, 18, 25):
            rows.append({"date": dt.date(2024, m, d), "desc": "GREENHOLLOW GROCERS", "amount": -round(141.30 + d * 2.11 + m, 2)})
    rows.append({"date": dt.date(2024, 5, 6), "desc": "FERROWMERE MEDICAL CENTER ED COPAY", "amount": -150.00})
    rows.append({"date": dt.date(2024, 5, 18), "desc": "QUILLAN'S HOME SUPPLY 0212", "amount": -86.40})
    rows.append({"date": dt.date(2024, 5, 22), "desc": "PENN'S USED TOOLS", "amount": -240.00})
    return sorted(rows, key=lambda r: (r["date"], -r["amount"]))


def penn_rows() -> list[dict]:
    rows = []
    for label, d in NIGHTS:
        for k, off in enumerate((4, 8, 12)):
            rows.append({"date": d + dt.timedelta(days=off), "desc": "BENCHYARD MARKETPLACE PAYOUT", "amount": round(1840.00 + 310.0 * k + d.day * 7, 2)})
    for day, num, amount in PENN_CHECKS:
        rows.append({"date": day, "desc": f"CHECK {num} TRAVIS KELL", "amount": -amount})
    rows.append({"date": dt.date(2024, 5, 8), "desc": "CARD SALE C RUIZ", "amount": 95.00})
    rows.append({"date": dt.date(2024, 5, 22), "desc": "CARD SALE M RUIZ", "amount": 240.00})
    rows.append({"date": dt.date(2024, 4, 1), "desc": "TESSALY PROPERTIES RENT", "amount": -2100.00})
    return sorted(rows, key=lambda r: (r["date"], -r["amount"]))


ACCOUNTS = {
    "kell": dict(holder="TRAVIS KELL", account="7730-554471", bank="Kestrel Point Bank", opening=2210.35, rows=kell_rows,
                 months=[(2024, m) for m in range(1, 7)]),
    "shop": dict(holder="RUIZ AUTO & TIRE LLC", account="0042-118847", bank="Larkfield Tradesmen Credit Union",
                 opening=18420.10, rows=shop_rows, months=[(2023, 10), (2023, 11), (2023, 12)] + [(2024, m) for m in range(1, 7)]),
    "mateo": dict(holder="MATEO RUIZ", account="0042-118830", bank="Larkfield Tradesmen Credit Union", opening=6310.80,
                  rows=mateo_rows, months=[(2024, m) for m in range(1, 7)]),
}


def write_ledgers(out: Path) -> dict:
    info = {}
    for key, acc in ACCOUNTS.items():
        rows, balance, files = acc["rows"](), acc["opening"], []
        for y, m in acc["months"]:
            month = _month_rows(rows, y, m)
            printed = []
            opening = balance
            for r in month:
                balance = round(balance + r["amount"], 2)
                printed.append({"Date": r["date"].strftime("%m/%d/%Y"), "Description": r["desc"], "Amount": f"{r['amount']:.2f}",
                                "Balance": f"{balance:.2f}"})
            first = dt.date(y, m, 1)
            last = dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)
            name = f"{key}-{y}-{m:02d}.pdf"
            opts = dict(opening=opening, start=first, end=last, holder=acc["holder"], account=acc["account"],
                        bank=acc["bank"], page_mark=BANNER, paginate=True, title_case=False)
            if key == "kell" and (y, m) == (2024, 3):
                opts["split_amounts"] = (MISREAD_AMOUNT,)
            if key == "kell" and (y, m) == (2024, 5):
                opts["omit_pages"] = (2,)  # the production left page 2 out
            path = out / "statements" / key / name
            path.parent.mkdir(parents=True, exist_ok=True)
            _statement(printed, path, opts)
            files.append(str(path.relative_to(out)))
            if key == "kell" and (y, m) == (2024, 4):  # the same statement again, in the State's exhibit bundle
                dup = out / "statements" / "state-exhibits" / "states-exhibit-14-kell-april-2024.pdf"
                dup.parent.mkdir(parents=True, exist_ok=True)
                _statement(printed, dup, dict(opts, page_mark=BANNER + "   STATE'S EXHIBIT 14"))
                files.append(str(dup.relative_to(out)))
        info[key] = {"files": files, "rows": len(rows), "closing": balance}
    # Penn's Used Tools: the bank gives CSV
    path = out / "statements" / "penn" / "penn-used-tools-old-ferrow-2024.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    balance = 7420.00
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([BANNER])
        w.writerow(["Old Ferrow Savings Bank", "PENN'S USED TOOLS LLC", "Account 5518-020931"])
        w.writerow(["Date", "Description", "Amount", "Balance"])
        for r in penn_rows():
            balance = round(balance + r["amount"], 2)
            w.writerow([r["date"].strftime("%m/%d/%Y"), r["desc"], f"{r['amount']:.2f}", f"{balance:.2f}"])
    info["penn"] = {"files": [str(path.relative_to(out))], "rows": len(penn_rows()), "closing": balance}
    return info


def _statement(printed, path, opts):
    fb.write_statement_pdf(printed, path, **opts)


# ---------------------------------------------------------------------------------------------------------------
# Documents: text PDFs (the builder's PDF object writer), one scanned PDF, a DOCX, an e-mail and CSVs


def _wrap(text: str, width: int = 92) -> list[str]:
    out = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            if len(line) + len(word) + 1 > width:
                out.append(line)
                line = word
            else:
                line = f"{line} {word}" if line else word
        out.append(line)
    return out


def write_text_pdf(path: Path, title: str, body: str) -> None:
    """A text-layer PDF, every page headed with the banner. Helvetica, WinAnsi (cp1252), no dates: deterministic."""
    lines = _wrap(body)
    per_page = 52
    chunks = [lines[i:i + per_page] for i in range(0, max(1, len(lines)), per_page)] or [[]]
    streams = []
    for n, chunk in enumerate(chunks):
        ops = [(36, 810, 8, BANNER), (470, 810, 8, f"Page {n + 1} of {len(chunks)}")]
        if n == 0:
            ops.append((36, 780, 13, title))
        y = 755 if n == 0 else 785
        for line in chunk:
            ops.append((36, y, 9, line))
            y -= 14
        streams.append("\n".join(f"BT /F1 {s} Tf 1 0 0 1 {x} {yy} Tm ({fb._pdf_text(t)}) Tj ET" for x, yy, s, t in ops)
                       .encode("cp1252"))
    _pdf(path, streams)


def _pdf(path: Path, streams: list[bytes], images: list[tuple[bytes, int, int]] | None = None) -> None:
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b"",
                            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids = []
    for i, stream in enumerate(streams):
        res = "/Font << /F1 3 0 R >>"
        if images:
            res += f" /XObject << /Im1 {len(objects) + 3} 0 R >>"
        kids.append(len(objects) + 1)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << {res} >> "
                       f"/Contents {len(objects) + 2} 0 R >>".encode())
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
        if images:
            data, w, h = images[i]
            objects.append(f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceGray "
                           f"/BitsPerComponent 8 /Filter /DCTDecode /Length {len(data)} >>\nstream\n".encode() + data
                           + b"\nendstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects):
        offsets.append(len(data))
        data += f"{i + 1} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    data += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    data += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(data))


def write_scanned_pdf(path: Path, lines: list[str]) -> bool:
    """A scanned handwritten statement: one greyscale JPEG page with no text layer except the banner."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:  # pragma: no cover
        write_text_pdf(path, "Handwritten statement (scan not made: Pillow absent)", "\n".join(lines))
        return False
    w, h = 1224, 1584
    img = Image.new("L", (w, h), 246)
    d = ImageDraw.Draw(img)
    font = _font(34, italic=True)
    y = 160
    for k, line in enumerate(lines):
        d.text((110 + (k % 3) * 4, y), line, fill=35, font=font)
        y += 62
        d.line([(100, y - 8), (w - 100, y - 8)], fill=205, width=1)
    img = img.rotate(0.6, fillcolor=246)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    stream = (f"q 612 0 0 792 0 25 cm /Im1 Do Q\nBT /F1 8 Tf 1 0 0 1 36 828 Tm ({fb._pdf_text(BANNER)}) Tj ET").encode("cp1252")
    _pdf(path, [stream], images=[(buf.getvalue(), w, h)])
    return True


def write_docx(path: Path, title: str, paragraphs: list[str]) -> None:
    """A minimal Word document (stdlib zip), the banner as the first paragraph and in the header."""
    def para(text, bold=False):
        rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
        return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
    body = para(BANNER, True) + para(title, True) + "".join(para(p) for p in paragraphs)
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>'
           f'{body}<w:sectPr><w:headerReference w:type="default" r:id="rId1"/></w:sectPr></w:body></w:document>')
    header = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' + para(BANNER) + '</w:hdr>')
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/_rels/document.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/></Relationships>',
        "word/document.xml": doc, "word/header1.xml": header,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            info = zipfile.ZipInfo(name, date_time=(2024, 6, 20, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, text)


def _police_report(label: str, day: dt.date) -> str:
    nxt = day + dt.timedelta(days=1)
    loss = serials(label)
    total = {"Torvane 20V hammer drill": 189, "Keldar 7in circular saw": 129, "Lumetra 55in television": 449,
             "Torvane 20V impact driver": 149, "Keldar 10in table saw": 529, "Lumetra 65in television": 699,
             "Torvane 20V combo kit": 329, "Lumetra soundbar": 179}
    value = sum(total[i] for i, _ in loss)
    lines = [
        f"Calder County Police Department (synthetic). Incident report CCPD-24-{1100 + NIGHTS.index((label, day)) * 37}.",
        f"Offense: theft from a commercial building, over $1,500. Reported {nxt:%A %d %B %Y} at 06:10 by the day manager.",
        "Location: Brightwater Logistics, Unit 7, 2200 Fenwick Ridge Industrial Park.",
        f"Time of offense: between {day:%d %B} 23:00 and {nxt:%d %B} 03:30 (dock 3 door log; camera 4 offline since February).",
        "Night guard on duty: Lena Marsh (contract guard, gate house). Night loader on shift: Desmond Okafor.",
        "Statement of guard: no vehicles seen entering after 22:45. No alarm. Dock 3 roller door found closed and unlocked.",
        f"Property taken ({len(loss)} items, retail value ${value:,}):",
    ]
    lines += [f"  {item}  serial {s}" for item, s in loss]
    if label == "N5":
        lines.append("Supplementary, 3 June: guard Lena Marsh now states she saw \"a white tow truck with RUIZ on the door\" "
                     "near the east fence at about 01:00. Not in her first account.")
    lines.append("Reporting officer: Ofc. R. Danforth #4471-S (synthetic).")
    return "\n".join(lines)


def documents(out: Path) -> dict:
    d = out / "documents"
    made = {}
    for label, day in NIGHTS:
        path = d / f"police-report-{label}-{day + dt.timedelta(days=1):%Y-%m-%d}.pdf"
        write_text_pdf(path, f"Incident report: theft at Brightwater Logistics, night {label}", _police_report(label, day))
        made[label] = str(path.relative_to(out))
    write_text_pdf(d / "search-warrant-affidavit-ruiz-garage.pdf", "Application and affidavit for search warrant", "\n".join([
        "Affiant: Det. Sgt. Paula Grennan (synthetic), Property Crimes Unit.",
        "Premises: Ruiz Auto & Tire, 4410 Calder Mill Road, including service bays 1 to 4, the office, and a white tow truck, "
        "Maryland plate 7TW-0142, with RUIZ AUTO & TIRE on both doors.",
        "Probable cause: a cooperating witness (CW-1) states that after each of five thefts from Brightwater Logistics the goods "
        "were driven to bay 4 of Ruiz Auto & Tire and left with the owner, Mateo Ruiz, who sold them on.",
        "Contract guard Lena Marsh states she saw a white tow truck with RUIZ on the door near the east fence on 1 June at about 01:00.",
        "Bank records show monthly payments of $650 from Travis Kell to Ruiz Auto & Tire. The affiant believes these are payments "
        "for receiving stolen goods.",
        "Sworn 13 June 2024.",
    ]))
    write_text_pdf(d / "search-inventory-ruiz-garage-2024-06-14.pdf", "Search warrant return and inventory, 14 June 2024", "\n".join([
        "Executed 14 June 2024 06:05 to 09:40. Owner Mateo Ruiz present, arrested 07:15.",
        "Item 1: one prepaid mobile phone, black, found in the glovebox of the tow truck (plate 7TW-0142). Powered on. Number 443-555-0131.",
        f"Item 2: {GARAGE_TOOLS[0][0]}, serial {GARAGE_TOOLS[0][1]}, on the bench in bay 2.",
        f"Item 3: {GARAGE_TOOLS[1][0]}, serial {GARAGE_TOOLS[1][1]}, on the bench in bay 2.",
        "Item 4: receipt, Penn's Used Tools, 22 May 2024, two used power tools, $240.00 paid by card, in the office desk.",
        "Item 5: bay 4: padlock (key held by the tenant per the owner), two empty pallets, shrink-wrap offcuts.",
        "Item 6: Mateo Ruiz's iPhone, from his person.",
        "No property matching the Brightwater loss lists was found.",
    ]))
    write_docx(d / "kell-proffer-transcript-2024-06-20.docx", "Proffer session: Travis Kell, 20 June 2024", [
        "Present: ASA M. Thorne (synthetic), Det. Sgt. P. Grennan, Travis Kell, his counsel. Recorded. Transcript excerpt.",
        "THORNE: Tell us what happened to the goods after each night.",
        "KELL: Every time, we took it to Mateo's garage. Bay 4. Mateo took it from there, he sold it.",
        "THORNE: Did you ever rent a storage unit?",
        "KELL: No. Never rented storage. Everything went to the garage.",
        "THORNE: How did you reach Mateo on those nights?",
        "KELL: I called him from the prepaid phone, the one in his truck. That's his phone. He gave me the number.",
        "THORNE: The $650 a month to Ruiz Auto & Tire?",
        "KELL: That was his cut. We called it rent so it looked normal.",
        "THORNE: When did this start?",
        "KELL: March. The first one was the middle of March, a Friday. Then April, then twice in May, then the end of May.",
        "THORNE: Did anyone at the warehouse help?",
        "KELL: Nobody at the warehouse. Just me and Mateo.",
    ])
    write_text_pdf(d / "marsh-police-interview-2024-06-12.pdf", "Recorded interview: Lena Marsh, 12 June 2024", "\n".join([
        "Interviewer: Det. Sgt. P. Grennan (synthetic). Witness: Lena Marsh, 52, contract night guard at Brightwater Logistics.",
        "Q: Tell me about the night of 31 May.",
        "A: I was in the gate house. About one in the morning I saw a white tow truck by the east fence. It said RUIZ on the door.",
        "Q: Did you tell the first officer that?",
        "A: No. I was scared. I'm telling you now.",
        "Q: Do you know Travis Kell?",
        "A: He was a supervisor. I don't really know him. I haven't talked to him since he left.",
        "Q: Has anyone paid you anything?",
        "A: No. Nobody pays me except the guard company.",
    ]))
    scanned = write_scanned_pdf(d / "marsh-handwritten-statement-2024-06-12.pdf", [
        "Statement of Lena Marsh   12 June 2024",
        "On the night of May 31 I was on the gate.",
        "At about 1 am I saw a white tow truck by",
        "the east fence. It had RUIZ on the door.",
        "I did not see who was driving.",
        "Nobody has paid me anything.",
        "Lena Marsh",
    ])
    write_text_pdf(d / "state-cell-site-report.pdf", "Historical cell-site analysis: number 443-555-0131", "\n".join([
        "Prepared for the State by an analyst of the Regional Intelligence Unit (synthetic).",
        "Records: call detail records of 443-555-0131, 1 March to 14 June 2024, with serving cell and sector.",
        "On each of the five theft nights, the phone's evening activity used cell 4471, sector 2.",
        "Sector 4471-2 covers Ruiz Auto & Tire at 4410 Calder Mill Road. In the analyst's opinion the phone's location is "
        "consistent with the garage on each of those nights.",
        "Coverage note (appendix B): sector 4471-2 also covers the residential area east of Calder Mill Road, including "
        "Larkmont Apartments, 18 Wexmoor Court. The sector is about 2.1 km deep.",
        "Activity after midnight on the theft nights used cell 5180 sector 1 (Fenwick Ridge Industrial Park) and cell 6022 "
        "sector 3 (Tallow Creek Road). These are not discussed in the opinion.",
        "No drive test was done.",
    ]))
    badge = d / "brightwater-badge-log-2024.csv"
    with open(badge, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([BANNER])
        w.writerow(["timestamp_local", "badge", "holder", "door", "result"])
        for label, day in NIGHTS:
            nxt = day + dt.timedelta(days=1)
            w.writerow([f"{day:%Y-%m-%d} 22:48", "B-20417", "OKAFOR, DESMOND", "Staff entrance", "granted"])
            w.writerow([f"{day:%Y-%m-%d} 23:06", "B-11032", "KELL, TRAVIS", "Dock 3", "granted"])
            w.writerow([f"{nxt:%Y-%m-%d} 03:12", "B-11032", "KELL, TRAVIS", "Dock 3", "granted"])
            w.writerow([f"{nxt:%Y-%m-%d} 06:02", "B-20417", "OKAFOR, DESMOND", "Staff entrance", "exit"])
        w.writerow(["2024-04-20 17:30", "B-11032", "KELL, TRAVIS", "HR", "termination recorded; deactivation requested"])
    write_text_pdf(d / "bay4-lease-2023-10-01.pdf", "Lease of service bay 4", "\n".join([
        "Landlord: Ruiz Auto & Tire LLC, 4410 Calder Mill Road. Tenant: Travis Kell, 18 Wexmoor Court, Apartment 3C.",
        "Premises: service bay 4 (separate roller door and padlock). Term: month to month from 1 October 2023.",
        "Rent: $650.00 a month, due on the 1st, by bank transfer, reference \"BAY 4 RENT\".",
        "Use: storage of the tenant's own vehicles, tools and personal property. No retail sales from the bay.",
        "Keys: the tenant receives one padlock key; the landlord keeps no copy.",
        "Signed 28 September 2023: Mateo Ruiz (for the landlord), Travis Kell (tenant).",
    ]))
    write_text_pdf(d / "stowell-rental-agreement-unit-212.pdf", "Self-storage rental agreement: unit 212", "\n".join([
        "Facility: Stowell Self Storage, 900 Tallow Creek Road. Unit 212 (10 by 15, drive-up).",
        "Occupant: Brianna Cole, phone 443-555-0151. Start date: 2 February 2024. Rent $139.00 a month.",
        "Payment method on file: debit card ending 4471, cardholder TRAVIS KELL.",
        "Gate code issued to the occupant and one authorised person: Travis Kell.",
        "Gate access log extract: 16 Mar 02:41, 13 Apr 02:38, 4 May 02:50, 18 May 02:44, 1 Jun 02:47 (code 2120).",
    ]))
    write_text_pdf(d / "tow-invoice-1187-2024-04-12.pdf", "Ruiz Auto & Tire: tow invoice 1187", "\n".join([
        "Customer: Harold Vint, 410-555-0191. Vehicle: silver sedan, plate 2HV-5530.",
        "Called in: 12 April 2024 22:31. Dispatched 22:40. On scene 23:20, Hobbet Mill Road past the reservoir sign.",
        "Towed to: Vint residence, 7 Cradlemere Lane. Cleared 01:15 on 13 April. Driver: Mateo Ruiz. Truck plate 7TW-0142.",
        "Charge: $185.00. Paid by bank transfer 15 April 2024.",
    ]))
    write_text_pdf(d / "tow-invoice-1242-2024-06-08.pdf", "Ruiz Auto & Tire: tow invoice 1242", "\n".join([
        "Customer: Travis Kell, 410-555-0121. Vehicle: blue pickup, plate 5KT-2207.",
        "Called in: 8 June 2024 13:52. On scene 14:10, Ferrow Avenue at the light. Customer rode in the tow truck cab.",
        "Towed to: Ruiz Auto & Tire lot. Arrived 14:50. Driver: Mateo Ruiz. Truck plate 7TW-0142.",
        "Charge: $160.00. Status: unpaid.",
    ]))
    write_text_pdf(d / "er-discharge-2024-05-04.pdf", "Ferrowmere Medical Center: emergency department discharge", "\n".join([
        "Patient: Lucía Ruiz. Arrived 3 May 2024 23:08. Discharged 4 May 2024 03:38.",
        "Accompanied by: husband, Mateo Ruiz (in the department throughout per the triage note).",
        "Diagnosis: renal colic. Discharged home with medication. Follow-up with primary care.",
    ]))
    listings = d / "benchyard-listings-export-penns-used-tools.csv"
    with open(listings, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([BANNER])
        w.writerow(["listed", "sold", "seller", "item", "serial", "price", "buyer"])
        names = {s: item for night in LOSSES for item, s in serials(night)}
        for k, s in enumerate(LISTED_SERIALS):
            w.writerow([f"2024-0{3 + k // 3}-{10 + k:02d}", f"2024-0{3 + k // 3}-{14 + k:02d}", "Penn's Used Tools", names[s], s,
                        f"{85 + 20 * k}.00", f"buyer {k + 1}"])
        w.writerow(["2024-05-02", "2024-05-08", "Penn's Used Tools", "Keldar 7in circular saw", "KLD-CS7-31877", "95.00", "Carla Ruiz"])
        w.writerow(["2024-05-15", "2024-05-22", "Penn's Used Tools", GARAGE_TOOLS[0][0], GARAGE_TOOLS[0][1], "150.00", "M. Ruiz (in store)"])
        w.writerow(["2024-05-15", "2024-05-22", "Penn's Used Tools", GARAGE_TOOLS[1][0], GARAGE_TOOLS[1][1], "90.00", "M. Ruiz (in store)"])
    write_text_pdf(d / "discovery-index-state.pdf", "State's discovery index, production 1", "\n".join([
        "State v. Mateo Ruiz (synthetic), case 03-K-24-001187.",
        "1. Police incident reports, five nights (5 files). 2. Search warrant affidavit and return. 3. Proffer of CW-1. "
        "4. Interview and written statement of L. Marsh. 5. Cell-site report, 443-555-0131. 6. Bank records: Kestrel Point Bank "
        "(T. Kell), Larkfield Tradesmen Credit Union (M. Ruiz; Ruiz Auto & Tire LLC). 7. Brightwater badge log.",
        "8. Mobile device extractions (7): E-1 iPhone of M. Ruiz; E-2 Android of T. Kell; E-3 prepaid phone from tow truck; "
        "E-4 D. Okafor (consent); E-5 B. Cole (consent); E-6 L. Marsh (consent); E-7 second handset recovered from T. Kell's vehicle.",
        "Items produced on disc 2: E-1 to E-6.",
    ]))
    mail = d / "brightwater-hr-termination-kell-2024-04-20.eml"
    mail.write_text("\n".join([
        "From: HR Desk <hr@brightwater-logistics.example.com>",
        "To: Site Security <security@brightwater-logistics.example.com>",
        "Date: Sat, 20 Apr 2024 17:31:00 -0400",
        "Subject: Termination: T. Kell, badge B-11032",
        "Message-ID: <lxdemo-0420-hr@example.com>",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
        BANNER,
        "",
        "Travis Kell's employment ended today. Please deactivate badge B-11032 at all doors, including dock 3.",
        "HR Desk",
    ]) + "\n", encoding="utf-8")
    return {"police_reports": made, "scanned_statement_made": scanned}


# ---------------------------------------------------------------------------------------------------------------


def demo_case(voice: bytes | None = None) -> tuple[fb.CaseSpec, dict]:
    bri, photos_made = brianna_phone()
    phones = [mateo_phone(), kell_phone(), burner_phone(), okafor_phone(voice), bri, marsh_phone()]
    return fb.CaseSpec(CASE_TITLE, PEOPLE, phones, ledger=False, seed=60), {"photos_made": photos_made}


def build_demo(out: Path, *, voice: bool = True) -> dict:
    out = Path(out)
    note = _voice_note() if voice else None
    case, made = demo_case(note)
    manifest = fb.build_case(case, out / "phones")
    manifest["voice_note_made"] = note is not None
    manifest.update(made)
    manifest["ledgers"] = write_ledgers(out)
    manifest["documents"] = documents(out)
    manifest["banner"] = BANNER
    (out / "demo-manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False))
    return manifest
