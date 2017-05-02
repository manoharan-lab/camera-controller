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

import numpy as np
import scipy.fftpack as fftpack

def fourier_filter2D(data, f_filter):
    '''Fourier filters a 2D array. by multiplying it with a filter in fourier space.
    TODO: extend this to a 1D and 3D (or nD) fourier filter?
     
    data = input array
    f_filter  = 2D array to use as the fourier filter
        Mirroring of the image is used to avoid edge ringing if f_filter is 3 times the size of data
    If data is 3D. It is assumed that data is a stack of 2D images.    
    '''
    if len(data.shape) == 2:
        # if f_filter is 3*data.shape, tile mirrored images of data to avoid ringing
        if f_filter.shape == tuple((3*np.array(data.shape))):
            data = np.concatenate( (data[:,::-1], data, data[:,::-1]) , 1)
            data = np.concatenate( (data[::-1,:], data, data[::-1,:]) , 0)
            data = ifft( f_filter * fft(data) )
            data = data[data.shape[0]/3 : 2*data.shape[0]/3, data.shape[1]/3 : 2*data.shape[1]/3]
        else:
            data = ifft( f_filter * fft(data) )

    
    elif len(data.shape)== 3:
        for i in range(0,data.shape[index_3D]):
            if i%100:
                print('Fourier Filter Frame '+str(i) )

            data[:,:,i] = fourier_filter2D(data[:,:,i], f_filter)
                    
    return abs(data)    

def bandpass_filter(filter_shape, px_bd = [None,None], blur = [None,None]):
    ''' creates a 2D bandpass filter. Ony works with a square image
    TODO: extend this to a 1D and 3D (or nD) bandpass filter. Use rectangular images.
    
    filter_shape = array of length 2 giving output filter shape
        to avoid ringing when using this with fourier_filter2D(), specify filter_shape = 3*np.array(data.shape)
    px_bd = array of length 2 giving low and high real space distance cutoffs for filter. 
        specifying None for either axis gives a low or high pass filter. If both axis are None returns an array of 1's.
    blur = array of length 2 giving width of gaussian blur to use to smooth edge of low and high real space cutoffs. Default = None, means no smoothing
    
    returns a 2D image to use as a bandpass filter in Fourier space.
    The center pixel is always set to 0
    '''
    
    #create high pass filter
    if px_bd[0] != None:
        freq_max = float(filter_shape[0])/px_bd[0]/2.
        bandpassfilter = round_filter(filter_shape[:2], freq_max, blur = blur[1])
        
        #create bandpass filter
        if px_bd[1] != None:
            freq_min = float(filter_shape[0])/px_bd[1]/2.
            bandpassfilter = ((1-round_filter(filter_shape, freq_min, blur = blur[0])) + round_filter(filter_shape, 0.5, blur = None)) * bandpassfilter
            
    #create low pass filter 
    elif px_bd[1] != None:
        freq_min = float(filter_shape[0])/px_bd[1]/2.
        bandpassfilter = ((1-round_filter(filter_shape, freq_min, blur = blur[0])) + round_filter(filter_shape, 0.5, blur = None))
    
    #don't filter anything 
    else:
        bandpassfilter = np.ones(filter_shape,dtype = int)

    return bandpassfilter
    
    

