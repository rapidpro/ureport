import json
import os
import traceback
from datetime import datetime, timezone

from gunicorn.glogging import Logger


class JSONAccessLogger(Logger):
    """
    Writes each access log line as a JSON object rather than the Apache-style line gunicorn produces by default. Field
    names follow the OpenTelemetry semantic conventions for HTTP, nested rather than dotted, so that jq and a log store
    which flattens JSON both address a value by the same path. Values are typed - the status is a number, the duration
    a float - and everything a client controls goes through the JSON encoder, so a crafted header can't break a line or
    forge fields in it, which is what a format string would allow.

    Enabled with --logger-class pointing at this class, and logging to wherever --access-logfile says.
    """

    def access(self, resp, req, environ, request_time):
        # the same test gunicorn's own access log applies
        cfg = self.cfg
        if not (
            cfg.accesslog
            or cfg.logconfig
            or cfg.logconfig_dict
            or cfg.logconfig_json
            or (cfg.syslog and not cfg.disable_redirect_access_to_syslog)
        ):
            return

        try:
            line = json.dumps(self.record(resp, environ, request_time), separators=(",", ":"))
        except Exception:
            self.error(traceback.format_exc())
            return

        self.access_log.info(line)

    def record(self, resp, environ, request_time) -> dict:
        # None if the app never got as far as a status, which gunicorn still logs
        status = resp.status.split(None, 1)[0] if resp.status else None

        # behind a load balancer the peer is the load balancer, and the client is whoever it says it forwarded for
        forwarded_for = environ.get("HTTP_X_FORWARDED_FOR")
        client = forwarded_for.split(",")[0].strip() if forwarded_for else environ.get("REMOTE_ADDR")

        return _prune(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "http": {
                    "request": {
                        "method": environ.get("REQUEST_METHOD"),
                        "header": {"referer": environ.get("HTTP_REFERER")},
                    },
                    "response": {
                        "status_code": int(status) if status else None,
                        "body": {"size": resp.sent},
                    },
                },
                "url": {
                    "scheme": environ.get("wsgi.url_scheme"),
                    "path": environ.get("PATH_INFO"),
                    "query": environ.get("QUERY_STRING"),
                },
                "network": {"protocol": {"version": environ.get("SERVER_PROTOCOL", "").removeprefix("HTTP/")}},
                # the host is also what says which org's site was asked for
                "server": {"address": environ.get("HTTP_HOST")},
                "client": {"address": client},
                "user_agent": {"original": environ.get("HTTP_USER_AGENT")},
                "duration_ms": round(request_time.total_seconds() * 1000, 1),
                # the worker that served it, so that a worker gunicorn reports as timing out can be matched to what it
                # was last seen serving - a timed out request never gets a line of its own
                "process": {"pid": os.getpid()},
            }
        )


def _prune(value):
    """
    Drops the leaves that have nothing to say, and then any branches left empty by that, so a line only carries the
    fields the request actually had.
    """
    if isinstance(value, dict):
        pruned = {k: _prune(v) for k, v in value.items()}
        return {k: v for k, v in pruned.items() if v is not None and v != "" and v != {}}
    return value
