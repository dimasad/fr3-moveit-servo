"""One-time joint nudge that works around a moveit_servo/MoveIt startup deadlock.

moveit_servo's PlanningSceneMonitor only latches in a current robot state once
it observes a joint state value actually change (see
https://github.com/moveit/moveit2/issues/3040). With fake/mock hardware the
simulated joints never move on their own, so servo_node logs "Waiting to
receive robot state update." forever and ignores all servo commands.

This node breaks the deadlock once at startup by commanding every arm joint a
tiny distance away from its current position and back again, which is enough
to make moveit_servo see a state update. It is only meant to run when
use_fake_hardware:=true; the real robot moves on its own and never needs it.
"""

import sys

import rclpy
from builtin_interfaces.msg import Duration
from rclpy.node import Node
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

ARM_JOINTS = [f"fr3_joint{i}" for i in range(1, 8)]
NUDGE_RAD = 0.01


def main(argv=None):
    rclpy.init(args=argv)
    node = Node("fake_hardware_nudge")

    received = []
    state_sub = node.create_subscription(JointState, "/joint_states", received.append, 10)
    while rclpy.ok() and not received:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_subscription(state_sub)

    if not received:
        node.destroy_node()
        rclpy.shutdown()
        return 1

    positions = dict(zip(received[0].name, received[0].position))
    start = [positions[name] for name in ARM_JOINTS]

    pub = node.create_publisher(
        JointTrajectory, "/fr3_arm_controller/joint_trajectory", 10
    )
    # Give the publisher time to match with the controller's subscription.
    deadline = node.get_clock().now().nanoseconds + int(1.0e9)
    while rclpy.ok() and node.get_clock().now().nanoseconds < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)

    traj = JointTrajectory()
    traj.joint_names = ARM_JOINTS
    out_point = JointTrajectoryPoint()
    out_point.positions = [p + NUDGE_RAD for p in start]
    out_point.time_from_start = Duration(sec=0, nanosec=300_000_000)
    back_point = JointTrajectoryPoint()
    back_point.positions = list(start)
    back_point.time_from_start = Duration(sec=0, nanosec=600_000_000)
    traj.points = [out_point, back_point]
    pub.publish(traj)

    deadline = node.get_clock().now().nanoseconds + int(1.5e9)
    while rclpy.ok() and node.get_clock().now().nanoseconds < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)

    node.get_logger().info("Sent one-time fake-hardware state nudge.")
    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
