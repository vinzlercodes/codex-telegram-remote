from codex_remote.formatting import rate_limits_summary, thread_transcript


def test_thread_transcript_renders_key_events():
    text = thread_transcript(
        {
            "id": "t1",
            "name": "Demo",
            "cwd": "/tmp/demo",
            "turns": [
                {
                    "status": "completed",
                    "items": [
                        {
                            "type": "userMessage",
                            "content": [{"type": "text", "text": "run tests"}],
                        },
                        {"type": "agentMessage", "text": "Tests passed."},
                        {
                            "type": "commandExecution",
                            "status": "completed",
                            "command": "pytest -q",
                            "exitCode": 0,
                            "aggregatedOutput": "1 passed",
                        },
                        {
                            "type": "fileChange",
                            "status": "completed",
                            "changes": [{"path": "app.py", "kind": "update", "diff": "..."}],
                        },
                    ],
                }
            ],
        }
    )

    assert "Thread: Demo" in text
    assert "User: run tests" in text
    assert "Codex: Tests passed." in text
    assert "Command (completed, exit 0)" in text
    assert "File changes (completed): app.py" in text


def test_rate_limits_summary_labels_daily_weekly():
    text = rate_limits_summary(
        {
            "rateLimitsByLimitId": {
                "codex": {
                    "limitName": "Codex",
                    "planType": "pro",
                    "primary": {"usedPercent": 12, "windowDurationMins": 1440},
                    "secondary": {"usedPercent": 34, "windowDurationMins": 10080},
                    "credits": {"hasCredits": True, "unlimited": False, "balance": "10.50"},
                }
            }
        }
    )

    assert "Codex  plan: pro" in text
    assert "credits: 10.50" in text
    assert "primary (daily): 12% used" in text
    assert "secondary (weekly): 34% used" in text
