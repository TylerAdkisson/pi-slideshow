# Raspberry Pi 3 Image Slideshow #

[![License: GPL v2](https://img.shields.io/badge/License-GPL%20v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

This is a network slideshow program intended for use on a Raspberry Pi 3, written in python 3.
This will rotate though and display all JPEG images (all files ending with `.jpg`) inside the path specified by the `IMAGE_DIR` variable.
Additionally, it will play any MP3 files in the path specified by `MUSIC_DIR` variable.

## Installation ##

The script needs python3, pi3d, numpy, and Pillow to run.  The following commands should help get you going (specify `sudo` before each command if you are not logged in as root):

```
# Install python packages
apt-get update
apt-get install -y python3 python3-dev python3-setuptools libjpeg-dev zlib1g-dev libpng12-dev libfreetype6-dev

# Install python libs
pip3 install pi3d
pip3 install numpy
pip3 install Pillow

# IMPORTANT: To play mp3s, you must also install mpg321:
apt-get install mpg321
```

Before running, ensure the file is executable by running

```
chmod +x slideshow.py
```
