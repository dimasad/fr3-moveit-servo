FROM docker.io/library/ros:humble-ros-base

RUN apt-get update && apt-get install -y \
  # Install libfranka build depencencies
  build-essential \
  cmake \
  git \
  libeigen3-dev \
  libfmt-dev \
  libpoco-dev \
  ros-humble-pinocchio \
  ros-humble-rmw-cyclonedds-cpp \
  # Install Moveit2 and moveit servo
  ros-humble-moveit \
  ros-humble-moveit-servo \
  # Install missing franka_ros2 build dependencies (workaround franka_ros2 issue 160)
  ros-humble-controller-interface \
  ros-humble-hardware-interface \
  # Install ros packages
  python3-colcon-common-extensions \
  python3-colcon-mixin \
  python3-pip \
  python3-vcstool \
  && rm -rf /var/lib/apt/lists/*

# Install libfranka, franka_ros2 and franka_description
# Note: The versions need to be set according to your robot's system version
# https://franka.de/fr3-compatibility-matrix
# Adjust these parameters in the docker-compose.yml or in a .env file
ARG LIBFRANKA_VERSION=0.15.0
ARG FRANKA_ROS2_VERSION=v2.1.0
ARG FRANKA_DESCRIPTION_VERSION=1.3.0

RUN /bin/bash -c 'source /opt/ros/humble/setup.bash && \
mkdir -p /tmp/franka_ros2 && cd /tmp/franka_ros2 && \
  git clone --recursive https://github.com/frankarobotics/libfranka --branch ${LIBFRANKA_VERSION} && \
  git clone --recursive https://github.com/frankarobotics/franka_ros2.git --branch ${FRANKA_ROS2_VERSION} && \
  git clone --recursive https://github.com/frankarobotics/franka_description.git --branch ${FRANKA_DESCRIPTION_VERSION} && \
  apt-get update && \
  rosdep update && \
  rosdep install --from-paths . --ignore-src -r -y && \
  rm -rf /var/lib/apt/lists/* && \
  colcon build --install-base /opt/ros/humble/franka --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=off  && \
  cd .. && \ 
  rm -rf /tmp/franka_ros2 && \
  echo "source /opt/ros/humble/franka/setup.bash" >> ~/.bashrc && \
  echo "source /opt/ros/humble/franka/setup.sh" >> ~/.profile'
