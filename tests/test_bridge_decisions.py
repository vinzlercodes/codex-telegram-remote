from codex_remote.bridge import CodexRemoteBridge


def test_command_approval_decision_mapping_accepts_once(tmp_path, monkeypatch):
    monkeypatch.setattr("codex_remote.bridge.STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr("codex_remote.bridge.DEFAULT_SOCKET", tmp_path / "codex.sock")
    bridge = CodexRemoteBridge()
    result = bridge._approval_response(
        "item/commandExecution/requestApproval",
        "accept",
        {},
    )
    assert result == {"decision": "accept"}


def test_always_uses_execpolicy_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr("codex_remote.bridge.STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr("codex_remote.bridge.DEFAULT_SOCKET", tmp_path / "codex.sock")
    bridge = CodexRemoteBridge()
    result = bridge._always_response(
        "item/commandExecution/requestApproval",
        {"proposedExecpolicyAmendment": ["allow rm build"]},
    )
    assert result == {
        "decision": {
            "acceptWithExecpolicyAmendment": {
                "execpolicy_amendment": ["allow rm build"],
            }
        }
    }
