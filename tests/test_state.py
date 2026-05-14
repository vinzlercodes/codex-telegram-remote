from codex_remote.state import StateStore


def test_state_defaults_and_update(tmp_path):
    store = StateStore(tmp_path / "state.json")
    data = store.load()
    assert data["active_sessions"] == {}
    assert data["pending_approvals"] == {}

    def edit(d):
        d["active_sessions"]["telegram:1"] = {"thread_id": "t1"}

    store.update(edit)
    assert store.load()["active_sessions"]["telegram:1"]["thread_id"] == "t1"
