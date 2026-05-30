"""Smoke test: connect to Reachy Mini and run a few expressive gestures.

Run with the daemon already running (`reachy-mini-daemon`) and the venv active:
    python sayam/hello_move.py

media_backend="no_media" keeps the camera free for the Presage vitals pipeline
(which reads the same physical camera directly as UVC device index 1).
"""

import time

from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose


def main() -> None:
    with ReachyMini(media_backend="no_media") as mini:
        print("Connected to Reachy Mini.")

        # Start from a clean neutral pose.
        mini.goto_target(create_head_pose(), antennas=[0.0, 0.0], duration=1.0)

        # Wiggle antennas — a friendly "hello".
        print("Wiggling antennas...")
        mini.goto_target(antennas=[0.5, -0.5], duration=0.5)
        mini.goto_target(antennas=[-0.5, 0.5], duration=0.5)
        mini.goto_target(antennas=[0.0, 0.0], duration=0.5)

        # Nod — look down then up (pitch in degrees).
        print("Nodding...")
        mini.goto_target(head=create_head_pose(pitch=15, degrees=True), duration=0.6)
        mini.goto_target(head=create_head_pose(pitch=-10, degrees=True), duration=0.6)

        # Gentle look left/right (yaw).
        print("Looking around...")
        mini.goto_target(head=create_head_pose(yaw=20, degrees=True), duration=0.6)
        mini.goto_target(head=create_head_pose(yaw=-20, degrees=True), duration=0.6)

        # Back to neutral.
        mini.goto_target(create_head_pose(), antennas=[0.0, 0.0], duration=0.8)
        time.sleep(0.3)
        print("Done.")


if __name__ == "__main__":
    main()
