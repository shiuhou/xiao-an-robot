"""Standard-library local HTTP server for Xiao An."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from base_station.api.response import ApiResponse, error
from base_station.api.router import ApiRouter
from base_station.api.runtime import ApiRuntime


def make_handler(router: ApiRouter, verbose: bool = False):
    class ApiRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._handle_request()

        def do_POST(self) -> None:
            self._handle_request()

        def do_OPTIONS(self) -> None:
            self._handle_request()

        def _handle_request(self) -> None:
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            try:
                body_json = self._read_json_body()
            except ValueError as exc:
                self._write_response(error(
                    code="invalid_json",
                    message=str(exc),
                    status=400,
                ))
                return

            response = router.route(
                method=self.command,
                path=parsed.path,
                query=query,
                body_json=body_json,
            )
            self._write_response(response)

        def _read_json_body(self) -> Any:
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            if content_length <= 0:
                return None
            raw_body = self.rfile.read(content_length)
            try:
                return json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Request body must be valid UTF-8 JSON") from exc

        def _write_response(self, response: ApiResponse) -> None:
            payload = json.dumps(
                response.body,
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header(
                "Access-Control-Allow-Methods",
                "GET,POST,OPTIONS",
            )
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format_string: str, *args: Any) -> None:
            if verbose:
                super().log_message(format_string, *args)

    return ApiRequestHandler


def create_server(
    host: str,
    port: int,
    runtime: ApiRuntime,
    verbose: bool | None = None,
) -> ThreadingHTTPServer:
    router = ApiRouter(runtime)
    handler = make_handler(
        router,
        verbose=runtime.verbose if verbose is None else bool(verbose),
    )
    return ThreadingHTTPServer((host, int(port)), handler)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Xiao An local HTTP API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db-path", default="agent/data/xiao_an.db")
    parser.add_argument(
        "--robot-ws-url",
        default="ws://127.0.0.1:8765/agent",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime = ApiRuntime(
        db_path=args.db_path,
        robot_ws_url=args.robot_ws_url,
        verbose=args.verbose,
    )
    server = create_server(
        host=args.host,
        port=args.port,
        runtime=runtime,
    )
    try:
        if args.verbose:
            host, port = server.server_address[:2]
            print(f"Xiao An API listening on http://{host}:{port}")
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
