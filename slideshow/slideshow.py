#!/usr/bin/env python3
# Image slideshow
# Copyright (c) 2016 SouthTech Network Solutions, LLC
#
# This program is free software; you can redistribute it and/or modify it 
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the
# Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
#
# Version: 1.0.4
# Authors: Tyler Adkisson
# Creation_date: 2016-11-05

import pi3d
import time, glob, os, signal

FPS = 30
DISPLAY_TIME = 11.0
FADE_TIME = 1.0
ERROR_FADE_TIME = 10.0
IMAGE_DIR = "/mnt/photos"
SCAN_TIME_BASE = 10 * 60
SCAN_TIME_ERROR = 1 * 60
SCAN_TIME = SCAN_TIME_BASE
ERROR_DIM_TIME = 10 * 60
FAIL_COUNT_TRIGGER = 5 # The number of failed loads in a row before scanning the dir again

# Set up display
display = pi3d.Display.create(background=(0.0, 0.0, 0.0, 1.0), frames_per_second=FPS)
shader = pi3d.Shader("2d_flat")
#transitionStep = 1.0 / (FPS * FADE_TIME);
#errorTransitionStep = 1.0 / (FPS * ERROR_FADE_TIME);
fileList = [None]

# Variables
currentIndex = -1
currentSlide = None
nextSlide = None
overlayAlpha = 0.0;
isTransitioning = False
lastSwitchTime = 0.0
lastScanTime = 0.0
lastDimTime = 0.0
currentFileIndex = -1;
loadFailures = 0
isErrored = False
isFadeIn = False

#fileLoaderThread = None

class Slide(pi3d.Canvas):
	def __init__(self, shader):
		super(Slide, self).__init__()
		self.set_shader(shader)
		self.set_alpha(0.0)
		
		self.width = 0.0
		self.height = 0.0
		self.x = 0.0
		self.y = 0.0
		self.alpha = 0.0
		
		self.is_ready = False
		self._fade_direction = 0
		self.fade_status = True
		self._fade_step = 1.0 / (FPS * 1.0)
		self._fill_screen = False
	
	def set_image(self, path):
		try:
			tex = pi3d.Texture(path, blend=True, mipmap=True)
		except:
			# File failed to load
			print("Failed to load image %s" % path)
			return False

		if self._fill_screen:
			# Stretch to fill screen
			wi = display.width
			hi = display.height
			xi = 0
			yi = 0
		else:
			# Center-fill image on display
			
			# SDTV Composite video output
			# We do special adjustments on composite SDTV (NTSC and PAL)
			#   to compensate for the non-square pixels (1.125:1 or 9:8 for NTSC)
			is_sdtv = display.width == 720 and display.height == 480
			disp_width = display.width
			xrat_tweak = 1.0
			if is_sdtv:
				disp_width = 640
				xrat_tweak = 1.125
			
			xrat = disp_width/tex.ix
			yrat = display.height/tex.iy
			
			if yrat < xrat:
				xrat = yrat
				
			wi, hi = tex.ix * xrat * xrat_tweak, tex.iy * xrat
			#wi, hi = tex.ix, tex.iy
			xi = (display.width - wi)/2
			yi = (display.height - hi)/2

		# Set canvas' texture
		# We increase size by 1 pixel as sometimes the top row of the image
		# wraps around to the bottom
		self.set_texture(tex)
		self.set_2d_size(w=wi, h=hi+1, x=xi, y=yi)
		self.set_alpha(1.0)
		self.alpha = 1.0
		
		# Store size and position
		self.width = wi
		self.height = hi+1
		self.x = xi
		self.y = yi
		
		#print("Image size: %i,%i %i x %i" % (self.x, self.y, self.width, self.height))
		
		#self.is_ready = True
		
		return True
	
	def set_fade_time(self, time):
		self._fade_step = 1.0 / (FPS * time)
	
	def set_fill_screen(self, value):
		self._fill_screen = value
	
	def hide(self):
		self.alpha = 0.0
		self.set_alpha(0.0)
	
	def show(self):
		self.alpha = 1.0
		self.set_alpha(1.0)
	
	def fadeInStep(self):
		#print("Fade in: Set alpha %f -> %f" % (self.alpha, self.alpha + transitionStep))
		if (self.alpha < 1.0):
			self.alpha += self._fade_step
		self.set_alpha(self.alpha)
		
		return self.alpha >= 1.0
		
	def fadeOutStep(self):
		#print("Fade out: Set alpha %f -> %f" % (self.alpha, self.alpha - transitionStep))
		if (self.alpha > 0.0):
			self.alpha -= self._fade_step
		self.set_alpha(self.alpha)
		
		return self.alpha <= 0.0

	def zoomInStep(self):
		self.width += 1
		self.height += 1
		
		self.x = (display.width - self.width) / 2.0
		self.y = (display.height - self.height) / 2.0
		
		#print("Set size to %i,%i %i x %i" % (self.x, self.y, self.width, self.height))
		self.set_2d_size(w=self.width, h=self.height, x=self.x, y=self.y)
	
	def fadeIn(self):
		self._fade_direction = 1
		
	def fadeOut(self):
		self._fade_direction = -1
	
	def update(self):
		if self._fade_direction == 1:
			self.fade_status = self.fadeInStep()
		elif self._fade_direction == -1:
			self.fade_status = self.fadeOutStep()
		else:
			self.fade_status = True
		
		if self.fade_status:
			self._fade_direction = 0

