import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright


# =========================================================
# CONFIG
# =========================================================

TARGET_URL = os.getenv(
    "TARGET_URL",
    "https://www.fotmob.com/matches/brabrand-vs-nykobing-fc/1dwc9ldq#5864708"
)

MATCH_ID = os.getenv(
    "MATCH_ID",
    "5864708"
)

MONITOR_SECONDS = int(
    os.getenv(
        "MONITOR_SECONDS",
        "120"
    )
)


# =========================================================
# DIRECTORIES
# =========================================================

ROOT = Path.cwd()

LATEST_DIR = ROOT / "data" / "latest"
LIVE_DIR = ROOT / "data" / "live"

LATEST_DIR.mkdir(
    parents=True,
    exist_ok=True
)

LIVE_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# =========================================================
# TIME
# =========================================================

def now():
    return datetime.now(
        timezone.utc
    ).isoformat()


# =========================================================
# CHECK INTERESTING REQUEST
# =========================================================

def is_interesting(
    url,
    resource_type
):

    url_lower = url.lower()

    # XHR / Fetch / WebSocket
    if resource_type in [
        "xhr",
        "fetch",
        "websocket"
    ]:
        return True

    # Important live API keywords
    keywords = [
        "/api/",
        "matchdetails",
        "matchmedia",
        "matchnews",
        "matchodds",
        "leagueDataForMatch",
        "audio-live-stream",
        "tvlisting",
        "live",
        "score",
        "event",
        "stats",
        "lineup",
        "commentary",
        "timeline",
        "socket"
    ]

    for keyword in keywords:

        if keyword in url_lower:
            return True

    return False


# =========================================================
# MAIN
# =========================================================

