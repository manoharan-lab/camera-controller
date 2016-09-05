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
from PySide import QtGui, QtCore
from PIL import Image
import h5py
from multiprocessing import Process
import matplotlib
matplotlib.use('Qt4Agg')
matplotlib.rcParams['backend.qt4']='PySide'
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from scipy.ndimage.measurements import center_of_mass
from scipy.ndimage.filters import gaussian_filter

from scipy.misc import toimage, fromimage, bytescale
import numpy as np
import time
import yaml
import json

import dummy_image_source
import epix_framegrabber
import thorcam_fs
from compress_h5 import compress_h5
from glob import glob
try:
    epix_framegrabber.Camera()
    epix_available = True
except epix_framegrabber.CameraOpenError:
    epix_available = False
try:
    thorcam_fs.Camera()
    thorcamfs_available = True
except thorcam_fs.CameraOpenError:
    thorcamfs_available = False

from utility import mkdir_p
from QtConvenience import (make_label, make_HBox, make_VBox,
                           make_LineEdit, make_button,
                           make_control_group, make_checkbox,
                           CheckboxGatedValue, increment_textbox,
                           zero_textbox, textbox_int, textbox_float,
                           make_combobox, make_tabs)


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
            self.camera = epix_framegrabber.Camera()
        else:
            self.camera = dummy_image_source.DummyCamera()
        
        if thorcamfs_available:
            self.camera_fs = thorcam_fs.Camera()    
        
        super(captureFrames, self).__init__()
        self.initUI()
        # we have to set this text after the internals are initialized since the filename is constructed from widget values
        self.update_filename()
        # pretend the last save was a timeseries, this just means that
        # we don't need to increment the dir number before saving the
        # first timeseries
        self.last_save_was_series = True
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self, self.close)


    def initUI(self):

        QtGui.QToolTip.setFont(QtGui.QFont('SansSerif', 10))

        #Timer is for updating for image display and text to user
        self.timerid = self.startTimer(30)  # event every x ms

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

        self.save = make_button(
            'Save\nesc', self.save_image, self, QtGui.QKeySequence('esc'), width=150,
            tooltip='Saves the frame that was current when this button was clicked. Freeze first if you want the frame to stay visible.')
        self.save.setCheckable(True)
        self.save.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")

        self.increment_dir_num = make_button(
            'Increment dir number', self.next_directory, self, width=150,
            tooltip='switch to the next numbered directory (if using numbered directories). Use this for example when switching to a new object')

        self.timeseries = make_button('Collect and Save\nTime Series',
                                      self.collectTimeSeries, self, QtGui.QKeySequence('f3'), width=200)
        self.timeseries.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")
        self.timeseries.setCheckable(True)

        self.timeseries_slow = make_button('Collect and Save\nSlow Time Series (<= 1 fps)',
                                           self.collectTimeSeries, self, QtGui.QKeySequence('f4'), width=200)
        self.timeseries_slow.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")
        self.timeseries_slow.setCheckable(True)

        self.save_buffer = make_button('Time machine!',
                                        self.collectTimeSeries, self, QtGui.QKeySequence('f12'), width=200)
        self.save_buffer.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")
        self.save_buffer.setCheckable(True)

        make_control_group(self, [self.livebutton, self.freeze],
                           default=self.livebutton)
        #TODO: fix control group, should you be allowed to do multiple at once?
        #make_control_group(self, [self.save, self.timeseries, self.timeseries_slow])

        self.numOfFrames = make_LineEdit('10', width=75)

        self.numOfFrames2 = make_LineEdit('10', width=75)
        self.interval = make_LineEdit('0.5', width=75)

        self.applybackground = make_button('Apply Background',
                                           self.select_background, self, width=150)
        self.applybackground.setCheckable(True)
        self.applybackground.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")
        self.background_image_filename = make_label("No background applied")
        self.background_image = None
        self.divide_background = make_checkbox("Divide\nBackground", callback = self.check_contrast_autoscale)
        self.get_bkgd_from_file = make_checkbox("Get Background\nFrom File")
        
        self.outfiletitle = QtGui.QLabel()
        self.outfiletitle.setText('Your next image will be saved as\n(use filenames tab to change):')
        self.outfiletitle.setFixedHeight(50)
        self.outfiletitle.setWordWrap(True)
        self.outfiletitle.setStyleSheet('font-weight:bold')

        self.path = make_label("")

        tab1_item_list = [make_HBox([self.livebutton, self.freeze,1]),
                 1,
                'Save image showing when clicked',
                 make_HBox([self.save, self.increment_dir_num]),
                 1,
                 'Store the requested number of images to the buffer and then save the files to hard disk. \n\nThe frame rate is set in the Photon Focus Remote software.',
                 make_HBox([self.timeseries, self.numOfFrames, 'frames', 1]),
                 1,
                 'Equivalent to clicking "Save" at regular intervals',
                 make_HBox([self.timeseries_slow,
                            make_VBox([make_HBox([self.numOfFrames2, 'frames', 1]),
                                       make_HBox([self.interval, 'minutes apart', 1])])]),
                 1,
                 "Save buffer",
                 make_HBox([self.save_buffer, self.increment_dir_num]),
                 "Automatically Apply a background image \n(only for display, it still saves the raw images)",
                 make_HBox([self.applybackground, self.divide_background, self.get_bkgd_from_file]),
                 self.background_image_filename,
                 self.outfiletitle,
                 self.path]
        
        if thorcamfs_available:
            self.stage_serialNo = make_LineEdit('29500244',width=60)
            self.close_open_stage_but = make_button('Open\nStage', self.close_open_stage)
            self.v_out = make_label('NA',bold = True,width=40)
            self.v_out.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            #self.v_out.editingFinished.connect(self.change_output_voltage)
            self.v_inc_but = make_button("+", self.inc_output_voltage, width = 20, height = 20)
            self.v_dec_but = make_button("-", self.dec_output_voltage, width = 20, height = 20)                       
            self.v_step = make_LineEdit('NA',width=40)
            self.v_step.editingFinished.connect(self.change_step_voltage) 
            self.lock_pos_box = make_checkbox("Lock Stage Position", callback = self.set_lock_pos)
            self.feedback_measure_disp = make_label('')
            self.fb_measure_to_voltage = make_LineEdit('0',width=40)
            self.max_spot_int_but = make_button('Maximize\nIntensity')
            self.max_spot_int_but.setCheckable(True)
            self.max_spot_int_but.setStyleSheet("QPushButton:checked {background-color: green} QPushButton:pressed {background-color: green}")
            self.spot_diam = make_LineEdit('3',width=20)
            self.v_focus_range = make_LineEdit('5.0',width=30)

            tab1_item_list = tab1_item_list + [make_label('____________________________________________', height=15, width = 300),
                 make_HBox([make_label('Z Stage Driver SN:', bold=True, height=15, align='top'), self.stage_serialNo,
                    self.close_open_stage_but, 1]),
                 make_HBox([make_label('Stage Output Voltage: ', bold=True, height=15, width = 130, align='top'), self.v_out,
                            make_label('%', bold=True, height=15, align='top'),
                            make_VBox([self.v_inc_but, self.v_dec_but,1]), 
                            make_label('Step:', bold=True, height=15, align='top'), self.v_step, 
                            make_label('%', bold=True, height=15, align='top'), 1]),
                 make_HBox([make_label('Feedback-Volts Conversion:', bold=True, height=15, width = 160, align='top'), self.fb_measure_to_voltage, 1]),
                 self.lock_pos_box, self.feedback_measure_disp,
                 make_HBox([self.max_spot_int_but, 
                             make_VBox( [make_HBox([make_label('Spot Diameter (Pixels):', bold=True, height=15, width = 140, align='top'), self.spot_diam, 1]),
                                         make_HBox([make_label('V Range (%):', bold=True, height=15, width = 80, align='top'), self.v_focus_range, 1]), 
                                         1]),  1]) ]
                                         
                 
        tab1 = ("Image Capture", tab1_item_list+[1])
        
        
        ###################################################################
        # Tab 2, camera settings need to be set in Photon Focus remote too

        ###################################################################
        cameras = ["Simulated"]
        if epix_available:
            cameras = ["PhotonFocus", "Basler"] + cameras
        if thorcamfs_available:
            cameras.append("ThorCam FS")
            

        self.buffersize = make_LineEdit('1000',callback=self.revise_camera_settings,width=80) #number of images kept in rolling buffer
        self.camera_choice = make_combobox(cameras, self.change_camera, width=150)
        if thorcamfs_available:
            self.camera_choice.model().item(cameras.index("ThorCam FS")).setEnabled(False)
        self.bitdepth_choice = make_combobox(['temp'],
                                            callback=self.revise_camera_settings, default=0, width=150)
        self.roi_size_choice = make_combobox(['temp'],
                                             callback=self.revise_camera_settings, default=0, width=150)
        self.roi_pos_choicex = make_LineEdit('0',width=60)
        self.roi_pos_choicey = make_LineEdit('0',width=60)
        self.roi_pos_choicex.editingFinished.connect(self.change_roi_pos)
        self.roi_pos_choicey.editingFinished.connect(self.change_roi_pos)
        self.posx_inc_but = make_button("+", self.roi_posx_inc, width = 20, height = 20)
        self.posx_dec_but = make_button("-", self.roi_posx_dec, width = 20, height = 20)
        self.posy_inc_but = make_button("+", self.roi_posy_inc, width = 20, height = 20)
        self.posy_dec_but = make_button("-", self.roi_posy_dec, width = 20, height = 20)
        
        self.exposure = make_LineEdit('NA',width=60)
        self.exposure.editingFinished.connect(self.change_exposure)
        self.frametime = make_LineEdit('NA',width=60)
        self.frametime.editingFinished.connect(self.change_frametime)
        self.framerate = make_LineEdit('NA',width=60)
        self.framerate.editingFinished.connect(self.change_framerate)

        i = 0
        opened = False
        while i < len(cameras) and not opened:
            self.camera_choice.setCurrentIndex(i)
            try:
                self.change_camera(self.camera_choice.currentText())
                opened = True
            except epix_framegrabber.CameraOpenError:
                i = i+1
        if not opened:
            print("failed to open a camera")

        tab2_item_list = ["Modify Camera Settings",
                 make_label("Camera:", bold=True),
                 self.camera_choice,
                 make_label("Bit Depth:", bold=True),
                 self.bitdepth_choice,
                 "Must match the data output type in camera manufacturer's software",
                 make_label("Region of Interest Size:", bold=True,
                            align='bottom', height=30),
                 'Frame size in pixels. Default to maximum size.\nRegions are taken from top left.\nWant a different size? Make a new format file.',
                 self.roi_size_choice,
                 make_HBox([make_label('X ', bold=True, height=15, align='top'), self.roi_pos_choicex,
                            make_VBox([self.posx_inc_but, self.posx_dec_but,1]), 
                            make_label('Y ', bold=True, height=15, align='top'), self.roi_pos_choicey, 
                            make_VBox([self.posy_inc_but, self.posy_dec_but,1]), 1]),
                 make_HBox([make_label('Exposure Time (ms):', bold=True, height=15, align='top'), self.exposure, 1]),
                 make_HBox([make_label('Frame Time (ms):', bold=True, height=15, align='top'), self.frametime,
                            make_label('Frame Rate (Hz):', bold=True, height=15, align='top'), self.framerate, 1]),
                 make_HBox([make_label('Rolling Buffer Size (# images):', bold=True, height=15, width=180, align='top'), self.buffersize, 1])]
        
        if thorcamfs_available:
            self.config_thorcam_fs = make_checkbox("Set ThorCam FS Camera Parameters", callback = self.switch_configurable_camera)
            self.close_open_thorcam_fs_but = make_button('Open\nThorCam FS', self.close_open_thorcam_fs)   
            self.fb_measure_figure = plt.figure(figsize=[2,4])
            self.fb_measure_ax = self.fb_measure_figure.add_subplot(111)
            self.fb_measure_ax.hold(False) #discard old plots
            self.fb_measure_canvas = FigureCanvas(self.fb_measure_figure)   
               
            tab2_item_list.insert(1, make_HBox([self.config_thorcam_fs, self.close_open_thorcam_fs_but,1]) )
            tab2_item_list = tab2_item_list +[make_label('\nFeedback Measure vs. time/(30 ms)', bold=True, height=30, align='top'), 
                                                self.fb_measure_canvas]
            
        tab2 = ("Camera", tab2_item_list+[1])

        #########################################
        # Tab 3, Options for saving output files
        #########################################
        # fileneame
        fileTypeLabel = make_label('Output File Format:', bold=True, height=30,
                                   align='bottom')

        self.outputformat = make_combobox(['.tif'], callback=self.update_filename, width=150)

        self.include_filename_text = CheckboxGatedValue(
            "Include this text:", make_LineEdit("image"), self.update_filename,
            True)
        self.include_current_date = CheckboxGatedValue(
            "include date", lambda : time.strftime("%Y-%m-%d_"),
            callback=self.update_filename)
        self.include_current_time = CheckboxGatedValue(
            "include time", lambda : time.strftime("%H_%M_%S_"),
            callback=self.update_filename)
        self.include_incrementing_image_num = CheckboxGatedValue(
            "include an incrementing number, next is:", make_LineEdit('0000'),
            self.update_filename, True)

        # Directory
        self.browse = make_button("Browse", self.select_directory, self,
                                  height=30, width=100)
        self.root_save_path = make_LineEdit(
            os.path.join("C:\\", "Users",     "manoharanlab", "data", "YourName"),
                                            self.update_filename)
        self.include_dated_subdir = CheckboxGatedValue(
            "Use a dated subdirectory", lambda : time.strftime("%Y-%m-%d"),
            self.update_filename, True)
        self.include_incrementing_dir_num = CheckboxGatedValue(
            "include an incrementing number, next is:", make_LineEdit('00'),
            self.update_filename, True)
        self.include_extra_dir_text = CheckboxGatedValue(
            "use the following text:", make_LineEdit(None), self.update_filename)

        self.saveMetaYes = make_checkbox('Save metadata as yaml file when saving image?')

        self.outfile = make_label("", height=50, align='top')

        self.reset = make_button("Reset to Default values", self.resetSavingOptions, self, height=None, width=None)

        self.path_example = make_label("")

        tab3 = ("Filenames",
                [make_label(
                    'Select the output format of your images and set up automatically '
                    'generated file names for saving images',
                    height=50, align='top'),
                 make_label('File Name:', bold=True, align='bottom', height=30),
                 make_HBox(["Image type", self.outputformat]),
                 self.include_filename_text,
                 self.include_current_date,
                 self.include_current_time,
                 self.include_incrementing_image_num,
                 ######
                 make_label('Directory:', bold=True, height=30, align='bottom'),
                 self.browse,
                 self.root_save_path,
                 self.include_dated_subdir,
                 self.include_incrementing_dir_num,
                 self.include_extra_dir_text,
                 1,
                 self.saveMetaYes,
                 make_label("If you save an image with these settings it will be saved as:", height=50, bold=True, align='bottom'),
                 self.path_example,
                 1,
                 self.reset])

        # TODO: make this function get its values from the defaults we give things
        # self.resetSavingOptions() #should set file name

        ################################
        # Tab 4, place to enter metadata
        ################################
        self.microSelections = make_combobox(["Uberscope", "Mgruberscope",
                                              "George", "Superscope", "iSCAT",
                                              "Other (edit to specify)"],
                                             width=250,
                                             editable=True)

        self.lightSelections = make_combobox(["660 nm Red Laser",
                                              "405 nm Violet Laser",
                                              "White LED Illuminator",
                                              "Nikon White Light",
                                              "Dic", "Other (edit to specify)"],
                                             width=250,
                                             editable=True)

        self.objectiveSelections = make_combobox(
            ["60x Nikon, Water Immersion, Correction Collar:",
             "100x Nikon, Oil Immersion",
             "10x Nikon, air",
             "40x Nikon, air",
             "?x Other: (edit to specify)"],
            editable=True)

        self.tubeYes = make_checkbox("Yes")

        self.metaNotes = QtGui.QLineEdit()

        self.saveMetaData = make_button("Save Metadata to Yaml", self.save_metadata, height=30, width=200)

        tab4 = ("Metadata",
                [make_label('User supplied metadata can be saved with button here, or alongside every image with a setting on the filenames tab', height=50, align='top'),
                 make_label('Microscope:', bold=True, height=30, align='bottom'),
                 self.microSelections,
                 make_label("Light source:", bold=True, height=30, align='bottom'),
                 self.lightSelections,
                 make_label('Microscope Objective:', bold=True, height=30, align='bottom'),
                 self.objectiveSelections,
                 make_HBox([
                     make_label("Using additional 1.5x tube lens?", bold=True),
                     self.tubeYes, 1]),
                 make_label('Notes (e.g. details about your sample):',
                            height=30, align='bottom', bold=True),
                 self.metaNotes,
                 self.saveMetaData])


        ################################
        # Tab 5, Overlays
        ################################
        self.edgeEntry = make_LineEdit(width=40)

        def make_color_combobox():
            return make_combobox(["Red", "Green", "Blue"], width=50, default=1)

        def make_pixel_entry():
            #TODO: do some kind of checking to make sure it is numeric
            return make_LineEdit(width=37)

        self.cornerRowEntry = make_pixel_entry()
        self.cornerColEntry = make_pixel_entry()
        self.sqcolor = make_color_combobox()

        self.diamEntry = QtGui.QLineEdit()
        self.centerRowEntry = make_pixel_entry()
        self.centerColEntry = make_pixel_entry()
        self.circolor = make_color_combobox()

        self.meshSizeEntry = make_pixel_entry()
        self.gridcolor = make_color_combobox()

        tab5 = ("Overlays",
                [make_label("Square", height=20, align='bottom', bold=True),
                 make_HBox(["Edge Length (pixels):", self.edgeEntry, 1]),
                 make_HBox(["Upper Left Corner Location (row, col):",
                            self.cornerRowEntry, self.cornerColEntry, self.sqcolor]),
                 make_label("Circle:", bold=True, height=30, align='bottom'),
                 make_HBox(["Diameter (pixels):", self.diamEntry]),
                 make_HBox(["Center Location (row, col)", self.centerRowEntry,
                            self.centerColEntry, self.circolor]),
                 make_label("Grid:", height=30, align='bottom', bold=True),
                 make_HBox(["Grid Square Size (pixels)", self.meshSizeEntry,
                            self.gridcolor]),
                 1])


        ################################################

        tab_widget = make_tabs([tab1, tab2, tab3, tab4, tab5])

        #Text at bottom of screen
        self.imageinfo = QtGui.QLabel()
        self.imageinfo.setText('Max pixel value: '+str(0))
        self.imageinfo.setFont("Arial") #monospaced font avoids flickering
        #self.imageinfo.setStyleSheet('font-weight:bold')
        self.imageinfo.setAlignment(QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft)

        #contrast scaling stuff
        self.contrastminlabel = QtGui.QLabel()
        self.contrastminlabel.setText('Min Contrast Value:')
        self.contrastminlabel.setFont("Arial") #monospaced font avoids flickering
        self.contrastminlabel.setAlignment(QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft)
        self.contrastmaxlabel = QtGui.QLabel()
        self.contrastmaxlabel.setText('Max Contrast Value:')
        self.contrastmaxlabel.setFont("Arial") #monospaced font avoids flickering
        self.contrastmaxlabel.setAlignment(QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft)
        self.minpixval = make_LineEdit('0', width=75)
        self.maxpixval = make_LineEdit('255', width=75)
        self.contrast_autoscale = make_checkbox("Autoscale Contrast")
        self.contrast_default = make_button('Default Contrast', self.set_default_contrast, self, height = 20)


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

        contrastbox = QtGui.QHBoxLayout()
        contrastbox.addWidget(self.contrastminlabel)
        contrastbox.addWidget(self.minpixval)
        contrastbox.addWidget(self.contrastmaxlabel)
        contrastbox.addWidget(self.maxpixval)
        contrastbox.addWidget(self.contrast_autoscale)
        contrastbox.addWidget(self.contrast_default)
        contrastbox.addStretch(1)
        
        textbox = QtGui.QVBoxLayout()
        textbox.addWidget(self.imageinfo)
        textbox.addStretch(1)

        largevbox = QtGui.QVBoxLayout()
        largevbox.addLayout(contentbox)
        largevbox.addStretch(1)
        largevbox.addLayout(contrastbox)
        largevbox.addLayout(textbox)

        self.setLayout(largevbox)

        self.setGeometry(10, 50, 800, 800) #window size and location
        self.setWindowTitle('Camera Controller')
        self.show()

    def timerEvent(self, event):
        #obtain most recent image
        frame_number = self.camera.get_frame_number()
        if thorcamfs_available and self.config_thorcam_fs.isChecked():
        #display thorcam_fs image if config box is checked and the camera is open
            if self.close_open_thorcam_fs_but.text() == 'Close\nThorCam FS':                
                self.image = self.camera_fs.get_image()
                
            else: print("ThorCam_fs not open")
        else:
            self.image = self.camera.get_image()

        #self.roi_shape = np.shape(self.image)

        #show most recent image
        self.showImage()

        #show info about this image
        def set_imageinfo():
            maxval = self.image.max()
            height = len(self.image)
            width = np.size(self.image)/height
            portion = round(np.sum(self.image == maxval)/(1.0*np.size(self.image)),3)
            if self.contrast_autoscale.isChecked():
                is_autoscaled=", Contrast Autoscaled"
            else:
                is_autoscaled=""
            
            imageinfo_text = 'Camera Controller Version 0.0.1, Image Size: {}x{}, Max pixel value: {}, Fraction at max: {}, Frame number in buffer: {}{}'.format(
                    width,height, maxval, portion, frame_number, is_autoscaled)
            if self.timeseries_slow.isChecked():
                imageinfo_text = imageinfo_text + ', Slow Time Series Frame: ' +str(textbox_int(self.include_incrementing_image_num))
            
            self.imageinfo.setText(imageinfo_text)

        set_imageinfo()

        if self.timeseries_slow.isChecked():
            if (textbox_int(self.include_incrementing_image_num) *
                textbox_float(self.interval) * 60) <= time.time()-self.slowseries_start:
                self.save_image()
            if textbox_int(self.include_incrementing_image_num) >= textbox_int(self.numOfFrames2):
                self.timeseries_slow.setChecked(False)
                if thorcamfs_available and self.close_open_stage_but.text() == 'Close\nStage':
                    np.savetxt(self.filename()+'_VOutHistory.txt', self.v_out_history)
                self.next_directory()
                

        #check if a time series to save has been finished collecting:
        if self.timeseries.isChecked():
            if self.camera.finished_live_sequence():
                time.sleep(0.1)
                set_imageinfo()
                self.freeze.toggle()
                mkdir_p(self.save_directory())

                write_timeseries(self.filename(), range(1, 1 + textbox_int(self.numOfFrames)), self.metadata, self)
                if thorcamfs_available and self.close_open_stage_but.text() == 'Close\nStage':
                    np.savetxt(self.filename()+'_VOutHistory.txt', self.v_out_history)
                    if self.lock_pos_box.isChecked():
                        #Stop Stage feedback loop since saving the data can take a long time and stage position is not updated during saving.
                        self.lock_pos_box.setChecked(False)
                        self.set_lock_pos()


                increment_textbox(self.include_incrementing_image_num)
                self.next_directory()
                self.timeseries.setChecked(False)
                self.livebutton.setChecked(True)
                self.live()


        #for back-saving the contents of the rolling buffer
        if self.save_buffer.isChecked():
            self.freeze.setChecked(True)
            self.live() #this processes that the freeze button was checked
            time.sleep(0.1)
            set_imageinfo()
            mkdir_p(self.save_directory())

            lastframe = self.camera.get_frame_number()

            imagenums = []
            for i in range(lastframe+2,textbox_int(self.buffersize)+1) + range(1,lastframe+2):
                #chonological
                imagenums.append(i)

            write_timeseries(self.filename(), imagenums, self.metadata, self)

            self.next_directory()
            self.save_buffer.setChecked(False)
            self.livebutton.setChecked(True)
            self.live()
        
        #update stage position for focus stabilization
        if thorcamfs_available and self.close_open_stage_but.text() == 'Close\nStage':
            self.update_output_voltage()
            if self.timeseries.isChecked() or self.timeseries_slow.isChecked():
                    self.v_out_history.append(np.array([self.camera_fs.stage_output_voltage, self.fb_sum]))
            if self.lock_pos_box.isChecked():
                self.correct_stage_voltage()

                
    def set_default_contrast(self):
        #resets image contrast to default
        if self.bit_depth == 8:
            maxval = 2**8-1
        elif self.bit_depth > 8:
            maxval = 2**16-1
        self.minpixval.setText('0')
        self.maxpixval.setText(str(maxval))

    
    @property
    def dtype(self):
        if self.bit_depth == 8:
            return 'uint8'
        else:
            return 'uint16'

    def check_contrast_autoscale(self):
        self.contrast_autoscale.setChecked(True)
    def showImage(self):
        #https://github.com/shuge/Enjoy-Qt-Python-Binding/blob/master/image/display_img/pil_to_qpixmap.py
        #myQtImage = ImageQt(im)
        #qimage = QtGui.QImage(myQtImage)
        im = self.image
       
        if (self.divide_background.isChecked() and
            self.background_image is not None):
            im = np.true_divide(im, self.background_image)
        if self.contrast_autoscale.isChecked():
            self.minpixval.setText(str( np.round(im.min(),3) ))
            self.maxpixval.setText(str( np.round(im.max(),3) ))
            
        minval = float(self.minpixval.text())
        maxval = float(self.maxpixval.text())
        if im.dtype==np.uint8:
            im = im.astype(np.int16)
        im = bytescale(im, minval, maxval)

        im = to_pil_image(im)
        #data = im.convert("RGBA").tostring('raw', "RGBA") #older version of PIL
        data = im.convert("RGBA").tobytes('raw', "RGBA") #newer version of PIL

        qim = QtGui.QImage(data, self.image.shape[0], self.image.shape[1], QtGui.QImage.Format_ARGB32)
        pixmap = QtGui.QPixmap.fromImage(qim)
        
        im_display_size = 900 #size of displayed image in pixels
        myScaledPixmap = pixmap.scaled(QtCore.QSize(im_display_size,im_display_size))

        self.frame.setPixmap(myScaledPixmap)

    def save_directory(self, linewrap_for_gui=False):
        root = str(self.root_save_path.text())
        if linewrap_for_gui and len(root) > 25:
            root += '\n'
        dirextra = "".join([self.include_incrementing_dir_num.text(),
                            self.include_extra_dir_text.text()])
        return os.path.join(*[a for a in [root, self.include_dated_subdir.text(), dirextra] if a])

    def base_filename(self, linewrap_for_gui=False):
        filename = "".join([self.include_current_date.text(),
                            self.include_current_time.text(),
                            self.include_filename_text.text(),
                            self.include_incrementing_image_num.text()])
        return os.path.join(self.save_directory(linewrap_for_gui), filename)

    def filename(self, linewrap_for_gui=False):
        return self.base_filename(linewrap_for_gui)

    @property
    def metadata_filename(self, linewrap_for_gui=False):
        return self.base_filename(linewrap_for_gui) + '.yaml'

    def update_filename(self):
        #update QLabel with example filename
        self.path.setText(self.filename(linewrap_for_gui=True))
        self.path_example.setText(self.filename(linewrap_for_gui=True))
        if os.path.isfile(self.filename() + '.tif'):
            self.path.setText('DANGER: SET TO OVERWRITE DATA, CHANGE FILENAME')

    def save_image(self):
        self.last_save_was_series = False
        mkdir_p(self.save_directory())

        write_image(self.filename()+'.tif', self.image, metadata = self.metadata)

        self.save.setChecked(False)
        if self.include_incrementing_image_num.isChecked():
            increment_textbox(self.include_incrementing_image_num)
        elif self.include_incrementing_dir_num.isChecked():
            increment_textbox(self.include_incrementing_dir_num)
            zero_textbox(self.include_incrementing_image_num)

    def next_directory(self):
        if self.include_incrementing_dir_num.isChecked():
            increment_textbox(self.include_incrementing_dir_num)
            zero_textbox(self.include_incrementing_image_num)

    @property
    def metadata(self):
        metadata = {'microscope' : str(self.microSelections.currentText()),
                    'light' : str(self.lightSelections.currentText()),
                    'objective' : str(self.objectiveSelections.currentText()),
                    'notes' : str(self.metaNotes.text())}

        magnification = int(metadata['objective'].split('x')[0].strip())
        if self.tubeYes.checkState():
            metadata['tube-magnification'] = '1.5X'
            magnification = magnification * 1.5
        else:
            metadata['tube-magnification'] = '1.0X'

        metadata['magnification'] = magnification
        return metadata

    def save_metadata(self):
        mkdir_p(self.save_directory())
        open(self.metadata_filename, 'w').write(yaml.dump(self.metadata))

    def live(self):
        '''
        Rolling repeating frame buffer.
        '''
        if self.livebutton.isChecked():
            self.camera.start_continuous_capture(textbox_int(self.buffersize))
            print 'starting live capture again'
        else:
            #on selecting "Freeze":
            self.camera.stop_live_capture()

    def collectTimeSeries(self):
        if thorcamfs_available and self.close_open_stage_but.text() == 'Close\nStage':
            self.v_out_history = []
        if (self.timeseries.isChecked()
            or self.timeseries_slow.isChecked()
            or self.save_buffer.isChecked()):
            # It doesn't make any sense to save a timeseries without
            # an incrementing number, so force this flag to be set
            self.include_incrementing_image_num.setChecked(True)
            if self.last_save_was_series == False:
                self.next_directory()
            zero_textbox(self.include_incrementing_image_num)
            self.last_save_was_series = True
        #both the fast and slow varieties
        if self.timeseries.isChecked():#fast
            numberOfImages = int(self.numOfFrames.text())
            self.camera.start_sequence_capture(numberOfImages)
        if self.timeseries_slow.isChecked():
            self.slowseries_start = time.time()
        if self.save_buffer.isChecked():
            print "I want to save the buffer."

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

        #superscope default:
        self.root_save_path.setText(os.path.join("C:", "Users", "manoharanlab",
                                                 "data", "YourName"))

    def revise_camera_settings(self):
        camera_str =  self.camera_choice.currentText()
        if thorcamfs_available and self.config_thorcam_fs.isChecked(): #configure ThorCam FS
            cam_to_revise = self.camera_fs
        else: #configure main camera
            cam_to_revise = self.camera

        self.roi_shape = [int(i) for i in
                      str(self.roi_size_choice.currentText()).split(' x ')]
        old_bit_depth = self.bit_depth
        self.bit_depth = int(str(self.bitdepth_choice.currentText()).split()[0])
        if self.bit_depth != old_bit_depth:
            self.set_default_contrast()
            
        if camera_str == "PhotonFocus" or camera_str == "Basler": #for cameras that can't change these dynamically
            self.camera.close()
            self.camera = epix_framegrabber.Camera()
            self.camera.open(self.bit_depth, self.roi_shape, camera = self.camera_choice.currentText())
        elif camera_str == "ThorCam FS" or camera_str == "Simulated": #for cameras that can change dynamically
            cam_to_revise.set_bit_depth(self.bit_depth)
            cam_to_revise.set_roi_shape(self.roi_shape)
            self.change_roi_pos()
    
        self.livebutton.toggle()
        self.live()
    
    def change_exposure(self):
        if self.config_thorcam_fs.isChecked(): #configure ThorCam FS
            cam_to_revise = self.camera_fs
        else: #configure main camera
            cam_to_revise = self.camera
    
        if str(self.exposure.text()) == 'NA':
            target_exposure = 0.01
        else:
            target_exposure = textbox_float(self.exposure)
        cam_to_revise.set_exposure(target_exposure)
        exposure_str=str( np.round(cam_to_revise.exposure,3) )

        self.exposure.setText(exposure_str)

    def change_frametime(self):
        if self.config_thorcam_fs.isChecked(): #configure ThorCam FS
            cam_to_revise = self.camera_fs
        else: #configure main camera
            cam_to_revise = self.camera
    
        if str(self.frametime.text()) == 'NA':
            target_frametime = 0.0
        else:
            target_frametime = textbox_float(self.frametime)
        cam_to_revise.set_frametime(target_frametime)
        frametime_str = str( np.round(cam_to_revise.frametime,3) )
        if cam_to_revise.frametime == 0:
            framerate_str = '0'
        else:
            framerate_str = str( np.round(1000.0/cam_to_revise.frametime,3) )
            
        self.frametime.setText(frametime_str)
        self.framerate.setText(framerate_str)
    
    
    def change_framerate(self):
        new_framerate = textbox_float(self.framerate)
        if new_framerate == 0: new_framerate = 100000.0
        self.frametime.setText( str(np.round(1000.0/new_framerate,3)) )
        self.change_frametime()
    
    def change_roi_pos(self):
        if self.config_thorcam_fs.isChecked(): #configure ThorCam FS
            cam_to_revise = self.camera_fs
        else: #configure main camera
            cam_to_revise = self.camera
            

        cam_to_revise.set_roi_pos([textbox_int(self.roi_pos_choicex), textbox_int(self.roi_pos_choicey)])
        x_pos_str = str(cam_to_revise.roi_pos[0])
        y_pos_str = str(cam_to_revise.roi_pos[1]) 
       
        self.roi_pos_choicex.setText(x_pos_str)
        self.roi_pos_choicey.setText(y_pos_str)

        self.change_frametime() # frametime should be updated after ROI is changed
        self.change_exposure() # exposure should be updated after ROI and frametime are changed
            
    def roi_posx_inc(self):
        new_pos = textbox_int(self.roi_pos_choicex)+10
        self.roi_pos_choicex.setText(str(new_pos))        
        self.change_roi_pos()        

    def roi_posx_dec(self):
        new_pos = textbox_int(self.roi_pos_choicex)-10
        self.roi_pos_choicex.setText(str(new_pos))        
        self.change_roi_pos()

    def roi_posy_inc(self):
        new_pos = textbox_int(self.roi_pos_choicey)+10
        self.roi_pos_choicey.setText(str(new_pos))        
        self.change_roi_pos()        

    def roi_posy_dec(self):
        new_pos = textbox_int(self.roi_pos_choicey)-10
        self.roi_pos_choicey.setText(str(new_pos))        
        self.change_roi_pos()
        
    def reopen_camera(self):
        self.roi_shape = [int(i) for i in
                          str(self.roi_size_choice.currentText()).split(' x ')]
        self.bit_depth = int(str(self.bitdepth_choice.currentText()).split()[0])

        self.camera.open(self.bit_depth, self.roi_shape, camera = self.camera_choice.currentText())
        self.exposure.setText(str( np.round(self.camera.exposure,3) ))
            
        self.frametime.setText(str( np.round(self.camera.frametime,3) ))
        if self.camera.frametime == 0:
            framerate_str = '0'
        else:
            framerate_str = str( np.round(1000.0/self.camera.frametime,3) )                        
        self.framerate.setText(framerate_str) 


        self.livebutton.toggle()
        self.live()

    def change_camera(self, camera_str):
        self.freeze.toggle()
        #if self.camera.pixci_opened:
         #   self.camera.close()
        self.camera.close()
        
        if camera_str == "Simulated":
            self.camera = dummy_image_source.DummyCamera()        
        elif (camera_str == "PhotonFocus") or (camera_str == "Basler"):
            self.camera = epix_framegrabber.Camera()
        elif camera_str == "ThorCam FS":
            self.camera = thorcam_fs.Camera()
        
        self.get_bit_and_roi_choices(camera_str)

        self.reopen_camera()

    def get_bit_and_roi_choices(self, camera_str):
        #assumes the same ROIs are available for each bit depth and ROIs are square
        self.bitdepth_choice.clear()
        self.roi_size_choice.clear()        
        
        bit_depths = []
        ROI_sizes = []
        if camera_str == "Simulated":
            bit_depths.append(8)
            ROI_sizes.append(1024) 


        elif (camera_str == "PhotonFocus") or (camera_str == "Basler"):            
            #find format files and extract ROIs and bit depths
            fmt_file_list = glob( os.path.join("formatFiles", camera_str+'_*.fmt') )
            for fmt_filename in fmt_file_list:
                filename_parsed = fmt_filename.split('_')
                bit_depths.append( int( (filename_parsed[1]).split('b')[0] ))
                ROI_sizes.append( int(((filename_parsed[2]).split('.')[0]).split('x')[0] ))

            bit_depths = list(set(bit_depths)) #get rid of duplicates and sort
            bit_depths.sort()
            ROI_sizes = list(set(ROI_sizes))
            ROI_sizes.sort()
            ROI_sizes.reverse()
        elif camera_str == "ThorCam FS":
            bit_depths.append(8)
            ROI_sizes = range(20,1020,20)
            ROI_sizes.append(1024)
            ROI_sizes.reverse()
            
        for i in np.arange(len(bit_depths)):
            self.bitdepth_choice.insertItem(i,str(bit_depths[i]) + " bit")
        for i in np.arange(len(ROI_sizes)):
            self.roi_size_choice.insertItem(i,str(ROI_sizes[i]) + " x " + str(ROI_sizes[i]))



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


        if self.applybackground.isChecked():
            if self.get_bkgd_from_file.isChecked():
                status = 'stay frozen'
                if self.livebutton.isChecked(): #pause live feed
                    self.freeze.setChecked(True)
                    self.live()
                    status = 'return to live'

                filename = QtGui.QFileDialog.getOpenFileName(
                    self, "Choose a background File", ".",
                    "Tiff Images (*.tif *.tiff)")
                im = fromimage(Image.open(str(filename[0])).convert('I'))
                
                if status == 'return to live':
                    self.livebutton.setChecked(True)
                    self.live()    
                
            else:
                filename = ["Background Set from Buffer"]
                im = self.image
            self.background_image_filename.setText(filename[0])
            # We are going to want to divide by this so make sure it doesn't have
            # any pixels which are 0
            im[im == 0] = 1
            self.background_image = im
            self.divide_background.setChecked(True)
            self.contrast_autoscale.setChecked(True)
        else:
            self.divide_background.setChecked(False)


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

    
    def close_open_thorcam_fs(self):
        
        if self.close_open_thorcam_fs_but.text() == 'Close\nThorCam FS':                
            if self.config_thorcam_fs.isChecked():
                self.config_thorcam_fs.setChecked(False)
                self.switch_configurable_camera()
            self.camera_fs.close()
            self.close_open_thorcam_fs_but.setText('Open\nThorCam FS')
        elif self.close_open_thorcam_fs_but.text() == 'Open\nThorCam FS':
            self.camera_fs.open(bit_depth=8, roi_shape=(1024, 1024), roi_pos=(0,0), camera="ThorCam FS", exposure = 0.01, frametime = 10.0)
            self.camera_fs.start_continuous_capture()
            self.close_open_thorcam_fs_but.setText('Close\nThorCam FS')
            
    
    def switch_configurable_camera(self):
        if self.close_open_thorcam_fs_but.text() == 'Open\nThorCam FS':
            self.close_open_thorcam_fs()
            
        if self.config_thorcam_fs.isChecked(): #configure ThorCam FS
            self.switch_cam_gui_fields(self.camera_fs, False)                            
        else:
            self.switch_cam_gui_fields(self.camera, True)            

    def switch_cam_gui_fields(self, new_cam, enable_flag):
            #setup camera_choice combo box            
            self.camera_choice.setCurrentIndex( self.camera_choice.findText(new_cam.camera) )
            combobox_enable_allbutone(self.camera_choice, self.camera_fs.camera, enable_flag)
            
            #populate bit depth and roi choices
            self.get_bit_and_roi_choices(new_cam.camera)
                    
            #setup bit-depth combo box 
            camera_bitdepth_str = str(new_cam.bit_depth) + " bit"
            self.bitdepth_choice.setCurrentIndex( self.bitdepth_choice.findText(camera_bitdepth_str) )
            
            #setup ROI size combo box
            camera_ROIchoice_str = str(new_cam.roi_shape[0]) + " x " + str(new_cam.roi_shape[0])
            self.roi_size_choice.setCurrentIndex( self.roi_size_choice.findText(camera_ROIchoice_str) )
            
            #setup ROI_pos, exposure, frametime, and framerate boxes
            self.roi_pos_choicex.setText(str(new_cam.roi_pos[0]))
            self.roi_pos_choicey.setText(str(new_cam.roi_pos[1]))
            self.exposure.setText(str( np.round(new_cam.exposure,3) ))                        
            self.frametime.setText(str( np.round(new_cam.frametime,3) ))
            if self.camera.frametime == 0:
                framerate_str = '0'
            else:
                framerate_str = str( np.round(1000.0/new_cam.frametime,3) )                        
            self.framerate.setText(framerate_str) 
                    
    def closing_sequence(self):
    #this will run when the main GUI window is closed 
        self.camera.close()
        if thorcamfs_available:
            if self.close_open_thorcam_fs_but.text() == 'Close\nThorCam FS':
                self.camera_fs.close()
            if self.close_open_stage_but.text() == 'Close\nStage':
                self.camera_fs.close_stage()            
            
    def close_open_stage(self):
        self.lock_pos_box.setChecked(False)
        if self.close_open_stage_but.text() == 'Close\nStage':                
            self.camera_fs.close_stage()
            self.close_open_stage_but.setText('Open\nStage')
            v_out_str = 'NA'
            v_step_str = 'NA'
            
        elif self.close_open_stage_but.text() == 'Open\nStage':
            self.camera_fs.open_stage(self.stage_serialNo.text(), poll_time = 10, v_out = 0.0, v_step = 5.0)
            self.close_open_stage_but.setText('Close\nStage')
            v_out_str = str( round(self.camera_fs.stage_output_voltage, 3) )
            v_step_str = str( round(self.camera_fs.stage_step_voltage, 3) )
            
        self.v_out.setText(v_out_str)           
        self.v_step.setText(v_step_str)           
                    
    def change_output_voltage(self):
        v_out_set = textbox_float(self.v_out)
        if v_out_set > 100:
            v_out_set = 100
        if v_out_set < 0:
            v_out_set = 0
        
        self.camera_fs.set_output_voltage(v_out_set)

                
    def inc_output_voltage(self):
        v_out_new = textbox_float(self.v_out) + textbox_float(self.v_step)
        self.v_out.setText(str( round(v_out_new, 3) ))
        self.change_output_voltage()

    def dec_output_voltage(self):
        v_out_new = textbox_float(self.v_out) - textbox_float(self.v_step)
        self.v_out.setText(str( round(v_out_new, 3) ))
        self.change_output_voltage()

    def change_step_voltage(self):
        v_step_set = textbox_float(self.v_step)
        if v_step_set > 100:
            v_step_set = 100
        if v_step_set < 0:
            v_step_set = 0
        
        self.camera_fs.set_step_voltage(v_step_set)
        self.v_step.setText(str( round(self.camera_fs.stage_step_voltage, 3) ))    
    
    def update_output_voltage(self):
        #update GUI display of stage output voltage
        self.camera_fs.get_output_voltage()        
        self.v_out.setText(str( round(self.camera_fs.stage_output_voltage, 3) ))
        
    def set_lock_pos(self):        
        if self.lock_pos_box.isChecked():
            #get feedback intensity for focus stabilition                
            image = self.camera_fs.get_image()        
            self.feedback_measure_lock = get_feedback_measure(image)[0]
            self.fb_measure_data = []
            self.v_step.setEnabled(False)
            self.v_dec_but.setEnabled(False)
            self.v_inc_but.setEnabled(False)            
            self.fb_measure_to_voltage.setEnabled(False)
            self.max_spot_int_but.setEnabled(False)
            
        else:
            self.v_step.setText(str( round(self.camera_fs.stage_step_voltage, 3) ))        
            self.v_out.setText(str( round(self.camera_fs.stage_output_voltage, 3) ))
            self.feedback_measure_disp.setText('')
            self.fb_measure_to_voltage.setEnabled(True)
            self.v_step.setEnabled(True)
            self.v_dec_but.setEnabled(True)
            self.v_inc_but.setEnabled(True)
            self.max_spot_int_but.setEnabled(True)

    def correct_stage_voltage(self):
        #update voltage output based on feedback spot position
        max_adjust = 1 #max voltage adjustment allowable (in %)
        
        #get center of spot
        image = self.camera_fs.get_image()        
        feedback_measure, self.fb_sum = get_feedback_measure(image)
        
        #choose update voltage
        update_voltage = self.camera_fs.stage_output_voltage + get_voltage_adjustment(self.feedback_measure_lock, feedback_measure, textbox_float(self.fb_measure_to_voltage))
        
        if abs(self.camera_fs.stage_output_voltage - update_voltage) > max_adjust:
            #if voltage adjustment is too large
            self.lock_pos_box.setChecked(False)
            self.v_out.setText( str( round(self.camera_fs.stage_output_voltage, 3) ) )
            self.v_step.setText( str( round(self.camera_fs.stage_step_voltage, 3) ) )
            self.feedback_measure_disp.setText('')
            self.fb_measure_to_voltage.setEnabled(True)
            self.v_step.setEnabled(True)
            self.v_dec_but.setEnabled(True)
            self.v_inc_but.setEnabled(True)
            self.max_spot_int_but.setEnabled(True)                      
            print('Attempted voltage adjustment too large')
        
        else:
            #set update voltage
            self.camera_fs.set_output_voltage(update_voltage)
            self.feedback_measure_disp.setText('Feedback measure = ' + str(feedback_measure) )
            self.fb_measure_data.append(feedback_measure)
            if not len(self.fb_measure_data)%100:
                self.fb_measure_ax.plot(self.fb_measure_data)
                self.fb_measure_canvas.draw()
                if len(self.fb_measure_data) > 2999:
                    #np.savetxt('fb_measure_data.txt', self.fb_measure_data) 
                    self.fb_measure_data = []
                    

    def mousePressEvent(self, QMouseEvent):
        if self.max_spot_int_but.isChecked():
            mouse_pos = QMouseEvent.pos()
            mouse_pos = np.array([mouse_pos.x(), mouse_pos.y()])
            if mouse_pos[0] >= 10 and mouse_pos[0] < 910 and mouse_pos[1] >= 10 and mouse_pos[1] < 910:
                self.maximize_spot_intensity(mouse_pos = mouse_pos)
                

    def maximize_spot_intensity(self, mouse_pos = None):
        #initalize spot intensity
        self.image = self.camera.get_image()       
        #convert from display pixels to camera pixels
        disp_to_cam = np.array(self.image.shape)/float(im_display_size)
        cam_pos = (mouse_pos-10)*disp_to_cam                    
        y,x = np.ogrid[-cam_pos[0]:self.image.shape[0]-cam_pos[0], -cam_pos[1]:self.image.shape[1]-cam_pos[1]]                   
        mask = x*x + y*y <= (textbox_float(self.spot_diam)*0.5)**2
        mask = np.transpose(mask)
        spot_intensity = np.mean(self.image[mask])
        
        v_range = textbox_float(self.v_focus_range) #voltage percentage range to scan over
        
        v_guess = textbox_float(self.v_out) #guess voltage for focus
        
        while v_range >= 0.1: #do loss coarse adjustments
            
            #scan over voltage range, measuring spot intensity
            v_values = np.linspace(v_guess-v_range/2.0, v_guess+v_range/2.0, 10)
            spot_intensities = np.empty(v_values.shape)
            for ii in range(len(v_values)):
                self.camera_fs.set_output_voltage(v_values[ii])
                time.sleep(0.1)
                self.image = self.camera.get_image()
                self.showImage()                
                spot_intensities[ii] = np.mean(self.image[mask])
            '''file_name = 'spot_intensities.txt'
            with open(file_name, 'a') as f_handle:
                np.savetxt(f_handle, spot_intensities, header = str(v_range))'''
            print [spot_intensities, v_range]
            v_guess  = v_values[spot_intensities.argmax() ]        
            if v_range > 0.1:
                v_range = max(0.1, v_range/5.0)
            else:
                v_range = 0.0
        
        self.camera_fs.set_output_voltage( v_values[spot_intensities.argmax()] )        
        self.max_spot_int_but.setChecked(False)
        
        #start feedback loop
        #self.lock_pos_box.setChecked(True)           
        #self.set_lock_pos()
        
                 
