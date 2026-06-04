import requests
from bs4 import BeautifulSoup
import re

QUALITY_REGEX = r"(2160p|1080p|720p|480p)"
SE_REGEX = r"S(\d{1,2})E(\d{1,2})"

JUNK = [
    "WEBRip", "WEB-DL", "WEB", "AMZN", "HDRip", "BluRay", "BRRip",
    "x264", "x265", "HEVC", "10Bit", "DDP5", "DDP5.1", "AAC",
    "Atmos", "H264", "H.264", "FLUX", "ETHEL", "MeGusta",
    "NeoNoir", "BONE", "RMTeam", "YIFY", "CAM", "PROPER",
    "REPACK", "DSNP", "DCPRip", "DCPRIP"
]


def fetch_remote():
    url = "https://thepibay.site/top/200"
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    items = []

    for row in soup.find_all("tr"):
        title_tag = row.select_one("a.detLink")
        magnet_tag = row.find("a", href=lambda x: x and x.startswith("magnet:"))

        if not title_tag:
            continue

        raw_title = title_tag.text.strip()
        page_link = title_tag["href"]
        magnet = magnet_tag["href"] if magnet_tag else None

        parsed = parse_release(raw_title)

        items.append({
            "raw": raw_title,
            "name": parsed["name"],
            "season_episode": parsed["season_episode"],
            "quality": parsed["quality"],
            "magnet": magnet,
            "page_link": page_link
        })

    return items


def clean_title(name: str):
    name = re.sub(r"\[.*?\]|\(.*?\)", "", name)
    name = name.replace(".", " ").replace("_", " ")

    for j in JUNK:
        name = name.replace(j, "")

    name = re.sub(r"\s+", " ", name).strip()
    return name


def parse_release(title: str):
    # QUALITY
    quality_match = re.search(QUALITY_REGEX, title)
    quality = quality_match.group(1) if quality_match else None

    # SEASON / EPISODE
    se_match = re.search(SE_REGEX, title, re.IGNORECASE)
    if se_match:
        season_episode = f"S{int(se_match.group(1)):02d}E{int(se_match.group(2)):02d}"
    else:
        season_episode = None

    # CLEAN NAME
    name = clean_title(title)

    return {
        "name": name,
        "season_episode": season_episode,
        "quality": quality
    }

def get_downloadable_torrents(title: str):
    base_url = "https://thepibay.site/search/"
    search_url = base_url + title.replace(" ", "%20")
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(search_url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    items = []
    for row in soup.find_all("tr"):
        title_tag = row.select_one("a.detLink")
        magnet_tag = row.find("a", href=lambda x: x and x.startswith("magnet:"))

        if not title_tag:
            continue

        raw_title = title_tag.text.strip()
        page_link = title_tag["href"]
        magnet = magnet_tag["href"] if magnet_tag else None

        # Seeders/leechers are in the last two <td> columns
        cols = row.find_all("td")
        seeders = cols[-2].text.strip() if len(cols) >= 2 else "?"
        leechers = cols[-1].text.strip() if len(cols) >= 2 else "?"

        # Size is in the description line
        desc = row.select_one("font.detDesc")
        size = None
        if desc:
            for part in desc.text.split(","):
                if "Size" in part:
                    size = part.replace("Size", "").strip()

        parsed = parse_release(raw_title)
        items.append({
            "raw": raw_title,
            "name": parsed["name"],
            "season_episode": parsed["season_episode"],
            "quality": parsed["quality"],
            "magnet": magnet,
            "page_link": page_link,
            "seeders": seeders,
            "leechers": leechers,
            "size": size or "Unknown"
        })

    return items


if __name__ == "__main__":
    results = fetch_remote()

    print("\nParsed items:\n")
    
    for i,r in enumerate(results):
        print(r["raw"])
        #print("NAME:", r["name"])
        #print("LINK:", r["page_link"])
        #print("----")
        if i >= 40:
            break