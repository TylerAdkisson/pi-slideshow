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
# Version: 1.1
# Authors: Tyler Adkisson
# Creation_date: 2016-11-05
# Last_modified: 2016-12-26

import pi3d
import time, glob, os, signal
import threading
from subprocess import Popen, PIPE, STDOUT

#
# Adjust these parameters to fit your needs
#
FPS = 30							# Render FPS.  In most cases, you should leave this at 30
DISPLAY_TIME = 11.0					# How long to display each image, in seconds
FADE_TIME = 1.0						# Image fade duration, in seconds
ERROR_FADE_TIME = 10.0				# Error screen fade in duration, in seconds
IMAGE_DIR = "/mnt/photos/photos"	# Path containing jpg images (must be lower-case '.jpg' in filenames)
MUSIC_DIR = "/mnt/photos/music"		# Path containing mp3 music tracks, if desired
SCAN_TIME_BASE = 5 * 60				# How often to scan for new images/music
SCAN_TIME_ERROR = 1 * 60			# How often to scan while displaying the error image
SCAN_TIME = SCAN_TIME_BASE
ERROR_DIM_TIME = 10 * 60			# How long to wait before dimming the display while displaying the error image (displays black.png semi-transparent on top)
FAIL_COUNT_TRIGGER = 5				# The number of failed loads in a row before scanning the dir again


# Set up display
# The display is run at whatever resolution the console is currently running at
display = pi3d.Display.create(background=(0.0, 0.0, 0.0, 1.0), frames_per_second=FPS)
shader = pi3d.Shader("2d_flat")
#transitionStep = 1.0 / (FPS * FADE_TIME);
#errorTransitionStep = 1.0 / (FPS * ERROR_FADE_TIME);
fileList = [None]
audioPlayer = None
audioFileList = [None]

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

class AudioPlayer:
	def __init__(self):
		# Start mpg321 player with remote control
		self._playerProcess = None
		self._isPlaying = False
		self._lastFilename = ""
		self._playlist = [None]
		self._currentPlaylistIndex = 0
		self._manualStop = False
		self._isReady = False
		self._playFailCount = 0
		self._readAbort = False
		
		self._initPlayer()
	
	def __del__(self):
		if self._playerProcess:
			self.close()
	
	@property
	def isPlaying(self):
		return self._isPlaying
		
	
	def playFile(self, filename):
		if self._isPlaying:
			return
		
		# Instruct mpg321 to load a new file
		self._fileLoaded = False
		self._writePlayer("LOAD %s" % filename)
		self._lastFilename = filename
		self._manualStop = False
	
	def loadFileList(self, playlist):
		self._playlist = list(playlist)
		# Fix index if it falls off the end of the new playlist
		if self._currentPlaylistIndex >= len(playlist):
			self._currentPlaylistIndex = 0
	
	def playNextFile(self):
		self._currentPlaylistIndex += 1
		if self._currentPlaylistIndex >= len(self._playlist):
			self._currentPlaylistIndex = 0
		
		if len(self._playlist) == 0:
			return
		
		self.playFile(self._playlist[self._currentPlaylistIndex])
	
	def stop(self):
		if not self._isPlaying:
			return
		
		self._manualStop = True
		self._writePlayer("STOP")
	
	def togglePause(self):
		self._writePlayer("PAUSE")
	
	def close(self):
		self._writePlayer("QUIT")
		if self._readThread:
			self._readAbort = True
			self._readThread.join(2.0)
		
		self._playerProcess = None
	
	def _initPlayer(self):
		if self._playerProcess and self._playerProcess.poll() is None:
			# Still running
			return
		
		self._isReady = False
		self._playerProcess = Popen([
			"mpg321",
			"-R",
			"-N", "slideshowAudio",
			"--skip-printing-frames=-1"
		], stdout=PIPE, stdin=PIPE, stderr=STDOUT)
		
		# Read the player's output from a different thread
		self._readThread = threading.Thread(target=self._innerReadPlayer, name="mpg321 output reader", daemon=True)
		self._readThread.start()
		print("[AudioPlayer] Player created")
	
	def _writePlayer(self, command):
		self._playerProcess.poll()
		if self._playerProcess and self._playerProcess.returncode is None:
			loopCount = 0;
			while not self._isReady and loopCount < 10:
				time.sleep(0.1)
				loopCount += 1
			
			try:
				print("[AudioPlayer] Send command \"%s\"" % command)
				self._playerProcess.stdin.write((command + "\n").encode())
				self._playerProcess.stdin.flush()
			except BrokenPipeError:
				print("[AudioPlayer] Player closed")
	
	def _innerReadPlayer(self):
		# Read player output lines forever
		for line in self._playerProcess.stdout:
			if self._readAbort:
				print("[AudioPlayer] Told to abort read thread")
				break;
			
			self._processPlayerLine(line.decode())
		
		while self._playerProcess.returncode is None:
			self._playerProcess.poll()
			print("[AudioPlayer] Player process not exited yet")
		if self._playerProcess.returncode != -12 and self._playerProcess.returncode != 0:
			# Exited badly, restart shortly
			print("[AudioPlayer] mpg321 return code: %i" % self._playerProcess.returncode)
			time.sleep(3)
			self._initPlayer()
			self._playFailCount += 1
			if self._playFailCount >= 5:
				self._isPlaying = False
				self._playFailCount = 0
				scanMusic()
			
			if len(self._playlist) > 0:
				self.playNextFile()
		
	def _processPlayerLine(self, line):
		segments = line.split()
		
		print(line)
		
		if segments[0] == "@R":
			self._isReady = True
		elif segments[0] == "@S": # File loaded
			self._fileLoaded = True
			self._playFailCount = 0
			print("[AudioPlayer] Loaded %s" % self._playlist[self._currentPlaylistIndex])
		elif segments[0] == "@P" and segments[1] == "3" and not self._manualStop: # File finished playing, play next
			self.playNextFile()
		elif False and line.startswith(self._playlist[self._currentPlaylistIndex]):
			# The name of the file last attempted to load is output if there is an error
			# Try to load the next file
			self._playFailCount += 1
			if self._playFailCount >= 5:
				self._isPlaying = False
				self._playFailCount = 0
				scanMusic()
			
			if len(self._playlist) > 0:
				self.playNextFile()
		

