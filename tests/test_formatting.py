from codex_remote.formatting import approval_summary


def test_command_approval_summary_includes_commands():
    text = approval_summary(
        "A1",
        "item/commandExecution/requestApproval",
        {"threadId": "t1", "cwd": "/tmp/repo", "command": "rm -rf build", "reason": "cleanup"},
        "Build thread",
    )
    assert "Codex approval A1" in text
    assert "rm -rf build" in text
    assert "/codex approve A1" in text
    assert "/codex deny A1 [alternate instructions]" in text
