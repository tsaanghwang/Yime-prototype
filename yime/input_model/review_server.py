"""Local HTTP interface for candidate review and rule-family registration."""

from __future__ import annotations

import json
import mimetypes
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .review_workbench import (
    AFFIX_ANALYSIS_CLASSES,
    APPROVAL_POLICIES,
    REVIEWABLE_CLASSES,
    TAIL_SEMANTIC_CLASSES,
    UnencodedCandidateReview,
)


UI_DIRECTORY = Path(__file__).with_name("review_ui")
ASSETS = {
    "/": UI_DIRECTORY / "index.html",
    "/index.html": UI_DIRECTORY / "index.html",
    "/app.js": UI_DIRECTORY / "app.js",
    "/styles.css": UI_DIRECTORY / "styles.css",
    "/assets/app.js": UI_DIRECTORY / "app.js",
    "/assets/styles.css": UI_DIRECTORY / "styles.css",
}


class ReviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        input_model_database: Path,
        source_database: Path,
    ):
        self.input_model_database = input_model_database
        self.source_database = source_database
        super().__init__(server_address, ReviewRequestHandler)

    def review(self) -> UnencodedCandidateReview:
        return UnencodedCandidateReview(
            input_model_database=self.input_model_database,
            source_database=self.source_database,
        )


