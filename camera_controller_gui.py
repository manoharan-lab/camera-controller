#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright 2011-2013, Vinothan N. Manoharan, Thomas G. Dimiduk,
# Rebecca W. Perry, Jerome Fung, and Ryan McGorty, Anna Wang
#
# This file is part of HoloPy.
#
# HoloPy is free software: you can redistribute it and/or modify
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

The timer event is for refreshing the window viewed by the user.

.. moduleauthor:: Rebecca W. Perry <perry.becca@gmail.com>
.. moduleauthor:: Aaron Goldfain
.. moduleauthor:: Thomas G. Dimiduk
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

#import epix_image_source as camera
import dummy_image_source as camera
from utility import mkdir_p
from QtConvenience import (make_label, make_HBox, make_VBox, make_LineEdit,
                           make_button, make_control_group)

#TODO: construct format file outside of the image grabbing loop, only
# when someone changes bit depth or ROI
#TODO: automate changing bit depth in PFRemote with the PF Remote DLL and some command like: SetProperty("DataResolution", Value(#1)")
#TODO: tie exposure time back to PFRemote ("SetProperty( "ExposureTime",Value(22.234))
#TODO: tie frame time back to PFRemote ("SetProperty( "ExposureTime",Value(22.234))
#TODO: limit text input for x and y in ROI to integers
#TODO: make sure that in a time series, the images stop getting collected at the end of the time series-- no overwriting the beginning of the buffer
#TODO: start slow time series by capturing an image, and start that as t=0


