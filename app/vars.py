from dotenv import load_dotenv
import os

load_dotenv()

HLS_BASE_DIR = "/home/tpharmsen/Documents/autotorrent/temp/hls_streams/"
PIRATE_URL = "https://thepibay.site/top/200"
MOVIE_URL = "https://api.themoviedb.org/3"

QB_URL = "http://localhost:8080"
QB_USER = os.getenv("QB_USER")
QB_PASS = os.getenv("QB_PASS")
QB_SAVE_PATH = "/home/tpharmsen/Documents/autotorrent/temp/"

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_API_RA_KEY = os.getenv("TMDB_API_RA_KEY")
