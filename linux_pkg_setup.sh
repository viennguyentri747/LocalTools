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

# DOCKER. Refer: https://docs.docker.com/engine/install/
# Add Docker's official GPG key:
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update