def get_voltage_adjustment(feedback_measure_lock, feedback_measure_new, fb_measure_to_voltage):

    voltage_adjust = (feedback_measure_lock - feedback_measure_new) * fb_measure_to_voltage
    return voltage_adjust  

        

def get_feedback_measure(image):
    # image is a 2D array

    # get y moment of gaussian distribution
    image = gaussian_filter(image,0)
    total = float(image.sum())
    Y = np.indices(image.shape)[1]
    y = (Y*image).sum()/total
    return y, total
    
    #return center_of_mass(gaussian_filter(image, 0))[1]

  
    
            
def combobox_enable_allbutone(combobox, exception, enable):
    #enable or disable all elements of a combobox, except for the item with text string <exception>
    #to enable, set enable = True. To disable set enable = False
    for ii in range(combobox.count()):
        if combobox.itemText(ii) != exception:
            combobox.model().item(ii).setEnabled(enable)    
            
def write_timeseries(filename, imageNums, metadata=None, self=None):
    #write_single "thumbmail" image for the first frame
    write_image(filename+'.tif',self.camera.get_image(imageNums[0]), metadata=metadata)
    print 'saving time series'

    uncompressed_name = filename+'.uncompressed.h5'
    f = h5py.File(uncompressed_name,'w')
    j = 0
    for i in imageNums:
        store_image(f,str(j),i,self)
        #print 'saving image: '+ str(i)
        j += 1
    f.close()

    p = Process(target=compress_h5, args=(uncompressed_name, True))
    p.start()

    #TODO: metadata

def store_image(fileobj, datasetname, imageNum, self):
    fileobj.create_dataset(datasetname, data=self.camera.get_image(imageNum))


def write_image(filename, image, metadata=None):
    print 'writing image: {}'.format(filename)
    to_pil_image(image).save(filename, autoscale=False,
                             tiffinfo={270 : json.dumps(metadata)})

def to_pil_image(image):
    if image.dtype == 'uint16':
        # PIL can't handle uint16, so we convert to int16 before sending to pil
        image = image.astype('int16')
    return Image.fromarray(image)

def main():

    app = QtGui.QApplication(sys.argv)
    ex = captureFrames()
    app.aboutToQuit.connect(ex.closing_sequence)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
    
