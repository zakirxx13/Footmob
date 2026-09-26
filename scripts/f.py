import asyncio
import json
import os
import shutil
from datetime import datetime, timezone

from playwright.async_api import async_playwright


# ============================================================
# CONFIG
# ============================================================

TARGET_URL = "https://www.fotmob.com/matches/brabrand-vs-nykobing-fc/1dwc9ldq#5864708"
MATCH_ID = "5864708"

MONITOR_SECONDS = 120

BASE_DIR = "data"
LIVE_DIR = os.path.join(BASE_DIR, "live")
LATEST_DIR = os.path.join(BASE_DIR, "latest")

os.makedirs(LIVE_DIR, exist_ok=True)
os.makedirs(LATEST_DIR, exist_ok=True)


# ============================================================
# HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def get_path(data, path, default=None):
    """
    Safely read nested dictionary/list values.
    Example:
        get_path(data, ["content", "matchFacts"])
    """

    current = data

    for key in path:

        if isinstance(current, dict):
            current = current.get(key)

        elif isinstance(current, list):

            try:
                current = current[int(key)]
            except Exception:
                return default

        else:
            return default

        if current is None:
            return default

    return current


def count_list(value):
    if isinstance(value, list):
        return len(value)

    return 0


def make_signature(snapshot):
    """
    Create a compact representation used to detect changes.
    """

    return json.dumps(
        snapshot,
        sort_keys=True,
        ensure_ascii=False
    )


# ============================================================
# EXTRACT MATCH DATA
# ============================================================

