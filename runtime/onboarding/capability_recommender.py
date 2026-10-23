from __future__ import annotations

from .capability_registry import CapabilityRegistry
from .types import (
    CapabilityRecommendation,
    ImplementationStatus,
    SceneProfile,
    SceneType,
)


class CapabilityRecommender:
    """Analyzes scene profiles against capability definitions to generate ranked recommendations."""

    def __init__(
        self,
        threshold_checked: float = 0.75,
        threshold_suggested: float = 0.40,
    ) -> None:
        self.threshold_checked = threshold_checked
        self.threshold_suggested = threshold_suggested

    def recommend(
        self,
        scene_profile: SceneProfile,
        registry: CapabilityRegistry,
    ) -> list[CapabilityRecommendation]:
        """Generate ranked capability recommendations based on scene analysis."""
        recommendations: list[CapabilityRecommendation] = []
        objects = set(scene_profile.objects)
        attrs = set(scene_profile.attributes)
        scene = scene_profile.scene_type

        vehicles = {"car", "truck", "bus", "motorcycle", "bicycle"}
        has_vehicles = bool(objects & vehicles)
        has_people = "person" in objects

        for cap in registry.all():
            score = 0.10
            reason = "Optional capability for this scene."
            evidence: list[str] = []

            if cap.id == "person_detection":
                if has_people:
                    score = 0.95
                    reason = "People were observed in multiple sampled frames."
                    evidence.append("Detected: person")
                elif scene in (SceneType.ENTRANCE, SceneType.OFFICE, SceneType.RETAIL, SceneType.FACTORY):
                    score = 0.65
                    reason = f"Scene classified as {scene}, where human activity is common."
                    evidence.append(f"Scene: {scene}")

            elif cap.id == "person_tracking":
                if has_people:
                    score = 0.91
                    reason = "People were observed in multiple frames with motion."
                    evidence.append("Detected: person with movement")
                elif scene in (SceneType.ENTRANCE, SceneType.OFFICE, SceneType.RETAIL):
                    score = 0.60
                    reason = f"Relevant for movement tracking in {scene}."
                    evidence.append(f"Scene: {scene}")

            elif cap.id == "vehicle_detection":
                if has_vehicles:
                    detected_v = sorted(list(objects & vehicles))
                    score = 0.92
                    reason = f"Vehicles observed in multiple frames ({', '.join(detected_v)})."
                    evidence.append(f"Detected: {', '.join(detected_v)}")
                elif scene in (SceneType.PARKING, SceneType.ROAD):
                    score = 0.70
                    reason = f"Traffic and parking scene identified: {scene}."
                    evidence.append(f"Scene: {scene}")

            elif cap.id == "vehicle_tracking":
                if has_vehicles:
                    score = 0.88
                    reason = "Vehicles observed in traffic flow."
                    evidence.append("Vehicles moving in observation window")
                elif scene in (SceneType.PARKING, SceneType.ROAD):
                    score = 0.65
                    reason = "Trajectory tracking for parking and roadway."
                    evidence.append(f"Scene: {scene}")

            elif cap.id == "zone_monitoring":
                if scene in (SceneType.FACTORY, SceneType.WAREHOUSE):
                    score = 0.76
                    reason = f"Industrial {scene} environment where restricted zones apply."
                    evidence.append(f"Scene: {scene}")
                elif has_people:
                    score = 0.55
                    reason = "Applicable for security perimeters if restricted areas exist."
                    evidence.append("People detected")

            elif cap.id == "entry_exit_counting":
                if scene == SceneType.ENTRANCE or "entrance/exit" in attrs:
                    score = 0.82
                    reason = "Entrance or pedestrian corridor detected; tripwire line configuration required."
                    evidence.append("Corridor / entrance flow observed")
                elif has_people:
                    score = 0.50
                    reason = "Can count pedestrian entry and exit once tripwire line is drawn."

            elif cap.id == "occupancy_monitoring":
                if scene in (SceneType.RETAIL, SceneType.OFFICE, SceneType.ENTRANCE):
                    score = 0.75
                    reason = f"Area classified as {scene}, suitable for headcount monitoring."
                    evidence.append(f"Scene: {scene}")
                elif has_people:
                    score = 0.50
                    reason = "Headcount monitoring available for human traffic."

            elif cap.id == "ppe_detection":
                if scene in (SceneType.FACTORY, SceneType.WAREHOUSE):
                    score = 0.68
                    reason = "Industrial workplace detected where PPE monitoring is common (module not implemented)."
                    evidence.append(f"Scene: {scene}")
                else:
                    score = 0.15
                    reason = "PPE detection module is not implemented in current release."

            elif cap.id == "anpr":
                if has_vehicles and scene in (SceneType.PARKING, SceneType.ROAD):
                    score = 0.65
                    reason = "Vehicles detected in traffic (ANPR plate detector/OCR module not implemented)."
                    evidence.append("Vehicles detected in roadway")
                else:
                    score = 0.10
                    reason = "ANPR module is not implemented in current release."

            # Determine whether it should be recommended checked
            # CRITICAL RULE: Never pre-check NOT_IMPLEMENTED capabilities
            available = cap.implementation_status in (
                ImplementationStatus.AVAILABLE,
                ImplementationStatus.REQUIRES_SETUP,
            )

            is_implemented = cap.implementation_status != ImplementationStatus.NOT_IMPLEMENTED
            recommended_checked = (
                is_implemented and
                cap.implementation_status == ImplementationStatus.AVAILABLE and
                score >= self.threshold_checked
            )

            recommendations.append(
                CapabilityRecommendation(
                    capability_id=cap.id,
                    display_name=cap.display_name,
                    score=round(score, 2),
                    reason=reason,
                    evidence=evidence,
                    available=available,
                    recommended_checked=recommended_checked,
                    status=str(cap.implementation_status),
                    dependencies=list(cap.dependencies),
                    requires_configuration=list(cap.requires_configuration),
                    estimated_compute_cost=cap.estimated_compute_cost,
                )
            )

        # Sort recommendations by score descending
        recommendations.sort(key=lambda r: r.score, reverse=True)
        return recommendations