def round_filter(c_shape, radius, center = None, rot = None, blur = None):
    '''
    TODO: generalize this so ellipsoids can be rotated out of x-y plane
    create a round (line, ellipse, ellipsoid) filter with smoothed edges to multiply an image (volume) with
    c_shape = shape of output filter
    radius = radii of output filter circle. Can be a scalar for circles/spheres or a list for ellipses/ellipsoids.
    center = center of output filter circle. Default = None uses center of output array.
    blur = width of gaussian blur to use to smooth edge of circle. Default = None, means no smoothing 
    rot = angle (in radians) specifying orientation of ellipse in x-y plane. The angle is from the x-axis to the x-minor-axis of the ellipse.
         Still need to implement rotation out of x-y plane
    
    returns array with shape of c_shape. It contains 1's inside the radius and 0's outside the radius.
    
    equation for 2D rotated ellipse taken from here
    http://math.stackexchange.com/questions/426150/what-is-the-general-equation-of-the-ellipse-that-is-not-in-the-origin-and-rotate
    '''

    if center == None:
        center = np.array(c_shape)/2

    if len(c_shape) == 1:
        if isinstance(radius, list) or isinstance(radius, np.ndarray):
            radius = radius[0]    
        x = np.ogrid[-center[0]:c_shape[0]-center[0]]  #create grid centered at ellipse center
        mask = x*x <= radius*radius
   
    elif len(c_shape) == 2:
        if not (isinstance(radius, list) or isinstance(radius, np.ndarray) ):
            radius = radius*np.ones(2)
        x,y = np.ogrid[-center[0]:c_shape[0]-center[0], -center[1]:c_shape[1]-center[1]] #create grid centered at ellipse center
        if rot == None or rot == 0: #non-rotated ellipse
            mask = (x/float(radius[0]))**2 + (y/float(radius[1]))**2 <= 1.0
        else: #rotated ellipse
            mask = ( (x*np.cos(rot)+y*np.sin(rot))/float(radius[0]) )**2 + ( (x*np.sin(rot)-y*np.cos(rot))/float(radius[1]) )**2 <= 1.0
                    
    elif len(c_shape) == 3:
        if not (isinstance(radius, list) or isinstance(radius, np.ndarray) ):
            radius = radius*np.ones(3)
        x,y,z = np.ogrid[-center[0]:c_shape[0]-center[0], -center[1]:c_shape[1]-center[1], -center[2]:c_shape[2]-center[2]] #create grid centered at ellipse center 
        if rot == None or rot == 0:#non-rotated ellipse
            mask = (x/float(radius[0]))**2 + (y/float(radius[1]))**2 + (z/float(radius[2]))**2 <= 1.0
        else: #ellipse rotated in x-y plane
            mask = ( (x*np.cos(rot)+y*np.sin(rot))/float(radius[0]) )**2 + ( (x*np.sin(rot)-y*np.cos(rot))/float(radius[1]) )**2 + (z/float(radius[2]))**2 <= 1.0
    
    circle = np.zeros(c_shape)           
    circle[mask] = 1
    
    if not (blur == None or blur == 0):
        from scipy.ndimage import gaussian_filter
        circle = gaussian_filter(circle, blur)
    
    return circle
    

def fft(a, overwrite=False, shift=True):
    """ Taken from holopy https://github.com/manoharan-lab/holopy on May 2, 2017.
    More convenient Fast Fourier Transform
    An easier to use fft function, it will pick the correct fft to do
    based on the shape of the array, and do the fftshift for you.  This
    is intended for working with images, and thus for dimensions
    greater than 2 does slicewise transforms of each "image" in a
    multidimensional stack
    Parameters
    ----------
    a : ndarray
       The array to transform
    overwrite : bool
       Allow this function to overwrite the Marry you pass in.  This
       may improve performance slightly.  Default is not to overwrite
    shift : bool
       Whether to preform an fftshift on the Marry to give low
       frequences near the center as you probably expect.  Default is
       to do the fftshift.
    Returns
    -------
    fta : ndarray
       The fourier transform of `a`
    """
    if a.ndim is 1:
        if shift:
            res = fftpack.fftshift(fftpack.fft(a, overwrite_x=overwrite))
        else:
            res = fftpack.fft(a, overwrite_x=overwrite)
    else:
        if shift:
            res = fftpack.fftshift(fftpack.fft2(a, axes=[0, 1],
                                                 overwrite_x=overwrite),
                                    axes=[0,1])
        else:
            res = fftpack.fft2(a, axes=[0, 1], overwrite_x=overwrite)
    return res


def ifft(a, overwrite=False, shift=True):
    """ Taken from holopy https://github.com/manoharan-lab/holopy on May 2, 2017.
    More convenient Inverse Fast Fourier Transform
    An easier to use ifft function, it will pick the correct ifft to
    do based on the shape of the input array, and do the fftshift for you.
    This is intended for working with images, and thus for
    dimensions greater than 2 does slicewise transforms of each
    "image" in a multidimensional stack
    Parameters
    ----------
    a : ndarray
       The array to transform
    overwrite : bool
       Allow this function to overwrite the Marry you pass in.  This
       may improve performance slightly.  Default is not to overwrite
    shift : bool
       Whether to preform an fftshift on the Marry to give low
       frequences near the center as you probably expect.  Default is to
       do the fftshift.
    Returns
    -------
    ifta : ndarray
       The inverse fourier transform of `a`
    """
    if a.ndim is 1:
        if shift:
            res = fftpack.ifft(fftpack.fftshift(a, overwrite_x=overwrite))
        else:
            res = fftpack.ifft(a, overwrite_x=overwrite)
    else:
        if shift:
            res = fftpack.ifft2(fftpack.fftshift(a, axes=[0,1]), axes=[0, 1],
                                 overwrite_x=overwrite)
        else:
            res = fftpack.ifft2(a, overwrite_x=overwrite)

    return res
    
