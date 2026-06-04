import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_RA_KEY = os.getenv("TMDB_API_RA_KEY")

HEADERS = {
    "Authorization": f"Bearer {API_RA_KEY}",
    "accept": "application/json"
}

BASE_URL = "https://api.themoviedb.org/3"


def get_popular_movies_of_week(page: int = 1):
    """
    Fetch popular movies (trending this week equivalent via 'popular' endpoint).
    
    Args:
        page (int): Pagination page number (default 1)

    Returns:
        list: List of popular movie dicts
    """

    url = f"{BASE_URL}/movie/popular"

    params = {
        "language": "en-US",
        "page": page
    }

    response = requests.get(url, headers=HEADERS, params=params)

    response.raise_for_status()  # raises error if request fails

    data = response.json()

    return data.get("results", [])

if __name__ == "__main__":
    movies = get_popular_movies_of_week()
    for movie in movies:
        print(movie['title'], movie['release_date'])