class ReviewRequestHandler(BaseHTTPRequestHandler):
    server: ReviewHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        print(f"[review-ui] {self.address_string()} {format % args}")

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if self.headers.get("Origin") == "null":
            self.send_header("Access-Control-Allow-Origin", "null")
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status)

    def _asset(self, path: Path) -> None:
        if not path.is_file():
            self._error(HTTPStatus.NOT_FOUND, "asset not found")
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ASSETS:
            self._asset(ASSETS[parsed.path])
            return
        try:
            if parsed.path == "/api/config":
                self._json(
                    {
                        "candidate_classes": REVIEWABLE_CLASSES,
                        "approval_policies": APPROVAL_POLICIES,
                        "rule_family_classes": AFFIX_ANALYSIS_CLASSES,
                        "affix_analysis_classes": AFFIX_ANALYSIS_CLASSES,
                        "tail_semantic_classes": TAIL_SEMANTIC_CLASSES,
                    }
                )
                return
            if parsed.path == "/api/summary":
                self._json(self.server.review().summary())
                return
            if parsed.path == "/api/queue":
                query = parse_qs(parsed.query)
                raw_text_length = query.get("text_length", [None])[0]
                page = self.server.review().queue(
                    status=query.get("status", ["proposed"])[0],
                    query=query.get("query", [""])[0],
                    minimum_frequency=int(query.get("minimum_frequency", ["0"])[0]),
                    text_length=(
                        int(raw_text_length)
                        if raw_text_length not in {None, ""}
                        else None
                    ),
                    limit=int(query.get("limit", ["50"])[0]),
                    cursor=query.get("cursor", [None])[0],
                )
                self._json(
                    {
                        "items": [asdict(item) for item in page.items],
                        "next_cursor": page.next_cursor,
                    }
                )
                return
            if parsed.path == "/api/candidate":
                query = parse_qs(parsed.query)
                text = query.get("text", [""])[0]
                if not text:
                    raise ValueError("text is required")
                self._json(self.server.review().detail(text))
                return
            if parsed.path == "/api/rule-families":
                self._json({"items": self.server.review().rule_families()})
                return
            if parsed.path == "/api/rule-family":
                query = parse_qs(parsed.query)
                family_id = query.get("family_id", [""])[0]
                if not family_id:
                    raise ValueError("family_id is required")
                self._json(self.server.review().rule_family_detail(family_id))
                return
            if parsed.path == "/api/affix-analysis":
                query = parse_qs(parsed.query)
                only_unencoded = query.get("only_unencoded", ["true"])[0].lower()
                if only_unencoded not in {"true", "false"}:
                    raise ValueError("only_unencoded must be true or false")
                self._json(
                    self.server.review().analyze_affix_family(
                        direction=query.get("direction", [""])[0],
                        root_anchor=query.get("root_anchor", [""])[0],
                        refinements=query.get("refinement", []),
                        intended_class=query.get(
                            "intended_class", ["productive_phrase"]
                        )[0],
                        minimum_frequency=int(
                            query.get("minimum_frequency", ["0"])[0]
                        ),
                        only_unencoded=only_unencoded == "true",
                        limit=int(query.get("limit", ["200"])[0]),
                    )
                )
                return
            if parsed.path == "/api/construction-analysis":
                query = parse_qs(parsed.query)
                only_unencoded = query.get("only_unencoded", ["true"])[0].lower()
                if only_unencoded not in {"true", "false"}:
                    raise ValueError("only_unencoded must be true or false")
                self._json(
                    self.server.review().analyze_construction_family(
                        template=query.get("template", [""])[0],
                        intended_class=query.get(
                            "intended_class", ["productive_phrase"]
                        )[0],
                        minimum_frequency=int(
                            query.get("minimum_frequency", ["0"])[0]
                        ),
                        only_unencoded=only_unencoded == "true",
                        limit=int(query.get("limit", ["200"])[0]),
                    )
                )
                return
            if parsed.path == "/api/automatic-screening":
                query = parse_qs(parsed.query)
                self._json(
                    self.server.review().automatic_screening(
                        minimum_frequency=int(
                            query.get("minimum_frequency", ["0"])[0]
                        ),
                        limit=int(query.get("limit", ["200"])[0]),
                    )
                )
                return
            self._error(HTTPStatus.NOT_FOUND, "not found")
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "candidate not found")
        except (ValueError, FileNotFoundError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in {
            "/api/decision",
            "/api/rule-family",
            "/api/automatic-screening/apply",
            "/api/tail-classifications",
            "/api/tail-classifications/apply",
        }:
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        if self.headers.get("X-Yime-Review") != "1":
            self._error(HTTPStatus.FORBIDDEN, "missing local review request marker")
            return
        if "application/json" not in self.headers.get("Content-Type", ""):
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "JSON body required")
            return
        origin = self.headers.get("Origin")
        if origin and origin != "null" and not (
            origin.startswith("http://127.0.0.1:")
            or origin.startswith("http://localhost:")
        ):
            self._error(HTTPStatus.FORBIDDEN, "cross-origin review write rejected")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 64_000:
                raise ValueError("invalid request body length")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            if parsed.path == "/api/decision":
                result = self.server.review().decide(
                    text=str(payload.get("text", "")),
                    action=str(payload.get("action", "")),
                    candidate_class=str(payload.get("candidate_class", "unknown")),
                    integration_policy=payload.get("integration_policy"),
                    rationale=str(payload.get("rationale", "")),
                    assessor=str(payload.get("assessor", "")),
                    review_standard=str(payload.get("review_standard", "standard")),
                    custom_criteria=payload.get("custom_criteria"),
                )
            elif parsed.path == "/api/rule-family":
                positive_examples = payload.get("positive_examples", [])
                negative_examples = payload.get("negative_examples", [])
                if not isinstance(positive_examples, list) or not isinstance(
                    negative_examples, list
                ):
                    raise ValueError("rule family examples must be JSON arrays")
                result = self.server.review().register_rule_family(
                    family_id=str(payload.get("family_id", "")),
                    title=str(payload.get("title", "")),
                    pattern_description=str(
                        payload.get("pattern_description", "")
                    ),
                    applicability_notes=str(payload.get("applicability_notes", "")),
                    representative=str(payload.get("representative", "")),
                    positive_examples=positive_examples,
                    negative_examples=negative_examples,
                    candidate_class=str(
                        payload.get("candidate_class", "productive_phrase")
                    ),
                    rationale=str(payload.get("rationale", "")),
                    assessor=str(payload.get("assessor", "")),
                    review_standard=str(payload.get("review_standard", "standard")),
                    custom_criteria=payload.get("custom_criteria"),
                    discovery_model=payload.get("discovery_model"),
                )
            elif parsed.path == "/api/automatic-screening/apply":
                result = self.server.review().apply_automatic_screening(
                    assessor=str(payload.get("assessor", "")),
                    minimum_frequency=int(payload.get("minimum_frequency", 0)),
                    maximum_items=int(payload.get("maximum_items", 1000)),
                )
            elif parsed.path == "/api/tail-classifications":
                classifications = payload.get("classifications", [])
                if not isinstance(classifications, list):
                    raise ValueError("classifications must be a JSON array")
                result = self.server.review().save_tail_classifications(
                    direction=str(payload.get("direction", "")),
                    root_anchor=str(payload.get("root_anchor", "")),
                    classifications=classifications,
                    assessor=str(payload.get("assessor", "")),
                )
            else:
                result = self.server.review().apply_tail_classifications(
                    direction=str(payload.get("direction", "")),
                    root_anchor=str(payload.get("root_anchor", "")),
                    assessor=str(payload.get("assessor", "")),
                    maximum_items=int(payload.get("maximum_items", 1000)),
                )
            self._json(result)
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "candidate not found")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_OPTIONS(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if (
            parsed.path
            not in {
                "/api/decision",
                "/api/rule-family",
                "/api/automatic-screening/apply",
                "/api/tail-classifications",
                "/api/tail-classifications/apply",
            }
            or self.headers.get("Origin") != "null"
        ):
            self._error(HTTPStatus.FORBIDDEN, "cross-origin request rejected")
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Yime-Review",
        )
        self.send_header("Access-Control-Max-Age", "600")
        if self.headers.get("Access-Control-Request-Private-Network") == "true":
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Vary", "Origin")
        self.end_headers()

def create_server(
    *,
    host: str,
    port: int,
    input_model_database: Path,
    source_database: Path,
) -> ReviewHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("the review server may only bind to the local machine")
    return ReviewHTTPServer(
        (host, port),
        input_model_database=input_model_database,
        source_database=source_database,
    )
