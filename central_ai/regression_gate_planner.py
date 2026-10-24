"""A11.15.8 read-only regression test planning.

Produces fixed, reviewable unittest commands; never runs generated code.
"""
import re

_ALLOWED = {
    "failure_audit": "test_failure_audit.py",
    "incident_registry": "test_fix_incident_registry.py",
    "isolated_stager": "test_isolated_repair_stager.py",
    "rollback_rehearsal": "test_repair_rollback_rehearsal.py",
}


class RegressionGatePlanner:
    def plan(self, requested_modules, *, include_regression=True):
        if not isinstance(requested_modules, (list, tuple)) or not requested_modules:
            raise ValueError("INVALID_MODULES")
        if not isinstance(include_regression, bool):
            raise ValueError("INVALID_REGRESSION_FLAG")
        if len(requested_modules) > len(_ALLOWED):
            raise ValueError("TOO_MANY_MODULES")
        if any(not isinstance(item, str) or item not in _ALLOWED
               for item in requested_modules):
            raise ValueError("UNAPPROVED_TEST_MODULE")
        modules = sorted(set(requested_modules))
        targeted = [
            ["python", "-m", "unittest", "discover", "-s", "tests",
             "-p", _ALLOWED[name], "-v"]
            for name in modules
        ]
        regression = (
            ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
            if include_regression else None
        )
        return {
            "modules": modules,
            "targeted_commands": targeted,
            "regression_command": regression,
            "execute": False,
            "deployment_allowed": False,
            "requires_review": True,
        }