def scanImages():
	global currentFileIndex, fileList, lastScanTime, isErrored, SCAN_TIME
	#print("Scanning %s for new images" % IMAGE_DIR)
	fileList = sorted(glob.glob(IMAGE_DIR + "/*.*"))
	#print("scanImages() - Found %i images" % len(fileList))
	
	# In the case where no images can be found, display error image
	if len(fileList) == 0:
		showFailureImage()
	else:
		isErrored = False
		SCAN_TIME = SCAN_TIME_BASE
		if currentFileIndex > len(fileList):
			print("Index %i too far off end" % currentFileIndex)
			currentFileIndex = -1
		
		#if getTime() - lastSwitchTime > (2 * DISPLAY_TIME):
		#	print("Time since last load is too large %f" % (getTime() - lastSwitchTime))
		#	loadNextImage()
	lastScanTime = getTime()
	
def loadNextImage(overridePath=None):
	global currentFileIndex
	if not overridePath:
		if len(fileList) == 0:
			return
		
		currentFileIndex = (currentFileIndex + 1) % len(fileList)
		path = fileList[currentFileIndex]
	else:
		path = overridePath
	#print("Loading %i / %i" % (currentFileIndex+1, len(fileList)))
	#return loadImage(fileList[currentFileIndex], slides[(currentIndex+1) % len(slides)])
	return slides[(currentIndex+1) % len(slides)].set_image(path)

def switchImage():
	# Select next image to show
	global currentIndex, isTransitioning, nextSlide, lastSwitchTime
	global currentAlpha, nextAlpha
	currentIndex = (currentIndex + 1) % len(slides)
	#print("Showing %i" % currentIndex)
	nextSlide = slides[currentIndex]
	
	# Order the slides so transparency works
	# Z goes from front to back. So a Z of 0.5 is behind a Z of 0
	if currentSlide:
		currentSlide.positionZ(0.1)
		currentSlide.show()
		currentSlide.fadeOut()
	
	nextSlide.hide()
	nextSlide.positionZ(0.0)
	nextSlide.fadeIn()
	
	#isTransitioning = True
	lastSwitchTime = getTime()

def showFailureImage():
	global isErrored, currentIndex, errorString, lastDimTime, SCAN_TIME
	#print("Showing failure image %i" % currentIndex)
	if isErrored:
		return
	
	mountExists = os.system('ls ' + IMAGE_DIR + ' > /dev/null 2>&1') == 0
	if not mountExists:
		print("Photos directory is unavailable")
	
	#loadImage("ErrorImage.png", slides[(currentIndex+1) % len(slides)])
	#slides[(currentIndex+1) % len(slides)].set_image("ErrorImage.png")
	loadNextImage("ErrorImage.png")
	#loadNextImage("smpte.png")
	switchImage()
	isErrored = True
	
	# Dim the screen in the future and increase the rate of folder scanning
	lastDimTime = getTime()
	SCAN_TIME = SCAN_TIME_ERROR

def getTime():
	return time.monotonic()

def handleTERM(signum, frame):
	display.stop()

def handleHUP(signum, frame):
	scanImages()

# Attach signal handlers
signal.signal(signal.SIGTERM, handleTERM)
signal.signal(signal.SIGHUP, handleHUP)

# Prepare image buffers
slides = [None]*2;
for i in range(2):
	slides[i] = Slide(shader)
	slides[i].set_fade_time(FADE_TIME)

# Black overlay to dim the screen
fadeOverlay = Slide(shader)
fadeOverlay.set_fill_screen(True)
fadeOverlay.set_image("black.png")
fadeOverlay.hide()
fadeOverlay.positionZ(-0.1)
fadeOverlay.set_fade_time(ERROR_FADE_TIME)


# Populate image list
scanImages()
loadNextImage()

#keyboard = pi3d.Keyboard()
CAMERA = pi3d.Camera.instance()
CAMERA.was_moved = False #to save a tiny bit of work each loop

# Render to screen
while display.loop_running():
	if getTime() - lastScanTime >= SCAN_TIME:
		scanImages()
	if (not isErrored) and (getTime() - lastSwitchTime >= DISPLAY_TIME):
		switchImage()
	
	# If the error message is displayed for long enough
	#   slowly strobe as to not burn in the screen
	if isErrored and (getTime() - lastDimTime >= ERROR_DIM_TIME):
		if isFadeIn:
			fadeOverlay.fadeInStep()
		else:
			fadeOverlay.fadeOutStep()
		
		if fadeOverlay.alpha >= 1.0:
			isFadeIn = False
		elif fadeOverlay.alpha <= 0:
			isFadeIn = True
	
	# Draw images
	if currentSlide:
		currentSlide.update()
		currentSlide.draw()
		
	if nextSlide:
		nextSlide.update()
		nextSlide.draw()
	
	if isErrored:
		fadeOverlay.draw()
	
	# Load next image
	if nextSlide and nextSlide.fade_status:
		currentSlide = nextSlide
		currentSlide.positionZ(0.0)
		nextSlide = None
		
		# Go ahead and load the next image
		while not isErrored and not loadNextImage():
			loadFailures = loadFailures + 1
			if loadFailures >= FAIL_COUNT_TRIGGER:
				scanImages()
				continue
			time.sleep(2) # Wait before trying again
	
	#if keyboard.read() == 27: # Escape keys
	#	keyboard.close()
	#	display.stop()

# Clean up display
display.destroy()