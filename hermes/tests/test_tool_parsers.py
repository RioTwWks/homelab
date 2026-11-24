import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "moltbot_api"))
sys.path.insert(0, str(ROOT / "hermes" / "tools"))
os.environ.setdefault("HOMELAB_ROOT", str(ROOT))

def test_media():
    from app.tools.media_control import parse_media_command
    assert parse_media_command("пауза")["action"] == "pause"

def test_ha():
    from app.tools.home_assistant import parse_ha_command
    assert parse_ha_command("включи свет в гостиная")["action"] == "turn_on"

def test_timer():
    from app.tools.timers import parse_timer_request
    assert parse_timer_request("поставь таймер на 5 минут")["duration_seconds"] == 300

def test_runtime():
    from _runtime import init_runtime, repo_root
    init_runtime()
    assert (repo_root() / "moltbot_api").is_dir()

def test_weather_city():
    from app.tools.weather import _extract_city_ru
    assert _extract_city_ru("погода в новосибирске") == "новосибирске"
    assert _extract_city_ru("какая погода завтра в москве") == "москве"
    assert _extract_city_ru("погода в москве завтра") == "москве"
    assert _extract_city_ru("погода в сочи на неделю") == "сочи"
    assert _extract_city_ru("какая погода сейчас") is None

def test_weather_time_request():
    from app.tools.weather import _parse_time_request
    assert _parse_time_request("какая погода будет через 3 часа") == ("hourly", 3)
    assert _parse_time_request("погода через час") == ("hourly", 1)
    assert _parse_time_request("погода завтра") == ("daily", 1)
    assert _parse_time_request("погода послезавтра") == ("daily", 2)
    assert _parse_time_request("прогноз на неделю") == ("weekly", 7)
    assert _parse_time_request("погода сейчас") == ("current", 0)

def test_weather_district():
    from app.tools.weather import _extract_district_ru
    assert _extract_district_ru("погода в районе калининский") == "калининский"
    assert _extract_district_ru("какая погода") is None

def test_news_clean_summary():
    from app.tools.news import _clean_summary
    assert _clean_summary("<b>Привет</b>   мир") == "Привет мир"
    assert _clean_summary("") == ""
    long_text = "а" * 500
    cleaned = _clean_summary(long_text)
    assert cleaned.endswith("…") and len(cleaned) <= 180

def test_web_search_query_normalization():
    from app.tools.web_search import _normalize_query_for_cache
    assert _normalize_query_for_cache("  Зоопарке  Новосибирска?  ") == "зоопарке новосибирск"
    assert _normalize_query_for_cache("Погода в Москве!") == "погода в москве"

def test_web_search_fact_context():
    from app.tools.web_search import _format_fact_context
    ctx = _format_fact_context(provider="ddg", query="тест", instant_answer="42", results=[], max_results=3)
    assert "provider=ddg" in ctx and "InstantAnswer: 42" in ctx
