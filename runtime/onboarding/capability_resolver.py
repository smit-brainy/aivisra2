from __future__ import annotations

from typing import Any
from .capability_registry import CapabilityRegistry
from .types import ImplementationStatus, ValidationResult


class CapabilityResolver:
    """Validates capability dependencies, configurations, and detects cycles in the dependency graph."""

    @staticmethod
    def detect_cycles(registry: CapabilityRegistry) -> list[list[str]]:
        """Detect circular dependencies in the capability registry graph using DFS."""
        visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        cycles: list[list[str]] = []
        path: list[str] = []

        def dfs(node: str) -> None:
            visited[node] = 1
            path.append(node)
            cap = registry.get(node)
            if cap:
                for dep in cap.dependencies:
                    if visited.get(dep, 0) == 1:
                        # Found cycle
                        cycle_start = path.index(dep)
                        cycles.append(path[cycle_start:] + [dep])
                    elif visited.get(dep, 0) == 0:
                        dfs(dep)
            path.pop()
            visited[node] = 2

        for cap in registry.all():
            if visited.get(cap.id, 0) == 0:
                dfs(cap.id)

        return cycles

    def resolve(
        self,
        selected_capabilities: list[str],
        registry: CapabilityRegistry,
        configurations: dict[str, Any] | None = None,
        auto_include_dependencies: bool = True,
    ) -> ValidationResult:
        """Resolve dependencies, validate implementation status, and verify required setups."""
        configs = configurations or {}
        errors: list[str] = []
        unsupported: list[str] = []
        missing_deps: dict[str, list[str]] = {}
        missing_configs: dict[str, list[str]] = {}

        # 1. Check for cycles in registry graph
        cycles = self.detect_cycles(registry)
        if cycles:
            cycle_desc = " -> ".join(cycles[0])
            errors.append(f"Circular dependency detected in capability registry: {cycle_desc}")
            return ValidationResult(
                valid=False,
                resolved_capabilities=[],
                errors=errors,
            )

        # 2. Check each requested capability exists and is implemented
        resolved = set(selected_capabilities)
        for cap_id in list(selected_capabilities):
            cap = registry.get(cap_id)
            if cap is None:
                errors.append(f"Unknown capability: '{cap_id}'")
                continue

            if cap.implementation_status == ImplementationStatus.NOT_IMPLEMENTED:
                unsupported.append(cap_id)
                errors.append(f"Capability '{cap.display_name}' ({cap_id}) is not implemented in this release.")
                continue

            if cap.implementation_status == ImplementationStatus.UNAVAILABLE:
                unsupported.append(cap_id)
                errors.append(f"Capability '{cap.display_name}' ({cap_id}) is currently unavailable.")
                continue

            # Check configuration requirements
            for req_cfg in cap.requires_configuration:
                if req_cfg not in configs or not configs[req_cfg]:
                    missing_configs.setdefault(cap_id, []).append(req_cfg)
                    errors.append(
                        f"Capability '{cap.display_name}' requires configuration '{req_cfg}' before activation."
                    )

            # Check dependencies
            for dep in cap.dependencies:
                dep_cap = registry.get(dep)
                if dep_cap is None:
                    errors.append(f"Dependency '{dep}' of capability '{cap_id}' does not exist.")
                    continue
                if dep_cap.implementation_status == ImplementationStatus.NOT_IMPLEMENTED:
                    errors.append(f"Required dependency '{dep_cap.display_name}' for '{cap.display_name}' is not implemented.")
                    unsupported.append(dep)
                    continue

                if dep not in resolved:
                    if auto_include_dependencies:
                        resolved.add(dep)
                    else:
                        missing_deps.setdefault(cap_id, []).append(dep)
                        errors.append(
                            f"Missing dependency: '{cap.display_name}' requires '{dep_cap.display_name}'."
                        )

        # Recursively ensure dependencies of added dependencies are also resolved
        if auto_include_dependencies and not unsupported and not missing_configs:
            added = True
            while added:
                added = False
                for c_id in list(resolved):
                    c = registry.get(c_id)
                    if c:
                        for d in c.dependencies:
                            if d not in resolved:
                                resolved.add(d)
                                added = True

        valid = (len(errors) == 0 and len(unsupported) == 0 and len(missing_configs) == 0)

        # Sort in topological dependency order (base dependencies first)
        ordered_resolved: list[str] = []
        visited_order: set[str] = set()

        def visit(c_id: str) -> None:
            if c_id in visited_order or c_id not in resolved:
                return
            c_def = registry.get(c_id)
            if c_def:
                for d in c_def.dependencies:
                    visit(d)
            visited_order.add(c_id)
            ordered_resolved.append(c_id)

        for c_id in sorted(resolved):
            visit(c_id)

        req_models: set[str] = set()
        req_components: set[str] = set()
        for cid in ordered_resolved:
            c = registry.get(cid)
            if c:
                req_models.update(c.required_models)
                if c.runtime_component:
                    req_components.add(c.runtime_component)

        return ValidationResult(
            valid=valid,
            resolved_capabilities=ordered_resolved,
            required_models=sorted(list(req_models)),
            required_runtime_components=sorted(list(req_components)),
            missing_dependencies=missing_deps,
            unsupported_capabilities=unsupported,
            missing_configuration=missing_configs,
            errors=errors,
        )
