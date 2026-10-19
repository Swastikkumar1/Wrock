from dataclasses import dataclass
from typing import Tuple, Optional, List, Dict, Any
import numpy as np

@dataclass
class Ray3D:
    origin: np.ndarray      # [x, y, z]
    direction: np.ndarray   # [dx, dy, dz] normalized

@dataclass
class RaycastHit:
    entity_id: str
    distance: float
    point: Tuple[float, float, float]
    normal: Tuple[float, float, float]

class SpatialRaycaster:
    """
    Projects 2D/3D screen space coordinates and hand pointing rays
    into 3D world space to test intersections with spatial entities.
    """

    def __init__(self, fov_deg: float = 60.0, aspect_ratio: float = 16.0 / 9.0):
        self.fov_deg = fov_deg
        self.aspect_ratio = aspect_ratio

    def screen_to_world_ray(
        self,
        norm_x: float,
        norm_y: float,
        camera_pos: np.ndarray,
        camera_target: np.ndarray,
        camera_up: Optional[np.ndarray] = None
    ) -> Ray3D:
        """
        Converts normalized screen coordinates ([0, 1], where (0,0) is top-left)
        to a 3D world ray originating at camera_pos.
        """
        if camera_up is None:
            camera_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        # NDC coordinates [-1, 1]
        ndc_x = (norm_x * 2.0) - 1.0
        ndc_y = 1.0 - (norm_y * 2.0)

        # Camera coordinate frame
        forward = camera_target - camera_pos
        forward_norm = forward / (np.linalg.norm(forward) + 1e-6)

        right = np.cross(forward_norm, camera_up)
        right_norm = right / (np.linalg.norm(right) + 1e-6)

        up = np.cross(right_norm, forward_norm)
        up_norm = up / (np.linalg.norm(up) + 1e-6)

        # Calculate ray direction
        half_fov_rad = np.radians(self.fov_deg / 2.0)
        tan_fov = np.tan(half_fov_rad)

        ray_dir = (
            forward_norm +
            (right_norm * (ndc_x * tan_fov * self.aspect_ratio)) +
            (up_norm * (ndc_y * tan_fov))
        )
        ray_dir = ray_dir / np.linalg.norm(ray_dir)

        return Ray3D(origin=camera_pos.copy(), direction=ray_dir)

    def intersect_sphere(
        self,
        ray: Ray3D,
        sphere_center: np.ndarray,
        radius: float
    ) -> Optional[float]:
        """
        Calculates distance along ray to intersection with sphere, or None.
        """
        oc = ray.origin - sphere_center
        a = float(np.dot(ray.direction, ray.direction))
        b = 2.0 * float(np.dot(oc, ray.direction))
        c = float(np.dot(oc, oc)) - (radius * radius)
        discriminant = (b * b) - (4.0 * a * c)

        if discriminant < 0:
            return None

        t = (-b - np.sqrt(discriminant)) / (2.0 * a)
        return float(t) if t >= 0 else None

    def find_nearest_intersected_entity(
        self,
        ray: Ray3D,
        entities: List[Dict[str, Any]],
        default_bounding_radius: float = 1.5
    ) -> Optional[RaycastHit]:
        nearest_hit: Optional[RaycastHit] = None
        min_dist = float("inf")

        for entity in entities:
            pos = entity.get("position", {})
            center = np.array([pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0)], dtype=np.float32)
            radius = entity.get("bounding_radius", default_bounding_radius)

            dist = self.intersect_sphere(ray, center, radius)
            if dist is not None and dist < min_dist:
                min_dist = dist
                hit_point = ray.origin + (ray.direction * dist)
                hit_normal = (hit_point - center) / (np.linalg.norm(hit_point - center) + 1e-6)

                nearest_hit = RaycastHit(
                    entity_id=entity.get("id", "unknown"),
                    distance=dist,
                    point=(float(hit_point[0]), float(hit_point[1]), float(hit_point[2])),
                    normal=(float(hit_normal[0]), float(hit_normal[1]), float(hit_normal[2]))
                )

        return nearest_hit
