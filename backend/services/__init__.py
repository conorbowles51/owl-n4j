"""
Services package - business logic layer.
"""

from importlib import import_module

__all__ = ["auth_service", "neo4j_service", "llm_service", "rag_service"]


class _LazyService:
    def __init__(self, module_name, attribute_name):
        self._module_name = module_name
        self._attribute_name = attribute_name
        self._resolved = None

    def _load(self):
        if self._resolved is None:
            module = import_module(self._module_name)
            self._resolved = getattr(module, self._attribute_name)
        return self._resolved

    def __getattr__(self, name):
        return getattr(self._load(), name)

    def __getitem__(self, key):
        return self._load()[key]

    def __call__(self, *args, **kwargs):
        return self._load()(*args, **kwargs)

    def __repr__(self):
        return repr(self._load())


auth_service = _LazyService("services.auth_service", "auth_service")
neo4j_service = _LazyService("services.neo4j_service", "neo4j_service")
llm_service = _LazyService("services.llm_service", "llm_service")
rag_service = _LazyService("services.rag_service", "rag_service")
