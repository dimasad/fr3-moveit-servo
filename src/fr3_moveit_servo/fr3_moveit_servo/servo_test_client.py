#!/usr/bin/env python3
"""
Test client for moveit_servo that sends joint velocity commands to rotate the wrist joint.
Sends commands to rotate the wrist (FR3 joint 7) at 0.25 rad/s.
"""

import sys
import rclpy
from rclpy.node import Node
from rclpy.utilities import remove_ros_args
from sensor_msgs.msg import JointState


class ServoTestClient(Node):
    def __init__(self):
        super().__init__("servo_test_client")
        
        # Create publisher for joint velocity commands
        self.joint_cmd_publisher = self.create_publisher(
            JointState, 
            "/servo_node/delta_joint_cmds", 
            10
        )
        
        self.get_logger().info("Servo test client initialized")
        self.get_logger().info("Publishing joint velocity commands to /servo_node/delta_joint_cmds")
        self.get_logger().info("Rotating wrist joint (fr3_joint7) at 0.25 rad/s")
    
    def send_wrist_velocity(self, wrist_velocity=0.25, duration=10.0):
        """
        Send velocity command to rotate the wrist joint.
        
        Args:
            wrist_velocity: Target velocity for wrist joint in rad/s (default: 0.25)
            duration: Duration to send commands in seconds (default: 10.0)
        """
        # FR3 joint names
        joint_names = [
            "fr3_joint1",
            "fr3_joint2", 
            "fr3_joint3",
            "fr3_joint4",
            "fr3_joint5",
            "fr3_joint6",
            "fr3_joint7"  # Wrist joint
        ]
        
        start_time = self.get_clock().now()
        rate = self.create_rate(100)  # 100 Hz command rate
        loop_count = 0
        
        while True:
            # Check if duration has elapsed using ROS time
            current_time = self.get_clock().now()
            elapsed = (current_time - start_time).nanoseconds / 1e9  # Convert to seconds
            
            if elapsed >= duration:
                break
            
            # Create joint state message with velocity commands
            # Only wrist joint (index 6) has non-zero velocity
            msg = JointState()
            msg.header.stamp = current_time.to_msg()
            msg.name = joint_names
            msg.velocity = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, wrist_velocity]
            
            self.joint_cmd_publisher.publish(msg)
            
            # Print status every 100 iterations (roughly every 1 second at 100Hz)
            loop_count += 1
            if loop_count % 100 == 0:
                self.get_logger().info(f"Elapsed: {elapsed:.1f}s, Sending wrist velocity: {wrist_velocity} rad/s")
            
            rate.sleep()
        
        # Send final stop command
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = joint_names
        msg.velocity = [0.0] * 7
        self.joint_cmd_publisher.publish(msg)
        
        self.get_logger().info("Test complete - wrist joint stopped")


def main(args=None):
    rclpy.init(args=args)
    
    # Filter out ROS 2 arguments to handle custom arguments properly
    filtered_args = remove_ros_args(sys.argv)
    
    # Parse command line arguments (skip the first element which is the script name)
    wrist_velocity = 0.25
    duration = 10.0
    
    if len(filtered_args) > 1:
        try:
            wrist_velocity = float(filtered_args[1])
        except ValueError:
            print(f"Invalid wrist velocity: {filtered_args[1]}. Expected a numeric value in rad/s.")
            sys.exit(1)
    
    if len(filtered_args) > 2:
        try:
            duration = float(filtered_args[2])
        except ValueError:
            print(f"Invalid duration: {filtered_args[2]}. Expected a numeric value in seconds.")
            sys.exit(1)
    
    client = ServoTestClient()
    client.send_wrist_velocity(wrist_velocity=wrist_velocity, duration=duration)
    
    rclpy.shutdown()


if __name__ == "__main__":
    main()
