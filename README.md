# fr3-moveit-servo

ROS 2 package that brings up [`moveit_servo`](https://moveit.picknik.ai/main/doc/examples/realtime_servo/realtime_servo_tutorial.html)
for a Franka FR3 arm (with Franka Hand) so the end-effector can be commanded
in real time by publishing to a topic, with commands expressed in the
robot's base frame (`fr3_link0`).

Tested against the container image built from the `Dockerfile` in this repo
(ROS 2 Jazzy, MoveIt 2, `moveit_servo` 2.x, `franka_ros2` v3.4.0).

## Architecture

`launch/fr3_moveit_servo.launch.py` starts the same node graph as
`franka_fr3_moveit_config`'s own `moveit.launch.py`
(`robot_state_publisher`, `ros2_control_node`, the `fr3_arm_controller` and
`joint_state_broadcaster` controllers, the gripper driver, and `move_group`),
then adds a standalone `moveit_servo` node on top:

```
/servo_node/delta_twist_cmds   (geometry_msgs/TwistStamped, frame fr3_link0)
/servo_node/delta_joint_cmds   (control_msgs/JointJog)
/servo_node/pose_target_cmds   (geometry_msgs/PoseStamped)
         |
         v
   moveit_servo (servo_node)
         |  JointTrajectory @ 100 Hz
         v
/fr3_arm_controller/joint_trajectory
         |
         v
   fr3_arm_controller (JointTrajectoryController, franka_ros2)
         |
         v
   /joint_states
```

`move_group` is also brought up alongside `moveit_servo` (for planning,
RViz, and collision-scene management); `moveit_servo` itself runs an
independent `PlanningSceneMonitor` so wrist commands keep working even
without `move_group`.

### `moveit_servo`'s ROS API on Jazzy (no `start_servo` service)

The [MoveIt Servo tutorial](https://moveit.picknik.ai/main/doc/examples/realtime_servo/realtime_servo_tutorial.html)
documents a `~/start_servo` `std_srvs/Trigger` service. That service does
not exist in the `moveit_servo` 2.x rewrite shipped with Jazzy — the servo
loop runs continuously from node startup. Instead:

- `~/switch_command_type` (`moveit_msgs/srv/ServoCommandType`) must be
  called once to select `JOINT_JOG` (0), `TWIST` (1), or `POSE` (2) before
  any commands on the corresponding topic take effect.
- `~/pause_servo` (`std_srvs/srv/SetBool`) pauses/resumes the loop without
  stopping the node.

## Building

```bash
docker compose run --rm dev bash
source /opt/ros/jazzy/setup.bash
source /opt/ros/jazzy/franka/setup.bash
cd /workspace
colcon build --packages-select fr3_moveit_servo --symlink-install
source install/setup.bash
```

## Manual testing (simulation, fake hardware)

### 1 — Launch with fake hardware

```bash
ros2 launch fr3_moveit_servo fr3_moveit_servo.launch.py use_fake_hardware:=true
```

Wait for `servo_node` to log `Servo initialized successfully` and for the
log lines from `fake_hardware_nudge` (see
[Fake hardware caveats](#fake-hardware-caveats) below) — give it about
20–30 seconds for `move_group`, the controllers, and the gripper driver to
all come up.

### 2 — Select the command type

In a second terminal (inside the same container):

```bash
source /opt/ros/jazzy/setup.bash
source /opt/ros/jazzy/franka/setup.bash
source /workspace/install/setup.bash
ros2 service call /servo_node/switch_command_type moveit_msgs/srv/ServoCommandType "{command_type: 1}"  # TWIST
```

### 3 — Send a Cartesian twist command

Commands are `geometry_msgs/TwistStamped`, expressed in whatever frame you
put in `header.frame_id` — use `fr3_link0` (the robot's base/global frame)
to command the end-effector in global coordinates. The example below rotates
the wrist about the base Z axis at 0.5 rad/s:

```bash
ros2 topic pub /servo_node/delta_twist_cmds geometry_msgs/msg/TwistStamped \
  "{header: {stamp: now, frame_id: fr3_link0}, twist: {angular: {z: 0.5}}}" \
  --rate 50
```

> **`stamp: now` is required.** `moveit_servo` drops any command older than
> `incoming_command_timeout` (0.1 s). `ros2 topic pub` leaves `header.stamp`
> at zero unless you use the `now` placeholder, so an unstamped command is
> always treated as 56 years stale and silently ignored — the arm just
> won't move, with no error printed anywhere. The same applies to the
> `JointJog` and `PoseStamped` examples below. Code that builds messages
> itself (e.g. the launch test) must set `header.stamp` from the node's
> clock on every publish for the same reason.

Watch `ros2 topic echo /joint_states` in another terminal to see the joints
move. Motion stops automatically `incoming_command_timeout` (0.1 s) after
the last command, e.g. as soon as you kill the publisher.

### 4 — Send a joint-space or pose command

```bash
ros2 service call /servo_node/switch_command_type moveit_msgs/srv/ServoCommandType "{command_type: 0}"  # JOINT_JOG
ros2 topic pub /servo_node/delta_joint_cmds control_msgs/msg/JointJog \
  "{header: {stamp: now, frame_id: fr3_link0}, joint_names: [fr3_joint7], velocities: [0.3]}" \
  --rate 50
```

```bash
ros2 service call /servo_node/switch_command_type moveit_msgs/srv/ServoCommandType "{command_type: 2}"  # POSE
ros2 topic pub /servo_node/pose_target_cmds geometry_msgs/msg/PoseStamped \
  "{header: {stamp: now, frame_id: fr3_link0}, pose: {position: {x: 0.4, y: 0.0, z: 0.5}, orientation: {w: 1.0}}}" \
  --once
```

Pose commands are tracked continuously after a single publish (servo keeps
driving toward the target until it's reached), unlike twist/joint-jog
commands which only move the arm while fresh commands keep arriving.

### Fake hardware caveats

Two things only apply when `use_fake_hardware:=true`, and exist solely to
make simulated testing work — neither runs on the real robot:

- **`fr3_arm_controller` is reconfigured to claim the `position` command
  interface** instead of the real robot's `effort` interface
  (`config/fr3_fake_controllers_override.yaml`). The simulated
  `mock_components/GenericSystem` hardware has no dynamics: it can only
  mirror a command interface directly into the identically named state
  interface, so it can't turn a commanded torque into motion. With
  `use_fake_hardware:=false` the launch file never loads this override and
  the controller keeps using effort control.
- **A one-time "nudge"** (`fr3_moveit_servo/fake_hardware_nudge.py`) moves
  every arm joint a tiny distance (0.01 rad) and back, once, shortly after
  the controller activates. This works around a `moveit_servo`/MoveIt
  upstream issue where the servo node's planning scene only latches a
  current robot state after it observes a joint actually change value
  ([moveit2#3040](https://github.com/moveit/moveit2/issues/3040)) — with
  fake hardware the joints never move on their own, so without the nudge
  `servo_node` logs `Waiting to receive robot state update.` forever and
  ignores every command. The real robot has continuously varying joint
  state from the moment it powers on, so it never needs this.

## Automated test

`test/test_servo_joint_motion.py` launches the full stack with fake
hardware, selects `TWIST` mode, publishes a constant angular-Z twist for 3 s,
and asserts the arm joints moved by at least 0.1 rad in total.

```bash
cd /workspace
colcon build --packages-select fr3_moveit_servo
colcon test --packages-select fr3_moveit_servo --event-handlers console_direct+
colcon test-result --verbose
```

(A SIGSEGV from `move_group` and a `KeyboardInterrupt` traceback from
`fake_gripper_state_publisher.py` during test teardown are expected — both
happen after the test's assertions complete, while `launch_testing` is
tearing down the process tree, and aren't test failures.)

## Running on the real robot

1. **Drop `use_fake_hardware`** (or pass `use_fake_hardware:=false`, the
   default) and set `robot_ip:=<robot's FCI address>` (typically
   `172.16.0.2`):

   ```bash
   ros2 launch fr3_moveit_servo fr3_moveit_servo.launch.py robot_ip:=172.16.0.2
   ```

   This skips the fake-hardware controller override and the startup nudge
   (see [above](#fake-hardware-caveats)) and keeps `fr3_arm_controller` on
   effort/torque control, as required by the real hardware interface.

2. **Network** — the control PC must be on the same subnet as the robot,
   and the container needs `network_mode: host` (already set in
   `docker-compose.yaml`).

3. **Real-time kernel** — Franka FCI requires a real-time Linux kernel on
   the control PC. The container image does not provide this; it must be
   installed on the host.

4. **Unlock and enable the robot** via the Franka Desk web interface, and
   release any prior brakes/holds, before launching.

5. **Review velocity/acceleration limits** in
   `config/fr3_servo_params.yaml` and the controller gains in
   `franka_fr3_moveit_config`'s `fr3_ros_controllers.yaml` before commanding
   fast motions — `command_in_type: speed_units` means twist/joint-jog
   commands are interpreted directly in m/s and rad/s, with no implicit
   joystick-style scaling.

6. **Populate the planning scene** with any known obstacles in the
   workspace before sending commands, so `check_collisions: true` can
   actually protect the robot.

7. Still call `/servo_node/switch_command_type` before sending commands —
   that requirement doesn't change between simulation and the real robot.
