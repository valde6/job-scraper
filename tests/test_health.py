"""Sundhedstjekket skal opdage ødelagte kilder uden at råbe op over enkeltstående fejl."""
from scraper.health import classify, evaluate, ALERT_AFTER
from scraper.run import suspicious


def hist(*listed):
    return [{"name": "X", "ok": True, "listed": n, "problem": None} for n in listed]


def test_ok_source():
    assert classify({"ok": True, "listed": 40}, hist(40, 42, 39)) is None


def test_error_and_empty_and_drop():
    assert classify({"ok": False, "error": "HTTPError"}, []) == "fejl"
    assert classify({"ok": True, "listed": 0}, hist(40, 41)) == "tom"
    assert classify({"ok": True, "listed": 5}, hist(40, 41, 39)) == "fald"
    assert classify({"ok": None}, []) is None


def test_alert_only_after_streak():
    status = [{"company": "X", "source": "workday", "ok": False, "error": "boom"}]
    rows_one_fail = [{"active": 100, "sources": [{"name": "X", "ok": True, "listed": 40, "problem": None}]}]
    assert evaluate(status, rows_one_fail, 100)["alerts"] == []          # første fejl: ingen alarm
    rows_prev_fail = rows_one_fail + [{"active": 100, "sources": [{"name": "X", "ok": False, "listed": None, "problem": "fejl"}]}]
    res = evaluate(status, rows_prev_fail, 100)
    assert ALERT_AFTER == 2 and len(res["alerts"]) == 1 and "X" in res["alerts"][0]


def test_total_collapse_alert():
    rows = [{"active": 100, "sources": []} for _ in range(5)]
    assert any("Samlet" in a for a in evaluate([], rows, 30)["alerts"])


def test_suspicious_guard():
    assert suspicious(0, 40)            # pludselig tom
    assert suspicious(5, 40)            # stort fald
    assert not suspicious(35, 40)
    assert not suspicious(0, None)      # ny kilde uden historik
    assert not suspicious(2, 4)         # små kilder svinger naturligt
