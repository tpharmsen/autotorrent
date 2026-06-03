import os
import requests
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")

BASE_URL = "https://api.themoviedb.org/3/search/movie"


def enrich(title: str):
    if not TMDB_API_KEY:
        return {}

    try:
        r = requests.get(BASE_URL, params={
            "api_key": TMDB_API_KEY,
            "query": title
        })

        data = r.json()

        if data.get("results"):
            m = data["results"][0]

            return {
                "poster": "https://image.tmdb.org/t/p/w300" + m.get("poster_path") if m.get("poster_path") else None,
                "rating": m.get("vote_average"),
                "overview": m.get("overview")
            }

    except Exception:
        pass

    return {}