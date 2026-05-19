from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agent import load_memory, run_optimization
from market_data import fetch_fundamentals, fetch_ohlc, search_symbols


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


class QuantLabHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        clean = parsed.path.lstrip("/")
        if clean.startswith("api/"):
            return str(FRONTEND / "index.html")
        if clean == "":
            clean = "index.html"
        return str(FRONTEND / clean)

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/get-memory-nodes":
            self.send_json({"memoryNodes": load_memory()})
            return
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "service": "BlackBox AI Quant Lab"})
            return
        if parsed.path == "/api/market-data":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", ["TSLA"])[0]
            period = query.get("period", ["1y"])[0]
            interval = query.get("interval", ["1d"])[0]
            self.send_json(fetch_ohlc(symbol, period=period, interval=interval))
            return
        if parsed.path == "/api/search-symbols":
            query = parse_qs(parsed.query)
            term = query.get("q", [""])[0]
            self.send_json(search_symbols(term))
            return
        if parsed.path == "/api/fundamentals":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", ["TSLA"])[0]
            self.send_json(fetch_fundamentals(symbol))
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = parse_qs(raw)

        if parsed.path == "/api/start-optimization":
            asset = payload.get("asset", "mTSLA")
            feedback = payload.get("feedback", "")
            generations = int(payload.get("generations", 3))
            self.send_json(run_optimization(asset=asset, feedback=feedback, generations=generations))
            return

        self.send_json({"error": "Not found"}, status=404)


def main() -> None:
    host = "127.0.0.1"
    port = 8000
    server = ThreadingHTTPServer((host, port), QuantLabHandler)
    print(f"BlackBox AI Quant Lab running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
