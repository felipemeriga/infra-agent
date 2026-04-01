from graph.state import DiagnoseState


def test_diagnose_state_has_status_field():
    state: DiagnoseState = {
        "service_name": "test",
        "container_status": None,
        "container_stats": None,
        "logs": None,
        "traefik_status": None,
        "compose_config": None,
        "diagnosis": None,
        "recommended_actions": [],
        "status": "checking",
    }
    assert state["status"] == "checking"


def test_restart_state_has_status_field():
    from graph.state import RestartState

    state: RestartState = {
        "service_name": "test",
        "pre_status": None,
        "post_status": None,
        "health_ok": False,
        "attempt": 0,
        "max_attempts": 3,
        "result": None,
        "status": "pre_check",
    }
    assert state["status"] == "pre_check"


def test_deploy_state_has_status_field():
    from graph.state import DeployState

    state: DeployState = {
        "service_name": "test",
        "image_tag": "latest",
        "old_container_id": None,
        "old_container_attrs": None,
        "new_container_id": None,
        "health_status": "unknown",
        "rollback_needed": False,
        "attempt": 0,
        "max_attempts": 3,
        "result": None,
        "status": "pulling",
    }
    assert state["status"] == "pulling"


def test_auto_respond_state_has_status_field():
    from graph.state import AutoRespondState

    state: AutoRespondState = {
        "service_name": "test",
        "trigger": "event:die",
        "container_status": None,
        "logs": None,
        "crash_history": None,
        "llm_decision": None,
        "action_taken": None,
        "action_succeeded": False,
        "result": None,
        "status": "assessing",
    }
    assert state["status"] == "assessing"
