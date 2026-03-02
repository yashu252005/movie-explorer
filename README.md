# Movie & TV Show Explorer

Flask-based movie discovery app powered by TMDB API.  
This project now includes Week 1 to Week 4 internship tasks.

## Features

### Core Discovery
- Search movies by title
- Discover movies using advanced filters:
  - Genre
  - Year
  - Minimum rating
  - Streaming provider availability
- Movie details page with cast, crew, similar movies, reviews, and where-to-watch providers

### Personal Tracking
- Watchlist management
- Favorites management
- User reviews and ratings
- Watch history tracking (`Mark as Watched`)
- Upcoming releases page (next 60 days)

### Week 4 Social & Customization
- Social sharing for recommendations from movie details:
  - Share on X
  - Share on WhatsApp
  - Share by email
  - Copy share link
- Custom collection lists:
  - Create collections
  - Add movies to collections
  - View/remove movies inside each collection
  - Delete collection

### Statistics Dashboard
- Total watched count
- Watchlist count
- Favorites count
- Collections count
- Monthly watch activity chart
- Top watched genres

## Tech Stack
- Python
- Flask
- SQLite
- Requests
- Bootstrap 5
- Chart.js (dashboard visualization)

## Project Structure

```text
movie_explorer/
  app.py
  database.py
  database.db
  requirements.txt
  wsgi.py
  Procfile
  static/
    style.css
  templates/
    index.html
    details.html
    watchlist.html
    favorites.html
    watch_history.html
    upcoming.html
    collections.html
    collection_details.html
    dashboard.html
```

## Setup (Local)

1. Open terminal in project folder:
```powershell
cd c:\Users\Yashaswini\Desktop\internship\movie_explore\movie_explorer
```

2. Install dependencies:
```powershell
pip install -r requirements.txt
```

3. (Recommended) Set TMDB API key as environment variable:
```powershell
$env:TMDB_API_KEY="your_tmdb_api_key"
```

4. Run app:
```powershell
python app.py
```

5. Open:
`http://127.0.0.1:8000`

## Database Initialization

Tables are auto-created on app start via `init_db()` in `database.py`.

## Deployment (Render Example)

1. Push project to GitHub.
2. Create a new Web Service in Render.
3. Configure:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn wsgi:app`
4. Add environment variable:
   - `TMDB_API_KEY` = your TMDB API key
5. Deploy.

`Procfile` and `wsgi.py` are included for production startup.

## Internship Week Mapping

- Week 1: Basic search and listing
- Week 2: Movie details, watchlist, favorites, reviews
- Week 3: Advanced filters, watch history, where-to-watch, upcoming releases
- Week 4: Social sharing, collections, analytics dashboard, deployment docs

