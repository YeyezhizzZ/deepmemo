from __future__ import annotations

import sys

if __name__ == "__main__" and sys.path:
    # Direct path execution can put src/ai before stdlib and shadow types.py.
    _script_dir = sys.path[0].replace("\\", "/")
    if _script_dir == "src/ai" or _script_dir.endswith("/src/ai"):
        sys.path.pop(0)

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


BASE_URL = "https://aihot.virxact.com"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

ITEM_FIELDS = [
    "id",
    "title",
    "title_en",
    "url",
    "source",
    "publishedAt",
    "summary",
    "category",
]

DAILY_FIELDS = [
    "date",
    "generatedAt",
    "windowStart",
    "windowEnd",
    "lead",
    "sections",
    "flashes",
]

CATEGORIES = {
    "ai-models",
    "ai-products",
    "industry",
    "paper",
    "tip",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


DATA_DIR = _repo_root() / "data" / "ai_hot"


class AIHotError(RuntimeError):
    pass


class AIHotNotFoundError(AIHotError):
    pass


@dataclass(frozen=True)
class FetchResult:
    data: Any
    status: int
    etag: str | None = None


@dataclass(frozen=True)
class WriteResult:
    path: Path | None
    count: int


@dataclass(frozen=True)
class DailySyncResult:
    date: str
    json_path: Path
    markdown_path: Path
    deleted_json: bool


class AIHotClient:
    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        user_agent: str = UA,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout

    def get(self, path: str, params: dict[str, Any] | None = None) -> FetchResult:
        query = _build_query(params or {})
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                data = json.loads(raw.decode("utf-8")) if raw else None
                return FetchResult(
                    data=data,
                    status=response.status,
                    etag=response.headers.get("ETag"),
                )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404:
                raise AIHotNotFoundError(f"AI HOT resource not found: {path}") from exc
            raise AIHotError(
                f"AI HOT request failed: HTTP {exc.code} {exc.reason}: {body[:300]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise AIHotError(f"AI HOT request failed: {exc.reason}") from exc


class AIHotAgent:
    def __init__(
        self,
        *,
        client: AIHotClient | None = None,
        data_dir: Path | str = DATA_DIR,
    ) -> None:
        self.client = client or AIHotClient()
        self.data_dir = Path(data_dir)
        self.daily_dir = self.data_dir / "daily"
        self.items_dir = self.data_dir / "items"
        self.index_dir = self.data_dir / "index"

    def fetch_daily(
        self,
        target_date: str | date | None = None,
        *,
        write: bool = True,
    ) -> dict[str, Any]:
        date_value = _format_date_arg(target_date)
        path = f"/api/public/daily/{date_value}" if date_value else "/api/public/daily"

        result = self.client.get(path)
        daily = _normalize_daily(result.data)

        if write:
            json_path = self._daily_json_path(daily, fallback_date=date_value)
            _write_json(json_path, daily)

        return daily

    def render_daily_markdown(
        self,
        json_path: Path | str,
        *,
        output_path: Path | str | None = None,
    ) -> Path:
        path = Path(json_path)
        daily = _read_json(path)
        normalized = _normalize_daily(daily)
        markdown_path = (
            Path(output_path)
            if output_path
            else self._daily_markdown_path(normalized)
        )
        _write_text(markdown_path, _render_daily_markdown(normalized))
        return markdown_path

    def fetch_dailies(
        self,
        *,
        take: int = 30,
        write: bool = True,
    ) -> dict[str, Any]:
        take = _validate_take(take, maximum=180)
        result = self.client.get("/api/public/dailies", {"take": take})
        data = result.data if isinstance(result.data, dict) else {"dailies": result.data}

        if write:
            _write_json(self.index_dir / "dailies.json", data)

        return data

    def fetch_items(
        self,
        since: str | datetime | date | None = None,
        category: str | None = None,
        query: str | None = None,
        *,
        write: bool = True,
        output_date: str | date | None = None,
    ) -> list[dict[str, Any]]:
        items = self.fetch_all_items(since=since, category=category, query=query)

        if write:
            path = self._items_json_path(output_date)
            self._merge_items_file(
                path,
                items,
                metadata={
                    "fetchedAt": _utc_now_iso(),
                    "mode": "selected",
                    "since": _format_since_arg(since),
                    "category": category,
                    "q": query,
                },
            )

        return items

    def fetch_all_items(
        self,
        since: str | datetime | date | None = None,
        category: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        _validate_category(category)

        items: list[dict[str, Any]] = []
        cursor: str | None = None
        since_value = _format_since_arg(since)

        while True:
            params: dict[str, Any] = {
                "mode": "selected",
                "take": 100,
            }
            if since_value:
                params["since"] = since_value
            if category:
                params["category"] = category
            if query:
                params["q"] = query
            if cursor:
                params["cursor"] = cursor

            result = self.client.get("/api/public/items", params)
            data = result.data
            if not isinstance(data, dict):
                raise AIHotError("AI HOT items response is not a JSON object")

            page_items = data.get("items") or []
            if not isinstance(page_items, list):
                raise AIHotError("AI HOT items response has invalid items field")
            items.extend(
                _normalize_item(item)
                for item in page_items
                if isinstance(item, dict)
            )

            if not data.get("hasNext"):
                break
            cursor = data.get("nextCursor")
            if not cursor:
                break

        return _sort_items(items)

    def sync_daily(
        self,
        *,
        target_date: str | date | None = None,
        delete_json: bool = True,
    ) -> DailySyncResult:
        daily = self.fetch_daily(target_date, write=True)
        json_path = self._daily_json_path(daily, fallback_date=_format_date_arg(target_date))
        markdown_path = self.render_daily_markdown(json_path)

        deleted_json = False
        if delete_json and json_path.exists():
            json_path.unlink()
            deleted_json = True

        return DailySyncResult(
            date=str(daily.get("date") or _format_date_arg(target_date) or date.today().isoformat()),
            json_path=json_path,
            markdown_path=markdown_path,
            deleted_json=deleted_json,
        )

    def latest_item_since(self) -> str | None:
        latest = self._latest_local_item_time()
        if not latest:
            return None
        return _format_since_arg(latest - timedelta(seconds=1))

    def _daily_json_path(self, daily: dict[str, Any], fallback_date: str | None = None) -> Path:
        date_value = daily.get("date") or fallback_date or date.today().isoformat()
        return self.daily_dir / f"{date_value}.json"

    def _daily_markdown_path(self, daily: dict[str, Any], fallback_date: str | None = None) -> Path:
        date_value = daily.get("date") or fallback_date or date.today().isoformat()
        return self.daily_dir / f"{_mmd_from_iso_date(date_value)}.md"

    def _items_json_path(self, output_date: str | date | None = None) -> Path:
        date_value = _format_date_arg(output_date) or date.today().isoformat()
        return self.items_dir / f"{date_value}.json"

    def _merge_items_file(
        self,
        path: Path,
        items: list[dict[str, Any]],
        *,
        metadata: dict[str, Any],
    ) -> WriteResult:
        existing = _read_items_payload(path)
        by_id: dict[str, dict[str, Any]] = {}
        anonymous_index = 0

        for item in existing + items:
            item_id = item.get("id")
            if not item_id:
                anonymous_index += 1
                item_id = f"anonymous-{anonymous_index}-{item.get('url') or item.get('title')}"
            by_id[str(item_id)] = item

        merged_items = _sort_items(list(by_id.values()))
        payload = {
            **metadata,
            "count": len(merged_items),
            "items": merged_items,
        }
        _write_json(path, payload)
        return WriteResult(path=path, count=len(merged_items))

    def _latest_local_item_time(self) -> datetime | None:
        latest: datetime | None = None
        for path in sorted(self.items_dir.glob("*.json")):
            for item in _read_items_payload(path):
                published_at = _parse_datetime(item.get("publishedAt"))
                if published_at and (latest is None or published_at > latest):
                    latest = published_at
        return latest


def fetch_daily(
    target_date: str | date | None = None,
    *,
    write: bool = True,
) -> dict[str, Any]:
    return AIHotAgent().fetch_daily(target_date, write=write)


def render_daily_markdown(json_path: Path | str) -> Path:
    return AIHotAgent().render_daily_markdown(json_path)


def fetch_items(
    since: str | datetime | date | None = None,
    category: str | None = None,
    *,
    write: bool = True,
) -> list[dict[str, Any]]:
    return AIHotAgent().fetch_items(since=since, category=category, write=write)


def fetch_all_items(
    since: str | datetime | date | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    return AIHotAgent().fetch_all_items(since=since, category=category)


def sync() -> DailySyncResult:
    return AIHotAgent().sync_daily()


def _build_query(params: dict[str, Any]) -> str:
    clean = {key: value for key, value in params.items() if value is not None and value != ""}
    return urllib.parse.urlencode(clean)


def _validate_take(take: int, *, maximum: int) -> int:
    if take < 1:
        raise ValueError("take must be >= 1")
    return min(take, maximum)


def _validate_category(category: str | None) -> None:
    if category and category not in CATEGORIES:
        allowed = ", ".join(sorted(CATEGORIES))
        raise ValueError(f"Invalid category {category!r}; expected one of: {allowed}")


def _format_date_arg(value: str | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _format_since_arg(value: str | datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = _ensure_utc(value)
        return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    if isinstance(value, date):
        dt = datetime.combine(value, time.min, tzinfo=timezone.utc)
        return dt.isoformat(timespec="seconds").replace("+00:00", "Z")

    value = value.strip()
    if not value:
        return None
    if "T" not in value and len(value) == 10:
        return f"{value}T00:00:00Z"
    if value.endswith("+00:00"):
        return value[:-6] + "Z"
    return value


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _ensure_utc(parsed)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {field: item.get(field) for field in ITEM_FIELDS}


def _normalize_daily(daily: Any) -> dict[str, Any]:
    if not isinstance(daily, dict):
        raise AIHotError("AI HOT daily response is not a JSON object")
    return {field: daily.get(field) for field in DAILY_FIELDS}


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: item.get("publishedAt") or "",
        reverse=True,
    )


def _read_items_payload(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items") or []
    else:
        items = []

    return [_normalize_item(item) for item in items if isinstance(item, dict)]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AIHotError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AIHotError(f"Invalid JSON file: {path}") from exc
    except OSError as exc:
        raise AIHotError(f"Failed to read JSON file: {path}: {exc}") from exc


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def _mmd_from_iso_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    # The daily covers the previous day, so subtract one to get the content date
    prev = parsed - timedelta(days=1)
    return f"{prev.month:02d}{prev.day:02d}"


def _render_daily_markdown(daily: dict[str, Any]) -> str:
    date_value = daily.get("date") or date.today().isoformat()
    lines: list[str] = [f"# AI HOT {date_value}", ""]

    generated_at = daily.get("generatedAt")
    window_start = daily.get("windowStart")
    window_end = daily.get("windowEnd")
    if generated_at:
        lines.extend([f"Generated at: {generated_at}", ""])
    if window_start or window_end:
        lines.extend([f"Window: {window_start or '-'} -> {window_end or '-'}", ""])

    lead = daily.get("lead")
    if isinstance(lead, dict):
        title = lead.get("title")
        paragraph = lead.get("leadParagraph")
        if title or paragraph:
            lines.extend(["## Lead", ""])
            if title:
                lines.extend([f"### {title}", ""])
            if paragraph:
                lines.extend([str(paragraph), ""])

    sections = daily.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            label = section.get("label") or "Section"
            lines.extend([f"## {label}", ""])
            lines.extend(_render_daily_items(section.get("items")))

    flashes = daily.get("flashes")
    if isinstance(flashes, list) and flashes:
        lines.extend(["## Flashes", ""])
        lines.extend(_render_daily_items(flashes))

    return "\n".join(lines).rstrip() + "\n"


def _render_daily_items(items: Any) -> list[str]:
    if not isinstance(items, list) or not items:
        return ["No items.", ""]

    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("title_en") or "Untitled"
        url = item.get("url") or item.get("sourceUrl")
        source = item.get("source") or item.get("sourceName")
        published_at = item.get("publishedAt")
        summary = item.get("summary")
        category = item.get("category")

        if url:
            lines.append(f"- [{title}]({url})")
        else:
            lines.append(f"- {title}")

        details = []
        if source:
            details.append(f"source={source}")
        if published_at:
            details.append(f"publishedAt={published_at}")
        if category:
            details.append(f"category={category}")
        if details:
            lines.append(f"  - {'; '.join(details)}")
        if summary:
            lines.append(f"  - {summary}")
    lines.append("")
    return lines


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _path_for_print(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(_repo_root()))
    except ValueError:
        return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch AI HOT public data into data/ai_hot.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily_parser = subparsers.add_parser("daily", help="Fetch latest or specified daily JSON.")
    daily_parser.add_argument("--date", help="Daily date in YYYY-MM-DD format.")
    daily_parser.add_argument("--dry-run", action="store_true", help="Fetch but do not write files.")

    render_parser = subparsers.add_parser("render", help="Render local daily JSON into MMD.md.")
    render_parser.add_argument("json_path", help="Path to daily JSON.")
    render_parser.add_argument("--delete-json", action="store_true", help="Delete JSON after successful render.")

    items_parser = subparsers.add_parser("items", help="Fetch selected items.")
    items_parser.add_argument("--since", help="ISO datetime or YYYY-MM-DD.")
    items_parser.add_argument("--category", choices=sorted(CATEGORIES))
    items_parser.add_argument("--q", help="Keyword search.")
    items_parser.add_argument("--dry-run", action="store_true", help="Fetch but do not write files.")

    dailies_parser = subparsers.add_parser("dailies", help="Fetch daily archive index.")
    dailies_parser.add_argument("--take", type=int, default=30, help="Number of archive records, max 180.")
    dailies_parser.add_argument("--dry-run", action="store_true", help="Fetch but do not write files.")

    sync_parser = subparsers.add_parser("sync", help="Fetch daily JSON, render MMD.md, then delete JSON.")
    sync_parser.add_argument("--date", help="Daily date in YYYY-MM-DD format.")
    sync_parser.add_argument("--keep-json", action="store_true", help="Keep JSON after successful render.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    agent = AIHotAgent()

    try:
        if args.command == "daily":
            daily = agent.fetch_daily(
                args.date,
                write=not args.dry_run,
            )
            json_path = agent._daily_json_path(daily, fallback_date=args.date)
            _print_json(
                {
                    "date": daily.get("date"),
                    "jsonPath": None if args.dry_run else _path_for_print(json_path),
                }
            )
            return 0

        if args.command == "render":
            json_path = Path(args.json_path)
            markdown_path = agent.render_daily_markdown(json_path)
            deleted_json = False
            if args.delete_json and json_path.exists():
                json_path.unlink()
                deleted_json = True
            _print_json(
                {
                    "markdownPath": _path_for_print(markdown_path),
                    "jsonPath": _path_for_print(json_path),
                    "deletedJson": deleted_json,
                }
            )
            return 0

        if args.command == "items":
            items = agent.fetch_items(
                since=args.since,
                category=args.category,
                query=args.q,
                write=not args.dry_run,
            )
            _print_json({"count": len(items)})
            return 0

        if args.command == "dailies":
            data = agent.fetch_dailies(take=args.take, write=not args.dry_run)
            count = (
                len(data.get("dailies") or data.get("items") or data)
                if isinstance(data, dict)
                else 0
            )
            _print_json({"count": count})
            return 0

        if args.command == "sync":
            result = agent.sync_daily(
                target_date=args.date,
                delete_json=not args.keep_json,
            )
            _print_json(
                {
                    "date": result.date,
                    "jsonPath": _path_for_print(result.json_path),
                    "markdownPath": _path_for_print(result.markdown_path),
                    "deletedJson": result.deleted_json,
                    }
                )
            return 0

    except (AIHotError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
