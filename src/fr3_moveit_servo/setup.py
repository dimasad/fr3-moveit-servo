from glob import glob

from setuptools import find_packages, setup

package_name = "fr3_moveit_servo"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="root",
    maintainer_email="root@todo.todo",
    description="Bring up moveit_servo for the Franka FR3 arm.",
    license="MIT",
    extras_require={
        "test": [
            "pytest",
            "launch_testing",
        ],
    },
    entry_points={
        "console_scripts": [
            "fake_hardware_nudge = fr3_moveit_servo.fake_hardware_nudge:main",
        ],
    },
)