def extract_match_data(data):

    if not isinstance(data, dict):
        return None

    # --------------------------------------------------------
    # GENERAL
    # --------------------------------------------------------

    general = data.get("general") or {}

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    header = data.get("header") or {}

    teams = header.get("teams") or []

    status = header.get("status") or {}

    home_team = {}
    away_team = {}

    if len(teams) > 0 and isinstance(teams[0], dict):
        home_team = teams[0]

    if len(teams) > 1 and isinstance(teams[1], dict):
        away_team = teams[1]

    # --------------------------------------------------------
    # LIVE TIME
    # --------------------------------------------------------

    live_time = status.get("liveTime") or {}

    # --------------------------------------------------------
    # CONTENT
    # --------------------------------------------------------

    content = data.get("content") or {}

    # --------------------------------------------------------
    # MATCH FACTS
    # --------------------------------------------------------

    match_facts = content.get("matchFacts") or {}

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------

    events_container = match_facts.get("events") or {}

    events = events_container.get("events") or []

    simplified_events = []

    if isinstance(events, list):

        for event in events:

            if not isinstance(event, dict):
                continue

            player = event.get("player") or {}

            assist = event.get("assist")

            if isinstance(assist, dict):
                assist_name = assist.get("name")
            else:
                assist_name = assist

            simplified_events.append({

                "eventId": event.get("eventId"),

                "type": event.get("type"),

                "time": event.get("time"),

                "timeStr": event.get("timeStr"),

                "isHome": event.get("isHome"),

                "player": player.get("name"),

                "playerId": player.get("id"),

                "newScore": event.get("newScore"),

                "assist": assist_name,

                "ownGoal": event.get("ownGoal"),

                "penalty": event.get("isPenaltyShootoutEvent"),

            })

    # --------------------------------------------------------
    # STATS
    # --------------------------------------------------------

    stats = content.get("stats")

    # Sometimes stats can have different structures.
    stats_type = None

    if isinstance(stats, list):
        stats_type = "list"

    elif isinstance(stats, dict):
        stats_type = "dict"

    elif stats is None:
        stats_type = "null"

    else:
        stats_type = type(stats).__name__

    # --------------------------------------------------------
    # PLAYER STATS
    # --------------------------------------------------------

    player_stats = content.get("playerStats")

    player_stats_type = None

    if isinstance(player_stats, list):
        player_stats_type = "list"

    elif isinstance(player_stats, dict):
        player_stats_type = "dict"

    elif player_stats is None:
        player_stats_type = "null"

    else:
        player_stats_type = type(player_stats).__name__

    # --------------------------------------------------------
    # LINEUP
    # --------------------------------------------------------

    lineup = content.get("lineup")

    lineup_type = None

    if isinstance(lineup, list):
        lineup_type = "list"

    elif isinstance(lineup, dict):
        lineup_type = "dict"

    elif lineup is None:
        lineup_type = "null"

    else:
        lineup_type = type(lineup).__name__

    # --------------------------------------------------------
    # SHOTMAP
    # --------------------------------------------------------

    shotmap = content.get("shotmap")

    shot_count = 0

    if isinstance(shotmap, dict):

        shots = shotmap.get("shots")

        if isinstance(shots, list):
            shot_count = len(shots)

    elif isinstance(shotmap, list):

        shot_count = len(shotmap)

    # --------------------------------------------------------
    # OTHER POSSIBLE LIVE DATA
    # --------------------------------------------------------

    substitutions = (
        match_facts.get("substitutions")
        or content.get("substitutions")
        or []
    )

    incidents = (
        match_facts.get("incidents")
        or content.get("incidents")
        or []
    )

    cards = (
        match_facts.get("cards")
        or content.get("cards")
        or []
    )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    home_score = home_team.get("score")
    away_score = away_team.get("score")

    score_display = status.get("scoreStr")

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    snapshot = {

        "capturedAt": now_iso(),

        "matchId": MATCH_ID,

        "teams": {

            "home": {
                "id": home_team.get("id"),
                "name": home_team.get("name"),
                "score": home_score
            },

            "away": {
                "id": away_team.get("id"),
                "name": away_team.get("name"),
                "score": away_score
            },

            "generalHome": general.get("homeTeam"),
            "generalAway": general.get("awayTeam")
        },

        "score": {

            "home": home_score,

            "away": away_score,

            "display": score_display
        },

        "status": {

            "started": status.get("started"),

            "ongoing": status.get("ongoing"),

            "finished": status.get("finished"),

            "cancelled": status.get("cancelled")
        },

        "liveTime": {

            "short": live_time.get("short"),

            "long": live_time.get("long"),

            "maxTime": live_time.get("maxTime"),

            "basePeriod": live_time.get("basePeriod"),

            "addedTime": live_time.get("addedTime")
        },

        "events": {

            "count": len(simplified_events),

            "items": simplified_events
        },

        "stats": {

            "available": stats is not None,

            "type": stats_type,

            "count": count_list(stats)
        },

        "playerStats": {

            "available": player_stats is not None,

            "type": player_stats_type,

            "count": count_list(player_stats)
        },

        "lineup": {

            "available": lineup is not None,

            "type": lineup_type,

            "count": count_list(lineup)
        },

        "shotmap": {

            "available": shotmap is not None,

            "shotCount": shot_count
        },

        "other": {

            "substitutionsCount": count_list(substitutions),

            "incidentsCount": count_list(incidents),

            "cardsCount": count_list(cards)
        }
    }

    return snapshot


# ============================================================
# FIND ALL JSON KEYS
# ============================================================

def collect_structure(value, path="", output=None):

    if output is None:
        output = []

    if isinstance(value, dict):

        for key, child in value.items():

            current_path = (
                f"{path}.{key}"
                if path
                else str(key)
            )

            output.append(current_path)

            collect_structure(
                child,
                current_path,
                output
            )

    elif isinstance(value, list):

        current_path = f"{path}[]"

        output.append(current_path)

        # Only inspect first few list items.
        for item in value[:3]:

            collect_structure(
                item,
                current_path,
                output
            )

    return output


# ============================================================
# MAIN
# ============================================================

