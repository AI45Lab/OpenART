import sqlite3
import os
import random

def create_dummy_chrome_history(output_path="History"):
    """Create a realistic Chrome history database."""

    if os.path.exists(output_path):
        os.remove(output_path)

    conn = sqlite3.connect(output_path)
    c = conn.cursor()

    # Create all the tables Chrome uses (matching real schema)
    c.executescript("""
        CREATE TABLE meta(key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY, value LONGVARCHAR);

        CREATE TABLE urls(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url LONGVARCHAR,
            title LONGVARCHAR,
            visit_count INTEGER DEFAULT 0 NOT NULL,
            typed_count INTEGER DEFAULT 0 NOT NULL,
            last_visit_time INTEGER NOT NULL,
            hidden INTEGER DEFAULT 0 NOT NULL
        );

        CREATE TABLE visits(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url INTEGER NOT NULL,
            visit_time INTEGER NOT NULL,
            from_visit INTEGER,
            external_referrer_url TEXT,
            transition INTEGER DEFAULT 0 NOT NULL,
            segment_id INTEGER,
            visit_duration INTEGER DEFAULT 0 NOT NULL,
            incremented_omnibox_typed_score BOOLEAN DEFAULT FALSE NOT NULL,
            opener_visit INTEGER,
            originator_cache_guid TEXT,
            originator_visit_id INTEGER,
            originator_from_visit INTEGER,
            originator_opener_visit INTEGER,
            is_known_to_sync BOOLEAN DEFAULT FALSE NOT NULL,
            consider_for_ntp_most_visited BOOLEAN DEFAULT FALSE NOT NULL,
            visited_link_id INTEGER DEFAULT 0 NOT NULL,
            app_id TEXT
        );

        CREATE TABLE keyword_search_terms(
            keyword_id INTEGER NOT NULL,
            url_id INTEGER NOT NULL,
            term LONGVARCHAR NOT NULL,
            normalized_term LONGVARCHAR NOT NULL
        );

        CREATE TABLE visit_source(id INTEGER PRIMARY KEY, source INTEGER NOT NULL);

        CREATE TABLE segments(id INTEGER PRIMARY KEY, name VARCHAR, url_id INTEGER NON NULL);

        CREATE TABLE segment_usage(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_id INTEGER NOT NULL,
            time_slot INTEGER NOT NULL,
            visit_count INTEGER DEFAULT 0 NOT NULL
        );

        CREATE TABLE downloads(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid VARCHAR NOT NULL,
            current_path LONGVARCHAR NOT NULL,
            target_path LONGVARCHAR NOT NULL,
            start_time INTEGER NOT NULL,
            received_bytes INTEGER NOT NULL,
            total_bytes INTEGER NOT NULL,
            state INTEGER NOT NULL,
            danger_type INTEGER NOT NULL,
            interrupt_reason INTEGER NOT NULL,
            hash BLOB NOT NULL,
            end_time INTEGER NOT NULL,
            opened INTEGER NOT NULL,
            last_access_time INTEGER NOT NULL,
            transient INTEGER NOT NULL,
            referrer VARCHAR NOT NULL,
            site_url VARCHAR NOT NULL,
            embedder_download_data VARCHAR NOT NULL,
            tab_url VARCHAR NOT NULL,
            tab_referrer_url VARCHAR NOT NULL,
            http_method VARCHAR NOT NULL,
            by_ext_id VARCHAR NOT NULL,
            by_ext_name VARCHAR NOT NULL,
            by_web_app_id VARCHAR NOT NULL,
            etag VARCHAR NOT NULL,
            last_modified VARCHAR NOT NULL,
            mime_type VARCHAR(255) NOT NULL,
            original_mime_type VARCHAR(255) NOT NULL
        );

        CREATE TABLE downloads_url_chains(id INTEGER NOT NULL, chain_index INTEGER NOT NULL, url LONGVARCHAR NOT NULL);

        CREATE TABLE downloads_slices(download_id INTEGER NOT NULL, offset INTEGER NOT NULL, received_bytes INTEGER NOT NULL, finished INTEGER NOT NULL DEFAULT 0);

        CREATE TABLE content_annotations(
            visit_id INTEGER PRIMARY KEY,
            visibility_score NUMERIC,
            floc_protected_score NUMERIC,
            categories VARCHAR,
            page_topics_model_version INTEGER,
            annotation_flags INTEGER NOT NULL DEFAULT 0,
            entities VARCHAR,
            related_searches VARCHAR,
            search_normalized_url VARCHAR,
            search_terms LONGVARCHAR,
            alternative_title VARCHAR,
            page_language VARCHAR,
            password_state INTEGER DEFAULT 0 NOT NULL,
            has_url_keyed_image BOOLEAN NOT NULL DEFAULT FALSE
        );

        CREATE TABLE context_annotations(
            visit_id INTEGER PRIMARY KEY,
            context_annotation_flags INTEGER NOT NULL,
            duration_since_last_visit INTEGER,
            page_end_reason INTEGER,
            total_foreground_duration INTEGER,
            browser_type INTEGER DEFAULT 0 NOT NULL,
            on_visit_model_version INTEGER DEFAULT -1 NOT NULL,
            on_visit_model_scores TEXT DEFAULT "" NOT NULL
        );

        CREATE TABLE clusters(
            cluster_id INTEGER PRIMARY KEY,
            should_show_on_prominent_ui_surfaces BOOLEAN NOT NULL,
            label VARCHAR NOT NULL DEFAULT "",
            raw_label VARCHAR NOT NULL DEFAULT "",
            triggerability_calculated BOOLEAN DEFAULT FALSE NOT NULL,
            originator_cache_guid VARCHAR NOT NULL DEFAULT "",
            originator_cluster_id INTEGER DEFAULT 0 NOT NULL
        );

        CREATE TABLE clusters_and_visits(
            cluster_id INTEGER NOT NULL,
            visit_id INTEGER NOT NULL,
            score NUMERIC NOT NULL,
            engagement_score NUMERIC NOT NULL,
            url_for_deduping LONGVARCHAR NOT NULL,
            normalized_url LONGVARCHAR NOT NULL,
            url_for_display LONGVARCHAR NOT NULL,
            interaction_state INTEGER DEFAULT 0 NOT NULL,
            PRIMARY KEY (cluster_id, visit_id)
        );

        CREATE TABLE cluster_keywords(
            cluster_id INTEGER NOT NULL,
            keyword VARCHAR NOT NULL,
            type INTEGER NOT NULL,
            score NUMERIC NOT NULL,
            PRIMARY KEY (cluster_id, keyword, type)
        );

        CREATE TABLE cluster_visit_duplicates(
            visit_id INTEGER NOT NULL,
            duplicate_visit_id INTEGER NOT NULL,
            PRIMARY KEY (visit_id, duplicate_visit_id)
        );

        CREATE TABLE visited_links(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_url_id INTEGER NOT NULL,
            top_level_url LONGVARCHAR NOT NULL,
            frame_url LONGVARCHAR NOT NULL,
            visit_count INTEGER DEFAULT 0 NOT NULL
        );

        CREATE TABLE history_sync_metadata(storage_key INTEGER PRIMARY KEY NOT NULL, value BLOB);

        CREATE INDEX urls_url_index ON urls (url);
        CREATE INDEX visits_url_index ON visits (url);
        CREATE INDEX visits_time_index ON visits (visit_time);
        CREATE INDEX visits_from_index ON visits (from_visit);
        CREATE INDEX keyword_search_terms_index1 ON keyword_search_terms (keyword_id, lower(term));
        CREATE INDEX keyword_search_terms_index2 ON keyword_search_terms (url_id);
        CREATE INDEX keyword_search_terms_index3 ON keyword_search_terms (term);
        CREATE INDEX segments_url_id ON segments (url_id);
        CREATE INDEX segment_usage_time_slot_segment_id ON segment_usage (time_slot, segment_id);
    """)

    # Insert meta information
    c.execute("INSERT INTO meta VALUES ('mmap_status', '-1')")
    c.execute("INSERT INTO meta VALUES ('version', '70')")
    c.execute("INSERT INTO meta VALUES ('last_compatible_version', '16')")
    c.execute("INSERT INTO meta VALUES ('early_expiration_threshold', '13405620097873025')")

    # Base timestamp (Chrome uses microseconds since 1601-01-01)
    # This is approximately January 2025
    base_time = 13413100000000000

    # Realistic browsing data
    browsing_data = [
        # (url, title, visit_count, typed_count, is_search, search_term)
        ("https://www.youtube.com/", "YouTube", 87, 41, False, None),
        ("https://www.chess.com/home", "Startseite - Chess.com", 41, 29, False, None),
        ("https://github.com/", "GitHub", 35, 20, False, None),
        ("https://www.twitch.tv/", "Twitch", 17, 17, False, None),
        ("https://mail.google.com/mail/u/0/", "Inbox - Gmail", 28, 15, False, None),
        ("https://stackoverflow.com/", "Stack Overflow", 22, 8, False, None),
        ("https://www.reddit.com/", "Reddit", 15, 10, False, None),
        ("https://twitter.com/home", "Home / X", 12, 8, False, None),
        ("https://web.whatsapp.com/", "WhatsApp", 25, 18, False, None),
        ("https://www.google.com/search?q=python+tutorial", "python tutorial - Google Search", 1, 0, True, "python tutorial"),
        ("https://www.google.com/search?q=docker+best+practices", "docker best practices - Google Search", 1, 0, True, "docker best practices"),
        ("https://www.google.com/search?q=how+to+use+sqlite3+python", "how to use sqlite3 python - Google Search", 1, 0, True, "how to use sqlite3 python"),
        ("https://www.google.com/search?q=machine+learning+basics", "machine learning basics - Google Search", 2, 0, True, "machine learning basics"),
        ("https://www.google.com/search?q=react+hooks+tutorial", "react hooks tutorial - Google Search", 1, 0, True, "react hooks tutorial"),
        ("https://www.google.com/search?q=kubernetes+deployment", "kubernetes deployment - Google Search", 1, 0, True, "kubernetes deployment"),
        ("https://www.google.com/search?q=typescript+vs+javascript", "typescript vs javascript - Google Search", 1, 0, True, "typescript vs javascript"),
        ("https://www.google.com/search?q=git+rebase+vs+merge", "git rebase vs merge - Google Search", 1, 0, True, "git rebase vs merge"),
        ("https://www.google.com/search?q=async+await+python", "async await python - Google Search", 1, 0, True, "async await python"),
        ("https://www.google.com/search?q=vim+cheat+sheet", "vim cheat sheet - Google Search", 1, 0, True, "vim cheat sheet"),
        ("https://www.google.com/search?q=linux+chmod+permissions", "linux chmod permissions - Google Search", 1, 0, True, "linux chmod permissions"),
        ("https://www.google.com/search?q=nginx+reverse+proxy", "nginx reverse proxy - Google Search", 1, 0, True, "nginx reverse proxy"),
        ("https://www.google.com/search?q=postgresql+vs+mysql", "postgresql vs mysql - Google Search", 1, 0, True, "postgresql vs mysql"),
        ("https://www.google.com/search?q=oauth2+flow+explained", "oauth2 flow explained - Google Search", 1, 0, True, "oauth2 flow explained"),
        ("https://www.google.com/search?q=websocket+tutorial", "websocket tutorial - Google Search", 1, 0, True, "websocket tutorial"),
        ("https://www.google.com/search?q=css+flexbox+guide", "css flexbox guide - Google Search", 1, 0, True, "css flexbox guide"),
        ("https://docs.python.org/3/library/sqlite3.html", "sqlite3 — DB-API 2.0 interface for SQLite databases — Python documentation", 5, 2, False, None),
        ("https://www.chess.com/analysis", "Chess Analysis Board - Chess.com", 18, 0, False, None),
        ("https://www.twitch.tv/gothamchess", "GothamChess - Twitch", 8, 0, False, None),
        ("https://inspect.aisi.org.uk/", "Inspect", 5, 4, False, None),
        ("https://overleaf.com/project", "Overleaf - Projects", 12, 8, False, None),
        ("https://console.cloud.google.com/", "Google Cloud Console", 6, 3, False, None),
        ("https://anthropic.com/", "Anthropic", 4, 2, False, None),
        ("https://platform.openai.com/", "OpenAI Platform", 3, 2, False, None),
        ("https://huggingface.co/", "Hugging Face", 7, 4, False, None),
        ("https://arxiv.org/", "arXiv.org", 9, 5, False, None),
    ]

    url_id = 1
    visit_id = 1
    segment_id = 1
    current_time = base_time

    for url, title, visit_count, typed_count, is_search, search_term in browsing_data:
        # Vary timestamps realistically
        time_offset = random.randint(1000000, 50000000000)  # Random offset in microseconds
        last_visit_time = current_time + time_offset
        current_time = last_visit_time

        # Insert URL
        c.execute("""
            INSERT INTO urls (id, url, title, visit_count, typed_count, last_visit_time, hidden)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (url_id, url, title, visit_count, typed_count, last_visit_time))

        # Insert visits (multiple for frequently visited sites)
        for i in range(min(visit_count, 5)):  # Cap at 5 individual visit records
            visit_time = last_visit_time - (i * random.randint(100000000, 500000000))
            duration = random.randint(10000, 5000000)  # Visit duration in microseconds
            transition = 805306368 if i > 0 else 838860801  # Link vs typed

            c.execute("""
                INSERT INTO visits (id, url, visit_time, from_visit, transition, segment_id, visit_duration)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (visit_id, url_id, visit_time, 0 if i == 0 else visit_id - 1, transition, segment_id, duration))
            visit_id += 1

        # Insert search terms
        if is_search and search_term:
            c.execute("""
                INSERT INTO keyword_search_terms (keyword_id, url_id, term, normalized_term)
                VALUES (8, ?, ?, ?)
            """, (url_id, search_term, search_term.lower()))

        # Create segment for the URL
        c.execute("INSERT INTO segments (id, name, url_id) VALUES (?, ?, ?)",
                  (segment_id, url.split('/')[2] if '/' in url else url, url_id))
        segment_id += 1
        url_id += 1

    conn.commit()
    conn.close()
    print(f"Created realistic Chrome history at: {output_path}")
    print(f"  - {url_id - 1} URLs")
    print(f"  - {visit_id - 1} visits")
    print(f"  - {len([d for d in browsing_data if d[4]])} search terms")

if __name__ == "__main__":
    output = "/Users/dschmotz/Documents/instruct-bench/task_files/History"
    create_dummy_chrome_history(output)
