# 🎬 Torrent Dashboard

A lightweight self-hosted media automation dashboard built with FastAPI, qBittorrent, and a custom torrent metadata parser.

It provides a mobile-friendly web interface to:
- Add magnet links
- Monitor active torrents
- Browse scraped torrent listings (remote feed)
- Parse and normalize release metadata (movies + TV shows)
- Extract quality + season/episode info automatically

---

## 🚀 Features

### 📡 Torrent Control
- Add magnet links directly from the web UI
- Pause / resume torrents via qBittorrent Web API
- View active downloads in real-time

### 🌍 Remote Torrent Scraper
- Scrapes torrent index pages
- Extracts:
  - Title
  - Magnet links
  - Page links
- Parses release metadata into structured format

### 🧠 Smart Metadata Parsing
Automatically extracts:
- Clean movie / show name
- Season / Episode (SxxExx)
- Video quality (1080p, 720p, 2160p)

Example:
Rick.and.Morty.S09E02.1080p.x265-ELiTE

Becomes:
name: Rick and Morty  
season_episode: S09E02  
quality: 1080p  

---

### 📱 Mobile-Friendly Dashboard
- Minimal dark UI
- Responsive layout
- Works well on phone browsers

---

## 🧱 Architecture

Frontend (HTML/JS)
        ↓
FastAPI Server
        ↓
------------------------------------------------
| Torrent API (qBittorrent Web API)            |
| Scraper (BeautifulSoup + Requests)           |
| Metadata Parser (Regex-based)                |
------------------------------------------------
        ↓
Data Sources:
- Torrent index site
- qBittorrent client

---

## ⚙️ Tech Stack

- FastAPI
- Requests
- BeautifulSoup4
- qBittorrent Web API
- Vanilla HTML + JavaScript
- Regex-based parsing

---

## 📦 Installation

### 1. Clone repository
git clone https://github.com/your-username/torrent-dashboard.git
cd torrent-dashboard

---

### 2. Install dependencies
pip install fastapi uvicorn requests beautifulsoup4

---

### 3. Install qBittorrent
Enable Web UI:
- Host: localhost
- Port: 8080
- Default credentials:
  username: admin  
  password: adminadmin  

---

### 4. Run server
python app/main.py

---

## 🌐 Access

Dashboard:
http://localhost:5000

API Docs:
http://localhost:5000/docs

---

## 📡 API Endpoints

POST /add
Add a magnet link to qBittorrent

GET /torrents
List active torrents

POST /pause/{hash}
Pause torrent

POST /resume/{hash}
Resume torrent

GET /transfer-info
Get download/upload speeds

---

## 🧠 Metadata Parser

Extracts structured fields from torrent release names:

- name → Clean movie/show title
- season_episode → S01E02 format (if available)
- quality → 1080p / 720p / 2160p

---

## ⚠️ Disclaimer

This project is intended for:
- Educational use
- Working with legally distributed torrents
- Personal media automation setups

The author does not condone piracy or copyright infringement.

---

## 🧩 Future Improvements

- TMDb API integration (posters + metadata)
- Smart filtering (seeders, size, quality)
- Netflix-style UI grid
- Auto-download rules engine
- WebSocket real-time updates
- Docker support

---

## 🧑‍💻 Author

Personal learning project focused on:
- Backend systems
- Scraping pipelines
- Media automation
- API orchestration

---

⭐ If you like this project, consider starring it!