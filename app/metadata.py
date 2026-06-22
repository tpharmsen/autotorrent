import requests
import os
from dotenv import load_dotenv

load_dotenv()
from vars import MOVIE_URL, TMDB_API_RA_KEY
HEADERS = {
    "Authorization": f"Bearer {TMDB_API_RA_KEY}",
    "accept": "application/json"
}
BASE_URL = MOVIE_URL


def search_movie(title: str) -> dict | None:
    response = requests.get(
        f"{BASE_URL}/search/movie",
        headers=HEADERS,
        params={"query": title, "language": "en-US"}
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    return results[0] if results else None

def search_movies(query: str) -> list:
    response = requests.get(
        f"{BASE_URL}/search/movie",
        headers=HEADERS,
        params={"query": query, "language": "en-US"}
    )
    response.raise_for_status()
    
    return response.json().get("results", [])


def get_movie_detail(movie_id: int) -> dict:
    response = requests.get(
        f"{BASE_URL}/movie/{movie_id}",
        headers=HEADERS,
        params={"append_to_response": "credits,videos,reviews", "language": "en-US"}
    )
    response.raise_for_status()
    return response.json()


def get_trending_movies(page: int = 1) -> list:
    response = requests.get(
        f"{BASE_URL}/trending/movie/week",
        headers=HEADERS,
        params={"page": page, "language": "en-US"}
    )
    response.raise_for_status()
    return response.json().get("results", [])


def get_trending_tv(page: int = 1) -> list:
    response = requests.get(
        f"{BASE_URL}/trending/tv/week",
        headers=HEADERS,
        params={"page": page, "language": "en-US"}
    )
    response.raise_for_status()
    return response.json().get("results", [])


def download_posters(data):
    
    poster_base_url = "https://image.tmdb.org/t/p/w500"
    for r in data:
        #print(r)
        name = r['original_title'] if r['media_type'] == 'movie' else r['original_name']
        poster_path = r['poster_path']
        if poster_path:
            poster_url = poster_base_url + poster_path
            response = requests.get(poster_url)
            if r['media_type'] == 'movie':
                filename = f"temp/posters/movies/{name}.jpg"
            else:
                filename = f"temp/posters/tv/{name}.jpg"
            with open(filename, "wb") as f:
                f.write(response.content)

if __name__ == "__main__":
    trending_movies = get_trending_movies()
    trending_tv = get_trending_tv()
    download_posters(trending_movies)
    download_posters(trending_tv)