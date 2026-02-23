import pytest
import json
from pathlib import Path
from auth import save_cookies, load_cookies, cookies_as_dict, cookies_path

def test_save_cookies_writes_json(tmp_path):
    path = tmp_path / "cookies.json"
    cookies = [{"name": "X-Auth-Request-Email", "value": "test@cisco.com", "domain": ".cisco.com"}]
    save_cookies(cookies, path=path)
    saved = json.loads(path.read_text())
    assert saved == cookies

def test_load_cookies_returns_list(tmp_path):
    path = tmp_path / "cookies.json"
    cookies = [{"name": "session", "value": "abc123", "domain": ".cisco.com"}]
    path.write_text(json.dumps(cookies))
    result = load_cookies(path=path)
    assert result == cookies

def test_load_cookies_missing_file_returns_none(tmp_path):
    path = tmp_path / "nonexistent.json"
    result = load_cookies(path=path)
    assert result is None

def test_cookies_as_dict_extracts_name_value():
    cookies = [
        {"name": "session", "value": "abc123", "domain": ".cisco.com", "httpOnly": True},
        {"name": "X-Auth-Request-Email", "value": "user@cisco.com", "domain": ".cisco.com"}
    ]
    result = cookies_as_dict(cookies)
    assert result == {"session": "abc123", "X-Auth-Request-Email": "user@cisco.com"}

def test_cookies_path_is_in_home_dir():
    assert cookies_path.parent == Path.home()
    assert cookies_path.name == ".cx-assistant-cookies.json"
