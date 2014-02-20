#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright 2014, Thomas G. Dimiduk, Rebecca W. Perry, Aaron Goldfain
#
# This file is part of Camera Controller
#
# Camera Controller is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HoloPy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HoloPy.  If not, see <http://www.gnu.org/licenses/>.
'''
Provides live feed from a photon focus microscope camera with
an epix frame grabber. Software built to allow extension to
other cameras.

Allows user to save images and time series of images using a
naming convention set by the user.

For the photon focus, it is assumed that the camera is set to
Constant Frame Rate using the Photon Focus Remote software. In
this mode, the camera sends out images at regular intervals
regardless of whether they are being read or not.

The timer event is for refreshing the window viewed by the user
and for timing long, slow time series captures.

.. moduleauthor:: Rebecca W. Perry <perry.becca@gmail.com>
.. moduleauthor:: Aaron Goldfain
.. moduleauthor:: Thomas G. Dimiduk <tom@dimiduk.net>
'''
#from __future__ import print_function

import sys
import os
from PyQt4 import QtGui, QtCore
from PIL.ImageQt import ImageQt
from PIL import Image

from scipy.misc import toimage
import numpy as np
import time
import yaml
import json

import dummy_image_source
try:
    import epix_framegrabber
    epix_available = True
except ImportError:
    epix_framegrabber = None
    epix_available = False

from utility import mkdir_p
from QtConvenience import (make_label, make_HBox, make_VBox,
                           make_LineEdit, make_button,
                           make_control_group, make_checkbox,
                           CheckboxGatedValue)


#TODO: construct format file outside of the image grabbing loop, only
# when someone changes bit depth or ROI
#TODO: automate changing bit depth in PFRemote with the PF Remote DLL and some command like: SetProperty("DataResolution", Value(#1)")
#TODO: tie exposure time back to PFRemote ("SetProperty( "ExposureTime",Value(22.234))
#TODO: tie frame time back to PFRemote ("SetProperty( "ExposureTime",Value(22.234))
#TODO: limit text input for x and y in ROI to integers
#TODO: make sure that in a time series, the images stop getting collected at the end of the time series-- no overwriting the beginning of the buffer
#TODO: start slow time series by capturing an image, and start that as t=0
#TODO: add light source tab

