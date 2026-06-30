"""Launch test: bring up fr3_moveit_servo.launch.py with fake hardware, send a
constant-velocity wrist rotation over the servo node's Cartesian twist topic,
and verify the simulated arm joints actually rotate in /joint_states.

Run with:
    colcon test --packages-select fr3_moveit_servo --event-handlers console_direct+
"""

import time
import unittest

import launch
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from geometry_msgs.msg import TwistStamped
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare
from moveit_msgs.srv import ServoCommandType
from sensor_msgs.msg import JointState

ARM_JOINTS = [f"fr3_joint{i}" for i in range(1, 8)]

# Bringing up move_group, ros2_control, the controllers, and moveit_servo
# together is slow, especially the first time plugins get loaded.
STARTUP_TIMEOUT = 120.0
# Extra time to let the one-time fake-hardware state nudge
# (see fr3_moveit_servo/fake_hardware_nudge.py) complete after the
# controller becomes active, before moveit_servo will act on any commands.
SERVO_READY_SETTLE_TIME = 20.0
# Duration (s) for which twist commands are published.
COMMAND_DURATION = 3.0
# Minimum total joint displacement (rad), summed over all arm joints,
# required to consider the wrist as having rotated.
MIN_DISPLACEMENT = 0.1

TWIST_COMMAND_TYPE = 1  # moveit_msgs/srv/ServoCommandType.Request.TWIST


@pytest.mark.launch_test
def generate_test_description():
    servo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            FindPackageShare("fr3_moveit_servo"), "/launch/fr3_moveit_servo.launch.py",
        ]),
        launch_arguments={"use_fake_hardware": "true", "use_rviz": "false"}.items(),
    )

    return launch.LaunchDescription([
        servo_launch,
        launch_testing.actions.ReadyToTest(),
    ])


class TestServoJointMotion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node("test_servo_joint_motion")

    @classmethod
    def tearDownClass(cls):
        cls.node.destroy_node()
        rclpy.shutdown()

    def _get_joint_state(self, timeout: float) -> JointState:
        """Block until one /joint_states message is received."""
        received = []
        sub = self.node.create_subscription(
            JointState, "/joint_states", received.append, 10
        )
        deadline = time.time() + timeout
        while not received and time.time() < deadline:
            rclpy.spin_once(self.node, timeout_sec=0.1)
        self.node.destroy_subscription(sub)
        return received[0] if received else None

    def _spin_for(self, duration: float) -> None:
        deadline = time.time() + duration
        while time.time() < deadline:
            rclpy.spin_once(self.node, timeout_sec=0.05)

    def test_wrist_rotation(self):
        # Wait for the full stack (move_group, controllers, servo) to be ready.
        initial_msg = self._get_joint_state(timeout=STARTUP_TIMEOUT)
        self.assertIsNotNone(
            initial_msg,
            f"No /joint_states message received within {STARTUP_TIMEOUT}s",
        )
        for name in ARM_JOINTS:
            self.assertIn(name, initial_msg.name, f"{name} not in joint states")

        # Let the fake-hardware startup nudge (see fake_hardware_nudge.py) run
        # so moveit_servo's planning scene latches a current robot state.
        self._spin_for(SERVO_READY_SETTLE_TIME)

        # moveit_servo requires the command type to be set before it will act
        # on any topic commands.
        client = self.node.create_client(
            ServoCommandType, "/servo_node/switch_command_type"
        )
        self.assertTrue(
            client.wait_for_service(timeout_sec=30.0),
            "/servo_node/switch_command_type service not available",
        )
        request = ServoCommandType.Request(command_type=TWIST_COMMAND_TYPE)
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)
        self.assertTrue(future.done() and future.result().success,
                         "/servo_node/switch_command_type failed")

        initial_msg = self._get_joint_state(timeout=5.0)
        initial_pos = dict(zip(initial_msg.name, initial_msg.position))

        # Publish angular-z twist commands (rotates the wrist about the base
        # z-axis). frame_id must match robot_link_command_frame (fr3_link0),
        # i.e. coordinates are in the robot's global/base frame.
        twist_pub = self.node.create_publisher(
            TwistStamped, "/servo_node/delta_twist_cmds", 10
        )
        cmd = TwistStamped()
        cmd.header.frame_id = "fr3_link0"
        cmd.twist.angular.z = 0.5  # rad/s

        deadline = time.time() + COMMAND_DURATION
        while time.time() < deadline:
            cmd.header.stamp = self.node.get_clock().now().to_msg()
            twist_pub.publish(cmd)
            rclpy.spin_once(self.node, timeout_sec=0.02)
            time.sleep(0.02)

        self.node.destroy_publisher(twist_pub)

        # Allow the controller to settle after the last command.
        self._spin_for(1.0)

        final_msg = self._get_joint_state(timeout=5.0)
        self.assertIsNotNone(final_msg, "No /joint_states after commanding motion")
        final_pos = dict(zip(final_msg.name, final_msg.position))

        total_displacement = sum(
            abs(final_pos[name] - initial_pos[name]) for name in ARM_JOINTS
        )

        self.assertGreater(
            total_displacement,
            MIN_DISPLACEMENT,
            f"Arm joints did not move (total displacement = {total_displacement:.4f} rad). "
            "Initial: " + ", ".join(f"{k}={initial_pos[k]:.3f}" for k in ARM_JOINTS)
            + "  Final: " + ", ".join(f"{k}={final_pos[k]:.3f}" for k in ARM_JOINTS),
        )
