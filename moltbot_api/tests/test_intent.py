from app.main import detect_intent_ru, should_use_chat_model


def test_detect_intent_weather() -> None:
    assert detect_intent_ru("Какая погода в Москве?") == "weather"


def test_detect_intent_news() -> None:
    assert detect_intent_ru("Дай новости России") == "news"


def test_detect_intent_timer() -> None:
    assert detect_intent_ru("Поставь таймер на 5 минут") == "timer"


def test_should_use_chat_model_for_detailed_request() -> None:
    assert should_use_chat_model("Объясни подробно, как работает MQTT", "chat") is True


def test_should_not_use_chat_model_for_tool_intents() -> None:
    assert should_use_chat_model("Какая погода завтра?", "weather") is False