class captureFrames(QtGui.QWidget):
    '''
    Fill rolling buffer, then save individual frames or time series on command.
    '''

    def __init__(self):
        if epix_available:
            self.camera = epix_framegrabber.PhotonFocusCamera()
        else:
            self.camera = dummy_image_source.DummyCamera()
        self.bit_depth = 12
        self.roi_shape = (1024, 1024)
        self.camera.open(self.bit_depth, self.roi_shape)

        super(captureFrames, self).__init__()
        self.initUI()
        # we have to set this text after the internals are initialized since the filename is constructed from widget values
        self.createFilename()
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self, self.close)


    def initUI(self):

        QtGui.QToolTip.setFont(QtGui.QFont('SansSerif', 10))

        #Timer is for updating for image display and text to user
        self.timerid = self.startTimer(30)  # event every x ms

        self.image = np.random.random(self.roi_shape)*100
        self.cameraNum = 0  # to keep track of which camera is in use

        #display for image coming from camera
        self.frame = QtGui.QLabel(self)
        self.frame.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)

        #########################################
        # Tab 1, Main controls viewing/saving
        #########################################

        self.livebutton = make_button('Live\nf1', self.live, self, QtGui.QKeySequence('f1'))
        self.livebutton.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")
        self.freeze = make_button('Freeze\nf2', self.live, self, QtGui.QKeySequence('f2'))
        self.freeze.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")

        self.save = make_button('Save\nesc', self.saveImage, self, QtGui.QKeySequence('esc'), width=200,
                                tooltip='Saves the frame that was current when this button was clicked. Freeze first if you want the frame to stay visible.')
        self.save.setCheckable(True)
        self.save.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")

        self.timeseries = make_button('Collect and Save\nTime Series',
                                      self.collectTimeSeries, self, QtGui.QKeySequence('f3'), width=200)
        self.timeseries.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")
        self.timeseries.setCheckable(True)

        self.timeseries_slow = make_button('Collect and Save\nSlow Time Series (<= 1 fps)',
                                           self.collectTimeSeries, self, QtGui.QKeySequence('f4'), width=200)
        self.timeseries_slow.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")
        self.timeseries_slow.setCheckable(True)

        make_control_group(self, [self.livebutton, self.freeze],
                           default=self.livebutton)
        #TODO: fix control group, should you be allowed to do multiple at once?
        #make_control_group(self, [self.save, self.timeseries, self.timeseries_slow])

        self.numOfFrames = make_LineEdit('10', width=75)

        self.numOfFrames2 = make_LineEdit('10', width=75)
        self.interval = make_LineEdit('0.5', width=75)

        self.applybackground = make_button('Apply Background',
                                           self.select_background, self, width=200)
        self.applybackground.setCheckable(True)
        self.applybackground.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")
        self.background_image_filename = make_label("No background applied")
        self.background_image = None

        self.outfiletitle = QtGui.QLabel()
        self.outfiletitle.setText('Your next image will be saved as\n(use filenames tab to change):')
        self.outfiletitle.setFixedHeight(50)
        self.outfiletitle.setWordWrap(True)
        self.outfiletitle.setStyleSheet('font-weight:bold')

        self.path = QtGui.QLabel()

        tab1 = QtGui.QWidget()

        make_VBox([
                   make_HBox([self.livebutton,
                   self.freeze,1]),
                   1,
                   'Save image showing when clicked',
                   self.save,
                   1,
                   'Store the requested number of images to the buffer and then save the files to hard disk. \n\nThe frame rate is set in the Photon Focus Remote software.',
                   make_HBox([self.timeseries, self.numOfFrames, 'frames', 1]),
                   1,
                   'Equivalent to clicking "Save" at regular intervals',
                   make_HBox([self.timeseries_slow,
                              make_VBox([make_HBox([self.numOfFrames2, 'frames', 1]),
                                         make_HBox([self.interval, 'minutes apart', 1])])]),
                   1,
                   "Automatically Apply a background image \n(only for display, it still saves the raw images)",
                   self.applybackground,
                   self.background_image_filename,
                   self.outfiletitle,
                   self.path, 1],
                  tab1)


        ###################################################################
        # Tab 2, camera settings need to be set in Photon Focus remote too

        ###################################################################

        tab2title = QtGui.QLabel()
        tab2title.setText('Modify camera settings')
        tab2title.setAlignment(QtCore.Qt.AlignTop)
        tab2title.setWordWrap(True)

        camera = QtGui.QLabel()
        camera.setFixedHeight(30)
        camera.setAlignment(QtCore.Qt.AlignBottom)
        camera.setText('Camera:')
        camera.setStyleSheet('font-weight:bold')

        self.cameraChoices = QtGui.QComboBox()
        self.cameraChoices.addItem("Simulated")
        if epix_available:
            self.cameraChoices.addItem("Photon Focus")
            self.cameraChoices.setCurrentIndex(1)
        self.cameraChoices.setFixedWidth(150)
        self.cameraChoices.activated[str].connect(self.change_camera)
        #self.bitdepth.activated[str].connect(self.reopen_camera)

        bit = QtGui.QLabel()
        bit.setFixedHeight(30)
        bit.setAlignment(QtCore.Qt.AlignBottom)
        bit.setText('Bit Depth:')
        bit.setStyleSheet('font-weight:bold')

        self.bitdepthChoices = QtGui.QComboBox()
        self.bitdepthChoices.addItem("8 bit")
        self.bitdepthChoices.addItem("10 bit")
        self.bitdepthChoices.addItem("12 bit")
        #self.bitdepthChoices.addItem("14 bit")
        self.bitdepthChoices.setFixedWidth(150)
        self.bitdepthChoices.setCurrentIndex(2)
        self.bitdepthChoices.activated[str].connect(self.reopen_camera)
        #self.bitdepth.activated[str].connect(self.reopen_camera)

        roititle = QtGui.QLabel()
        roititle.setText('Frame size in pixels. Default to maximum size.\nRegions are taken from top left.')
        roititle.setFixedHeight(40)
        roititle.setWordWrap(True)
        roititle.setAlignment(QtCore.Qt.AlignTop)

        roiSizeLabel = QtGui.QLabel()
        roiSizeLabel.setFixedHeight(30)
        roiSizeLabel.setAlignment(QtCore.Qt.AlignBottom)
        roiSizeLabel.setText('Region of Interest Size:')
        roiSizeLabel.setStyleSheet('font-weight:bold')

        self.roiSizeChoices = QtGui.QComboBox()
        self.roiSizeChoices.addItem("1024 x 1024")
        self.roiSizeChoices.addItem("512 x 512")
        self.roiSizeChoices.addItem("256 x 256 ")
        self.roiSizeChoices.addItem("128 x 128")
        self.roiSizeChoices.addItem("64 x 64")
        self.roiSizeChoices.setFixedWidth(150)
        self.roiSizeChoices.activated[str].connect(self.reopen_camera)

        roiLocLabel = QtGui.QLabel()
        roiLocLabel.setFixedHeight(45)
        roiLocLabel.setAlignment(QtCore.Qt.AlignBottom)
        roiLocLabel.setText('ROI Location: \nTODO')
        roiLocLabel.setStyleSheet('font-weight:bold')

        self.framerate = QtGui.QLabel()
        self.framerate.setText('Must match the data output type in PFRemote')

        tab2 = QtGui.QWidget()

        make_VBox([
                   camera, self.cameraChoices,
                   bit, self.bitdepthChoices,
                   self.framerate,
                   roiSizeLabel, roititle, self.roiSizeChoices,
                   roiLocLabel,
                   1],
                  tab2)



        #########################################
        # Tab 3, Options for saving output files
        #########################################

        tab3 = QtGui.QWidget()

        tab3title = make_label(
            'Select the output format of your images and set up automatically '
            'generated file names for saving images',
            height=50, align='top')

        ###
        fileTypeLabel = make_label('Output File Format:', bold=True, height=30,
                                   align='bottom')

        self.outputformat = QtGui.QComboBox()
        self.outputformat.addItem(".tif")
        self.outputformat.setFixedWidth(150)
        self.outputformat.activated[str].connect(self.createFilename)

        ###

        self.include_filename_text = CheckboxGatedValue(
            "Include this text:", make_LineEdit("image"), self.createFilename,
            True)
        self.include_current_date = CheckboxGatedValue(
            "include date", lambda : time.strftime("%y_%m_%d_"))
        self.include_current_time = CheckboxGatedValue(
            "include time", lambda : time.strftime("%H_%M_%S"))
        self.include_incrementing_image_num = CheckboxGatedValue(
            "include an incrementing number, next is:", make_LineEdit('0000'),
            self.createFilename, True)


        ###
        self.browse = make_button("Browse", self.select_directory, self,
                                  height=30, width=100)
        self.root_save_path = make_LineEdit("C:/Users/manoharanlab/data/[YOUR NAME]",
                                            self.createFilename)
        self.include_incrementing_dir_num = CheckboxGatedValue(
            "include an incrementing number, next is:", make_LineEdit('00'),
            self.createFilename, True)
        self.include_extra_dir_text = CheckboxGatedValue(
            "use the following text:", make_LineEdit(None), self.createFilename)

        self.saveMetasYes = make_checkbox('Save metadata as yaml file when saving image?')

        self.outfile = make_label("", height=50, align='top')

        self.reset = make_button("Reset to Default values", self.resetSavingOptions, self, height=None, width=None)
        self.reset.setDefault(True)

        self.path_example = make_label("")
        tab3_layout = make_VBox([
            tab3title,
            fileTypeLabel,
            self.outputformat,
            make_label('File Name:', bold=True, align='bottom', height=30),
            self.include_filename_text,
            self.include_current_date,
            self.include_current_time,
            self.include_incrementing_image_num,
            ######
            make_label('Directory:', bold=True, height=30, align='bottom'),
            self.browse,
            self.root_save_path,
            self.include_incrementing_dir_num,
            self.include_extra_dir_text,
            self.saveMetasYes,
            make_label("If you save an image with these settings it will be saved as:", height=50, bold=True, align='bottom'),
            self.path_example,
            1,
            self.reset
        ], tab3)


        # TODO: make this function get its values from the defaults we give things
