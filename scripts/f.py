import asyncio
import json
import os
import re
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


def safe_json_loads(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def get_nested(data, *keys, default=None):
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def extract_live_snapshot(data):
    """
    Extract only the important live information.
    This keeps the output small.
    """

    if not isinstance(data, dict):
        return None

    general = data.get("general", {})
    header = data.get("header", {})
    teams = header.get("teams", [])
    status = header.get("status", {})
    events_root = data.get("events", {})

    home_team = general.get("homeTeam", {})
    away_team = general.get("awayTeam", {})

    home_name = home_team.get("name")
    away_name = away_team.get("name")

    home_score = None
    away_score = None

    if len(teams) >= 2:
        home_score = teams[0].get("score")
        away_score = teams[1].get("score")

    score_str = status.get("scoreStr")

    live_time = status.get("liveTime", {})

    # --------------------------------------------------------
    # Events
    # --------------------------------------------------------

    all_events = []

    try:
        match_facts = data.get("content", {}).get("matchFacts", {})
        event_container = match_facts.get("events", {})
        all_events = event_container.get("events", []) or []
    except Exception:
        all_events = []

    simplified_events = []

    for event in all_events:
        if not isinstance(event, dict):
            continue

        player = event.get("player") or {}

        simplified_events.append({
            "eventId": event.get("eventId"),
            "type": event.get("type"),
            "time": event.get("time"),
            "timeStr": event.get("timeStr"),
            "isHome": event.get("isHome"),
            "player": player.get("name"),
            "playerId": player.get("id"),
            "newScore": event.get("newScore"),
            "assist": event.get("assistStr"),
            "ownGoal": event.get("ownGoal"),
            "penalty": event.get("isPenaltyShootoutEvent")
        })

    # --------------------------------------------------------
    # Stats / shotmap / lineup
    # --------------------------------------------------------

    stats = data.get("content", {}).get("stats")
    player_stats = data.get("content", {}).get("playerStats")
    shotmap = data.get("content", {}).get("shotmap")
    lineup = data.get("content", {}).get("lineup")

    shot_count = 0

    if isinstance(shotmap, dict):
        shots = shotmap.get("shots")
        if isinstance(shots, list):
            shot_count = len(shots)

    return {
        "capturedAt": now_iso(),

        "matchId": MATCH_ID,

        "teams": {
            "home": home_name,
            "away": away_name,
            "homeId": home_team.get("id"),
            "awayId": away_team.get("id")
        },

        "score": {
            "home": home_score,
            "away": away_score,
            "display": score_str
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

        "dataAvailability": {
            "stats": stats is not None,
            "playerStats": player_stats is not None,
            "lineup": lineup is not None,
            "shotmap": shotmap is not None,
            "shotCount": shot_count
        }
    }


# ============================================================
# MAIN
# ============================================================

async def main():

    session_name = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H-%M-%S"
    )

    session_dir = os.path.join(LIVE_DIR, session_name)
    os.makedirs(session_dir, exist_ok=True)

    print("=" * 60)
    print("FOTMOB LIVE CHANGE MONITOR")
    print("=" * 60)

    print("URL:", TARGET_URL)
    print("MATCH ID:", MATCH_ID)
    print("MONITOR:", MONITOR_SECONDS, "seconds")
    print()

    snapshots = []
    changes = []

    last_snapshot_signature = None

    match_details_count = 0

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

        async def handle_response(response):

            nonlocal match_details_count
            nonlocal last_snapshot_signature

            url = response.url

            if "api/data/matchDetails" not in url:
                return

            if f"matchId={MATCH_ID}" not in url:
                return

            match_details_count += 1

            timestamp = now_iso()

            print(
                f"[MATCH DETAILS #{match_details_count}] "
                f"{timestamp}"
            )

            try:
                body = await response.text()
            except Exception as e:
                print("Could not read response:", e)
                return

            data = safe_json_loads(body)

            if data is None:
                print("Response was not valid JSON.")
                return

            snapshot = extract_live_snapshot(data)

            if snapshot is None:
                return

            snapshot["responseNumber"] = match_details_count
            snapshot["responseTime"] = timestamp

            snapshots.append(snapshot)

            # ------------------------------------------------
            # Create compact signature
            # ------------------------------------------------

            signature_data = {
                "score": snapshot["score"],
                "status": snapshot["status"],
                "liveTime": snapshot["liveTime"],
                "events": snapshot["events"],
                "dataAvailability": snapshot["dataAvailability"]
            }

            signature = json.dumps(
                signature_data,
                sort_keys=True,
                ensure_ascii=False
            )

            # ------------------------------------------------
            # Detect change
            # ------------------------------------------------

            if last_snapshot_signature is None:

                change_type = "INITIAL"

                changes.append({
                    "time": timestamp,
                    "responseNumber": match_details_count,
                    "changeType": change_type,
                    "snapshot": snapshot
                })

                print("  -> INITIAL SNAPSHOT")

            elif signature != last_snapshot_signature:

                change_type = "CHANGED"

                changes.append({
                    "time": timestamp,
                    "responseNumber": match_details_count,
                    "changeType": change_type,
                    "snapshot": snapshot
                })

                print("  -> LIVE DATA CHANGED")

            else:

                print("  -> NO CHANGE")

            last_snapshot_signature = signature

        page.on("response", handle_response)

        print("Opening FotMob...")

        try:
            await page.goto(
                TARGET_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )
        except Exception as e:
            print("Page navigation warning:", e)

        print("Page opened.")
        print()

        # Give the page time to load initial APIs.
        await page.wait_for_timeout(10000)

        start_time = asyncio.get_event_loop().time()

        while True:

            elapsed = asyncio.get_event_loop().time() - start_time

            if elapsed >= MONITOR_SECONDS:
                break

            remaining = MONITOR_SECONDS - elapsed

            print(
                f"Monitoring... "
                f"{int(elapsed)}s / {MONITOR_SECONDS}s"
            )

            await asyncio.sleep(
                min(10, remaining)
            )

        print()
        print("Monitoring finished.")

        await context.close()
        await browser.close()

    # ========================================================
    # SAVE COMPACT RESULTS
    # ========================================================

    snapshots_file = os.path.join(
        session_dir,
        "live_snapshots.json"
    )

    changes_file = os.path.join(
        session_dir,
        "live_changes.json"
    )

    latest_file = os.path.join(
        LATEST_DIR,
        "live_changes.json"
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

    shutil.copy2(
        changes_file,
        latest_file
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = {
        "targetUrl": TARGET_URL,
        "matchId": MATCH_ID,
        "monitorSeconds": MONITOR_SECONDS,

        "matchDetailsResponses": match_details_count,

        "snapshotsCaptured": len(snapshots),

        "changesDetected": len(changes),

        "files": {
            "snapshots": snapshots_file,
            "changes": changes_file
        }
    }

    summary_file = os.path.join(
        session_dir,
        "live_change_summary.json"
    )

    latest_summary = os.path.join(
        LATEST_DIR,
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

    shutil.copy2(
        summary_file,
        latest_summary
    )

    # ========================================================
    # PRINT RESULT
    # ========================================================

    print()
    print("=" * 60)
    print("RESULT")
    print("=" * 60)

    print(
        "matchDetails responses:",
        match_details_count
    )

    print(
        "snapshots:",
        len(snapshots)
    )

    print(
        "changes detected:",
        len(changes)
    )

    print()
    print("Files:")
    print(changes_file)
    print(latest_file)
    print(latest_summary)

    print()
    print("DONE.")


if __name__ == "__main__":
    asyncio.run(main())