async def main():

    session_name = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%dT%H-%M-%S"
    )

    session_dir = os.path.join(
        LIVE_DIR,
        session_name
    )

    os.makedirs(
        session_dir,
        exist_ok=True
    )

    print("=" * 70)
    print("FOTMOB LIVE DATA STRUCTURE MONITOR")
    print("=" * 70)

    print("TARGET URL:")
    print(TARGET_URL)

    print()
    print("MATCH ID:", MATCH_ID)
    print("MONITOR:", MONITOR_SECONDS, "seconds")
    print()

    snapshots = []

    changes = []

    structure = set()

    last_signature = None

    match_details_count = 0

    response_errors = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(

            headless=True,

            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        context = await browser.new_context(

            viewport={
                "width": 1280,
                "height": 720
            }
        )

        page = await context.new_page()

        # ====================================================
        # RESPONSE HANDLER
        # ====================================================

        async def handle_response(response):

            nonlocal match_details_count
            nonlocal last_signature

            url = response.url

            if "api/data/matchDetails" not in url:
                return

            if f"matchId={MATCH_ID}" not in url:
                return

            match_details_count += 1

            response_number = match_details_count

            timestamp = now_iso()

            print()
            print(
                f"[MATCH DETAILS #{response_number}]"
            )

            print(
                "Time:",
                timestamp
            )

            try:

                body = await response.text()

            except Exception as e:

                error = {

                    "responseNumber": response_number,

                    "time": timestamp,

                    "error": str(e),

                    "url": url
                }

                response_errors.append(error)

                print(
                    "ERROR reading response:",
                    e
                )

                return

            data = load_json(body)

            if data is None:

                print(
                    "Response is not valid JSON."
                )

                return

            # -----------------------------------------------
            # Collect JSON structure
            # -----------------------------------------------

            paths = collect_structure(data)

            for path in paths:
                structure.add(path)

            # -----------------------------------------------
            # Extract compact data
            # -----------------------------------------------

            snapshot = extract_match_data(data)

            if snapshot is None:
                return

            snapshot["responseNumber"] = response_number

            snapshot["responseTime"] = timestamp

            snapshots.append(snapshot)

            # -----------------------------------------------
            # Detect change
            # -----------------------------------------------

            signature = make_signature(snapshot)

            if last_signature is None:

                change_type = "INITIAL"

                print(
                    "CHANGE: INITIAL"
                )

                changes.append({

                    "time": timestamp,

                    "responseNumber": response_number,

                    "changeType": change_type,

                    "snapshot": snapshot
                })

            elif signature != last_signature:

                change_type = "CHANGED"

                print(
                    "CHANGE: YES"
                )

                changes.append({

                    "time": timestamp,

                    "responseNumber": response_number,

                    "changeType": change_type,

                    "snapshot": snapshot
                })

            else:

                print(
                    "CHANGE: NO"
                )

            last_signature = signature

            # -----------------------------------------------
            # Console summary
            # -----------------------------------------------

            print(
                "Score:",
                snapshot["score"]["display"]
            )

            print(
                "Time:",
                snapshot["liveTime"]["long"]
            )

            print(
                "Events:",
                snapshot["events"]["count"]
            )

            print(
                "Stats:",
                snapshot["stats"]["available"]
            )

            print(
                "Lineup:",
                snapshot["lineup"]["available"]
            )

            print(
                "Shotmap:",
                snapshot["shotmap"]["available"]
            )

        # ====================================================
        # REGISTER LISTENER
        # ====================================================

        page.on(
            "response",
            handle_response
        )

        # ====================================================
        # OPEN PAGE
        # ====================================================

        print("Opening FotMob page...")

        try:

            await page.goto(

                TARGET_URL,

                wait_until="domcontentloaded",

                timeout=60000
            )

        except Exception as e:

            print(
                "Navigation warning:",
                e
            )

        print(
            "Page opened."
        )

        print()

        # Give initial API requests time.
        await page.wait_for_timeout(
            10000
        )

        # ====================================================
        # MONITOR LOOP
        # ====================================================

        start_time = asyncio.get_event_loop().time()

        while True:

            elapsed = (
                asyncio.get_event_loop().time()
                - start_time
            )

            if elapsed >= MONITOR_SECONDS:
                break

            remaining = (
                MONITOR_SECONDS
                - elapsed
            )

            print(
                f"Monitoring: "
                f"{int(elapsed)} / "
                f"{MONITOR_SECONDS} seconds"
            )

            await asyncio.sleep(
                min(10, remaining)
            )

        print()
        print(
            "Monitoring finished."
        )

        await context.close()

        await browser.close()

    # ========================================================
    # SAVE SNAPSHOTS
    # ========================================================

    snapshots_file = os.path.join(
        session_dir,
        "live_snapshots.json"
    )

    with open(
        snapshots_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            snapshots,
            f,
            ensure_ascii=False,
            indent=2
        )

    # ========================================================
    # SAVE CHANGES
    # ========================================================

    changes_file = os.path.join(
        session_dir,
        "live_changes.json"
    )

    with open(
        changes_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            changes,
            f,
            ensure_ascii=False,
            indent=2
        )

    # ========================================================
    # SAVE JSON STRUCTURE
    # ========================================================

    structure_file = os.path.join(
        session_dir,
        "endpoint_structure.json"
    )

    sorted_structure = sorted(
        structure
    )

    with open(
        structure_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "matchId": MATCH_ID,

                "endpoint":
                    "matchDetails",

                "totalUniquePaths":
                    len(sorted_structure),

                "paths":
                    sorted_structure
            },

            f,

            ensure_ascii=False,

            indent=2
        )

    # ========================================================
    # SAVE ERRORS
    # ========================================================

    errors_file = os.path.join(
        session_dir,
        "response_errors.json"
    )

    with open(
        errors_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            response_errors,
            f,
            ensure_ascii=False,
            indent=2
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = {

        "targetUrl": TARGET_URL,

        "matchId": MATCH_ID,

        "monitorSeconds":
            MONITOR_SECONDS,

        "finishedAt":
            now_iso(),

        "matchDetailsResponses":
            match_details_count,

        "snapshotsCaptured":
            len(snapshots),

        "changesDetected":
            len(changes),

        "uniqueJsonPaths":
            len(sorted_structure),

        "errors":
            len(response_errors),

        "files": {

            "snapshots":
                snapshots_file,

            "changes":
                changes_file,

            "structure":
                structure_file,

            "errors":
                errors_file
        }
    }

    summary_file = os.path.join(
        session_dir,
        "live_change_summary.json"
    )

    with open(
        summary_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            summary,
            f,
            ensure_ascii=False,
            indent=2
        )

    # ========================================================
    # COPY SMALL RESULTS TO latest
    # ========================================================

    latest_files = [

        snapshots_file,

        changes_file,

        structure_file,

        errors_file,

        summary_file
    ]

    for source in latest_files:

        destination = os.path.join(
            LATEST_DIR,
            os.path.basename(source)
        )

        shutil.copy2(
            source,
            destination
        )

    # ========================================================
    # FINAL OUTPUT
    # ========================================================

    print()
    print("=" * 70)
    print("FINAL RESULT")
    print("=" * 70)

    print(
        "matchDetails responses:",
        match_details_count
    )

    print(
        "snapshots captured:",
        len(snapshots)
    )

    print(
        "changes detected:",
        len(changes)
    )

    print(
        "unique JSON paths:",
        len(sorted_structure)
    )

    print(
        "errors:",
        len(response_errors)
    )

    print()
    print("Generated files:")

    print(
        "data/latest/live_snapshots.json"
    )

    print(
        "data/latest/live_changes.json"
    )

    print(
        "data/latest/endpoint_structure.json"
    )

    print(
        "data/latest/response_errors.json"
    )

    print(
        "data/latest/live_change_summary.json"
    )

    print()
    print("DONE.")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
