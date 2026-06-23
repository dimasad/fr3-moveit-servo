# Testing moveit_servo with FR3 Fake Hardware

This guide provides step-by-step instructions for testing moveit_servo with the FR3 robot using fake hardware.

## Prerequisites

- Docker installed on your system
- The container image available at `ghcr.io/dimasad/fr3-moveit-servo:latest`
- The repository cloned locally

## Step 1: Start the Development Container

From the repository root directory, start the development container:

```bash
docker-compose up -d dev
```

This will start the container with the necessary environment. If you prefer to run it interactively in the foreground:

```bash
docker-compose run --rm dev bash
```

## Step 2: Build the Workspace

Inside the container, build the ROS 2 workspace:

```bash
cd /workspace
colcon build
source install/setup.bash
```

## Step 3: Launch moveit_servo with Fake Hardware

Start moveit_servo with fake hardware enabled:

```bash
ros2 launch fr3_moveit_servo fr3_moveit_servo.launch.py use_fake_hardware:=true
```

This will:
1. Start the MoveIt2 move group node with fake hardware
2. Initialize the servo node
3. Make the system ready to accept servo commands

You should see output indicating that the servo node is running and listening for commands.

## Step 4: Send Servo Commands to Rotate the Wrist

In a new terminal (or in the container), run the test client to send velocity commands:

```bash
# Option 1: Use default parameters (0.25 rad/s for 10 seconds)
ros2 run fr3_moveit_servo servo_test_client

# Option 2: Specify custom wrist velocity (in rad/s)
ros2 run fr3_moveit_servo servo_test_client 0.25

# Option 3: Specify both velocity and duration (in seconds)
ros2 run fr3_moveit_servo servo_test_client 0.25 10.0
```

### Expected Behavior

When the test client runs, you should see:
1. The test client prints: "Publishing joint velocity commands to /servo_node/delta_joint_cmds"
2. The test client prints: "Rotating wrist joint (FR3_joint7) at X rad/s" (where X is your specified velocity)
3. Every 2 seconds, it prints the elapsed time
4. After the specified duration, it prints "Test complete - wrist joint stopped"

### Monitoring Joint State

To verify that joint commands are being executed, in another terminal monitor the joint state:

```bash
ros2 topic echo /joint_states
```

You should see the joint7 position changing over time as the wrist rotates.

### Alternative: Manual Topic Publishing

If you want to manually test servo commands without the test client:

```bash
# In one terminal, publish velocity commands
ros2 topic pub -r 100 /servo_node/delta_joint_cmds sensor_msgs/JointState "{header: {frame_id: 'fr3_link0'}, name: ['fr3_joint1', 'fr3_joint2', 'fr3_joint3', 'fr3_joint4', 'fr3_joint5', 'fr3_joint6', 'fr3_joint7'], velocity: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.25]}"
```

## Step 5: Verify Joint Movement

Monitor the `/joint_states` topic to see the wrist joint (fr3_joint7) position changing:

```bash
ros2 topic echo /joint_states --field position
```

The 7th element in the position array should be continuously increasing (for positive velocity).

## Troubleshooting

### Issue: "Servo node not ready" or timeouts

**Solution:**
- Ensure the base MoveIt launch completed successfully
- Check that all MoveIt components are properly initialized by monitoring logs
- Verify the fake hardware flag is set correctly: `use_fake_hardware:=true`

### Issue: Joint commands not being executed

**Possible causes:**
1. Servo node timeout - commands must be sent continuously (within 0.1s intervals per `fr3_servo_params.yaml`)
2. Collision checking preventing motion - check logs for collision warnings
3. Incorrect joint names - FR3 joints are named `fr3_joint1` through `fr3_joint7`

**Solutions:**
- Increase command frequency or use the test client which publishes at 100 Hz
- Check servo node logs for collision warnings and adjust thresholds if needed
- Verify joint names match those in the FR3 URDF

### Issue: Servo node crashes

**Solution:**
- Check the servo node logs for error messages
- Ensure MoveIt configuration is correct for FR3
- Verify `franka_fr3_moveit_config` package is properly installed

### Issue: No motion despite commands

**Possible causes:**
1. Fake hardware not properly enabled
2. Joint velocity commands below minimum threshold
3. Servo smoothing configuration causing issues

**Solutions:**
- Verify `use_fake_hardware:=true` is set in the launch command
- Try increasing velocity to 0.5 rad/s or higher
- Check the smoothing parameters in `config/fr3_servo_params.yaml`

## Configuration

The servo parameters are configured in `src/fr3_moveit_servo/config/fr3_servo_params.yaml`:

- **move_group_name**: Set to `fr3_arm` (matches FR3 MoveIt config)
- **planning_frame**: Set to `fr3_link0` (FR3 base frame)
- **ee_frame_name**: Set to `fr3_link8` (FR3 end-effector)
- **command_out_topic**: Set to `/fr3_arm_controller/joint_trajectory` (compatible with franka_ros2)
- **publish_period**: 0.01s (100 Hz command rate)
- **incoming_command_timeout**: 0.1s (servo stops if no commands received for 100ms)

## Advanced Testing

### Cartesian Commands

To test Cartesian (twist) commands instead of joint commands:

```bash
# Publish Cartesian velocity commands (twist)
ros2 topic pub -r 100 /servo_node/delta_twist_cmds geometry_msgs/TwistStamped "{
  header: {frame_id: 'fr3_link0'},
  twist: {
    linear: {x: 0.0, y: 0.0, z: 0.0},
    angular: {x: 0.0, y: 0.0, z: 0.25}
  }
}"
```

This rotates the wrist by sending Cartesian rotation commands (0.25 rad/s around z-axis).

### Collision Checking

Verify that collision checking is working by:

1. Monitoring for collision warnings in servo node logs
2. Trying commands that would cause self-collisions
3. The servo should stop or reject commands that violate collision thresholds

### Performance Monitoring

Monitor servo performance:

```bash
# Check servo node status
ros2 node list | grep servo

# View detailed servo diagnostics
ros2 topic echo /diagnostics

# Monitor command latency
ros2 topic echo /servo_node/status
```

## Cleanup

To stop the container and remove it:

```bash
docker-compose down
```

To stop without removing (if running detached):

```bash
docker-compose stop dev
```

## References

- MoveIt Servo Documentation: https://moveit.picknik.ai/humble/doc/examples/servo_tutorial/servo_tutorial.html
- FR3 Documentation: https://franka.de/
- franka_ros2 Repository: https://github.com/frankarobotics/franka_ros2