#        self.resetSavingOptions() #should set file name


        ################################
        # Tab 4, place to enter metadata
        ################################

        tab4 = QtGui.QWidget()
        tab4_layout = QtGui.QVBoxLayout(tab4)

        tab4title = QtGui.QLabel()
        tab4title.setText('User supplied metadata can be saved with button here, or alongside every image with a setting on the filenames tab')
        tab4title.setFixedHeight(50)
        tab4title.setWordWrap(True)
        tab4title.setAlignment(QtCore.Qt.AlignTop)
        tab4_layout.addWidget(tab4title)

        microLabel = QtGui.QLabel()
        microLabel.setFixedHeight(30)
        microLabel.setAlignment(QtCore.Qt.AlignBottom)
        microLabel.setText('Microscope:')
        microLabel.setStyleSheet('font-weight:bold')

        self.microSelections = QtGui.QComboBox(editable=True)
        self.microSelections.setFixedWidth(250)
        self.microSelections.addItem("Uberscope")
        self.microSelections.addItem("Mgruberscope")
        self.microSelections.addItem("George")
        self.microSelections.addItem("Superscope")
        self.microSelections.addItem("Other: (edit to specify)")

        lightLabel = QtGui.QLabel()
        lightLabel.setFixedHeight(30)
        lightLabel.setAlignment(QtCore.Qt.AlignBottom)
        lightLabel.setText('Light source:')
        lightLabel.setStyleSheet('font-weight:bold')

        self.lightSelections = QtGui.QComboBox(editable=True)
        self.lightSelections.setFixedWidth(250)
        self.lightSelections.addItem("Red Laser, 660 nm")
        self.lightSelections.addItem("White LED Illuminator")
        self.lightSelections.addItem("Other: (edit to specify)")

        objectiveLabel = QtGui.QLabel()
        objectiveLabel.setFixedHeight(30)
        objectiveLabel.setAlignment(QtCore.Qt.AlignBottom)
        objectiveLabel.setText('Microscope Objective:')
        objectiveLabel.setStyleSheet('font-weight:bold')

        self.objectiveSelections = QtGui.QComboBox(editable=True)
        self.objectiveSelections.addItem("Nikon 60x Water Immersion, Correction Collar:")
        self.objectiveSelections.addItem("Nikon 100x Oil Immersion")
        self.objectiveSelections.addItem("Nikon 10x, air")
        self.objectiveSelections.addItem("Nikon 40x, air")
        self.objectiveSelections.addItem("Other: (edit to specify)")

        tubeLensLabel = QtGui.QLabel()
        #tubeLensLabel.setFixedHeight(30)
        tubeLensLabel.setAlignment(QtCore.Qt.AlignBottom)
        tubeLensLabel.setText('Using additional 1.5x tube lens?')
        tubeLensLabel.setStyleSheet('font-weight:bold')

        self.tubeYes = QtGui.QCheckBox()
        self.tubeYes.setText("Yes")

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(tubeLensLabel)
        hbox.addWidget(self.tubeYes)
        hbox.addStretch(1)

        notesLabel = QtGui.QLabel()
        notesLabel.setFixedHeight(30)
        notesLabel.setAlignment(QtCore.Qt.AlignBottom)
        notesLabel.setText('Notes (e.g. details about your sample):')
        notesLabel.setStyleSheet('font-weight:bold')

        self.metaNotes = QtGui.QLineEdit()

        self.saveMetaData = QtGui.QPushButton('Save Metadata To Yaml', self)
        self.saveMetaData.setFixedHeight(30) #attribute from qwidget class
        self.saveMetaData.setFixedWidth(200)
        self.saveMetaData.clicked.connect(self.saveMetadata)

        tab4_layout.addWidget(microLabel)
        tab4_layout.addWidget(self.microSelections)
        tab4_layout.addWidget(lightLabel)
        tab4_layout.addWidget(self.lightSelections)
        tab4_layout.addWidget(objectiveLabel)
        tab4_layout.addWidget(self.objectiveSelections)

        tab4_layout.addLayout(hbox)
        tab4_layout.addWidget(notesLabel)
        tab4_layout.addWidget(self.metaNotes)
        tab4_layout.addWidget(self.saveMetaData)
        tab4_layout.addStretch(1)

        #TODO: put this in a function and update when any metadata changes
        #package metadata for saving in tif tag "description"
        self.metadata = dict(microscope='george', wavelength='600', lightsource='white')
        self.metadata = json.dumps(self.metadata)


        ################################
        # Tab 5, place to enter metadata
        ################################
        tab5 = QtGui.QWidget()
        tab5_layout = QtGui.QVBoxLayout(tab5)

        sqtitle = QtGui.QLabel()
        sqtitle.setText('Square:')
        sqtitle.setFixedHeight(30)
        sqtitle.setStyleSheet('font-weight:bold')
        sqtitle.setWordWrap(True)
        sqtitle.setAlignment(QtCore.Qt.AlignTop)

        self.edgeLabel = QtGui.QLabel()
        self.edgeLabel.setText("Edge Length (pixels):")
        self.edgeEntry = QtGui.QLineEdit()

        hbox4 = QtGui.QHBoxLayout()
        hbox4.addWidget(self.edgeLabel)
        hbox4.addWidget(self.edgeEntry)


        self.cornerLabel = QtGui.QLabel()
        self.cornerLabel.setText("Upper Left Corner Location (row, col):")
        self.cornerRowEntry = QtGui.QLineEdit()
        self.cornerColEntry = QtGui.QLineEdit()

        hbox5 = QtGui.QHBoxLayout()
        hbox5.addWidget(self.cornerLabel)
        hbox5.addWidget(self.cornerRowEntry)
        hbox5.addWidget(self.cornerColEntry)

        self.sqcolor = QtGui.QComboBox()
        self.sqcolor.addItem("Red")
        self.sqcolor.addItem("Green")
        self.sqcolor.addItem("Blue")
        self.sqcolor.setCurrentIndex(1)
        self.sqcolor.setFixedWidth(150)


        cirtitle = QtGui.QLabel()
        cirtitle.setText('Circle:')
        cirtitle.setFixedHeight(30)
        cirtitle.setStyleSheet('font-weight:bold')
        cirtitle.setWordWrap(True)
        cirtitle.setAlignment(QtCore.Qt.AlignTop)



        self.diamLabel = QtGui.QLabel()
        self.diamLabel.setText("Diameter (pixels):")
        self.diamEntry = QtGui.QLineEdit()

        hbox6 = QtGui.QHBoxLayout()
        hbox6.addWidget(self.diamLabel)
        hbox6.addWidget(self.diamEntry)


        self.centerLabel = QtGui.QLabel()
        self.centerLabel.setText("Center Location (row, col):")
        self.centerRowEntry = QtGui.QLineEdit()
        self.centerColEntry = QtGui.QLineEdit()

        hbox7 = QtGui.QHBoxLayout()
        hbox7.addWidget(self.centerLabel)
        hbox7.addWidget(self.centerRowEntry)
        hbox7.addWidget(self.centerColEntry)

        self.circolor = QtGui.QComboBox()
        self.circolor.addItem("Red")
        self.circolor.addItem("Green")
        self.circolor.addItem("Blue")
        self.circolor.setCurrentIndex(1)
        self.circolor.setFixedWidth(150)



        gridtitle = QtGui.QLabel()
        gridtitle.setText('Grid:')
        gridtitle.setFixedHeight(30)
        gridtitle.setStyleSheet('font-weight:bold')
        gridtitle.setWordWrap(True)
        gridtitle.setAlignment(QtCore.Qt.AlignTop)

        self.meshLabel = QtGui.QLabel()
        self.meshLabel.setText("Grid Square Size (pixels):")
        self.meshSizeEntry = QtGui.QLineEdit()

        hbox8 = QtGui.QHBoxLayout()
        hbox8.addWidget(self.meshLabel)
        hbox8.addWidget(self.meshSizeEntry)

        self.gridcolor = QtGui.QComboBox()
        self.gridcolor.addItem("Red")
        self.gridcolor.addItem("Green")
        self.gridcolor.addItem("Blue")
        self.gridcolor.setCurrentIndex(1)
        self.gridcolor.setFixedWidth(150)


        tab5_layout.addWidget(sqtitle)
        tab5_layout.addLayout(hbox4)
        tab5_layout.addLayout(hbox5)
        tab5_layout.addWidget(self.sqcolor)
        tab5_layout.addStretch(1)
        tab5_layout.addWidget(cirtitle)
        tab5_layout.addLayout(hbox6)
        tab5_layout.addLayout(hbox7)
        tab5_layout.addWidget(self.circolor)
        tab5_layout.addStretch(1)
        tab5_layout.addWidget(gridtitle)
        tab5_layout.addLayout(hbox8)
        tab5_layout.addWidget(self.gridcolor)
        tab5_layout.addStretch(1)

        ################################################

        tab_widget = QtGui.QTabWidget()
        tab_widget.addTab(tab1, "Image Capture")
        tab_widget.addTab(tab2, "Camera")
        tab_widget.addTab(tab3, "Filenames")
        tab_widget.addTab(tab4, "Meta Data")
        tab_widget.addTab(tab5, "Overlays")

        #Text at bottom of screen
        self.imageinfo = QtGui.QLabel()
        self.imageinfo.setText('Max pixel value: '+str(0))
        #self.imageinfo.setStyleSheet('font-weight:bold')
        self.imageinfo.setAlignment(QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft)

        self.sphObject = QtGui.QLabel(self)
        self.sphObject.setAlignment(QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft)
        self.sphObject.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.schemaObject = QtGui.QLabel(self)
        self.schemaObject.setWordWrap(True)
        self.schemaObject.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        self.warning = QtGui.QLabel(self)
        self.warning.setText('')
        self.warning.setStyleSheet('font-size: 20pt; color: red')
        self.warning.setGeometry(30,300,350,100)
        self.warning.setWordWrap(True)

        #show live images when program is opened
        self.live()

        #################
        #MASTER LAYOUT
        #################

        #puts all the parameter adjustment buttons together
        vbox = QtGui.QVBoxLayout()
        vbox.addWidget(tab_widget)
        vbox.addStretch(1)

        contentbox = QtGui.QHBoxLayout()
        contentbox.addWidget(self.frame) #image
        contentbox.addLayout(vbox)

        textbox = QtGui.QVBoxLayout()
        textbox.addWidget(self.imageinfo)
        textbox.addStretch(1)

        largevbox = QtGui.QVBoxLayout()
        largevbox.addLayout(contentbox)
        largevbox.addStretch(1)
        largevbox.addLayout(textbox)

        self.setLayout(largevbox)

        self.setGeometry(100, 100, 800, 500) #window size and location
        self.setWindowTitle('Camera Controller')
        self.show()

    def timerEvent(self, event):
        #print time.time()
        #obtain most recent image

        frame_number = self.camera.get_frame_number()
        self.image = self.camera.get_image()

        self.roi_shape = np.shape(self.image)

        #show most recent image
        self.showImage()

        #show info about this image
        def set_imageinfo(maxval=self.image.max(), frame_number=frame_number):
            portion = round(np.sum(self.image == maxval)/(1.0*np.size(self.image)),3)
            self.imageinfo.setText(
                'Max pixel value: {}, Fraction at max: {}, Frame number in buffer: {}'.format(maxval, portion, frame_number))

        set_imageinfo()

        #check if a slow time series was requested and if the current time is a time to be recorded
        if self.timeseries_slow.isChecked() and self.lastimageflag == False:
            currentmod = round(time.time(),0)%(round(float(str(self.interval.text()))*60,0))
            if currentmod == 0 and self.lastmod !=0: #TODO: replace with actual interval between images
                self.imageCounter +=1
                if self.imageCounter == float(str(self.numOfFrames2.text())):
                    self.lastimageflag = True
                    self.timeseries_slow.setChecked(False)
                self.saveImages()
            self.lastmod = currentmod

        #check if a time series to save has been finished collecting:
        if self.timeseries.isChecked():
            if self.camera.finished_live_sequence():
                time.sleep(0.1)
                set_imageinfo()
                self.freeze.toggle()
                self.saveImageOrYaml(True, True)

    @property
    def filename(self):
        root = str(self.root_save_path.text())
        dirextra = "".join([self.include_incrementing_dir_num.text(),
                            self.include_extra_dir_text.text()])
        filename = "".join([self.include_current_date.text(),
                            self.include_current_time.text(),
                            self.include_filename_text.text(),
                            self.include_incrementing_image_num.text(),
                            '.tif'])
        return os.path.join(*[a for a in [root, dirextra, filename] if a])

    def saveImage(self):
        self.saveImageOrYaml(True)

    def saveImages(self):
        self.saveImageOrYaml(True, False, True)

    def saveMetadata(self):
        self.saveImageOrYaml(False)

    def saveImageOrYaml(self, img, series = False, slowseries = False):
        '''
        For saving images and metadata to locations on hard disk. Autogenerates a suggested file name
        based on the user's input in the "Saving" tab. User may also type in a
        different name at this point. User will be asked to change name if the file
        already exists.

        Is not allowed to overwrite any files.
        '''

        # img is true if saving an image, false if saving a yaml file
        if img and series and self.include_incrementing_image_num.isChecked(): #include number
            self.keynumber.setText(str(0).zfill(4))
            self.createFilename()

        #Write yaml file
        if img and self.saveMetaYes.checkState():
            self.saveImageOrYaml(False)

        savingcheck = QtGui.QInputDialog()

        #get correct filename for yamls
        if img:
            fname = self.filename
        else:
            tempname = self.filename
            filetype = tempname.split('.')[-1]
            n_filetype = filetype.__len__()
            fname = tempname[:-n_filetype] +'yaml'

        #grab image for saving
        selectedFrame = Image.fromarray(self.image)

        usersfilename = fname

        if series == False:
            numOfFrames = 1
        else:
            #TODO: implement numOfFrames2
            numOfFrames = int(str(self.numOfFrames.text()))

        for i in range(1,numOfFrames+1):
            if series == True:
                #get each image
                selectedFrame = self.camera.get_image(i)
                selectedFrame = toimage(selectedFrame) #PIL image
                usersfilename = self.filename

            #TODO: move overwriting check elsewhere
            '''#don't overwrite files
            if os.path.isfile(str(usersfilename)):
                directorywarning = QtGui.QMessageBox()
                directorywarning.setWindowTitle('Filename Error')
                directorywarning.setText('Overwriting data not allowed. Choose a different name or delete the item with the same name.')
                ret = directorywarning.exec_()
                self.saveImageOrYaml(img) #cycle back to try again

            else:'''

            directory, filename = os.path.split(str(usersfilename))

            mkdir_p(directory)

            if os.path.isdir(directory):
                if img:#save image
                    if usersfilename[-4:]== '.tif':
                        selectedFrame.save(str(usersfilename), autoscale=False)
                    else:
                        selectedFrame.save(str(usersfilename), autoscale=False)
                else:#write yaml
                    data = self.createYaml()
                    with open(str(usersfilename), 'w') as outfile:
                        outfile.write( yaml.dump(data, default_flow_style=True) )

                #saving was successful, advance the incrementers if they are being used
                #numbered file, increment if checked and if saving an image
                if img and self.include_incrementing_image_num.isChecked(): #include number
                    int(self.keynumber.text()) + 1
                    self.keynumber.setText(str((int(self.keynumber.text())+ 1)).zfill(4))
                self.createFilename()

                if not slowseries:
                    if series == False or i == numOfFrames:
                        #only increment the directory if done with this series
                        #numbered directory, increment if checked
                        if img and self.include_incrementing_dir_num.isChecked():
                            int(self.keynumberdir.text())+1
                            #automatically sets first image number back to zero
                            self.keynumber.setText(str(int(0)).zfill(4))
                            self.keynumberdir.setText(str((int(self.keynumberdir.text())+ 1)).zfill(2))
                        self.createFilename()
                        self.timeseries.setChecked(False)
                if slowseries:
                    if self.lastimageflag == True:
                        self.livebutton.toggle()
                        #only increment the directory if done with the series
                        if img and self.include_incrementing_dir_num.isChecked():
                            int(self.keynumberdir.text())+1
                            #automatically sets first image number back to zero
                            self.keynumber.setText(str(int(0)).zfill(4))
                            self.keynumberdir.setText(str((int(self.keynumberdir.text())+ 1)).zfill(2))
                        self.createFilename()
            else:
                directorywarning = QtGui.QMessageBox()
                directorywarning.setWindowTitle('Filename Error')
                directorywarning.setText('The directory you chose does not exist. This software will only create the directory for you if the path exists all the way up to the final subdirectory. Create the necessary path structure on your computer or save to an already existing location. Image NOT saved.')
                ret = directorywarning.exec_()
                self.saveImageOrYaml(img)
        self.save.setChecked(False)


    def live(self):
        '''
        Rolling repeating frame buffer.
        '''
        if self.livebutton.isChecked():
            self.camera.start_continuous_capture()
        else:
            #on selecting "Freeze":
            self.camera.stop_live_capture()


    def collectTimeSeries(self):
        #both the fast and slow varieties
        if self.timeseries.isChecked():#fast
            numberOfImages = int(self.numOfFrames.text())
            self.camera.start_sequence_capture(numberOfImages)

        if self.timeseries_slow.isChecked():
            #set flags to be referenced by  event handler
            self.lastmod = 1
            self.lastimageflag = False
            self.imageCounter = 0

    def showImage(self):
        #https://github.com/shuge/Enjoy-Qt-Python-Binding/blob/master/image/display_img/pil_to_qpixmap.py
        #myQtImage = ImageQt(im)
        #qimage = QtGui.QImage(myQtImage)
        im = self.image
        if self.background_image is not None:
            im = np.true_divide(im, self.background_image)
            im = (im * 255.0/im.max()).astype('uint8')
        elif self.bit_depth > 8:
            im = im // 2**(self.bit_depth-8)
        im = Image.fromarray(im)
        data = im.convert("RGBA").tostring('raw', "RGBA")

        qim = QtGui.QImage(data, self.roi_shape[0], self.roi_shape[1], QtGui.QImage.Format_ARGB32)
        pixmap = QtGui.QPixmap.fromImage(qim)

        myScaledPixmap = pixmap.scaled(QtCore.QSize(750,750))

        self.frame.setPixmap(myScaledPixmap)

    def createFilename(self):
        #update QLabel with example filename
        self.path.setText(self.filename)
        self.path_example.setText(self.filename)
        if os.path.isfile(self.filename):
            self.path.setText('DANGER: SET TO OVERWRITE DATA, CHANGE FILENAME')


    def resetSavingOptions(self):
        self.outputformat.setCurrentIndex(0)
        self.include_filename_text.setCheckState(2)
        self.include_filename_text.setText("image")
        self.include_current_date.setCheckState(False)
        self.include_current_time.setCheckState(False)
        self.include_incrementing_image_num.setCheckState(2)
        self.include_incrementing_image_num.setText("0000")
        self.include_incrementing_dir_num.setCheckState(2)
        self.include_incrementing_dir_num.setText("00")
        #self.include_extra_dir_text.setText("")
        self.include_extra_dir_text.setCheckState(0)

        #rperry laptop default
        #self.root_save_path.setText("/home/rperry/Desktop/camera/images")
        #self.root_save_path.setText("/Home/Desktop/camera")

        #Aaron default
        #self.root_save_path.setText("/home/agoldfain/Desktop")
        #superscope default:
        self.root_save_path.setText("C:/Users/manoharanlab/data/[YOUR NAME]")


    def reopen_camera(self, size_str):
        self.roi_shape = [int(i) for i in
                      str(self.roiSizeChoices.currentText()).split(' x ')]
        self.bit_depth = int(str(self.bitdepthChoices.currentText()).split()[0])

        self.camera.open(self.bit_depth, self.roi_shape)

        self.livebutton.toggle()
        self.live()

    def change_camera(self, camera_str):
        self.camera.close()
        if camera_str == "Photon Focus":
            self.camera = epix_framegrabber.PhotonFocusCamera()
        if camera_str == "Simulate":
            self.camera = dummy_image_source.DummyCamera()

    def setROIx(self, x_pos):
        print('The ROI x-coordinate must be set to ', str(x_pos))

    def setROIy(self, y_pos):
        print('The ROI y-coordinate must be set to ', str(y_pos))

    def createYaml(self):

        microName = str(self.microSelections.currentText())
        lightName = str(self.lightSelections.currentText())
        objName = str(self.objectiveSelections.currentText())

        if self.tubeYes.checkState():
            tubestate = '1.5X'
        else:
            tubestate = '1.0X'

        notes = str(self.metaNotes.text())

        return dict(Microscope = microName, Light = lightName, Objective = objName, TubeMagnification = tubestate, Notes = notes)

    def select_background(self):
        stutus = 'stay frozen'
        if self.livebutton.isChecked(): #pause live feed
            self.freeze.setChecked(True)
            self.live()
            status = 'return to live'

        if self.applybackground.isChecked():
            filename = QtGui.QFileDialog.getOpenFileName(
                self, "Choose a background File", ".",
                "Tiff Images (*.tif *.tiff)")
            self.background_image_filename.setText(filename)
            self.background_image = np.array(Image.open(str(filename))).astype('uint8')
        else:
            self.background_image_filename.setText("No background applied")
            self.background_image = None

        if status == 'return to live':
            self.livebutton.setChecked(True)
            self.live()

    def select_directory(self):
        status = 'stay frozen'
        if self.livebutton.isChecked(): #pause live feed
            self.freeze.setChecked(True)
            self.live()
            status = 'return to live'

        directory = QtGui.QFileDialog.getExistingDirectory(
            self, "Choose a directory to save your data in", ".")
        self.root_save_path.setText(directory)

        if status == 'return to live':
            self.livebutton.setChecked(True)
            self.live()

def main():

    app = QtGui.QApplication(sys.argv)
    ex = captureFrames()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
