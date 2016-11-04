# Raspberry Pi 3 Image Slideshow #

[![License: GPL v2](https://img.shields.io/badge/License-GPL%20v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

This is a network slideshow program intended for use on a Raspberry Pi 3, written in python 3.

## Installation ##

The script needs python3, pi3d, numpy, and Pillow to run.  The following commands should help get you going:

```
# Install python packages
apt-get update
apt-get install -y python3 python3-dev python3-setuptools libjpeg-dev zlib1g-dev libpng12-dev libfreetype6-dev

# Install python libs
pip3 install pi3d
pip3 install numpy
pip3 install Pillow
```