async def main():

    # -----------------------------------------------------
    # Storage
    # -----------------------------------------------------

    requests = []

    responses = []

    response_bodies = []

    websocket_data = []


    # -----------------------------------------------------
    # Session directory
    # -----------------------------------------------------

    session_name = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%dT%H-%M-%S"
    )

    session_dir = (
        LIVE_DIR /
        session_name
    )

    session_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    # -----------------------------------------------------
    # Start information
    # -----------------------------------------------------

    print("")
    print("=" * 70)
    print("FOTMOB LIVE API MONITOR")
    print("=" * 70)

    print(
        "TARGET URL:",
        TARGET_URL
    )

    print(
        "MATCH ID:",
        MATCH_ID
    )

    print(
        "MONITOR:",
        MONITOR_SECONDS,
        "seconds"
    )

    print("=" * 70)
    print("")


    # =====================================================
    # PLAYWRIGHT
    # =====================================================

    async with async_playwright() as p:

        browser = await p.chromium.launch(

            headless=True,

            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )


        # -------------------------------------------------
        # Browser context
        # -------------------------------------------------

        context = await browser.new_context(

            user_agent=(
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/128.0.0.0 "
                "Safari/537.36"
            ),

            viewport={
                "width": 1440,
                "height": 900
            },

            locale="en-US",

            timezone_id="Europe/Copenhagen"
        )


        page = await context.new_page()


        # =================================================
        # REQUEST LISTENER
        # =================================================

        async def handle_request(request):

            try:

                url = request.url

                resource_type = (
                    request.resource_type
                )


                if not is_interesting(
                    url,
                    resource_type
                ):

                    return


                item = {

                    "time":
                        now(),

                    "method":
                        request.method,

                    "url":
                        url,

                    "resourceType":
                        resource_type,

                    "headers":
                        await request.all_headers()
                }


                requests.append(
                    item
                )


                print(
                    "[REQUEST]",
                    request.method,
                    resource_type,
                    url
                )


            except Exception as error:

                print(
                    "[REQUEST ERROR]",
                    str(error)
                )


        page.on(
            "request",
            handle_request
        )


        # =================================================
        # RESPONSE LISTENER
        # =================================================

        async def handle_response(
            response
        ):

            try:

                url = response.url


                try:

                    resource_type = (
                        response.request.resource_type
                    )

                except Exception:

                    resource_type = ""


                if not is_interesting(
                    url,
                    resource_type
                ):

                    return


                headers = (
                    await response.all_headers()
                )


                content_type = (
                    headers.get(
                        "content-type",
                        ""
                    )
                )


                item = {

                    "time":
                        now(),

                    "status":
                        response.status,

                    "url":
                        url,

                    "resourceType":
                        resource_type,

                    "contentType":
                        content_type,

                    "headers":
                        headers
                }


                responses.append(
                    item
                )


                print(
                    "[RESPONSE]",
                    response.status,
                    resource_type,
                    url
                )


                # =========================================
                # CAPTURE BODY
                # =========================================

                content_lower = (
                    content_type.lower()
                )


                if any(
                    x in content_lower
                    for x in [
                        "json",
                        "text",
                        "javascript"
                    ]
                ):

                    try:

                        body = await response.text()


                        body_item = {

                            "time":
                                now(),

                            "status":
                                response.status,

                            "url":
                                url,

                            "resourceType":
                                resource_type,

                            "contentType":
                                content_type,

                            "body":
                                body
                        }


                        response_bodies.append(
                            body_item
                        )


                        # =================================
                        # SAVE MATCH DETAILS
                        # =================================

                        if (
                            "matchdetails"
                            in url.lower()
                            and MATCH_ID
                            in url
                        ):

                            match_file = (
                                LATEST_DIR /
                                "matchDetails.json"
                            )


                            try:

                                parsed = json.loads(
                                    body
                                )


                                match_file.write_text(

                                    json.dumps(
                                        parsed,
                                        indent=2,
                                        ensure_ascii=False
                                    ),

                                    encoding="utf-8"
                                )


                                print(
                                    "[MATCH DETAILS SAVED]"
                                )


                            except Exception:

                                raw_file = (
                                    LATEST_DIR /
                                    "matchDetails_raw.txt"
                                )


                                raw_file.write_text(

                                    body,

                                    encoding="utf-8"
                                )


                                print(
                                    "[MATCH DETAILS RAW SAVED]"
                                )


                    except Exception as error:

                        print(
                            "[BODY ERROR]",
                            str(error)
                        )


            except Exception as error:

                print(
                    "[RESPONSE ERROR]",
                    str(error)
                )


        page.on(
            "response",
            handle_response
        )


        # =================================================
        # WEBSOCKET
        # =================================================

        def handle_websocket(ws):

            socket_item = {

                "openedAt":
                    now(),

                "url":
                    ws.url,

                "events":
                    []
            }


            websocket_data.append(
                socket_item
            )


            print(
                "[WEBSOCKET OPEN]",
                ws.url
            )


            # ---------------------------------------------
            # Received frame
            # ---------------------------------------------

            def received(message):

                socket_item[
                    "events"
                ].append({

                    "time":
                        now(),

                    "direction":
                        "received",

                    "data":
                        str(message)[
                            :50000
                        ]
                })


                print(
                    "[WS RECEIVED]",
                    ws.url
                )


            # ---------------------------------------------
            # Sent frame
            # ---------------------------------------------

            def sent(message):

                socket_item[
                    "events"
                ].append({

                    "time":
                        now(),

                    "direction":
                        "sent",

                    "data":
                        str(message)[
                            :50000
                        ]
                })


                print(
                    "[WS SENT]",
                    ws.url
                )


            ws.on(
                "framereceived",
                received
            )

            ws.on(
                "framesent",
                sent
            )


        page.on(
            "websocket",
            handle_websocket
        )


        # =================================================
        # PAGE CONSOLE
        # =================================================

        def handle_console(message):

            text = message.text

            keywords = [
                "match",
                "score",
                "live",
                "socket",
                "goal",
                "event"
            ]


            if any(
                keyword in text.lower()
                for keyword in keywords
            ):

                print(
                    "[PAGE]",
                    text
                )


        page.on(
            "console",
            handle_console
        )


        # =================================================
        # PAGE ERROR
        # =================================================

        def handle_page_error(error):

            print(
                "[PAGE ERROR]",
                str(error)
            )


        page.on(
            "pageerror",
            handle_page_error
        )


        # =================================================
        # OPEN FOTMOB
        # =================================================

        print(
            "[OPENING FOTMOB]"
        )


        try:

            await page.goto(

                TARGET_URL,

                wait_until="domcontentloaded",

                timeout=60000
            )


        except Exception as error:

            print(
                "[PAGE LOAD ERROR]",
                str(error)
            )


        # =================================================
        # INITIAL LOAD WAIT
        # =================================================

        print(
            "[WAITING FOR INITIAL API DATA]"
        )


        await page.wait_for_timeout(
            10000
        )


        print("")
        print(
            "[LIVE MONITORING STARTED]"
        )
        print("")


        # =================================================
        # MONITOR
        # =================================================

        start = (
            asyncio.get_event_loop().time()
        )

        last_report = -1


        while True:

            elapsed = (

                asyncio
                .get_event_loop()
                .time()

                - start
            )


            if (
                elapsed
                >= MONITOR_SECONDS
            ):

                break


            await asyncio.sleep(
                1
            )


            seconds = int(
                elapsed
            )


            # Every 10 seconds
            if (

                seconds % 10 == 0

                and seconds != last_report

            ):

                last_report = seconds


                print(

                    "[MONITOR]",

                    f"{seconds}s",

                    "| requests:",
                    len(requests),

                    "| responses:",
                    len(responses),

                    "| bodies:",
                    len(response_bodies),

                    "| websockets:",
                    len(websocket_data)
                )


        # =================================================
        # SAVE SESSION FILES
        # =================================================

        session_files = {

            "requests.json":
                requests,

            "responses.json":
                responses,

            "response_bodies.json":
                response_bodies,

            "websockets.json":
                websocket_data
        }


        for filename, data in (
            session_files.items()
        ):

            file_path = (
                session_dir /
                filename
            )


            file_path.write_text(

                json.dumps(
                    data,
                    indent=2,
                    ensure_ascii=False
                ),

                encoding="utf-8"
            )


        # =================================================
        # FIND MATCH DETAILS RESPONSES
        # =================================================

        match_details_responses = [

            response

            for response
            in responses

            if (
                "matchdetails"
                in response["url"].lower()
            )
        ]


        # =================================================
        # FIND ALL API URLS
        # =================================================

        unique_urls = sorted(
            set(
                response["url"]
                for response
                in responses
            )
        )


        # =================================================
        # MATCH DETAILS RESPONSE TIMES
        # =================================================

        match_details_times = []

        for response in (
            match_details_responses
        ):

            match_details_times.append({

                "time":
                    response["time"],

                "status":
                    response["status"],

                "url":
                    response["url"]
            })


        # =================================================
        # SUMMARY
        # =================================================

        summary = {

            "targetUrl":
                TARGET_URL,

            "matchId":
                MATCH_ID,

            "monitorSeconds":
                MONITOR_SECONDS,

            "startedAt":
                session_name,

            "finishedAt":
                now(),

            "totalRequests":
                len(requests),

            "totalResponses":
                len(responses),

            "totalResponseBodies":
                len(response_bodies),

            "websocketConnections":
                len(websocket_data),

            "uniqueResponseUrls":
                len(unique_urls),

            "matchDetailsResponses":
                len(match_details_responses),

            "matchDetailsUpdates":
                match_details_times,

            "matchDetailsUrls":
                sorted(
                    set(
                        response["url"]

                        for response
                        in match_details_responses
                    )
                )
        }


        # =================================================
        # SAVE SUMMARY
        # =================================================

        summary_file = (
            session_dir /
            "summary.json"
        )


        summary_file.write_text(

            json.dumps(
                summary,
                indent=2,
                ensure_ascii=False
            ),

            encoding="utf-8"
        )


        # =================================================
        # COPY LATEST
        # =================================================

        for filename in [

            "requests.json",

            "responses.json",

            "response_bodies.json",

            "websockets.json",

            "summary.json"

        ]:

            source = (
                session_dir /
                filename
            )


            destination = (
                LATEST_DIR /
                filename
            )


            if source.exists():

                destination.write_bytes(
                    source.read_bytes()
                )


        # =================================================
        # CLOSE
        # =================================================

        await browser.close()


        # =================================================
        # FINAL OUTPUT
        # =================================================

        print("")
        print("=" * 70)
        print("MONITORING FINISHED")
        print("=" * 70)

        print(
            json.dumps(
                summary,
                indent=2,
                ensure_ascii=False
            )
        )

        print("")
        print(
            "Files saved in:"
        )

        print(
            "data/latest/"
        )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