class captureFrames(QtGui.QWidget):
    '''
    Fill rolling buffer, then save individual frames or time series on command.
    '''
    camera.open_camera()

    def __init__(self):
        super(captureFrames, self).__init__()
        self.initUI()

    def initUI(self):

        QtGui.QToolTip.setFont(QtGui.QFont('SansSerif', 10))

        #Timer is for updating for image display and text to user
        self.timerid = self.startTimer(30)  # event every x ms

        self.numOfCols = 1024
        self.numOfRows = 1024
        self.image = np.random.random([self.numOfRows, self.numOfCols])*100
        self.cameraNum = 0  # to keep track of which camera is in use

        #display for image coming from camera
        self.frame = QtGui.QLabel(self)
        self.frame.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)

        #########################################
        # Tab 1, Main controls viewing/saving
        #########################################

        self.livebutton = make_button('Live', self.live, self, 'Ctrl+L')
        self.freeze = make_button('Freeze', self.live, self, 'Ctrl+F')
        self.save = make_button('Save', self.saveImage, self, 'Ctrl+S', width=200,
                                tooltip='Saves the frame that was current when this button was clicked. Freeze first if you want the frame to stay visible.')
        self.timeseries = make_button('Collect and Save Time Series',
                                      self.collectTimeSeries, self, 'Ctrl+T', width=200)
        self.timeseries_slow = make_button('Collect and Save Slow Time Series',
                                           self.collectTimeSeries, self, width=200)

        make_control_group(self, [self.livebutton, self.freeze,
                                  self.save, self.timeseries, self.timeseries_slow],
                           default=self.livebutton)

        self.numOfFrames = make_LineEdit(75, '10')

        self.numOfFrames2 = make_LineEdit(40, '10')
        self.interval = make_LineEdit(40, '0.5')

        self.applybackground = make_button('Apply Background',
                                           self.select_background, self)
        self.applybackground.setCheckable(True)
        self.background_image_filename = make_label("No background applied")
        self.background_image = None

        tab1 = QtGui.QWidget()

        make_VBox(['This program is for viewing and saving images from cameras. Other features relate to this program\'s intended purpose of being used with cameras mounted to microscopes.',
                   self.livebutton,
                   self.freeze,
                   1,
                   'Save the image that was showing when you clicked this button. Will ask for confirmation of filename.',
                   self.save,
                   1,
                   'Stores the requested number of images to the buffer and then saves the files to hard disk. The frame time is set in the Photon Focus Remote software.',
                   make_HBox([self.timeseries, self.numOfFrames, 'frames', 1]),
                   1,
                   'Is equivalent to clicking "Save this Frame" <frames> times <minutes apart> minutes apart except it will only warn you if the file name is NOT ok.',
                   make_HBox([self.timeseries_slow,
                              make_VBox([make_HBox([self.numOfFrames2, 'frames', 1]),
                                         make_HBox([self.interval, 'minutes apart', 1])])]),
                   1,
                   "Automatically Apply a background image (only for display, it still saves the raw images)",
                   self.applybackground,
                   self.background_image_filename],
                  tab1)



        ###########################################
        # Tab 2
        ###########################################

        tab2 = QtGui.QWidget()
        tab2_layout = QtGui.QVBoxLayout(tab2)


        tab2title = QtGui.QLabel()
        tab2title.setText('Modify camera settings.')
        #tab2title.setFixedHeight(20)
        tab2title.setAlignment(QtCore.Qt.AlignTop)
        tab2title.setWordWrap(True)
        tab2_layout.addWidget(tab2title)


        camera = QtGui.QLabel()
        camera.setFixedHeight(30)
        camera.setAlignment(QtCore.Qt.AlignBottom)
        camera.setText('Camera:')
        camera.setStyleSheet('font-weight:bold')

        self.cameraChoices = QtGui.QComboBox()
        self.cameraChoices.addItem("Simulated")
        self.cameraChoices.addItem("Photon Focus")
        self.cameraChoices.setCurrentIndex(1)
        self.cameraChoices.setFixedWidth(150)
        #self.bitdepth.activated[str].connect(self.changeROISize)

        tab2_layout.addWidget(camera)
        tab2_layout.addWidget(self.cameraChoices)


        bit = QtGui.QLabel()
        bit.setFixedHeight(30)
        bit.setAlignment(QtCore.Qt.AlignBottom)
        bit.setText('Bit Depth:')
        bit.setStyleSheet('font-weight:bold')

        self.bitdepthChoices = QtGui.QComboBox()
        self.bitdepthChoices.addItem("8bit")
        self.bitdepthChoices.addItem("10bit")
        self.bitdepthChoices.addItem("12bit")
        #self.bitdepthChoices.addItem("14bit")
        self.bitdepthChoices.setFixedWidth(150)
        self.bitdepthChoices.activated[str].connect(self.changeROISize)
        #self.bitdepth.activated[str].connect(self.changeROISize)

        tab2_layout.addWidget(bit)
        tab2_layout.addWidget(self.bitdepthChoices)

        self.framerate = QtGui.QLabel()
        self.framerate.setText('You also need to change the data output type in PFRemote.')
        tab2_layout.addWidget(self.framerate)

        tab2_layout.addStretch(1)

        #########################################
        # Tab 3, Options for saving output files
        #########################################

        tab3 = QtGui.QWidget()
        tab3_layout = QtGui.QVBoxLayout(tab3)

        self.outfile = QtGui.QLabel()
        self.outfile.setFixedHeight(50)
        self.outfile.setAlignment(QtCore.Qt.AlignTop)

        tab3title = QtGui.QLabel()
        tab3title.setText('These settings are for selecting the output format of your images and for automatically generating file names for images when you save them.')
        tab3title.setFixedHeight(50)
        tab3title.setWordWrap(True)
        tab3title.setAlignment(QtCore.Qt.AlignTop)
        tab3_layout.addWidget(tab3title)

        ###
        fileTypeLabel = QtGui.QLabel()
        fileTypeLabel.setFixedHeight(30)
        fileTypeLabel.setAlignment(QtCore.Qt.AlignBottom)
        fileTypeLabel.setText('Output File Format:')
        fileTypeLabel.setStyleSheet('font-weight:bold')

        self.outputformat = QtGui.QComboBox()
        self.outputformat.addItem(".tif")
        self.outputformat.addItem(".png")
        self.outputformat.setFixedWidth(150)
        self.outputformat.activated[str].connect(self.createFilename)

        tab3_layout.addWidget(fileTypeLabel)
        tab3_layout.addWidget(self.outputformat)

        ###
        fileLabel = QtGui.QLabel()
        fileLabel.setFixedHeight(30)
        fileLabel.setAlignment(QtCore.Qt.AlignBottom)
        fileLabel.setText('File Name:')
        fileLabel.setStyleSheet('font-weight:bold')

        self.imageKeywordToggle = QtGui.QCheckBox()
        self.imageKeywordToggle.setText("Include this text:")
        self.imageKeywordToggle.toggle()
        self.imageKeywordToggle.stateChanged.connect(self.createFilename)
        self.imageKeyword = QtGui.QLineEdit()
        self.imageKeyword.textChanged.connect(self.createFilename)

        self.currentdatelabel = QtGui.QCheckBox()
        self.currentdatelabel.setText("include date")
        self.currentdatelabel.stateChanged.connect(self.createFilename)
        self.current_date = time.strftime("%y_%m_%d_")

        self.currenttimelabel = QtGui.QCheckBox()
        self.currenttimelabel.setText("include time")
        self.currenttimelabel.stateChanged.connect(self.createFilename)
        self.current_time = time.strftime("%H_%M_%S")

        self.numberincrement = QtGui.QCheckBox()
        self.numberincrement.setText("include an incrementing number, next is:")
        self.numberincrement.toggle()
        self.numberincrement.stateChanged.connect(self.createFilename)
        self.keynumber = QtGui.QLineEdit()
        self.keynumber.textChanged.connect(self.createFilename)


        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.imageKeywordToggle)
        hbox.addWidget(self.imageKeyword)

        hbox2 = QtGui.QHBoxLayout()
        hbox2.addWidget(self.numberincrement)
        hbox2.addWidget(self.keynumber)

        tab3_layout.addWidget(fileLabel)
        tab3_layout.addLayout(hbox)
        tab3_layout.addWidget(self.currentdatelabel)
        tab3_layout.addWidget(self.currenttimelabel)
        tab3_layout.addLayout(hbox2)

        ######

        dirLabel = QtGui.QLabel()
        dirLabel.setText('Directory:')
        dirLabel.setStyleSheet('font-weight:bold')
        dirLabel.setFixedHeight(40)
        dirLabel.setAlignment(QtCore.Qt.AlignBottom)
        self.typingspace = QtGui.QLineEdit()
        self.typingspace.textChanged.connect(self.createFilename)
        #self.typingspace.setWordWrapMode(QtGui.QTextOption.WrapAnywhere)


        self.numberincrementdir = QtGui.QCheckBox()
        self.numberincrementdir.setText("include an incrementing number, next is:")
        self.numberincrementdir.toggle()
        self.numberincrementdir.stateChanged.connect(self.createFilename)
        self.keynumberdir = QtGui.QLineEdit()
        self.keynumberdir.textChanged.connect(self.createFilename)

        hbox3 = QtGui.QHBoxLayout()
        hbox3.addWidget(self.numberincrementdir)
        hbox3.addWidget(self.keynumberdir)


        self.keyworddir = QtGui.QCheckBox()
        self.keyworddir.setText("use the following text:")
        self.keyworddir.stateChanged.connect(self.createFilename)
        self.keywordvaldir = QtGui.QLineEdit()
        self.keywordvaldir.textChanged.connect(self.createFilename)

        hbox4 = QtGui.QHBoxLayout()
        hbox4.addWidget(self.keyworddir)
        hbox4.addWidget(self.keywordvaldir)

        self.resetSavingOptions() #should set file name

        tab3_layout.addWidget(dirLabel)
        tab3_layout.addWidget(self.typingspace)
        tab3_layout.addLayout(hbox3)
        tab3_layout.addLayout(hbox4)
        hbox.addStretch(1)


        yamlLabel = QtGui.QLabel()
        yamlLabel.setFixedHeight(30)
        yamlLabel.setAlignment(QtCore.Qt.AlignBottom)
        yamlLabel.setText('Save metadata as yaml file when saving image?')
        yamlLabel.setStyleSheet('font-weight:bold')

        self.saveMetaYes = QtGui.QCheckBox()
        self.saveMetaYes.setText("Yes")

        tab3_layout.addWidget(yamlLabel)
        tab3_layout.addWidget(self.saveMetaYes)

        outfiletitle = QtGui.QLabel()
        outfiletitle.setText('If you saved an image at the time you selected these settings, it would have been saved as:')
        outfiletitle.setFixedHeight(50)
        dirLabel.setAlignment(QtCore.Qt.AlignBottom)
        outfiletitle.setWordWrap(True)
        outfiletitle.setStyleSheet('font-weight:bold')

        tab3_layout.addWidget(outfiletitle)
        tab3_layout.addWidget(self.outfile)

        tab3_layout.addStretch(1)

        self.reset = QtGui.QPushButton('Reset to Default Values', self)
        self.reset.setDefault(True)
        self.reset.clicked.connect(self.resetSavingOptions)

        tab3_layout.addWidget(self.reset)

        self.resetSavingOptions()
        self.typingspace.textChanged.connect(self.createFilename)

        ################################
        # Tab 4, place to enter metadata
        ################################

        tab4 = QtGui.QWidget()
        tab4_layout = QtGui.QVBoxLayout(tab4)


        tab4title = QtGui.QLabel()
        tab4title.setText('Metadata that we want to save with the images-- also want to save some other metadata that does not need to be entered manually.')
        tab4title.setFixedHeight(50)
        tab4title.setWordWrap(True)
        tab4title.setAlignment(QtCore.Qt.AlignTop)
        tab4_layout.addWidget(tab4title)

        microLabel = QtGui.QLabel()
        microLabel.setFixedHeight(30)
        microLabel.setAlignment(QtCore.Qt.AlignBottom)
        microLabel.setText('Microscope:')
        microLabel.setStyleSheet('font-weight:bold')


        self.microgroup = QtGui.QButtonGroup(QtGui.QWidget(self))
        self.microgroup.setExclusive(True)

        uberscope = QtGui.QCheckBox()
        uberscope.setText("Uberscope")
        uberscope.toggle()
        self.microgroup.addButton(uberscope)

        mgruberscope = QtGui.QCheckBox()
        mgruberscope.setText("Mgruberscope")
        self.microgroup.addButton(mgruberscope)

        george = QtGui.QCheckBox()
        george.setText("George")
        self.microgroup.addButton(george)

        superscope = QtGui.QCheckBox()
        superscope.setText("Superscope")
        self.microgroup.addButton(superscope)

        otherscope = QtGui.QCheckBox()
        otherscope.setText("Other:")
        self.microgroup.addButton(otherscope)

        self.otherscopedetails = QtGui.QLineEdit()

        hbox10 = QtGui.QHBoxLayout()
        hbox10.addWidget(otherscope)
        hbox10.addWidget(self.otherscopedetails)

        tab4_layout.addWidget(microLabel)
        tab4_layout.addWidget(uberscope)
        tab4_layout.addWidget(mgruberscope)
        tab4_layout.addWidget(george)
        tab4_layout.addWidget(superscope)
        tab4_layout.addLayout(hbox10)

        lightLabel = QtGui.QLabel()
        lightLabel.setFixedHeight(30)
        lightLabel.setAlignment(QtCore.Qt.AlignBottom)
        lightLabel.setText('Light source:')
        lightLabel.setStyleSheet('font-weight:bold')

        self.illumgroup = QtGui.QButtonGroup(QtGui.QWidget(self))
        self.illumgroup.setExclusive(True)

        red = QtGui.QCheckBox()
        red.setText("Red laser, 660 nm")
        red.toggle()
        self.illumgroup.addButton(red)

        white = QtGui.QCheckBox()
        white.setText("White, brightfield illumination")
        self.illumgroup.addButton(white)

        otherlight = QtGui.QCheckBox()
        otherlight.setText("Other:")
        self.illumgroup.addButton(otherlight)

        self.otherlightdetails = QtGui.QLineEdit()

        hbox0 = QtGui.QHBoxLayout()
        hbox0.addWidget(otherlight)
        hbox0.addWidget(self.otherlightdetails)

        tab4_layout.addWidget(lightLabel)
        tab4_layout.addWidget(red)
        tab4_layout.addWidget(white)
        tab4_layout.addLayout(hbox0)

        objectiveLabel = QtGui.QLabel()
        objectiveLabel.setFixedHeight(30)
        objectiveLabel.setAlignment(QtCore.Qt.AlignBottom)
        objectiveLabel.setText('Microscope Objective:')
        objectiveLabel.setStyleSheet('font-weight:bold')
        tab4_layout.addWidget(objectiveLabel)

        self.objgroup = QtGui.QButtonGroup(QtGui.QWidget(self))
        self.objgroup.setExclusive(True)

        water60x = QtGui.QCheckBox()
        water60x.setText("Nikon 60x Water Immersion, Correction Collar:")
        water60x.toggle()
        self.objgroup.addButton(water60x)

        self.collardetails = QtGui.QLineEdit()

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(water60x)
        hbox.addWidget(self.collardetails)

        oil100x = QtGui.QCheckBox()
        oil100x.setText("Nikon 100x Oil Immersion")
        self.objgroup.addButton(oil100x)

        air10x = QtGui.QCheckBox()
        air10x.setText("Nikon 10x, air")
        self.objgroup.addButton(air10x)

        air40x = QtGui.QCheckBox()
        air40x.setText("Nikon 40x, air")
        self.objgroup.addButton(air40x)

        otherobj = QtGui.QCheckBox()
        otherobj.setText("Other:")
        self.objgroup.addButton(otherobj)

        self.otherobjdetails = QtGui.QLineEdit()

        hbox2 = QtGui.QHBoxLayout()
        hbox2.addWidget(otherobj)
        hbox2.addWidget(self.otherobjdetails)

        tab4_layout.addLayout(hbox)
        tab4_layout.addWidget(oil100x)
        tab4_layout.addWidget(air10x)
        tab4_layout.addWidget(air40x)
        tab4_layout.addLayout(hbox2)

        tubeLensLabel = QtGui.QLabel()
        tubeLensLabel.setFixedHeight(30)
        tubeLensLabel.setAlignment(QtCore.Qt.AlignBottom)
        tubeLensLabel.setText('Using 1.5x tube lens?')
        tubeLensLabel.setStyleSheet('font-weight:bold')

        self.tubeYes = QtGui.QCheckBox()
        self.tubeYes.setText("Yes")

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

        tab4_layout.addWidget(tubeLensLabel)
        tab4_layout.addWidget(self.tubeYes)
        tab4_layout.addWidget(notesLabel)
        tab4_layout.addWidget(self.metaNotes)
        tab4_layout.addWidget(self.saveMetaData)
        tab4_layout.addStretch(1)

        #TODO: put this in a function and update when any metadata changes
        #package metadata for saving in tif tag "description"
        self.metadata = dict(microscope='george', wavelength='600', lightsource='white')
        self.metadata = json.dumps(self.metadata)


        ################################
        # Tab 5, Adjust the ROI
        ################################

        tab5 = QtGui.QWidget()
        tab5_layout = QtGui.QVBoxLayout(tab5)

        tab5title = QtGui.QLabel()
        tab5title.setText('ROI = Region of Interest. Choose the frame size and the region of the camera to capture from. Default to full screen.')
        tab5title.setFixedHeight(40)
        tab5title.setWordWrap(True)
        tab5title.setAlignment(QtCore.Qt.AlignTop)
        tab5_layout.addWidget(tab5title)

        roiSizeLabel = QtGui.QLabel()
        roiSizeLabel.setFixedHeight(30)
        roiSizeLabel.setAlignment(QtCore.Qt.AlignBottom)
        roiSizeLabel.setText('ROI Size:')
        roiSizeLabel.setStyleSheet('font-weight:bold')

        self.roiSizeChoices = QtGui.QComboBox()
        self.roiSizeChoices.addItem("1024 x 1024")
        self.roiSizeChoices.addItem("512 x 512")
        self.roiSizeChoices.addItem("256 x 256 ")
        self.roiSizeChoices.addItem("128 x 128")
        self.roiSizeChoices.addItem("64 x 64")
        self.roiSizeChoices.setFixedWidth(150)
        self.roiSizeChoices.activated[str].connect(self.changeROISize)

        roiLocationLabel = QtGui.QLabel()
        #roiLocationLabel.setFixedHeight(80)
        #roiLocationLabel.setAlignment(QtCore.Qt.AlignBottom)
        roiLocationLabel.setText('Small frames taken from top left')



        tab5_layout.addWidget(roiSizeLabel)
        tab5_layout.addWidget(self.roiSizeChoices)
        tab5_layout.addWidget(roiLocationLabel)

        tab5_layout.addStretch(1)

        ################################################

        tab_widget = QtGui.QTabWidget()
        tab_widget.addTab(tab1, "Image Capture")
        tab_widget.addTab(tab2, "Camera")
        tab_widget.addTab(tab3, "Saving")
        tab_widget.addTab(tab4, "Meta Data")
        tab_widget.addTab(tab5, "ROI")

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
        self.setWindowTitle('Continuous Image Capture')
        self.show()


    def timerEvent(self, event):
        #print time.time()
        #obtain most recent image

        frame_number = camera.get_frame_number()
        self.pfim = camera.get_image()
        self.im = toimage(self.pfim) #PIL image

        self.numOfRows = np.shape(self.im)[0]
        self.numOfCols = np.shape(self.im)[1]

        #show most recent image
        self.showImage()

        #show info about this image
        def set_imageinfo(maxval=self.pfim.max(), frame_number=frame_number):
            self.imageinfo.setText(
                'Max pixel value: {}, Frame number: {}'.format(maxval, frame_number))

        set_imageinfo()

        #check if a slow time series was requested and if the current time is a time to be recorded
        if self.timeseries_slow.isChecked() and self.lastimageflag == False:
            currentmod = round(time.time(),0)%(round(float(str(self.interval.text()))*60,0))
            if currentmod == 0 and self.lastmod !=0: #TODO: replace with actual interval between images
                self.imageCounter +=1
                if self.imageCounter == float(str(self.numOfFrames2.text())):
                    self.lastimageflag = True
                self.saveImages()
            self.lastmod = currentmod

        #check if a time series to save has been finished collecting:
        if self.timeseries.isChecked():
            if camera.finished_live_sequence():
                time.sleep(0.1)
                set_imageinfo()
                self.freeze.toggle()
                self.saveImageOrYaml(True, True)

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

        if img and series and self.numberincrement.isChecked(): #include number
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
        selectedFrame = self.im

        #ask if the current autogenerated filename is OK with user
        #leave extra spaces after image as to make dialog window long enough for text edit

        ok = False

        if not slowseries:
            usersfilename, ok = savingcheck.getText(self, 'Output Filename', 'This image/metadata will be saved as:                                                                                                                         ', 0, fname);
        if slowseries: #no option to change it
            usersfilename = fname

        #TODO: renaming only allowed for single images, not tseries
        #TODO: tseries require number?
        #TODO: allow user to choose different directory?
        if ok or slowseries: #user thinks name is now OK
            if series == False:
                numOfFrames = 1
            else:
                #TODO: implement numOfFrames2
                numOfFrames = int(str(self.numOfFrames.text()))

            for i in range(1,numOfFrames+1):
                if series == True:
                    #get each image
                    selectedFrame = frameToArray(i)
                    selectedFrame = toimage(selectedFrame) #PIL image
                    usersfilename = self.filename

                #don't overwrite files
                if os.path.isfile(str(usersfilename)):
                    directorywarning = QtGui.QMessageBox()
                    directorywarning.setWindowTitle('Filename Error')
                    directorywarning.setText('Overwriting data not allowed. Choose a different name or delete the item with the same name.')
                    ret = directorywarning.exec_()
                    self.saveImageOrYaml(img) #cycle back to try again

                else:
                    #check if directory exists, and make it, save, or warn
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
                        if img and self.numberincrement.isChecked(): #include number
                            int(self.keynumber.text()) + 1
                            self.keynumber.setText(str((int(self.keynumber.text())+ 1)).zfill(4))
                        self.createFilename()

                        if not slowseries:
                            if series == False or i == numOfFrames:
                                #only increment the directory if done with this series
                                #numbered directory, increment if checked
                                if img and self.numberincrementdir.isChecked():
                                    int(self.keynumberdir.text())+1
                                    #automatically sets first image number back to zero
                                    self.keynumber.setText(str(int(0)).zfill(4))
                                    self.keynumberdir.setText(str((int(self.keynumberdir.text())+ 1)).zfill(2))
                                self.createFilename()
                        if slowseries:
                            if self.lastimageflag == True:
                                self.livebutton.toggle()
                                #only increment the directory if done with the series
                                if img and self.numberincrementdir.isChecked():
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

    def live(self):
        '''
        Rolling repeating frame buffer.
        '''
        if self.livebutton.isChecked():
            camera.start_continuous_capture()
        else:
            #on selecting "Freeze":
            camera.stop_live_capture()


    def collectTimeSeries(self):
        #both of the fast and slow varieties
        #openEpix()

        if self.timeseries.isChecked():#fast
            numberOfImages = int(self.numOfFrames.text())
            camera.start_sequence_capture(numberOfImages)

        if self.timeseries_slow.isChecked():
            #set flags to be referenced by  event handler
            self.lastmod = 1
            self.lastimageflag = False
            self.imageCounter = 0

    def showImage(self):
        #self.im = toimage(self.image) #PIL image
        #https://github.com/shuge/Enjoy-Qt-Python-Binding/blob/master/image/display_img/pil_to_qpixmap.py
        #myQtImage = ImageQt(im)
        #qimage = QtGui.QImage(myQtImage)
        im = self.pfim
        if self.background_image is not None:
            im = np.true_divide(im, self.background_image)
            im = (im * 255.0/im.max()).astype('uint8')
        im = Image.fromarray(im)
        data = im.convert("RGBA").tostring('raw', "RGBA")

        qim = QtGui.QImage(data, self.numOfRows, self.numOfCols, QtGui.QImage.Format_ARGB32)
        pixmap = QtGui.QPixmap.fromImage(qim)

        myScaledPixmap = pixmap.scaled(QtCore.QSize(750,750))

        self.frame.setPixmap(myScaledPixmap)

    def createFilename(self):
        self.filename = str(self.typingspace.text()) #directory name
        self.filename += r"//" #linux
        #self.filename += r"\\" #windows
        self.filename = self.filename[0:-1]

        #include an incrementing number
        if self.numberincrementdir.isChecked() and self.keyworddir.isChecked():
            self.filename += str(self.keynumberdir.text())
            self.filename += str(self.keywordvaldir.text())
            self.filename += r"//" #linux
            #self.filename += r"\\" #windows
            self.filename = self.filename[0:-1]

        #include text
        elif self.numberincrementdir.isChecked():
            self.filename += str(self.keynumberdir.text())
            self.filename += r"//" #linux
            #self.filename += r"\\" #windows
            self.filename = self.filename[0:-1]

        #include text
        elif self.keyworddir.isChecked():
            self.filename += str(self.keywordvaldir.text())
            self.filename += r"//" #linux
            #self.filename += r"\\" #windows
            self.filename = self.filename[0:-1]

        #include date
        if self.currentdatelabel.isChecked():
            self.current_date = time.strftime("%y%m%d")
            self.filename += self.current_date

        #include time
        if self.currenttimelabel.isChecked():
            self.current_time = time.strftime("%H%M%S")
            self.filename += self.current_time

        #include keyword
        if self.imageKeywordToggle.isChecked():
            self.filename += str(self.imageKeyword.text())

        #include number
        if self.numberincrement.isChecked(): #include number
            self.filename += str(self.keynumber.text())

        #finsih with the the file format
        if self.outputformat.currentText() == ".tif": #include number
            self.filename += ".tif"

        if self.outputformat.currentText() == ".png": #include number
            self.filename += ".png"

        #update QLabel with example filename
        self.outfile.setText(self.filename)


    def resetSavingOptions(self):
        self.outputformat.setCurrentIndex(0)
        self.imageKeywordToggle.setCheckState(2)
        self.imageKeyword.setText("image")
        self.currentdatelabel.setCheckState(False)
        self.currenttimelabel.setCheckState(False)
        self.numberincrement.setCheckState(2)
        self.keynumber.setText("0000")
        self.numberincrementdir.setCheckState(2)
        self.keynumberdir.setText("00")
        #self.keywordvaldir.setText("")
        self.keyworddir.setCheckState(0)

        #rperry laptop default
        #self.typingspace.setText("/home/rperry/Desktop/camera/images")
        #self.typingspace.setText("/Home/Desktop/camera")

        #Aaron default
        #self.typingspace.setText("/home/agoldfain/Desktop")
        #superscope default:
        self.typingspace.setText("C:/Users/manoharanlab/data/[YOUR NAME]")


    def changeROISize(self, size_str):
        size = [1024,512,256,128,64]
        current = self.roiSizeChoices.currentIndex()
        depth = self.bitdepthChoices.currentText()
        self.numOfRows = size[current]
        self.numOfCols = size[current]
        self.image = np.random.random([self.numOfRows, self.numOfCols])*100
        camera.close_camera()
        ffile = "PhotonFocus_"+str(depth)+"_"+str(size[current])+"x"+str(size[current])+".fmt"

        camera.open_camera(formatfile=ffile)
        self.livebutton.toggle()
        self.live()

    def setROIx(self, x_pos):
        print('The ROI x-coordinate must be set to ', str(x_pos))

    def setROIy(self, y_pos):
        print('The ROI y-coordinate must be set to ', str(y_pos))

    def createYaml(self):

        microName = str(self.microgroup.checkedButton().text())
        if microName == 'Other:':
            microName = str(self.otherscopedetails.text())

        lightName = str(self.illumgroup.checkedButton().text())
        if lightName == 'Other:':
            lightName = str(self.otherlightdetails.text())

        objName = str(self.objgroup.checkedButton().text())
        if objName == 'Other:':
            objName = str(self.otherobjdetails.text())
        elif objName == "Nikon 60x Water Immersion, Correction Collar:":
            objName = str(objName) + str(self.collardetails.text())

        if self.tubeYes.checkState():
            tubestate = '1.5X'
        else:
            tubestate = '1.0X'

        notes = str(self.metaNotes.text())

        return dict(Microscope = microName, Light = lightName, Objective = objName, TubeMagnification = tubestate, Notes = notes)

    def select_background(self):
        if self.applybackground.isChecked():
            filename = QtGui.QFileDialog.getOpenFileName(
                self, "Choose a background File", ".",
                "Tiff Images (*.tif *.tiff)")
            self.background_image_filename.setText(filename)
            self.background_image = np.array(Image.open(str(filename))).astype('uint8')
        else:
            self.background_image_filename.setText("No background applied")
            self.background_image = None



def main():

    app = QtGui.QApplication(sys.argv)
    ex = captureFrames()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
