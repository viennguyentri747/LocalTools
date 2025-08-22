#!/bin/bash
sudo apt update
sudo apt install gitlab-ci-local=4.61.0
sudo apt install cppcheck=2.7-1
sudo apt install clang-tidy-14
# For notifications
# sudo apt install python3-dbus libnotify-bin