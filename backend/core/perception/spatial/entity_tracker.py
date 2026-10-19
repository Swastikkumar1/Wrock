import math
import time
import random
from typing import List
from .scene_graph import (
    SpatialSceneGraph,
    SpatialEntity,
    SpatialPosition,
    SpatialVelocity,
    EntityType,
    ThreatLevel,
)

class EntityTracker:
    """
    Manages live physical kinematic tracking and telemetry simulation
    for satellites, aerial drones, and ground assets in the God's Eye perspective.
    """

    def __init__(self, scene_graph: SpatialSceneGraph):
        self.scene_graph = scene_graph
        self._last_tick_time = time.time()
        self._seed_default_tactical_entities()

    def _seed_default_tactical_entities(self) -> None:
        """Seed initial orbital, aerial, and ground assets for the tactical space."""
        # Orbital Recon Satellite (Keyhole / EDITH constellation)
        sat_1 = SpatialEntity(
            id="SAT-KH11-EDITH",
            name="EDITH-Orbital-01",
            type=EntityType.SATELLITE,
            position=SpatialPosition(x=12.0, y=18.0, z=-10.0),
            velocity=SpatialVelocity(vx=0.08, vy=0.0, vz=0.05),
            heading_deg=45.0,
            altitude_m=420000.0,
            threat_level=ThreatLevel.FRIENDLY,
            bounding_radius=2.0,
            telemetry={
                "orbital_period_min": 92.4,
                "sensor": "Multispectral SAR + LiDAR",
                "uplink_dbm": -42.8,
                "status": "NOMINAL",
            }
        )
        self.scene_graph.upsert_entity(sat_1)

        # Autonomous Tactical Drone 1 (Patrol)
        drone_1 = SpatialEntity(
            id="DRONE-STARK-01",
            name="Tactical Drone Alpha",
            type=EntityType.DRONE,
            position=SpatialPosition(x=-4.5, y=3.2, z=2.0),
            velocity=SpatialVelocity(vx=0.15, vy=0.02, vz=-0.1),
            heading_deg=130.0,
            altitude_m=120.0,
            threat_level=ThreatLevel.FRIENDLY,
            bounding_radius=1.2,
            telemetry={
                "airspeed_kmh": 78.5,
                "battery_pct": 89.2,
                "payload": "Optical Zoom 50x / Thermal FLIR",
                "link_latency_ms": 14,
            }
        )
        self.scene_graph.upsert_entity(drone_1)

        # Autonomous Tactical Drone 2 (Unidentified / Hostile)
        drone_2 = SpatialEntity(
            id="UAV-BOGEY-99",
            name="Unidentified Fast Mover",
            type=EntityType.DRONE,
            position=SpatialPosition(x=6.0, y=4.5, z=-5.0),
            velocity=SpatialVelocity(vx=-0.22, vy=0.0, vz=0.18),
            heading_deg=220.0,
            altitude_m=180.0,
            threat_level=ThreatLevel.HOSTILE,
            bounding_radius=1.4,
            telemetry={
                "airspeed_kmh": 142.0,
                "transponder": "SQUAWK-7700-UNAUTHORIZED",
                "threat_assessment": "RADAR_EMITTER_DETECTED",
                "bearing": "042_DEG",
            }
        )
        self.scene_graph.upsert_entity(drone_2)

        # Ground Recon Rover / Vehicle
        vehicle_1 = SpatialEntity(
            id="UGV-ROVER-04",
            name="Autonomous Recon Vehicle",
            type=EntityType.VEHICLE,
            position=SpatialPosition(x=1.5, y=0.1, z=3.5),
            velocity=SpatialVelocity(vx=0.04, vy=0.0, vz=0.02),
            heading_deg=35.0,
            altitude_m=2.0,
            threat_level=ThreatLevel.FRIENDLY,
            bounding_radius=1.0,
            telemetry={
                "ground_speed_kmh": 32.0,
                "fuel_cell_pct": 94.0,
                "route_checkpoint": "SECTOR_7B",
            }
        )
        self.scene_graph.upsert_entity(vehicle_1)

        # Tactical Command Center Base Anchor
        base_anchor = SpatialEntity(
            id="BASE-STARK-HQ",
            name="Tactical Command Outpost",
            type=EntityType.INFRASTRUCTURE,
            position=SpatialPosition(x=0.0, y=0.0, z=0.0),
            heading_deg=0.0,
            altitude_m=0.0,
            threat_level=ThreatLevel.FRIENDLY,
            bounding_radius=2.5,
            telemetry={
                "perimeter_shield": "ONLINE",
                "power_grid_mw": 14.2,
                "sensors_active": 128,
            }
        )
        self.scene_graph.upsert_entity(base_anchor)

        # Dynamic Anchor
        self.scene_graph.add_spatial_anchor("ANCHOR-LZ1", "Landing Zone Alpha", (3.0, 0.0, -2.5))
        self.scene_graph.add_spatial_anchor("ANCHOR-RADAR", "Perimeter Radar Mast", (-5.0, 0.0, -4.0))

    def update_physics(self, dt: float) -> None:
        """Advance orbital and flight kinematics for continuous tracking realism."""
        now = time.time()
        entities = self.scene_graph.get_all_entities()

        for entity in entities:
            # SATELLITE: Circular orbital progression
            if entity.type == EntityType.SATELLITE:
                theta = now * 0.15
                radius = 16.0
                entity.position.x = radius * math.cos(theta)
                entity.position.z = radius * math.sin(theta)
                entity.position.y = 18.0 + math.sin(now * 0.2) * 1.5
                entity.heading_deg = (math.degrees(theta + math.pi/2)) % 360

            # DRONE: Patrol looping or waypoint steering
            elif entity.type == EntityType.DRONE:
                if entity.id == "DRONE-STARK-01":
                    omega = now * 0.25
                    entity.position.x = 5.0 * math.cos(omega)
                    entity.position.z = 4.0 * math.sin(omega * 1.3)
                    entity.position.y = 3.0 + math.sin(now * 0.5) * 0.4
                    entity.heading_deg = (math.degrees(-omega)) % 360
                elif entity.id == "UAV-BOGEY-99":
                    # Figure-8 trajectory
                    t = now * 0.2
                    entity.position.x = 7.0 * math.sin(t)
                    entity.position.z = 6.0 * math.sin(t) * math.cos(t)
                    entity.position.y = 4.5 + math.cos(now * 0.4) * 0.5
                    entity.heading_deg = (math.degrees(t * 2)) % 360

            # VEHICLE: Ground perimeter patrol
            elif entity.type == EntityType.VEHICLE:
                t = now * 0.1
                entity.position.x = 4.0 * math.cos(t)
                entity.position.z = 4.0 * math.sin(t)
                entity.heading_deg = (math.degrees(-t)) % 360

            # Update timestamp
            entity.last_updated = now
