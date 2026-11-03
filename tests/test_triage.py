from portpilot import triage


def test_hex_dumps_are_decoded_back_into_text():
    log = ["test_basic.c:87: File should be empty: pack.err",
           "0000 62 73 64 74 61 72 3a 20 66 69 6c 65 3a 20 43 61 bsdtar: file: Ca",
           "0010 6e 6e 6f 74 20 73 74 61 74 0a                   nnot stat.",
           "test_basic.c:43: File should exist: file"]
    assert triage.readable_log(log) == [log[0], "  [dump] bsdtar: file: Cannot stat", log[3]]


def test_failures_text_keeps_the_start_of_long_logs():
    r = {"test": "t", "verdict": "FAIL", "rc": 1, "log": [f"line {k}" for k in range(40)]}
    text = triage.failures_text([r])
    assert "line 0" in text and "line 13" in text and "line 14" not in text and "line 39" in text
