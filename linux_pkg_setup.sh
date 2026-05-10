#!/bin/bash
sudo apt update
sudo apt install -y cppcheck
sudo apt install -y clang-tidy-14
sudo apt install -y xclip
sudo apt install -y git-lfs
sudo apt install -y repo
git lfs install
#sudo apt install gitlab-ci-local=4.61.0
# For notifications
# sudo apt install python3-dbus libnotify-bin