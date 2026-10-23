from __future__ import annotations

from typing import Iterator
from .types import CapabilityDefinition, ImplementationStatus


class CapabilityRegistry:
    """Central registry of system AI capabilities, dependencies, and implementation statuses.

    CRITICAL RULE: Capability is not the same as a model. A capability maps to models,
    trackers, or runtime rules.
    """

    def __init__(self, custom_definitions: list[CapabilityDefinition] | None = None) -> None:
        self._capabilities: dict[str, CapabilityDefinition] = {}
        if custom_definitions is not None:
            for cap in custom_definitions:
                self.register(cap)
        else:
            self._load_defaults()

    def register(self, capability: CapabilityDefinition) -> None:
        self._capabilities[capability.id] = capability

    def get(self, capability_id: str) -> CapabilityDefinition | None:
        return self._capabilities.get(capability_id)

    def all(self) -> list[CapabilityDefinition]:
        return list(self._capabilities.values())

    def is_available(self, capability_id: str) -> bool:
        cap = self.get(capability_id)
        return cap is not None and cap.implementation_status in (
            ImplementationStatus.AVAILABLE,
            ImplementationStatus.REQUIRES_SETUP,
        )

    def is_implemented(self, capability_id: str) -> bool:
        cap = self.get(capability_id)
        return cap is not None and cap.implementation_status != ImplementationStatus.NOT_IMPLEMENTED

    def __iter__(self) -> Iterator[CapabilityDefinition]:
        return iter(self._capabilities.values())

    def __len__(self) -> int:
        return len(self._capabilities)

    def _load_defaults(self) -> None:
        defaults = [
            CapabilityDefinition(
                id="person_detection",
                display_name="Person Detection",
                description="Detect humans in the camera field of view using YOLO11n.",
                category="Safety & Security",
                dependencies=(),
                required_models=("base_yolo",),
                implementation_status=ImplementationStatus.AVAILABLE,
                requires_configuration=(),
                supported_classes=("person",),
                estimated_compute_cost="Low",
                default_enabled=True,
            ),
            CapabilityDefinition(
                id="person_tracking",
                display_name="Person Tracking",
                description="Multi-object ByteTrack tracking with persistent IDs, velocity, and trajectory.",
                category="Safety & Security",
                dependencies=("person_detection",),
                required_models=("base_yolo",),
                runtime_component="bytetrack",
                implementation_status=ImplementationStatus.AVAILABLE,
                requires_configuration=(),
                supported_classes=("person",),
                estimated_compute_cost="Low",
                default_enabled=True,
            ),
            CapabilityDefinition(
                id="vehicle_detection",
                display_name="Vehicle Detection",
                description="Detect cars, trucks, buses, motorcycles, and bicycles.",
                category="Traffic & Parking",
                dependencies=(),
                required_models=("base_yolo",),
                implementation_status=ImplementationStatus.AVAILABLE,
                requires_configuration=(),
                supported_classes=("car", "truck", "bus", "motorcycle", "bicycle"),
                estimated_compute_cost="Low",
                default_enabled=False,
            ),
            CapabilityDefinition(
                id="vehicle_tracking",
                display_name="Vehicle Tracking",
                description="Track vehicle trajectories, entry/exit direction, and speeds.",
                category="Traffic & Parking",
                dependencies=("vehicle_detection",),
                required_models=("base_yolo",),
                runtime_component="bytetrack",
                implementation_status=ImplementationStatus.AVAILABLE,
                requires_configuration=(),
                supported_classes=("car", "truck", "bus", "motorcycle", "bicycle"),
                estimated_compute_cost="Low",
                default_enabled=False,
            ),
            CapabilityDefinition(
                id="zone_monitoring",
                display_name="Restricted Zone Monitoring",
                description="Alert when tracked persons or vehicles enter a defined polygon boundary.",
                category="Safety & Security",
                dependencies=("person_tracking",),
                required_models=("base_yolo",),
                implementation_status=ImplementationStatus.AVAILABLE,
                requires_configuration=("zone_polygon",),
                supported_classes=("person",),
                estimated_compute_cost="Low",
                default_enabled=False,
            ),
            CapabilityDefinition(
                id="line_crossing",
                display_name="Line Crossing Detection",
                description="Detect and alert when tracked targets cross a designated virtual line.",
                category="Analytics & Flow",
                dependencies=("person_tracking",),
                required_models=("base_yolo",),
                implementation_status=ImplementationStatus.AVAILABLE,
                requires_configuration=("tripwire_line",),
                supported_classes=("person",),
                estimated_compute_cost="Low",
                default_enabled=False,
            ),
            CapabilityDefinition(
                id="entry_exit_counting",
                display_name="Entry/Exit Counting",
                description="Bidirectional line-crossing counter for people and vehicles.",
                category="Analytics & Flow",
                dependencies=("line_crossing",),
                required_models=("base_yolo",),
                implementation_status=ImplementationStatus.AVAILABLE,
                requires_configuration=("tripwire_line",),
                supported_classes=("person",),
                estimated_compute_cost="Low",
                default_enabled=False,
            ),
            CapabilityDefinition(
                id="dwell_monitoring",
                display_name="Dwell Time Monitoring",
                description="Track duration of stay and alert when dwell threshold is exceeded.",
                category="Analytics & Flow",
                dependencies=("zone_monitoring",),
                required_models=("base_yolo",),
                implementation_status=ImplementationStatus.AVAILABLE,
                requires_configuration=("zone_polygon",),
                supported_classes=("person",),
                estimated_compute_cost="Low",
                default_enabled=False,
            ),
            CapabilityDefinition(
                id="visible_occupancy",
                display_name="Visible Occupancy",
                description="Real-time visible headcount of confirmed targets inside defined zones.",
                category="Analytics & Flow",
                dependencies=("zone_monitoring",),
                required_models=("base_yolo",),
                implementation_status=ImplementationStatus.AVAILABLE,
                requires_configuration=("zone_polygon",),
                supported_classes=("person",),
                estimated_compute_cost="Low",
                default_enabled=False,
            ),
            CapabilityDefinition(
                id="flow_occupancy",
                display_name="Flow-Based Occupancy",
                description="Population estimation based on baseline and verified IN/OUT line crossings.",
                category="Analytics & Flow",
                dependencies=("line_crossing",),
                required_models=("base_yolo",),
                implementation_status=ImplementationStatus.AVAILABLE,
                requires_configuration=("tripwire_line",),
                supported_classes=("person",),
                estimated_compute_cost="Low",
                default_enabled=False,
            ),
            CapabilityDefinition(
                id="occupancy_monitoring",
                display_name="Occupancy Monitoring",
                description="Live headcount of people currently inside the monitored area.",
                category="Analytics & Flow",
                dependencies=("person_tracking",),
                required_models=("base_yolo",),
                implementation_status=ImplementationStatus.AVAILABLE,
                requires_configuration=(),
                supported_classes=("person",),
                estimated_compute_cost="Low",
                default_enabled=False,
            ),
            CapabilityDefinition(
                id="ppe_detection",
                display_name="PPE Monitoring",
                description="Hard hat, vest, and protective equipment compliance monitoring.",
                category="Industrial Safety",
                dependencies=("person_detection",),
                required_models=("ppe_model",),
                implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
                requires_configuration=(),
                supported_classes=("hardhat", "vest", "goggles"),
                estimated_compute_cost="Medium",
                default_enabled=False,
            ),
            CapabilityDefinition(
                id="anpr",
                display_name="Automatic Number Plate Recognition (ANPR)",
                description="Vehicle license plate localization and alphanumeric OCR.",
                category="Traffic & Parking",
                dependencies=("vehicle_detection",),
                required_models=("plate_detector", "ocr"),
                implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
                requires_configuration=(),
                supported_classes=("plate",),
                estimated_compute_cost="High",
                default_enabled=False,
            ),
        ]
        for cap in defaults:
            self.register(cap)

