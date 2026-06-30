"""Bring up the Franka FR3 ros2_control controllers, MoveIt move_group, and
moveit_servo so the end-effector can be commanded in real time over a topic.

This mirrors the node graph that franka_fr3_moveit_config's own
moveit.launch.py builds (robot_state_publisher, ros2_control_node, the arm and
gripper controllers, move_group), then adds a standalone moveit_servo node on
top, fed with its own copy of the robot description/kinematics as required by
the moveit_servo ROS API.

Run with use_fake_hardware:=true for simulated testing; see the package
README for the manual testing procedure and what to change for the real
robot.
"""

import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    OpaqueFunction,
    RegisterEventHandler,
    Shutdown,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def load_yaml(package_name, file_path):
    package_path = get_package_share_directory(package_name)
    absolute_file_path = os.path.join(package_path, file_path)
    with open(absolute_file_path, "r") as file:
        return yaml.safe_load(file)


def launch_setup(context, *args, **kwargs):
    robot_ip = LaunchConfiguration("robot_ip")
    use_fake_hardware = LaunchConfiguration("use_fake_hardware")
    load_gripper = LaunchConfiguration("load_gripper")
    use_rviz = LaunchConfiguration("use_rviz")
    use_fake_hardware_str = use_fake_hardware.perform(context)

    # robot_description: same xacro the stock franka_fr3_moveit_config
    # moveit.launch.py uses, so move_group, ros2_control, and servo all agree
    # on the same kinematic model (the embedded <ros2_control> tags are
    # ignored by everything except ros2_control_node).
    franka_xacro_file = os.path.join(
        get_package_share_directory("franka_bringup"), "urdf", "franka_arm.urdf.xacro"
    )
    robot_description_content = Command([
        FindExecutable(name="xacro"), " ", franka_xacro_file,
        " hand:=", load_gripper,
        " robot_type:=fr3",
        " ee_id:=franka_hand",
        " robot_ip:=", robot_ip,
        " use_fake_hardware:=", use_fake_hardware,
        " fake_sensor_commands:=false",
    ])
    robot_description = {
        "robot_description": ParameterValue(robot_description_content, value_type=str)
    }

    franka_semantic_xacro_file = os.path.join(
        get_package_share_directory("franka_description"), "robots", "fr3", "fr3.srdf.xacro"
    )
    robot_description_semantic_content = Command([
        FindExecutable(name="xacro"), " ", franka_semantic_xacro_file,
        " hand:=", load_gripper,
        " ee_id:=franka_hand",
    ])
    robot_description_semantic = {
        "robot_description_semantic": ParameterValue(
            robot_description_semantic_content, value_type=str
        )
    }

    kinematics_config = {
        "robot_description_kinematics": load_yaml(
            "franka_fr3_moveit_config", "config/kinematics.yaml"
        )
    }
    joint_limits_config = {
        "robot_description_planning": load_yaml(
            "franka_fr3_moveit_config", "config/fr3_joint_limits.yaml"
        )
    }

    ompl_planning_pipeline_config = {
        "move_group": {
            "planning_plugins": ["ompl_interface/OMPLPlanner"],
            "request_adapters": [
                "default_planning_request_adapters/ResolveConstraintFrames",
                "default_planning_request_adapters/ValidateWorkspaceBounds",
                "default_planning_request_adapters/CheckStartStateBounds",
                "default_planning_request_adapters/CheckStartStateCollision",
            ],
            "response_adapters": [
                "default_planning_response_adapters/AddTimeOptimalParameterization",
                "default_planning_response_adapters/ValidateSolution",
                "default_planning_response_adapters/DisplayMotionPath",
            ],
            "start_state_max_bounds_error": 0.1,
        }
    }
    ompl_planning_pipeline_config["move_group"].update(
        load_yaml("franka_fr3_moveit_config", "config/ompl_planning.yaml")
    )

    moveit_controllers = {
        "moveit_simple_controller_manager": load_yaml(
            "franka_fr3_moveit_config", "config/fr3_controllers.yaml"
        ),
        "moveit_controller_manager": (
            "moveit_simple_controller_manager/MoveItSimpleControllerManager"
        ),
    }
    trajectory_execution = {
        "moveit_manage_controllers": True,
        "trajectory_execution.allowed_execution_duration_scaling": 1.2,
        "trajectory_execution.allowed_goal_duration_margin": 0.5,
        "trajectory_execution.allowed_start_tolerance": 0.01,
    }
    planning_scene_monitor_parameters = {
        "publish_planning_scene": True,
        "publish_geometry_updates": True,
        "publish_state_updates": True,
        "publish_transforms_updates": True,
    }

    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            robot_description,
            robot_description_semantic,
            kinematics_config,
            joint_limits_config,
            ompl_planning_pipeline_config,
            trajectory_execution,
            moveit_controllers,
            planning_scene_monitor_parameters,
        ],
    )

    rviz_config_file = os.path.join(
        get_package_share_directory("franka_fr3_moveit_config"), "rviz", "moveit.rviz"
    )
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="log",
        arguments=["-d", rviz_config_file],
        condition=IfCondition(use_rviz),
        parameters=[
            robot_description,
            robot_description_semantic,
            ompl_planning_pipeline_config,
            kinematics_config,
        ],
    )

    robot_state_publisher_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="both",
        parameters=[robot_description],
    )

    # ros2_control_node parameters: the stock franka controller config claims
    # the "effort" command interface, matching the real torque-controlled
    # hardware. Fake hardware has no dynamics and can only mirror a command
    # interface directly into the identically named state interface, so for
    # use_fake_hardware:=true an override switches fr3_arm_controller to the
    # "position" interface -- otherwise commanded motion would never show up
    # in /joint_states. See config/fr3_fake_controllers_override.yaml.
    ros2_controllers_path = os.path.join(
        get_package_share_directory("franka_fr3_moveit_config"),
        "config",
        "fr3_ros_controllers.yaml",
    )
    ros2_control_parameters = [robot_description, ros2_controllers_path]
    if use_fake_hardware_str.lower() == "true":
        ros2_control_parameters.append(
            os.path.join(
                get_package_share_directory("fr3_moveit_servo"),
                "config",
                "fr3_fake_controllers_override.yaml",
            )
        )

    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=ros2_control_parameters,
        remappings=[("joint_states", "franka/joint_states")],
        output={"stdout": "screen", "stderr": "screen"},
        on_exit=Shutdown(),
    )

    arm_controller_spawner = ExecuteProcess(
        cmd=[
            "ros2", "run", "controller_manager", "spawner", "fr3_arm_controller",
            "--controller-manager-timeout", "60",
            "--controller-manager", "/controller_manager",
        ],
        output="screen",
    )
    joint_state_broadcaster_spawner = ExecuteProcess(
        cmd=[
            "ros2", "run", "controller_manager", "spawner", "joint_state_broadcaster",
            "--controller-manager-timeout", "60",
            "--controller-manager", "/controller_manager",
        ],
        output="screen",
    )

    joint_state_publisher_node = Node(
        package="joint_state_publisher",
        executable="joint_state_publisher",
        parameters=[
            {"source_list": ["franka/joint_states", "fr3_gripper/joint_states"], "rate": 30}
        ],
    )

    franka_robot_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["franka_robot_state_broadcaster"],
        output="screen",
        condition=UnlessCondition(use_fake_hardware),
    )

    gripper_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([FindPackageShare("franka_gripper"), "launch", "gripper.launch.py"])
        ]),
        launch_arguments={
            "robot_ip": robot_ip,
            "use_fake_hardware": use_fake_hardware,
            "namespace": "",
        }.items(),
        condition=IfCondition(load_gripper),
    )

    servo_yaml_path = os.path.join(
        get_package_share_directory("fr3_moveit_servo"), "config", "fr3_servo_params.yaml"
    )
    servo_node = Node(
        package="moveit_servo",
        executable="servo_node",
        name="servo_node",
        output="screen",
        parameters=[
            servo_yaml_path,
            robot_description,
            robot_description_semantic,
            kinematics_config,
            joint_limits_config,
        ],
    )

    # Work around a moveit_servo/MoveIt limitation: with fake hardware the
    # simulated joints never move on their own, so servo_node's planning
    # scene never latches a current robot state and silently ignores all
    # commands (https://github.com/moveit/moveit2/issues/3040). Nudge every
    # arm joint once, after the controller is active, to unblock it. Not
    # needed (or wanted) on the real robot, which has continuously varying
    # joint state from the start.
    fake_hardware_nudge_node = Node(
        package="fr3_moveit_servo",
        executable="fake_hardware_nudge",
        output="screen",
        condition=IfCondition(use_fake_hardware),
    )
    nudge_after_controllers_active = RegisterEventHandler(
        OnProcessExit(
            target_action=arm_controller_spawner,
            on_exit=[TimerAction(period=2.0, actions=[fake_hardware_nudge_node])],
        ),
        condition=IfCondition(use_fake_hardware),
    )

    return [
        move_group_node,
        rviz_node,
        robot_state_publisher_node,
        ros2_control_node,
        arm_controller_spawner,
        joint_state_broadcaster_spawner,
        joint_state_publisher_node,
        franka_robot_state_broadcaster_spawner,
        gripper_launch,
        servo_node,
        nudge_after_controllers_active,
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            "robot_ip",
            default_value="172.16.0.2",
            description="IP address of the robot (ignored when use_fake_hardware is true)",
        ),
        DeclareLaunchArgument(
            "use_fake_hardware",
            default_value="false",
            description="Use simulated hardware instead of the real robot over FCI",
        ),
        DeclareLaunchArgument(
            "load_gripper",
            default_value="true",
            description="Bring up the Franka Hand gripper driver",
        ),
        DeclareLaunchArgument(
            "use_rviz",
            default_value="false",
            description="Launch RViz with the MoveIt display",
        ),
        OpaqueFunction(function=launch_setup),
    ])
