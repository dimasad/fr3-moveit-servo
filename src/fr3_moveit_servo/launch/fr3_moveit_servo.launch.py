import os
import pathlib

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder

def generate_launch_description():
    # 1. Declare runtime arguments
    robot_ip_arg = DeclareLaunchArgument("robot_ip", default_value="172.16.0.2")
    use_fake_arg = DeclareLaunchArgument("use_fake_hardware", default_value="false")

    # 2. Include the official Franka MoveIt launch sequence
    franka_moveit_dir = get_package_share_directory("franka_moveit_config")
    base_moveit_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(franka_moveit_dir, "launch", "moveit.launch.py")),
        launch_arguments={
            "robot_ip": LaunchConfiguration("robot_ip"),
            "use_fake_hardware": LaunchConfiguration("use_fake_hardware"),
        }.items()
    )

    # 3. Pull configurations specifically for the Servo Node parameter mapping
    moveit_config = (
        MoveItConfigsBuilder("franka_fr3_moveit_config", package_path="share/franka_fr3_moveit_config")
        .robot_description()
        .robot_description_semantic()
        .robot_description_kinematics()
        .to_moveit_configs()
    )

    servo_yaml_path = str(
        pathlib.Path(__file__).parents[1] / "config" / "fr3_servo_params.yaml"
    )

    servo_node = Node(
        package="moveit_servo",
        executable="servo_node_main",
        name="servo_node",
        output="screen",
        parameters=[
            servo_yaml_path,
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
        ],
    )

    return LaunchDescription([
        robot_ip_arg,
        use_fake_arg,
        base_moveit_launch,
        servo_node
    ])
