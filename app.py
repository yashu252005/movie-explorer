from collections import Counter
from datetime import date, datetime, timedelta
from functools import wraps
import os
from urllib.parse import quote_plus

import requests
import sqlite3
from flask import Flask, flash, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from database import init_db

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")

# Add your TMDB API key here
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "116ec84b522be7ae3bc95e4a85de3ccb")
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DEFAULT_REGION = "US"

init_db()


PASSWORD_RESET_SALT = "movie-explorer-password-reset"


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


@app.context_processor
def inject_current_user():
    return {
        "current_user": session.get("username"),
        "is_authenticated": "user_id" in session,
    }


def serializer():
    return URLSafeTimedSerializer(app.secret_key)


def generate_password_reset_token(email, password_hash):
    return serializer().dumps({"email": email, "pwd": password_hash}, salt=PASSWORD_RESET_SALT)


def verify_password_reset_token(token, max_age=60 * 60):
    try:
        payload = serializer().loads(token, salt=PASSWORD_RESET_SALT, max_age=max_age)
        return payload
    except (BadSignature, SignatureExpired):
        return None


def development_link_message(label, link):
    # This app currently has no mail sender configured, so links are surfaced for local use.
    print(f"[AUTH] {label}: {link}")
    flash(f"{label}: {link}", "info")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("signup.html")
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("signup.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("signup.html")

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
        existing_user = cursor.fetchone()
        if existing_user:
            conn.close()
            flash("Username or email already exists.", "warning")
            return render_template("signup.html")

        password_hash = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()

        session["user_id"] = user_id
        session["username"] = username
        flash("Signup successful. Welcome!", "success")
        return redirect(url_for("home"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    next_url = request.args.get("next", "/")

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next", "/")

        if not identifier or not password:
            flash("Enter username/email and password.", "danger")
            return render_template("login.html", next_url=next_url)

        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (identifier, identifier.lower()),
        )
        user = cursor.fetchone()
        conn.close()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid credentials.", "danger")
            return render_template("login.html", next_url=next_url)

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        flash("Logged in successfully.", "success")
        return redirect(next_url if next_url.startswith("/") else url_for("home"))

    return render_template("login.html", next_url=next_url)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Please enter your email address.", "danger")
            return render_template("forgot_password.html")

        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT email, password_hash FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        flash(
            "If an account exists for that email, a password reset link has been generated.",
            "info",
        )
        if user:
            token = generate_password_reset_token(user["email"], user["password_hash"])
            reset_link = url_for("reset_password", token=token, _external=True)
            development_link_message("Password reset link", reset_link)

        return redirect(url_for("forgot_password"))

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    payload = verify_password_reset_token(token)
    if not payload:
        flash("Reset link is invalid or expired.", "danger")
        return redirect(url_for("forgot_password"))

    email = payload.get("email")
    token_pwd_hash = payload.get("pwd")
    if not email or not token_pwd_hash:
        flash("Reset link is invalid.", "danger")
        return redirect(url_for("forgot_password"))

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    if not user or user["password_hash"] != token_pwd_hash:
        conn.close()
        flash("Reset link has already been used or is no longer valid.", "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password:
            conn.close()
            flash("Password is required.", "danger")
            return render_template("reset_password.html")
        if len(password) < 6:
            conn.close()
            flash("Password must be at least 6 characters.", "danger")
            return render_template("reset_password.html")
        if password != confirm_password:
            conn.close()
            flash("Passwords do not match.", "danger")
            return render_template("reset_password.html")

        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user["id"]),
        )
        conn.commit()
        conn.close()
        flash("Password reset successful. Please log in.", "success")
        return redirect(url_for("login"))

    conn.close()
    return render_template("reset_password.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


def tmdb_get(endpoint, **params):
    """Small TMDB helper with shared API key and safe fallback."""
    payload = {"api_key": TMDB_API_KEY, **params}
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", params=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return {}


def get_genres():
    data = tmdb_get("/genre/movie/list", language="en-US")
    return data.get("genres", [])


def get_watch_providers(region=DEFAULT_REGION):
    data = tmdb_get("/watch/providers/movie", watch_region=region)
    return sorted(data.get("results", []), key=lambda item: item.get("provider_name", ""))


def get_trending_movies():
    data = tmdb_get("/trending/movie/week", language="en-US", page=1)
    return data.get("results", [])[:8]


@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    # Support both GET and old POST search form.
    search_query = request.values.get("search", "").strip()
    genre = request.values.get("genre", "").strip()
    year = request.values.get("year", "").strip()
    min_rating = request.values.get("rating", "").strip()
    provider = request.values.get("provider", "").strip()

    genres = get_genres()
    providers = get_watch_providers(DEFAULT_REGION)
    trending_movies = get_trending_movies()

    movies = []
    if search_query:
        params = {
            "query": search_query,
            "include_adult": "false",
            "language": "en-US",
            "page": 1,
        }
        if year:
            params["year"] = year
        data = tmdb_get("/search/movie", **params)
        movies = data.get("results", [])
    else:
        params = {
            "sort_by": "popularity.desc",
            "include_adult": "false",
            "include_video": "false",
            "language": "en-US",
            "page": 1,
        }
        if genre:
            params["with_genres"] = genre
        if year:
            params["primary_release_year"] = year
        if min_rating:
            params["vote_average.gte"] = min_rating
        if provider:
            params["watch_region"] = DEFAULT_REGION
            params["with_watch_providers"] = provider
            params["with_watch_monetization_types"] = "flatrate"

        data = tmdb_get("/discover/movie", **params)
        movies = data.get("results", [])

    filters = {
        "search": search_query,
        "genre": genre,
        "year": year,
        "rating": min_rating,
        "provider": provider,
    }

    return render_template(
        "index.html",
        movies=movies,
        trending_movies=trending_movies,
        image_url=IMAGE_BASE_URL,
        genres=genres,
        providers=providers,
        filters=filters,
        region=DEFAULT_REGION,
    )


@app.route("/movie/<int:movie_id>")
@login_required
def movie_details(movie_id):
    movie = tmdb_get(f"/movie/{movie_id}", language="en-US")
    if not movie or movie.get("success") is False:
        return "Could not fetch movie details."

    credits = tmdb_get(f"/movie/{movie_id}/credits", language="en-US")
    similar = tmdb_get(f"/movie/{movie_id}/similar", language="en-US")
    providers_data = tmdb_get(f"/movie/{movie_id}/watch/providers")

    region_data = providers_data.get("results", {}).get(DEFAULT_REGION, {})
    stream_options = region_data.get("flatrate", [])
    rent_options = region_data.get("rent", [])
    buy_options = region_data.get("buy", [])
    provider_link = region_data.get("link")

    cast = credits.get("cast", [])[:8]
    crew = credits.get("crew", [])[:8]
    genres = movie.get("genres", [])
    production = movie.get("production_companies", [])

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT rating, review FROM reviews WHERE movie_id = ?", (movie_id,))
    reviews = cursor.fetchall()
    conn.row_factory = sqlite3.Row
    collections_cursor = conn.cursor()
    collections_cursor.execute("SELECT id, name FROM collections ORDER BY name ASC")
    collections = collections_cursor.fetchall()
    conn.close()

    share_url = request.url
    share_text = f"Check out this movie recommendation: {movie.get('title', 'Movie')}"
    twitter_share = f"https://twitter.com/intent/tweet?text={quote_plus(share_text)}&url={quote_plus(share_url)}"
    whatsapp_share = f"https://wa.me/?text={quote_plus(share_text + ' ' + share_url)}"
    email_share = f"mailto:?subject={quote_plus('Movie Recommendation')}&body={quote_plus(share_text + chr(10) + share_url)}"

    return render_template(
        "details.html",
        movie=movie,
        cast=cast,
        crew=crew,
        genres=genres,
        production=production,
        similar=similar.get("results", []),
        reviews=reviews,
        stream_options=stream_options,
        rent_options=rent_options,
        buy_options=buy_options,
        provider_link=provider_link,
        collections=collections,
        share_url=share_url,
        twitter_share=twitter_share,
        whatsapp_share=whatsapp_share,
        email_share=email_share,
        image_url=IMAGE_BASE_URL,
    )


@app.route("/add_watchlist/<int:movie_id>")
@login_required
def add_watchlist(movie_id):
    movie = tmdb_get(f"/movie/{movie_id}", language="en-US")
    if not movie:
        return redirect(url_for("home"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO watchlist (movie_id, title, poster) VALUES (?, ?, ?)",
        (movie_id, movie.get("title"), movie.get("poster_path")),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("watchlist"))


@app.route("/remove_watchlist/<int:movie_id>")
@login_required
def remove_watchlist(movie_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watchlist WHERE movie_id = ?", (movie_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("watchlist"))


@app.route("/watchlist")
@login_required
def watchlist():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM watchlist")
    movies = cursor.fetchall()
    conn.close()

    return render_template("watchlist.html", movies=movies, image_url=IMAGE_BASE_URL)


@app.route("/favorites")
@login_required
def favorites():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM favorites")
    movies = cursor.fetchall()
    conn.close()

    return render_template("favorites.html", movies=movies, image_url=IMAGE_BASE_URL)


@app.route("/add_favorite/<int:movie_id>")
@login_required
def add_favorite(movie_id):
    movie = tmdb_get(f"/movie/{movie_id}", language="en-US")
    if not movie:
        return redirect(url_for("home"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO favorites (movie_id, title, poster) VALUES (?, ?, ?)",
        (movie_id, movie.get("title"), movie.get("poster_path")),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("favorites"))


@app.route("/remove_favorite/<int:movie_id>")
@login_required
def remove_favorite(movie_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM favorites WHERE movie_id = ?", (movie_id,))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("favorites"))


@app.route("/review/<int:movie_id>", methods=["POST"])
@login_required
def review(movie_id):
    rating = request.form.get("rating")
    review_text = request.form.get("review")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reviews (movie_id, rating, review) VALUES (?, ?, ?)",
        (movie_id, rating, review_text),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("movie_details", movie_id=movie_id))


@app.route("/mark_watched/<int:movie_id>")
@login_required
def mark_watched(movie_id):
    movie = tmdb_get(f"/movie/{movie_id}", language="en-US")
    if not movie:
        return redirect(url_for("movie_details", movie_id=movie_id))

    genres = ", ".join([g.get("name", "") for g in movie.get("genres", []) if g.get("name")])
    watched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO watch_history (movie_id, title, poster, genres, release_date, tmdb_rating, watched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(movie_id) DO UPDATE SET
            title = excluded.title,
            poster = excluded.poster,
            genres = excluded.genres,
            release_date = excluded.release_date,
            tmdb_rating = excluded.tmdb_rating,
            watched_at = excluded.watched_at
        """,
        (
            movie_id,
            movie.get("title"),
            movie.get("poster_path"),
            genres,
            movie.get("release_date"),
            movie.get("vote_average"),
            watched_at,
        ),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("history"))


@app.route("/history")
@login_required
def history():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM watch_history ORDER BY datetime(watched_at) DESC")
    records = cursor.fetchall()
    conn.close()

    total_watched = len(records)
    ratings = [r["tmdb_rating"] for r in records if r["tmdb_rating"] is not None]
    average_rating = round(sum(ratings) / len(ratings), 1) if ratings else None

    genre_counter = Counter()
    for item in records:
        genres = item["genres"] or ""
        for genre in [g.strip() for g in genres.split(",") if g.strip()]:
            genre_counter[genre] += 1

    top_genres = genre_counter.most_common(5)

    insights = {
        "total_watched": total_watched,
        "average_rating": average_rating,
        "top_genres": top_genres,
    }

    return render_template(
        "watch_history.html",
        records=records,
        insights=insights,
        image_url=IMAGE_BASE_URL,
    )


@app.route("/upcoming")
@login_required
def upcoming():
    today = date.today()
    end_date = today + timedelta(days=60)

    data = tmdb_get(
        "/discover/movie",
        language="en-US",
        sort_by="primary_release_date.asc",
        include_adult="false",
        include_video="false",
        page=1,
        **{
            "primary_release_date.gte": today.isoformat(),
            "primary_release_date.lte": end_date.isoformat(),
        },
    )

    movies = data.get("results", [])
    return render_template(
        "upcoming.html",
        movies=movies,
        start_date=today.isoformat(),
        end_date=end_date.isoformat(),
        image_url=IMAGE_BASE_URL,
    )


@app.route("/collections", methods=["GET", "POST"])
@login_required
def collections():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if name:
            conn = sqlite3.connect("database.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO collections (name, description, created_at) VALUES (?, ?, ?)",
                (name, description, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
            conn.close()
        return redirect(url_for("collections"))

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT c.id, c.name, c.description, c.created_at, COUNT(ci.id) AS items_count
        FROM collections c
        LEFT JOIN collection_items ci ON c.id = ci.collection_id
        GROUP BY c.id
        ORDER BY c.created_at DESC
        """
    )
    collection_list = cursor.fetchall()
    conn.close()
    return render_template("collections.html", collections=collection_list)


@app.route("/collections/<int:collection_id>")
@login_required
def collection_details(collection_id):
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM collections WHERE id = ?", (collection_id,))
    collection = cursor.fetchone()
    cursor.execute(
        """
        SELECT * FROM collection_items
        WHERE collection_id = ?
        ORDER BY datetime(added_at) DESC
        """,
        (collection_id,),
    )
    items = cursor.fetchall()
    conn.close()
    if not collection:
        return redirect(url_for("collections"))
    return render_template("collection_details.html", collection=collection, items=items, image_url=IMAGE_BASE_URL)


@app.route("/collections/delete/<int:collection_id>")
@login_required
def delete_collection(collection_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM collection_items WHERE collection_id = ?", (collection_id,))
    cursor.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("collections"))


@app.route("/collections/add", methods=["POST"])
@login_required
def add_to_collection():
    collection_id = request.form.get("collection_id")
    movie_id = request.form.get("movie_id")
    if not collection_id or not movie_id:
        return redirect(request.referrer or url_for("collections"))

    movie = tmdb_get(f"/movie/{movie_id}", language="en-US")
    if not movie:
        return redirect(request.referrer or url_for("collections"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO collection_items
        (collection_id, movie_id, title, poster, added_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(collection_id),
            int(movie_id),
            movie.get("title"),
            movie.get("poster_path"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("collections"))


@app.route("/collections/<int:collection_id>/remove/<int:movie_id>")
@login_required
def remove_from_collection(collection_id, movie_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM collection_items WHERE collection_id = ? AND movie_id = ?",
        (collection_id, movie_id),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("collection_details", collection_id=collection_id))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS count FROM watch_history")
    watched_count = cursor.fetchone()["count"]
    cursor.execute("SELECT COUNT(*) AS count FROM watchlist")
    watchlist_count = cursor.fetchone()["count"]
    cursor.execute("SELECT COUNT(*) AS count FROM favorites")
    favorites_count = cursor.fetchone()["count"]
    cursor.execute("SELECT COUNT(*) AS count FROM collections")
    collections_count = cursor.fetchone()["count"]

    cursor.execute(
        """
        SELECT substr(watched_at, 1, 7) AS month_key, COUNT(*) AS watched
        FROM watch_history
        WHERE watched_at IS NOT NULL
        GROUP BY substr(watched_at, 1, 7)
        ORDER BY month_key ASC
        """
    )
    monthly_rows = cursor.fetchall()
    monthly_labels = [row["month_key"] for row in monthly_rows]
    monthly_values = [row["watched"] for row in monthly_rows]

    cursor.execute("SELECT genres FROM watch_history")
    genre_rows = cursor.fetchall()
    conn.close()

    genre_counter = Counter()
    for row in genre_rows:
        genres = row["genres"] or ""
        for genre in [g.strip() for g in genres.split(",") if g.strip()]:
            genre_counter[genre] += 1

    top_genres = genre_counter.most_common(8)

    return render_template(
        "dashboard.html",
        watched_count=watched_count,
        watchlist_count=watchlist_count,
        favorites_count=favorites_count,
        collections_count=collections_count,
        monthly_labels=monthly_labels,
        monthly_values=monthly_values,
        top_genres=top_genres,
    )


if __name__ == "__main__":
    app.run(debug=True, port=8000)
