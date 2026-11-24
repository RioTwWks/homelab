from app.main import _strip_urls


def test_strip_urls_removes_links() -> None:
    assert _strip_urls("Новость: https://example.com/a и ещё текст") == "Новость: и ещё текст"


def test_strip_urls_collapses_whitespace() -> None:
    assert _strip_urls("строка   с   пробелами\nи табом\tтут") == "строка с пробелами\nи табом тут"


def test_strip_urls_keeps_letter_t() -> None:
    assert _strip_urls("mqtt и http://a.b не должны пострадать: mqtt") == "mqtt и не должны пострадать: mqtt"
