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


def search_movie_by_title(title: str) -> dict | None:
    response = requests.get(
        f"{BASE_URL}/search/movie",
        headers=HEADERS,
        params={"query": title, "language": "en-US"}
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    return results[0] if results else None

def search_movie_by_id(id: str) -> dict | None:
    response = requests.get(
        f"{BASE_URL}/movie/{id}",
        headers=HEADERS,
        params={"language": "en-US"}
    )
    response.raise_for_status()
    return response.json() if response.status_code == 200 else None

def search_movies(query: str) -> list:
    response = requests.get(
        f"{BASE_URL}/search/movie",
        headers=HEADERS,
        params={"query": query, "language": "en-US"}
    )
    response.raise_for_status()
    
    return response.json().get("results", [])

def search_tv(query: str) -> list:
    response = requests.get(
        f"{BASE_URL}/search/tv",
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

def get_tv_detail(tv_id: int) -> dict:
    response = requests.get(
        f"{BASE_URL}/tv/{tv_id}",
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

def get_trending_posters_movies():
    trending_movies = get_trending_movies()
    results = []
    for r in trending_movies:
        poster_path = r.get('poster_path')
        if not poster_path:
            continue  # skip entries with no poster instead of breaking the grid
        results.append({
            "id": r["id"],
            "title": r.get("original_title") or r.get("title"),
            "poster_url": "https://image.tmdb.org/t/p/w500" + poster_path,
        })
    return results

def get_trending_posters_tv():
    trending_tv = get_trending_tv()
    results = []
    for r in trending_tv:
        poster_path = r.get('poster_path')
        if not poster_path:
            continue  # skip entries with no poster instead of breaking the grid
        results.append({
            "id": r["id"],
            "title": r.get("original_name") or r.get("name"),
            "poster_url": "https://image.tmdb.org/t/p/w500" + poster_path,
        })
    return results

if __name__ == "__main__":
    trending_movies = get_trending_posters_movies()
    trending_tv = get_trending_posters_tv()
    print("Trending Movies Posters:")
    for movie in trending_movies:
        print(f"{movie['title']}: {movie['poster_url']}")
    print("\nTrending TV Posters:")
    for tv in trending_tv:
        print(f"{tv['title']}: {tv['poster_url']}")