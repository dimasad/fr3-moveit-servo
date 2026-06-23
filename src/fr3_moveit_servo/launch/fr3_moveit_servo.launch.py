import os
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, Command, FindExecutable
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def load_yaml(file_path):
    """Load a YAML file and return its contents as a dictionary."""
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def generate_launch_description():
    # 1. Declare runtime arguments
    robot_ip_arg = DeclareLaunchArgument("robot_ip", default_value="172.16.0.2")
    use_fake_arg = DeclareLaunchArgument("use_fake_hardware", default_value="false")

    # 2. Include the official Franka MoveIt launch sequence
    franka_moveit_dir = get_package_share_directory("franka_fr3_moveit_config")
    base_moveit_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(franka_moveit_dir, "launch", "moveit.launch.py")),
        launch_arguments={
            "robot_ip": LaunchConfiguration("robot_ip"),
            "use_fake_hardware": LaunchConfiguration("use_fake_hardware"),
        }.items()
    )

    # 3. Load servo configuration parameters from YAML file
    fr3_servo_config_dir = get_package_share_directory("fr3_moveit_servo")
    servo_yaml_file = os.path.join(fr3_servo_config_dir, "config", "fr3_servo_params.yaml")
    
    # Load YAML and wrap in moveit_servo key as expected by servo_node
    servo_yaml = load_yaml(servo_yaml_file)
    # Extract the nested ros__parameters and wrap in moveit_servo key
    servo_params = {"moveit_servo": servo_yaml.get("servo_node", {}).get("ros__parameters", {})}

    # 4. Load kinematics configuration from franka_fr3_moveit_config
    kinematics_file = os.path.join(
        get_package_share_directory("franka_fr3_moveit_config"),
        "config", "kinematics.yaml"
    )
    kinematics_yaml = load_yaml(kinematics_file)
    kinematics_params = {"kinematics_solver_search_resolution": {"fr3_arm": kinematics_yaml}}

    # Get robot description from franka_description package
    franka_xacro_file = os.path.join(
        get_package_share_directory("franka_description"),
        "robots", "fr3", "fr3.urdf.xacro"
    )

    robot_description_content = Command(
        [
            FindExecutable(name="xacro"),
            " ",
            franka_xacro_file,
            " hand:=true",
            " use_fake_hardware:=",
            LaunchConfiguration("use_fake_hardware"),
            " robot_ip:=",
            LaunchConfiguration("robot_ip"),
        ]
    )

    robot_description = {
        "robot_description": ParameterValue(robot_description_content, value_type=str)
    }

    # Get SRDF from franka_description package
    srdf_file = os.path.join(
        get_package_share_directory("franka_description"),
        "robots", "fr3", "fr3.srdf.xacro"
    )

    robot_description_semantic_content = Command(
        [
            FindExecutable(name="xacro"),
            " ",
            srdf_file,
            " hand:=true",
        ]
    )

    robot_description_semantic = {
        "robot_description_semantic": ParameterValue(robot_description_semantic_content, value_type=str)
    }

    servo_node = Node(
        package="moveit_servo",
        executable="servo_node_main",
        name="servo_node",
        output="screen",
        parameters=[
            robot_description,
            robot_description_semantic,
            servo_params,
            kinematics_params,
        ],
    )

    return LaunchDescription([
        robot_ip_arg,
        use_fake_arg,
        base_moveit_launch,
        servo_node
    ])