def scanImages():
	global currentFileIndex, fileList, lastScanTime, isErrored, SCAN_TIME
	#print("Scanning %s for new images" % IMAGE_DIR)
	prevFileName = None
	if fileList and len(fileList) > 0 and currentFileIndex > -1:
		prevFileName = fileList[currentFileIndex]
	
	fileList = sorted(glob.glob(IMAGE_DIR + "/*.*"))
	#print("scanImages() - Found %i images" % len(fileList))
	
	# In the case where no images can be found, display error image
	if len(fileList) == 0:
		showFailureImage()
	else:
		isErrored = False
		SCAN_TIME = SCAN_TIME_BASE
		# Try to find the displaying image index in the new list
		newIndex = -1
		if prevFileName:
			tmpIndex = 0
			for path in fileList:
				if path == prevFileName:
					break
				tmpIndex += 1
			
			# Only set the new index if we actually found the file
			if tmpIndex != len(fileList):
				newIndex = tmpIndex
		
		currentFileIndex = newIndex
		#if currentFileIndex > len(fileList):
		#	print("Index %i too far off end" % currentFileIndex)
		#	currentFileIndex = -1
		
		#if getTime() - lastSwitchTime > (2 * DISPLAY_TIME):
		#	print("Time since last load is too large %f" % (getTime() - lastSwitchTime))
		#	loadNextImage()
	lastScanTime = getTime()

def scanMusic():
	global audioFileList, audioPlayer
	audioFileList = sorted(glob.glob(MUSIC_DIR + "/*.mp3"))
	
	# In the case where not audio is found, simply don't play any
	if len(audioFileList) == 0:
		#print("No audio found, not playing audio")
		return
	
	hasPlayer = audioPlayer is not None
	if not hasPlayer:
		audioPlayer = AudioPlayer()
	
	audioPlayer.loadFileList(audioFileList)
	if not hasPlayer:
		audioPlayer.playNextFile()
	

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
	# Z goes from front to back, origin at 0.  Thus -1 is in front of 0, which is in front of 1
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
scanMusic()
loadNextImage()

#keyboard = pi3d.Keyboard()
CAMERA = pi3d.Camera.instance()
CAMERA.was_moved = False #to save a tiny bit of work each loop

# Render to screen
while display.loop_running():
	if getTime() - lastScanTime >= SCAN_TIME:
		scanImages()
		scanMusic()
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
				scanMusic()
				continue
			time.sleep(2) # Wait before trying again
	
	#if keyboard.read() == 27: # Escape keys
	#	keyboard.close()
	#	display.stop()

# Clean up display
display.destroy()

# Clean up audio player
if audioPlayer:
	audioPlayer.close()