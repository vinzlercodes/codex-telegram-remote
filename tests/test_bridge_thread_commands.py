from codex_remote.bridge import CodexRemoteBridge


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def request(self, method, params=None, timeout=0):
        self.requests.append((method, params or {}))
        return self.responses.pop(0)

    def request_null(self, method, timeout=0):
        self.requests.append((method, None))
        return self.responses.pop(0)


def make_bridge(tmp_path, monkeypatch, responses):
    monkeypatch.setattr("codex_remote.bridge.STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr("codex_remote.bridge.DEFAULT_SOCKET", tmp_path / "codex.sock")
    bridge = CodexRemoteBridge()
    bridge._client = FakeClient(responses)
    return bridge


def test_thread_command_reads_full_thread(tmp_path, monkeypatch):
    bridge = make_bridge(
        tmp_path,
        monkeypatch,
        [
            {
                "thread": {
                    "id": "abcdefabcdefabcdefabcd",
                    "name": "Demo",
                    "cwd": "/repo",
                    "turns": [
                        {
                            "status": "completed",
                            "items": [{"type": "agentMessage", "text": "Done"}],
                        }
                    ],
                }
            }
        ],
    )

    out = bridge._cmd_thread("abcdefabcdefabcdefabcd")

    assert "Thread: Demo" in out
    assert "Codex: Done" in out
    assert bridge._client.requests[0] == (
        "thread/read",
        {"threadId": "abcdefabcdefabcdefabcd", "includeTurns": True},
    )


def test_workspaces_command_groups_by_cwd(tmp_path, monkeypatch):
    bridge = make_bridge(
        tmp_path,
        monkeypatch,
        [
            {
                "data": [
                    {"id": "t1", "cwd": "/repo/a", "name": "A", "updatedAt": 20},
                    {"id": "t2", "cwd": "/repo/a", "name": "A old", "updatedAt": 10},
                    {"id": "t3", "cwd": "/repo/b", "name": "B", "updatedAt": 30},
                ],
                "nextCursor": None,
            },
            {"data": [], "nextCursor": None},
        ],
    )

    out = bridge._cmd_workspaces()

    assert "Codex workspaces: 2" in out
    assert "/repo/a" in out
    assert "threads: 2" in out
    assert "/repo/b" in out


def test_limits_command_reads_rate_limits(tmp_path, monkeypatch):
    bridge = make_bridge(
        tmp_path,
        monkeypatch,
        [
            {
                "rateLimits": {
                    "limitName": "codex",
                    "planType": "pro",
                    "primary": {"usedPercent": 25, "windowDurationMins": 1440},
                    "secondary": {"usedPercent": 40, "windowDurationMins": 10080},
                }
            }
        ],
    )

    out = bridge._cmd_limits()

    assert "Codex limits:" in out
    assert "codex  plan: pro" in out
    assert "primary (daily): 25% used" in out
    assert "secondary (weekly): 40% used" in out
    assert bridge._client.requests[0] == ("account/rateLimits/read", None)
