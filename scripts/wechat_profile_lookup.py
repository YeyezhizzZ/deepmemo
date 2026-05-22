#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import types
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = REPO_ROOT / "reference" / "WechatSogou"
PROXY_ENV_KEYS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")


def _normalize_name(text: str) -> str:
    value = " ".join(str(text or "").split())
    value = value.replace(" - 微信公众平台", "")
    value = value.replace("- 微信公众平台", "")
    value = value.replace("微信公众号", "")
    value = value.replace("微信公众平台", "")
    value = value.replace("（微信公众平台）", "")
    value = value.replace("(微信公众平台)", "")
    return value.strip().lower()


def _ensure_werkzeug_contrib_cache_shim() -> None:
    try:
        from werkzeug.contrib.cache import FileSystemCache  # type: ignore  # noqa: F401
        return
    except Exception:
        pass

    try:
        import werkzeug as real_werkzeug  # type: ignore
    except Exception:
        real_werkzeug = types.ModuleType("werkzeug")
        sys.modules["werkzeug"] = real_werkzeug

    contrib_module = types.ModuleType("werkzeug.contrib")
    cache_module = types.ModuleType("werkzeug.contrib.cache")

    class FileSystemCache:  # type: ignore[too-many-ancestors]
        _store: dict[str, tuple[Any, float | None]] = {}

        def __init__(self, cache_dir: str = "/tmp/wechatsogou-cache", default_timeout: int = 300) -> None:
            self.cache_dir = cache_dir
            self.default_timeout = default_timeout

        def get(self, key: str) -> Any | None:
            item = self._store.get(key)
            if not item:
                return None
            value, expires_at = item
            if expires_at is not None and expires_at < time.time():
                self._store.pop(key, None)
                return None
            return value

        def set(self, key: str, value: Any, timeout: int | None = None) -> bool:
            ttl = self.default_timeout if timeout is None else timeout
            expires_at = None if ttl is None else time.time() + ttl
            self._store[key] = (value, expires_at)
            return True

    cache_module.FileSystemCache = FileSystemCache
    contrib_module.cache = cache_module
    setattr(real_werkzeug, "contrib", contrib_module)
    sys.modules["werkzeug"] = real_werkzeug
    sys.modules["werkzeug.contrib"] = contrib_module
    sys.modules["werkzeug.contrib.cache"] = cache_module


def _set_proxy_mode(use_env_proxy: bool) -> None:
    if use_env_proxy:
        return
    for key in PROXY_ENV_KEYS:
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


def _load_reference_api(*, use_env_proxy: bool = False):
    _set_proxy_mode(use_env_proxy)
    _ensure_werkzeug_contrib_cache_shim()
    if str(REFERENCE_ROOT) not in sys.path:
        sys.path.insert(0, str(REFERENCE_ROOT))
    import wechatsogou  # type: ignore

    return wechatsogou.WechatSogouAPI(captcha_break_time=3)


def _normalize_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _pick_best_candidate(keyword: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None

    normalized_keyword = _normalize_name(keyword)
    exact_name_matches = [
        item for item in candidates if _normalize_name(str(item.get("wechat_name", ""))) == normalized_keyword
    ]
    if exact_name_matches:
        return exact_name_matches[0]

    exact_id_matches = [
        item for item in candidates if _normalize_name(str(item.get("wechat_id", ""))) == normalized_keyword
    ]
    if exact_id_matches:
        return exact_id_matches[0]

    with_profile = [item for item in candidates if str(item.get("profile_url", "")).strip()]
    if with_profile:
        return with_profile[0]

    return candidates[0]


def lookup_profile(
    keyword: str,
    *,
    page: int = 1,
    use_env_proxy: bool = False,
    debug_dir: Path | None = None,
) -> dict[str, Any]:
    api = _load_reference_api(use_env_proxy=use_env_proxy)
    candidates = []
    debug_info: dict[str, Any] = {}

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)

    try:
        candidates = list(api.search_gzh(keyword, page=page, decode_url=True))
        debug_info["search_gzh"] = {"ok": True, "count": len(candidates)}
    except Exception as exc:
        debug_info["search_gzh"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        candidates = []

    if not candidates:
        try:
            maybe = api.get_gzh_info(keyword, decode_url=True)
            debug_info["get_gzh_info"] = {"ok": True, "found": bool(maybe)}
            candidates = [maybe] if maybe else []
        except Exception as exc:
            debug_info["get_gzh_info"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            candidates = []

    best = _pick_best_candidate(keyword, candidates)
    result = {
        "keyword": keyword,
        "candidate_count": len(candidates),
        "best": best,
        "candidates": candidates,
        "debug": debug_info,
    }
    if debug_dir is not None:
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        (debug_dir / "result.json").write_text(payload, encoding="utf-8")
        (debug_dir / "keyword.txt").write_text(_normalize_search_text(keyword), encoding="utf-8")
    return {
        "keyword": keyword,
        "candidate_count": len(candidates),
        "best": best,
        "candidates": candidates,
        "debug": debug_info,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lookup a WeChat public account profile_url via WechatSogou.")
    parser.add_argument("keyword", help="公众号名或微信号")
    parser.add_argument("--page", type=int, default=1, help="Sogou search page, default: 1")
    parser.add_argument(
        "--use-env-proxy",
        action="store_true",
        help="Respect http_proxy/https_proxy environment variables instead of forcing direct access",
    )
    parser.add_argument(
        "--debug-dir",
        type=Path,
        help="Write debug JSON and small helper files to this directory",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = lookup_profile(
        args.keyword,
        page=args.page,
        use_env_proxy=args.use_env_proxy,
        debug_dir=args.debug_dir,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    best = result.get("best") or {}
    if not best:
        print(f"未找到公众号：{args.keyword}")
        return 1

    print(f"keyword: {args.keyword}")
    print(f"candidate_count: {result['candidate_count']}")
    print(f"wechat_name: {best.get('wechat_name', '')}")
    print(f"wechat_id: {best.get('wechat_id', '')}")
    print(f"profile_url: {best.get('profile_url', '')}")
    print(f"authentication: {best.get('authentication', '')}")
    print(f"introduction: {best.get('introduction', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
