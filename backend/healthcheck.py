"""Container health check for API and SQLite availability."""

import json
import sys
from urllib.request import urlopen


def main() -> None:
    with urlopen("http://127.0.0.1:8000/api/health", timeout=2) as response:
        if json.load(response).get("status") != "ok":
            sys.exit(1)


if __name__ == "__main__":
    main()
