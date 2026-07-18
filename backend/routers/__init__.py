"""
Routers package - API endpoints.
"""

from importlib import import_module

_ROUTER_MODULES = {
    "graph_router": "routers.graph",
    "chat_router": "routers.chat",
    "agent_router": "routers.agent",
    "query_router": "routers.query",
    "timeline_router": "routers.timeline",
    "snapshots_router": "routers.snapshots",
    "cases_router": "routers.cases",
    "case_members_router": "routers.case_members",
    "case_profiles_router": "routers.case_profiles",
    "auth_router": "routers.auth",
    "evidence_router": "routers.evidence",
    "background_tasks_router": "routers.background_tasks",
    "profiles_router": "routers.profiles",
    "filesystem_router": "routers.filesystem",
    "chat_history_router": "routers.chat_history",
    "system_logs_router": "routers.system_logs",
    "backfill_router": "routers.backfill",
    "database_router": "routers.database",
    "llm_config_router": "routers.llm_config",
    "workspace_router": "routers.workspace",
    "users_router": "routers.users",
    "setup_router": "routers.setup",
    "cost_ledger_router": "routers.cost_ledger",
    "admin_ai_costs_router": "routers.admin_ai_costs",
    "admin_update_router": "routers.admin_update",
    "financial_router": "routers.financial",
    "maintenance_router": "routers.maintenance",
    "case_deadlines_router": "routers.case_deadlines",
    "notebook_router": "routers.notebook",
    "evidence_folders_router": "routers.evidence_folders",
    "cellebrite_router": "routers.cellebrite",
    "triage_router": "routers.triage",
}


def __getattr__(name: str):
    module_name = _ROUTER_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module 'routers' has no attribute {name!r}")

    router = import_module(module_name).router
    globals()[name] = router
    return router

__all__ = list(_ROUTER_MODULES)
