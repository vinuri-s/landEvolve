#!/usr/bin/env python3
"""
Drive landscape evolution with pseudo-random earthquake
sequences.

@author: amforte
"""

from .fault_generator import DippingFault, VerticalFault

import multiprocessing as mp

import numpy as np
from landlab import RasterModelGrid, HexModelGrid
from landlab.grid.mappers import map_mean_of_link_nodes_to_link
import okada4py as ok92
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import Normalize
from matplotlib import path

from scipy.special import gammaincc 
from scipy.stats import rv_continuous

import pprint

import warnings
import pickle
import copy
import os



def _rot_coord(x,y,xo,yo,angle):
    '''
    Rotates a set of x,y coordinates about an origin point by a specified angle

    Parameters
    ----------
    x : float, or array of floats
        x-coordinate of positions to be rotated.
    y : float, or array of floats
        y-coordinate of positions to be rotated.
    xo : float
        x-coordinate of origin of rotated coordinate system.
    yo : float
        y-coordinate of origin of rotated coordinate system.
    angle : float
        angle in degrees to rotate coordinate system.

    Returns
    -------
    xp : float, or array of floats
        x-coordinates of rotated positions.
    yp : float, or array of floats
        y-coordinates of rotated positions.

    '''
    xp = (x*np.cos(np.radians(angle)) + y*np.sin(np.radians(angle))) + xo
    yp = (-x*np.sin(np.radians(angle)) + y*np.cos(np.radians(angle))) + yo
    return xp,yp

def _rot_coord_inv(xp,yp,xo,yo,angle):
    '''
    Un-rotates a set of x,y coordinates about an origin point by a specified angle

    Parameters
    ----------
    xp : float, or array of floats
        x-coordinate of rotated positions.
    yp : float, or array of floats
        y-coordinate of positions to be rotated.
    xo : float
        x-coordinate of origin of rotated coordinate system.
    yo : float
        y-coordinate of origin of rotated coordinate system.
    angle : float
        original angle in degrees that rotated the coordinate system.

    Returns
    -------
    x : float, or array of floats
        original x-coordinates before rotation.
    y : float, or array of floats
        original y-coordinates before rotation.

    '''
    x = (xp*np.cos(np.radians(angle)) - yp*np.sin(np.radians(angle))) - xo
    y = (xp*np.sin(np.radians(angle)) + yp*np.cos(np.radians(angle))) - yo
    return x,y

def _survive(x):
    """
    Calculates survival function  (1 - cumulative distribution function) of 
    an arbitrary array

    Parameters
    ----------
    x : array of floats
        variable for which to calculate the survivor function.

    Returns
    -------
    x_sort : array of floats
        sorted version of input variable.
    x_freq_excd : TYPE
        exceedance frequency of sorted variable.

    """
    x_sort=np.sort(x)
    xn=len(x_sort)
    xrank=np.arange(1,xn+1,1)
    x_freq_excd=(xn+1-xrank)/xn
    return x_sort,x_freq_excd

def _cumcount(x):
    """
    Calculates cumulative count of an arbitrary array

    Parameters
    ----------
    x : array of floats
        variable for which to calculate the cumulative rank.

    Returns
    -------
    x_sort : array of floats
        sorted version of input variable.
    x_count : array of floats
        cumulative count of sorted variable.

    """
    x_sort = np.flip(np.sort(x))
    x_ones = np.ones(x.shape)
    x_count = np.cumsum(x_ones)
    return x_sort,x_count

def _eq_moment_to_magnitude(M0):
    """
    Converts scalar seismic moment in Newton-meters to moment magnitude 

    Parameters
    ----------
    M0 : float or array of floats
        scalar seismic moments in N-m.

    Returns
    -------
    Mw : float or array of floats
        moment magnitude.

    """
    Mw = np.zeros(M0.shape)
    idx = M0>0
    Mw[idx] = (2/3)*np.log10(M0[idx]) - 6.07
    return Mw

def _eq_magnitude_to_moment(Mw):
    """
    Converts moment magnitude to scalar seismic moment in Newton-meters

    Parameters
    ----------
    Mw : float or array of floats
        moment magnitude.

    Returns
    -------
    M0 : float or array of floats
        scalar seismic moment in N-m.

    """
    return 10**((Mw + 6.07)/(2/3))

def _Y_func(b,a,X):
    """
    Takes a function of form log(X) = a + b*log10(Y) and inverts 
    it to solve for Y

    Parameters
    ----------
    b : float
        coefficeint on log.
    a : float
        constant.
    X : float or array of floats
        unknown on left side of equal sign.

    Returns
    -------
    Y : float or array of floats
        unknown on right side of equal sign.

    """
    logX = np.log10(X)
    Y = 10**((logX-a)/b)
    return Y

def _X_func(b,a,Y):
    """
    Directly solves function of form log(X) = a + b*log(Y)

    Parameters
    ----------
    b : float
        coefficeint on log.
    a : float
        constant.
    Y : float or array of floats
        unknown on right side of equal sign.

    Returns
    -------
    X : float or array of floats
        unknown on left side of equal sign.

    """
    logY = np.log10(Y)
    X = 10**(a + b*logY)
    return X


def _leonard14_scaling(fault_type,M0=None,L=None,W=None):
    """
    Implements calculation of rupture length (L), rupture width (W), 
    rupture area (A), rupture average displacement (D), and scalar seismic moment (M0)
    based on the self consistent scaling relationships from Table 3 of Leonard, 2014, BSSA 
    
    Can accept inputs of known scalar seismic moment (M0), length (L), or width (W)

    Parameters
    ----------
    M0 : array of floats, optional
        Seismic moments of events to calculate rupture parameters. 
        The default is None.
    L : array of floats, optional
        Length of events to calculate rupture parameters. 
        The default is None.
    W : array of floats, optional
        Width of events to calculate rupture parameters. The default is None.


    Returns
    -------
    L : array of floats
        Length of ruptures (m).
    W : array of floats
        Width of ruptures (m).
    A : array of floats
        Area of ruptures (m^2).
    D : array of floats
        Displacement of ruptures (m).
    M0 : array of floats
        Seismic moment of ruptures (N-m).

    """

    if np.all(M0==None) & np.all(L==None) & np.all(W==None):
        raise Exception('Must provide an input for either "M0", "L", "W"')
    if np.all(M0!=None) & np.all(L!=None) & np.all(W!=None):
        raise Exception('Cannot provide values for both "M0",  "L" , and "W"')

    if np.all(M0!=None):
        if fault_type=='Interplate_DS':
            # Calculate Area
            A = _Y_func(1.5,6.098,M0)
            # Calculate D
            D = _X_func(0.5,-4.420,A)
            # Calculate W
            W=np.zeros(A.shape)
            Aidx=A<=28.7e6
            W[Aidx]=_X_func(0.5,0,A[Aidx])
            W[~Aidx]=_X_func(0.4,0.746,A[~Aidx])
            # Calculate L (Assumes rectangular fault)
            L=A/W
        elif fault_type=='Interplate_SS':
            # Calculate Area
            A = _Y_func(1.5,6.087,M0)
            # Calculate D
            D = _X_func(0.5,-4.432,A)
            # Calculate W
            W=np.zeros(A.shape)
            Aidx1 = A<=11.5e6
            Aidx2 = (A>11.5e6) & (A<=702e6)
            Aidx3 = A>702e6
            W[Aidx1] = _X_func(0.5,0,A[Aidx1])
            W[Aidx2] = _X_func(0.4,0.706,A[Aidx2])
            W[Aidx3] = _X_func(0,4.244,A[Aidx3])
            # Calculate L
            L=A/W
        elif fault_type=='SCR_DS':
            # Calculate Area
            A = _Y_func(1.5,6.38,M0)
            # Calculate D
            D = _X_func(0.5,-4.137,A)
            # Calculate W
            W=np.zeros(A.shape)
            Aidx=A<=6.2e6
            W[Aidx]=_X_func(0.5,0,A[Aidx])
            W[~Aidx]=_X_func(0.4,0.678,A[~Aidx])
            # Calculate L (Assumes rectangular fault)
            L=A/W
        elif fault_type=='SCR_SS':
            # Calculate Area
            A = _Y_func(1.5,6.370,M0)
            # Calculate D
            D = _X_func(0.5,-4.149,A)
            # Calculate W
            W=np.zeros(A.shape)
            Aidx1 = A<=2.5e6
            Aidx2 = (A>2.5e6) & (A<=1400e6)
            Aidx3 = A>1400e6
            W[Aidx1] = _X_func(0.5,0,A[Aidx1])
            W[Aidx2] = _X_func(0.4,0.641,A[Aidx2])
            W[Aidx3] = _X_func(0,4.298,A[Aidx3])
            # Calculate L
            L=A/W
    elif np.all(L!=None):
        if fault_type=='Interplate_DS':
            Lidx=L<=5360
            # Calculate Area
            A=np.zeros(L.shape)
            A[Lidx] = _X_func(2.0,0,L[Lidx])
            A[~Lidx] = _X_func(1.667,1.243,L[~Lidx])
            # Calculate D
            D=np.zeros(L.shape)
            D[Lidx] = _X_func(1.0,-4.420,L[Lidx])
            D[~Lidx] = _X_func(0.833,-3.799,L[~Lidx])
            # Calculate W
            W=np.zeros(L.shape)
            W[Lidx]=_X_func(1.0,0,L[Lidx])
            W[~Lidx]=_X_func(0.668,1.243,L[~Lidx])
            # Calculate M0
            M0=np.zeros(L.shape)
            M0[Lidx]=_X_func(3.0,6.098,L[Lidx])
            M0[~Lidx]=_X_func(2.5,7.963,L[~Lidx])                
        elif fault_type=='Interplate_SS':
            Lidx1=L<=3400
            Lidx2=(L>3400) & (L<=40000)
            Lidx3=L>40000
            # Calculate Area
            A=np.zeros(L.shape)
            A[Lidx1] = _X_func(2.0,0,L[Lidx1])
            A[Lidx2] = _X_func(1.667,1.176,L[Lidx2])
            A[Lidx3] = _X_func(1.0,4.244,L[Lidx3])
            # Calculate D
            D=np.zeros(L.shape)
            D[Lidx1] = _X_func(1.0,-4.432,L[Lidx1])
            D[Lidx2] = _X_func(0.833,-3.844,L[Lidx2])
            D[Lidx3] = _X_func(0.5,-2.310,L[Lidx3])
            # Calculate W
            W=np.zeros(L.shape)
            W[Lidx1] = _X_func(1.0,0,L[Lidx1])
            W[Lidx2] = _X_func(0.667,1.176,L[Lidx2])
            W[Lidx3] = _X_func(0,4.244,L[Lidx3])
            # Calculate M0
            M0=np.zeros(L.shape)
            M0[Lidx1] = _X_func(3.0,6.087,L[Lidx1])
            M0[Lidx2] = _X_func(2.5,7.851,L[Lidx2])
            M0[Lidx3] = _X_func(1.5,12.45,L[Lidx3])
        elif fault_type=='SCR_DS':
            Lidx=L<=2500
            # Calculate Area
            A=np.zeros(L.shape)
            A[Lidx] = _X_func(2.0,0,L[Lidx])
            A[~Lidx] = _X_func(1.667,1.130,L[~Lidx])
            # Calculate D
            D=np.zeros(L.shape)
            D[Lidx] = _X_func(1.0,-4.137,L[Lidx])
            D[~Lidx] = _X_func(0.833,-3.572,L[~Lidx])
            # Calculate W
            W=np.zeros(L.shape)
            W[Lidx]=_X_func(1.0,0.0,L[Lidx]) # In Leonard, 2014, a is 1.0, but assume this is mis-print
            W[~Lidx]=_X_func(0.667,1.130,L[~Lidx])
            # Calculate M0
            M0=np.zeros(L.shape)
            M0[Lidx]=_X_func(3.0,6.382,L[Lidx])
            M0[~Lidx]=_X_func(2.5,8.077,L[~Lidx]) 
        elif fault_type=='SCR_SS':
            Lidx1=L<=1600
            Lidx2=(L>1600) & (L<=70000)
            Lidx3=L>70000
            # Calculate Area
            A=np.zeros(L.shape)
            A[Lidx1] = _X_func(2.0,0,L[Lidx1])
            A[Lidx2] = _X_func(1.667,1.068,L[Lidx2])
            A[Lidx3] = _X_func(1.0,4.298,L[Lidx3])
            # Calculate D
            D=np.zeros(L.shape)
            D[Lidx1] = _X_func(1.0,-4.149,L[Lidx1])
            D[Lidx2] = _X_func(0.833,-3.615,L[Lidx2])
            D[Lidx3] = _X_func(0.5,-2.022,L[Lidx3])
            # Calculate W
            W=np.zeros(L.shape)
            W[Lidx1] = _X_func(1.0,0,L[Lidx1])
            W[Lidx2] = _X_func(0.667,1.068,L[Lidx2])
            W[Lidx3] = _X_func(0,4.298,L[Lidx3])
            # Calculate M0
            M0=np.zeros(L.shape)
            M0[Lidx1] = _X_func(3.0,6.370,L[Lidx1])
            M0[Lidx2] = _X_func(2.5,7.972,L[Lidx2])
            M0[Lidx3] = _X_func(1.5,12.750,L[Lidx3])
    elif np.all(W!=None):
        if fault_type=='Interplate_DS':
            Widx = W <= 5360
            # Calculate L
            L=np.zeros(W.shape)
            L[Widx] = W[Widx]
            L[~Widx] = _Y_func(0.667,1.243,W[~Widx])
            Lidx=L<=5360
            A=np.zeros(L.shape)
            A[Lidx] = _X_func(2.0,0,L[Lidx])
            A[~Lidx] = _X_func(1.667,1.243,L[~Lidx])
            # Calculate D
            D=np.zeros(L.shape)
            D[Lidx] = _X_func(1.0,-4.420,L[Lidx])
            D[~Lidx] = _X_func(0.833,-3.799,L[~Lidx])
            # Calculate M0
            M0=np.zeros(L.shape)
            M0[Lidx]=_X_func(3.0,6.098,L[Lidx])
            M0[~Lidx]=_X_func(2.5,7.963,L[~Lidx])
        elif fault_type=='SCR_DS':
            Widx = W <= 2500
            # Calculate L
            L=np.zeros(W.shape)
            L[Widx] = _Y_func(1.0,1.0,W[Widx])
            L[~Widx] = _Y_func(0.667,1.130,W[~Widx]) 
            Lidx=L<=2500
            # Calculate Area
            A=np.zeros(L.shape)
            A[Lidx] = _X_func(2.0,0,L[Lidx])
            A[~Lidx] = _X_func(1.667,1.130,L[~Lidx])
            # Calculate D
            D=np.zeros(L.shape)
            D[Lidx] = _X_func(1.0,-4.137,L[Lidx])
            D[~Lidx] = _X_func(0.833,-3.572,L[~Lidx])
            # Calculate M0
            M0=np.zeros(L.shape)
            M0[Lidx]=_X_func(3.0,6.382,L[Lidx])
            M0[~Lidx]=_X_func(2.5,8.077,L[~Lidx])                 
        elif fault_type=='Interplate_SS':
            raise Exception('Scaling is not fully defined based on widths for strike-slip faults')
        elif fault_type=='SCR_SS':
            raise Exception('Scaling is not fully defined based on widths for strike-slip faults')
            
    return L,W,A,D,M0

def _aftershocks(Mw_parents,M0_parents,Mw_min,Mw_max,
                  seed,b_d,delta_m_star,c,p,d,q):
    """
    Generates a series of aftershocks for a given input sequence of
    earthquakes using the BASS algorithm

    Parameters
    ----------
    Mw_parents : array of floats
        Moment magnitude of parent events.
    M0_parents : array of floats
        Scalar seismic moment of parent events.
    Mw_min : float
        Minimum magnitude that can generate an aftershock and minimum 
        magnitude of generated aftershocks.
    Mw_max : float
        Maximum magnitude of aftershock/foreshock permitted in the catalog.
    seed : int
        Seed for random number generation, for reproducibility.
    b_d : float
        The b sub d parameter in the modified Bath's law, see Turcotte et al., 2007 for 
        more discussion.
    delta_m_star : float
        The delta m star parameter in the modified Bath's law, see Turcotte et al., 2007
        for more details.
    c : float
        The c parameter in Omori's law, see Turcotte et al., 2007 for more details.
    p : float
        The p parameter in Omori's law, see Turcotte et al., 2007 for more details.
    d : float
        The d parameter in the spatial Omori's law, see Turcotte et al., 2007 
        for more detail.
    q : float
        The q parameter in the spatial Omori's law, see Turcotte et al., 2007
        for more detail.

    Returns
    -------
    Mw : array of floats
        Moment magnitude of all events including parents and children.
    M0 : array of floats
        Scalar seismic moments of all events including parents and children.
    t_offset : array of floats
        Time in years from the parent event to the child occurrence,
        value is -1 for parent events.
    rad : array of floats
        Radial distance of child events from parents, value is 0 for parent
        events.
    parent : list of numpy arrays
        List of event IDs, each element of list is a numpy array. First ID will
        always be the parent ID that generated the event chain followed by a
        variable number of integers. For example, if the ID_parent was 10 and an 
        element of the list was [10, 5] this would imply that this was the sixth 
        (counting starts at 0) aftershock that was directly spawned by the parent event. 
        Instead if the element was [10, 5, 1, 0], this would imply this event is the 
        first aftershock of  an event that was the second aftershock of an event that 
        was the sixth aftershock of the original parent event. This parent list can 
        be used to trace back details of events necessary since timing and distance
        are relative to the parent, but where the parent is to that aftershock,
        not necessarily the original parent event. 

    """
    
    # Generate empty numpy arrays to build on
    Mw = np.array([]); M0 = np.array([]); 
    t_offset = np.array([]); 
    rad = np.array([])
    # Generate empty list for id chains
    parent = []
    # Count events
    num_events = len(Mw_parents)
    # Generate unique ids for parents
    ID_parents = np.arange(0,num_events,1)
    
        
    for i in range(num_events):
        if Mw_parents[i]>Mw_min:
            m_d,t_d,r_d,p_d = _BASS(Mw_parents[i],ID_parents[i],Mw_min,Mw_max,delta_m_star,b_d,c,p,d,q,seed+i)
            
            # Some parents just above minimum will also not generate any 
            # aftershocks, short circuit if this is the case
            if m_d.shape[0]==0:
                # Only append the parent to the running list
                Mw = np.append(Mw,np.array([Mw_parents[i]]))
                M0 = np.append(M0,np.array([M0_parents[i]]))
                t_offset = np.append(t_offset,np.array([-1]))

                rad = np.append(rad,np.array([0]))
                parent.append(np.array([ID_parents[i]]))
            else:
                # Process aftershock sequence
                M0_d = _eq_magnitude_to_moment(m_d)
                
                # Append details of parent event first
                Mw = np.append(Mw,np.array([Mw_parents[i]]))
                M0 = np.append(M0,np.array([M0_parents[i]]))
                t_offset = np.append(t_offset,np.array([-1]))
                rad = np.append(rad,np.array([0]))
                parent.append(np.array([ID_parents[i]]))
                
                # Append details of aftershocks
                Mw = np.append(Mw,m_d)
                M0 = np.append(M0,M0_d)
                t_offset = np.append(t_offset,t_d)
                rad = np.append(rad,r_d)
                parent = parent+p_d
        else:
            # No aftershocks are generated if the parent is equal to the Mw_min
            Mw = np.append(Mw,np.array([Mw_parents[i]]))
            M0 = np.append(M0,np.array([M0_parents[i]]))
            t_offset = np.append(t_offset,np.array([-1]))
            rad = np.append(rad,np.array([0]))
            parent.append(np.array([ID_parents[i]]))
            
    return Mw, M0, t_offset, rad, parent


def _BASS(Mw_parent,ID_parent,Mw_min,Mw_max,delta_m_star,b_d,c,p,d,q,seed,max_order=30):
    """
    Implementation of recursive BASS model for simulating an aftershock sequence 
    from Turcotte et al., 2007 for a single parent event. Modified to prevent 
    any aftershocks greater than imposed Mw_max from occurring.

    Parameters
    ----------
    Mw_parent : float
        Moment magnitude of parent event.
    ID_parent : int
        Identifying integer for parent event.
    Mw_min : float
        Minimum moment magnitude for aftershocks.
    Mw_max : float
        Maximum moment magnitude for aftershocks.
    b_d : float
        The b sub d parameter in the modified Bath's law, see Turcotte et al., 2007 for 
        more discussion.
    delta_m_star : float
        The delta m star parameter in the modified Bath's law, see Turcotte et al., 2007
        for more details.
    c : float
        The c parameter in Omori's law, see Turcotte et al., 2007 for more details.
    p : float
        The p parameter in Omori's law, see Turcotte et al., 2007 for more details.
    d : float
        The d parameter in the spatial Omori's law, see Turcotte et al., 2007 
        for more detail.
    q : float
        The q parameter in the spatial Omori's law, see Turcotte et al., 2007
        for more detail.
    seed : int
        Seed for random number generation, for reproducibility.
    max_order : int, optional
        Limit on number of recursive sequences to allow as a catch to prevent 
        infinite loop. The default is 30.

    Returns
    -------
    m_d : array of floats
        Moment magnitude of child events.
    t_d : array of floats
        Time in years for child events relative to parent
    r_d : array of floats
        Radial distance of child events relative to parent
    p_d : list of numpy arrays
        List of event IDs, each element of list is a numpy array. First ID will
        always be the input ID_parent followed by a variable number of integers.
        For example, if the ID_parent was 10 and an element of the list was 
        [10, 5] this would imply that this was the sixth (counting starts at 0)
        aftershock that was directly spawned by the parent event. Instead if the element
        was [10, 5, 1, 0], this would imply this event is the first aftershock of 
        an event that was the second aftershock of an event that was the sixth aftershock
        of the original parent event.

    """
    
    def num_aftershocks(m_parent,m_min,b_d,delta_m_star):
        # Equation 8  from Turcotte et al., 2017
        return int(10**(b_d*(m_parent - delta_m_star - m_min)))

    def magnitude_of_daughter(P,m_min,b_d):
        # Rearrangement of equation 9 to solve for daughter magnitude
        return (np.log10(P) - b_d*m_min)/-b_d
        
    def time_of_daughter(P,c,p):
        # Rearrangment of equation 13 to solve for daughter time
        return ((1/P)**(1/(p-1)) - 1) * c

    def distance_of_daughter(P,d,m_parent,q):
        # Rearrangement of equation 14 to solve for radial distance of daughter
        return ((1/P)**(1/(q-1)) - 1) * (d*10**(0.5*m_parent))

    def single_BASS_sequence(m_parent,m_min,m_max,delta_m_star,b_d,c,p,d,q,seed):
        # Determine number of aftershocks in expected from given mainshock
        N_A = num_aftershocks(m_parent,m_min,b_d,delta_m_star)
        
        # Intialize random generator based on the provided seed for reproducibility
        rng=np.random.default_rng(seed)
        
        # Generate three sets of random numbers between 0-1, one for each step in the process
        # where each is the length of the number of aftershocks
        P_cm = rng.random(N_A)
        P_ct = rng.random(N_A)
        P_cr = rng.random(N_A)

        # Convert to values via the inverse of the cumulative distribution functions
        m_d = magnitude_of_daughter(P_cm,m_min,b_d)
        t_d = time_of_daughter(P_ct,c,p)
        r_d = distance_of_daughter(P_cr,d,m_parent,q)
        
        # Place hard cap and restrict aftershocks to being the size of m_max
        m_d[m_d>m_max]=m_max

        # Return the arrays 
        return m_d, t_d, r_d
    

    # Generate first order sequence
    order = 1
    m_d, t_d, r_d = single_BASS_sequence(Mw_parent,Mw_min,Mw_max,delta_m_star,b_d,c,p,d,q,seed)
    
    # Generate original pointer list
    p_d = [np.array(ID_parent) for _ in range(len(m_d))]
    for i in range(len(m_d)):
        p_d[i] = np.append(p_d[i],i)

    
    # Place these in a list before beginning recursion
    m_d_l = [m_d]; t_d_l = [t_d]; r_d_l=[r_d]; p_d_l=[p_d]
    
    # Begin recursion based on whether any aftershock events exceed the minimum
    while (np.any(m_d_l[order-1]>=Mw_min)) & (order<=max_order):

        # Grab the aftershocks generate in the previous order
        m_p = m_d_l[order-1]
        p_d_p = p_d_l[order-1]
        
        
        # Remove any that don't spawn aftershocks
        idx = m_p>=Mw_min
        m_p = m_p[idx] 
        # Initiate empty lists
        m_d_ls = []; t_d_ls = []; r_d_ls=[]; p_d_ls=[]
        
        for k in range(len(m_p)):
            m_d_k, t_d_k, r_d_k = single_BASS_sequence(m_p[k],Mw_min,Mw_max,delta_m_star,b_d,c,p,d,q,seed+k+1)
            # Add to list
            m_d_ls.append(m_d_k)
            t_d_ls.append(t_d_k)
            r_d_ls.append(r_d_k)
            
            p_d_ = [p_d_p[k] for _ in range(len(m_d_k))]
            for l in range(len(m_d_k)):
                p_d_[l] = np.append(p_d_[l],l)
            
            p_d_ls = p_d_ls + p_d_
            p_d = p_d + p_d_
            
        # Merge into a single array
        m_d_ls = np.concat(m_d_ls,axis=0)
        t_d_ls = np.concat(t_d_ls,axis=0)
        r_d_ls = np.concat(r_d_ls,axis=0)
        # Append to the list of aftershocks
        m_d_l.append(m_d_ls)
        t_d_l.append(t_d_ls)
        r_d_l.append(r_d_ls)
        p_d_l.append(p_d_ls)
        
        # Increment order 
        order +=1
    
    # Concat the aftershock lists, and overwrite original as these already
    # include the first order aftershocks
    m_d = np.concat(m_d_l,axis=0)
    t_d = np.concat(t_d_l,axis=0)
    r_d = np.concat(r_d_l,axis=0)
    
    # Convert time in days to years
    t_d = t_d/365.25
    
    return m_d,t_d,r_d,p_d

def _find_parent_index(parent,event_id):
    """
    Function to find the respective parent event id
    for each aftershock

    Parameters
    ----------
    parent : list of numpy arrays
        The "parent" output from the aftershock function.
    event_id : numpy array
        Unique ids for all earthquake events (including aftershocks) and where the
        id is the index of the event as well.

    Returns
    -------
    ix : numpy array
        ID of the direct parent for each event, IDs for an original parent event
        will simply be its index.
    no : numpy array
        The order of each event within the aftershock sequence. Original parent events
        will be order 0, aftershocks generated from original parents will be order 1, 
        and so on
    num_orders : int
        The total number of orders (including the original parent events).

    """
    
    # Generate empty master ix
    ix = np.full(event_id.shape,np.nan)
    no = np.full(event_id.shape,np.nan)
    
    # Initiate loop variables
    lp = 1
    sz = 1
    p = []
    
    while lp > 0:
        p0 = [(ind,x) for ind,x in enumerate(parent) if x.size==sz]
        # p0 will be a list of tuples, each tuple will include the index 
        # and the "gen chain" for each event. For each iteration, it will build a 
        # p0 for each aftershock order including all events of that order (i.e., length of
        # gen chain)
        #
        # For example, p0 the first time through might look like 
        # [(0,array([0])), (4, array([1]))]
        # Indicating that there are two original parent events in the 0th and 4th index
        # And the next loop might look like
        # [(1, array([0, 0])), (2, array([0, 1])), (5, array([1, 0])), (6, array([1, 1]))]
        # Indicating there are four aftershocks generated from each of these in the 1st, 2nd,
        # 5th, and 6th index position of all event lists and that the first two were generated
        # from the first main event and the second two from the second main event, and so on.
        lp = len(p0)
        if lp>0:
            p.append(p0)
            sz += 1
            
    num_orders = len(p)
    
    for i in range(num_orders):
        pix,pid = zip(*p[i])
        # This step basically splits out the components of the tuples from above, 
        # so for the first example, pix would look like (0,4) and pid would
        # look like (array([0]), array([1]))
        pix = np.array(pix)
        if i == 0:
            # Deals with original events where the index position is the event id as well
            ix[pix] = event_id[pix]
            no[pix] = i
        else:
            for j in range(len(pix)):
                gen_chain = pid[j][:-1]
                # Strips out the last part of the generator chain
                pp = [(ind,x) for ind,x in enumerate(parent) if x.size==gen_chain.size and np.all(x==gen_chain)]
                # Above looks for and returns entries in parent that are the same size of the gen_chain
                # and matches the values in the gen chain.
                try:
                    pix0,_=zip(*pp)
                except:
                    print([x for x in parent if np.all(x==gen_chain)])
                        
                pix0 = np.array(pix0)
                ix[pix[j]]=event_id[pix0[0]]
                no[pix[j]] = i                
                
    return ix.astype(int),no.astype(int),num_orders

def _find_children_to_remove(ix,event_id,remove_id):
    """
    Searches lists of events with aftershocks to find all
    children events associated with a given set of event ids

    Parameters
    ----------
    ix : numpy array
        ix output from '_find_parent_index'.
    event_id : numpy array
        Unique ID for each event.
    remove_id : numpy array
        IDs of events to remove.

    Returns
    -------
    remove_idx : boolean array
        Array of booleans where True values indicate these whould be removed.

    """
    
    # Generate empty logical array
    remove_idx = np.zeros(event_id.shape).astype(bool)
    
    # Find the position within the event_id array of the event to be removed
    remove_ix = np.nonzero(np.isin(event_id,remove_id))[0]
    # Flag that as to be removed
    remove_idx[remove_ix]=True
    
    # Recursively find children events and flag them for removal
    for i in range(len(event_id)):
        # Make a copy of the remove_idx array at the beginning of the loop
        remove_idx0 = remove_idx.copy()
        remove_ix = np.nonzero(np.isin(ix,remove_ix))[0]
        remove_idx[remove_ix]=True

        # Check against copy, if nothing has been added, break
        if np.all(remove_idx == remove_idx0):
            break
    
    return remove_idx

def _parse_events_dipping(xs,ys,zs,strike,ss,ds,mu,nu,events,subevents,event_ids,topo,zsr):
    """
    Produces an interable containing a sequence of tuples suitable for the _calc_elastic_dipping_mp function

    Parameters
    ----------
    xs : numpy array
        x-coordinates of recievers for elastic dislocation calculation.
    ys : numpy array
        y-coordinates of recievers for elastic dislocation calculation.
    zs : numpy array
        z-coordinate of recievers for elastic dislocation calculation.
    strike : float
        strike of all ruptures for elastic dislocation calculations.
    ss : float
        strike-slip component of slip-rate.
    ds : float
        dip-slip component of slip-rate.
    mu : float
        Shear modulus in Pa.
    nu : float
        Poissons ratio.
    events : dict
        Event dictionary created by a generator of the EarthquakeSequence.
    subevents : dict
        SubEvent dictionary created by a generate of the EarthquakeSequence.
    event_ids : numpy array
        id numbers of events which occur within a given timestep.
    topo : boolean
        Flag to indicate whether topographic correction should be applied or not.
    zsr : numpy array
        z-coordinates of topographic surface if topographic correction is considered.

    Returns
    -------
    items : iterable
        iterable of tuples to be passed to the _calc_elastic_dipping_mp function.

    """
    idx = np.isin(subevents['Event_ID'],event_ids)
    
    cx = subevents['Center_X'][idx]
    cy = subevents['Center_Y'][idx]
    cz = subevents['Center_Z'][idx]
    rdip = subevents['Dip'][idx]
    rwidth = subevents['Width'][idx]
    rlength = subevents['Length'][idx]
    disp = subevents['Displacement'][idx]
    ss_part = ss[0] / (ss[0] + ds[0])
    ds_part = ds[0] / (ss[0] + ds[0])
    ss_sign = np.sign(ss[0])
    ds_sign = np.sign(ds[0])
    ds = disp * ds_part * ds_sign
    ss = disp * ss_part * ss_sign
    ts = np.zeros(cx.shape)
    rstrike = np.full(cx.shape,strike)
    
    num_events = len(cx)
    if topo:
        items = [(xs,ys,zs,cx[i],cy[i],cz[i],rlength[i],rwidth[i],rdip[i],rstrike[i],ss[i],ds[i],ts[i],mu,nu,zsr) for i in range(num_events)]
    else:
        items = [(xs,ys,zs,cx[i],cy[i],cz[i],rlength[i],rwidth[i],rdip[i],rstrike[i],ss[i],ds[i],ts[i],mu,nu) for i in range(num_events)]
        
    return items

def _parse_events_vertical(xs,ys,zs,dip,ss,ds,mu,nu,events,subevents,event_ids,topo,zsr):
    """
    Produces an interable containing a sequence of tuples suitable for the _calc_elastic_vertical_mp function
    

    Parameters
    ----------
    xs : numpy array
        x-coordinates of recievers for elastic dislocation calculation.
    ys : numpy array
        y-coordinates of recievers for elastic dislocation calculation.
    zs : numpy array
        z-coordinate of recievers for elastic dislocation calculation.
    dip : float
        Dip of all ruptures.
    ss : float
        strike-slip component of slip-rate.
    ds : float
        dip-slip component of slip-rate.
    mu : float
        Shear modulus in Pa.
    nu : float
        Poissons ratio.
    events : dict
        Event dictionary created by a generator of the EarthquakeSequence.
    subevents : dict
        SubEvent dictionary created by a generate of the EarthquakeSequence.
    event_ids : numpy array
        id numbers of events which occur within a given timestep.
    topo : boolean
        Flag to indicate whether topographic correction should be applied or not.
    zsr : numpy array
        z-coordinates of topographic surface if topographic correction is considered.

    Returns
    -------
    items : iterable
        iterable of tuples to be passed to the _calc_elastic_vertical_mp function.

    """
    idx = np.isin(subevents['Event_ID'],event_ids)
    
    cx = subevents['Center_X'][idx]
    cy = subevents['Center_Y'][idx]
    cz = subevents['Center_Z'][idx]
    rstrike = subevents['Strike'][idx]
    rwidth = subevents['Width'][idx]
    rlength = subevents['Length'][idx]
    disp = subevents['Displacement'][idx]
    ss_part = ss[0] / (ss[0] + ds[0])
    ds_part = ds[0] / (ss[0] + ds[0])
    ss_sign = np.sign(ss[0])
    ds_sign = np.sign(ds[0])
    ds = disp * ds_part * ds_sign
    ss = disp * ss_part * ss_sign
    ts = np.zeros(cx.shape)
    rdip = np.full(cx.shape,dip)
    
    num_events = len(cx)
    if topo:
        items = [(xs,ys,zs,cx[i],cy[i],cz[i],rlength[i],rwidth[i],rdip[i],rstrike[i],ss[i],ds[i],ts[i],mu,nu,zsr) for i in range(num_events)]
    else:
        items = [(xs,ys,zs,cx[i],cy[i],cz[i],rlength[i],rwidth[i],rdip[i],rstrike[i],ss[i],ds[i],ts[i],mu,nu) for i in range(num_events)]
        
    return items    

def _calc_elastic_single(xs, ys, zs, xc, yc, depth, length, width, dip, strike, ss, ds, ts, mu, nu):
    """
    Wrapper for okada92 without topographic correction

    Parameters
    ----------
    xs : numpy array
        X-coordinates of recievers for elastic dislocation calculation (m).
    ys : numpy array
        Y-coordinates of recievers for elastic dislocation calculation (m).
    zs : numpy array
        Z-coordinate of recievers for elastic dislocation calculation (m).
    xc : float
        X-coordinate of rupture center (m).
    yc : float
        Y-coordinate of rupture center (m).
    depth : float
        Depth of rupture center (positive downward, m).
    length : float
        Length of rupture in strike direction (m).
    width : float
        Width of rupture in dip direction (m).
    dip : float
        Dip of rupture (degrees).
    strike : float
        Strike of rupture (degrees from north, right hand rule).
    ss : float
        Strike-slip component of displacement (m).
    ds : float
        Dip-slip component of displacement (m).
    ts : float
        Tensile component of displacement (m).
    mu : float
        Shear modulus (Pa).
    nu : float
        Poissons ratio.

    Returns
    -------
    cx : numpy array
        X-component of displacement at recievers
    cy : numpy array
        Y- component of displacement at recievers.
    cz : numpy array
        Z - component of displacement at recievers.

    """
    u, d, s, flag, flag2 = ok92.okada92(xs, ys, zs, np.array([xc]), np.array([yc]), 
                                        np.array([depth]), np.array([length]), np.array([width]), np.array([dip]),
                                        np.array([strike]), np.array([ss]), np.array([ds]), np.array([ts]), mu, nu)
    u = u.reshape((xs.shape[0], 3))
    cx = u[:,0]
    cy = u[:,1]
    cz = u[:,2]
    return cx,cy,cz

def _calc_elastic_single_topo(xs, ys, zs, xc, yc, depth, length, width, dip, strike, ss, ds, ts, mu, nu, zsr):
    """
    Wrapper for okada92 with topographic correction
    
    Parameters
    ----------
    xs : numpy array
        X-coordinates of recievers for elastic dislocation calculation (m).
    ys : numpy array
        Y-coordinates of recievers for elastic dislocation calculation (m).
    zs : numpy array
        Z-coordinate of recievers for elastic dislocation calculation (m).
    xc : float
        X-coordinate of rupture center (m).
    yc : float
        Y-coordinate of rupture center (m).
    depth : float
        Depth of rupture center (positive downward, m).
    length : float
        Length of rupture in strike direction (m).
    width : float
        Width of rupture in dip direction (m).
    dip : float
        Dip of rupture (degrees).
    strike : float
        Strike of rupture (degrees from north, right hand rule).
    ss : float
        Strike-slip component of displacement (m).
    ds : float
        Dip-slip component of displacement (m).
    ts : float
        Tensile component of displacement (m).
    mu : float
        Shear modulus (Pa).
    nu : float
        Poissons ratio.
    zsr : numpy array
        Z-coordinate of topographic surface.

    Returns
    -------
    cx : numpy array
        X-component of displacement at recievers
    cy : numpy array
        Y- component of displacement at recievers.
    cz : numpy array
        Z - component of displacement at recievers.

    """
    u, d, s, flag, flag2 = ok92.okada92(xs, ys, zs, np.array([xc]), np.array([yc]), 
                                        np.array([depth]), np.array([length]), np.array([width]), np.array([dip]),
                                        np.array([strike]), np.array([ss]), np.array([ds]), np.array([ts]), mu, nu, zsr)
    u = u.reshape((xs.shape[0], 3))
    cx = u[:,0]
    cy = u[:,1]
    cz = u[:,2]
    return cx,cy,cz


def _calc_elastic_dipping_mp(xs,ys,zs,strike,ss,ds,mu,nu,events,subevents,event_ids,num_processes,topo,zsr):
    """
    Function for calculating summed coseismic displacements for a series of events on a dipping fault 
    optimized for multiprocessing 

    Parameters
    ----------
    xs : numpy array
        x-coordinates of recievers for elastic dislocation calculation.
    ys : numpy array
        y-coordinates of recievers for elastic dislocation calculation.
    zs : numpy array
        z-coordinate of recievers for elastic dislocation calculation.
    strike : float
        strike of all ruptures for elastic dislocation calculations.
    ss : float
        strike-slip component of slip-rate.
    ds : float
        dip-slip component of slip-rate.
    mu : float
        Shear modulus in Pa.
    nu : float
        Poissons ratio.
    events : dict
        Event dictionary created by a generator of the EarthquakeSequence.
    subevents : dict
        SubEvent dictionary created by a generate of the EarthquakeSequence.
    event_ids : numpy array
        id numbers of events which occur within a given timestep.
    num_processes : int
        Number of processors to use in multiprocessing.
    topo : boolean
        Flag to indicate whether topographic correction should be applied or not.
    zsr : numpy array
        z-coordinates of topographic surface if topographic correction is considered.    

    Returns
    -------
    cvx : numpy array
        X-component of summed displacement at recievers
    cvy : numpy array
        Y- component of summed displacement at recievers.
    cvz : numpy array
        Z - component of summed displacement at recievers.

    """
    items = _parse_events_dipping(xs,ys,zs,strike,ss,ds,mu,nu,events,subevents,event_ids,topo,zsr)
    if topo:
        with mp.Pool(num_processes) as pool:
            res = pool.starmap(_calc_elastic_single_topo,items)
            res = np.sum(list(zip(*res)),axis=1)
            cvx = res[0,:].ravel(); cvy=res[1,:].ravel(); cvz=res[2,:].ravel()
    else:
        with mp.Pool(num_processes) as pool:
            res = pool.starmap(_calc_elastic_single,items)
            res = np.sum(list(zip(*res)),axis=1)
            cvx = res[0,:].ravel(); cvy=res[1,:].ravel(); cvz=res[2,:].ravel()
    return cvx,cvy,cvz


def _calc_elastic_vertical_mp(xs,ys,zs,dip,ss,ds,mu,nu,events,subevents,event_ids,num_processes,topo,zsr):
    """
    Function for calculating summed coseismic displacements for a series of events on a vertical fault 
    optimized for multiprocessing    

    Parameters
    ----------
    
    xs : numpy array
        x-coordinates of recievers for elastic dislocation calculation.
    ys : numpy array
        y-coordinates of recievers for elastic dislocation calculation.
    zs : numpy array
        z-coordinate of recievers for elastic dislocation calculation.
    dip : float
        Dip of all ruptures.
    ss : float
        strike-slip component of slip-rate.
    ds : float
        dip-slip component of slip-rate.
    mu : float
        Shear modulus in Pa.
    nu : float
        Poissons ratio.
    events : dict
        Event dictionary created by a generator of the EarthquakeSequence.
    subevents : dict
        SubEvent dictionary created by a generate of the EarthquakeSequence.
    event_ids : numpy array
        id numbers of events which occur within a given timestep.
    num_processes : int
        Number of processors to use.
    topo : boolean
        Flag to indicate whether topographic correction should be applied or not.
    zsr : numpy array
        z-coordinates of topographic surface if topographic correction is considered.

    Returns
    -------
    cvx : numpy array
        X-component of summed displacement at recievers
    cvy : numpy array
        Y- component of summed displacement at recievers.
    cvz : numpy array
        Z - component of summed displacement at recievers.

    """
    items = _parse_events_vertical(xs,ys,zs,dip,ss,ds,mu,nu,events,subevents,event_ids,topo,zsr)
    if topo:
        with mp.Pool(num_processes) as pool:
            res = pool.starmap(_calc_elastic_single_topo,items)
            res = np.sum(list(zip(*res)),axis=1)
            cvx = res[0,:].ravel(); cvy=res[1,:].ravel(); cvz=res[2,:].ravel()
    else:
        with mp.Pool(num_processes) as pool:
            res = pool.starmap(_calc_elastic_single,items)
            res = np.sum(list(zip(*res)),axis=1)
            cvx = res[0,:].ravel(); cvy=res[1,:].ravel(); cvz=res[2,:].ravel()
    return cvx,cvy,cvz


## Moment - frequency relationships
def _eq_moment_gamma(num_events,seed,m_t,m_cm,beta):
    """
    Randomly samples a "Kagan" gamma distribution of scalar seismic moments

    Parameters
    ----------
    num_events : int
        Number of events to sample.
    seed : int
        Seed for random number generator, for reproducibility.
    m_t : float
        Moment magnitude of minimum magnitude, i.e., magnitude of completeness
        for catalog.
    m_cm : float
        Moment magnitude of corner moment for distribution.
    beta : float
        "beta" parameter, i.e., shape parameter for distribution.

    Returns
    -------
    M0 : array of floats
        Seismic moments of sampled events.
    Mw : array of floats
        Moment magnitudes of sampled events.

    """
    M_t = _eq_magnitude_to_moment(m_t)
    M_cm = _eq_magnitude_to_moment(m_cm)
    M_max = _eq_magnitude_to_moment(9.9) # Dummy edge for evaluation range
    kagan_gamma = KaganGamma(name='kagan_gamma',a=M_t,b=M_max)
    M0 = kagan_gamma.rvs(beta=beta,Mt=M_t,Mcm=M_cm,size=num_events,random_state=seed)
    Mw = _eq_moment_to_magnitude(M0)
    return M0, Mw 

def _eq_moment_tapered_pareto(num_events,seed,m_t,m_cm,beta):
    """
    Randomly samples a tapered pareto distribution of scalar seismic moments

    Parameters
    ----------
    num_events : int
        Number of events to sample.
    seed : int
        Seed for random number generator, for reproducibility.
    m_t : float
        Moment magnitude of minimum magnitude, i.e., magnitude of completeness
        for catalog.
    m_cm : float
        Moment magnitude of corner moment for distribution.
    beta : float
        "beta" parameter, i.e., shape parameter for distribution.

    Returns
    -------
    M0 : array of floats
        Seismic moments of sampled events.
    Mw : array of floats
        Moment magnitudes of sampled events.

    """
    M_t = _eq_magnitude_to_moment(m_t)
    M_cm = _eq_magnitude_to_moment(m_cm)
    M_max = _eq_magnitude_to_moment(9.9) # Dummy edge for evaluation range
    tapered_pareto = TaperedPareto(name='tapered_pareto',a=M_t,b=M_max)
    M0 = tapered_pareto.rvs(beta=beta,Mt=M_t,Mcm=M_cm,size=num_events,random_state=seed)
    Mw = _eq_moment_to_magnitude(M0)
    return M0, Mw 

def _eq_moment_truncated_pareto(num_events,seed,m_t,m_x,beta):
    """
    Randomly samples a truncated pareto distribution of scalar seismic moments

    Parameters
    ----------
    num_events : int
        Number of events to sample.
    seed : int
        Seed for random number generator, for reproducibility.
    m_t : float
        Moment magnitude of minimum magnitude, i.e., magnitude of completeness
        for catalog.
    m_x : float
        Moment magnitude of maximum magnitude and the magnitude to which the 
        catalog will expontentially taper.
    beta : float
        "beta" parameter, i.e., shape parameter for distribution.

    Returns
    -------
    M0 : array of floats
        Seismic moments of sampled events.
    Mw : array of floats
        Moment magnitudes of sampled events.

    """
    M_t = _eq_magnitude_to_moment(m_t)
    M_x = _eq_magnitude_to_moment(m_x)
    trunc_pareto = TruncPareto(name='truncated_pareto',a=M_t,b=M_x)
    M0 = trunc_pareto.rvs(beta=beta,Mt=M_t,Mx=M_x,size=num_events,random_state=seed)
    Mw = _eq_moment_to_magnitude(M0)
    return M0, Mw 

def _eq_moment_characteristic(num_events,seed,m_t,m_c,beta):
    """
    Randomly sample a characteristic distribution of scalar seismic moments

    Parameters
    ----------
    num_events : int
        Number of events to sample.
    seed : int
        Seed for random number generator, for reproducibility.
    m_t : float
        Moment magnitude of minimum magnitude, i.e., magnitude of completeness
        for catalog.
    m_c : float
        Moment magnitude of characteristic magnitude and the magnitude above
        which the distribution will be truncated.
    beta : float
        "beta" parameter, i.e., shape parameter for distribution.

    Returns
    -------
    M0 : array of floats
        Seismic moments of sampled events.
    Mw : array of floats
        Moment magnitudes of sampled events.

    """
    
    M_t = _eq_magnitude_to_moment(m_t)
    M_c = _eq_magnitude_to_moment(m_c)
    char = Characteristic(name='characteristic',a=M_t,b=M_c)
    M0 = char.rvs(beta=beta,Mt=M_t,Mc=M_c,size=num_events,random_state=seed)
    Mw = _eq_moment_to_magnitude(M0)
    return M0, Mw


class TaperedPareto(rv_continuous):
    """Implementation of a tapered pareto distribution from Kagan, 2002
    
    """
    def _shape_info(self):
        beta = _ShapeInfo("beta", False, (0, np.inf), (False, False))
        Mt = _ShapeInfo("Mt", False, (0, np.inf), (False, False))
        Mcm = _ShapeInfo("Mcm", False, (0, np.inf), (False, False))
        return [beta, Mt, Mcm]
    def _pdf(self,x,beta,Mt,Mcm):
        if x < Mt:
            return 0
        else:
            return ((beta/x) + (1/Mcm)) * ((Mt/x)**beta) * np.exp((Mt - x)/Mcm)     
    def _cdf(self,x,beta,Mt,Mcm):
        if x < Mt:
            return 0
        else:
            return 1 - (Mt/x)**beta * np.exp((Mt-x)/Mcm)
    def _sf(self,x,beta,Mt,Mcm):
        if x < Mt:
            return 0
        else:
            return (Mt/x)**beta * np.exp((Mt-x)/Mcm)
        

class KaganGamma(rv_continuous):
    """ Implementation of a gamma distribtution from Kagan, 2002 
    
    """
    def _shape_info(self):
        beta = _ShapeInfo("beta", False, (0, np.inf), (False, False))
        Mt = _ShapeInfo("Mt", False, (0, np.inf), (False, False))
        Mcm = _ShapeInfo("Mcm", False, (0, np.inf), (False, False))
        return [beta, Mt, Mcm]
    def _pdf(self,x,beta,Mt,Mcm):
        if x < Mt:
            return 0
        else:
            C = 1 - (Mt/Mcm)**beta * np.exp(Mt/Mcm) * gammaincc(1-beta,Mt/Mcm)
            pdf = (C**-1) * (beta/x) * ((Mt/x)**beta) ** np.exp((Mt-x)/Mcm)
            return pdf
    def _cdf(self,x,beta,Mt,Mcm):
        if x< Mt:
            return 0
        else:
            C = 1 - (Mt/Mcm)**beta * np.exp(Mt/Mcm) * gammaincc(1-beta,Mt/Mcm)
            ccdf1 = (C**-1) * ((Mt/x)**beta) * np.exp((Mt - x)/Mcm)
            ccdf2 = 1 - ((x/Mcm)**beta) * np.exp(x/Mcm) * gammaincc(1-beta,x/Mcm)
            return 1 - (ccdf1*ccdf2)
    def _sf(self,x,beta,Mt,Mcm):
        if x< Mt:
            return 0
        else:
            C = 1 - (Mt/Mcm)**beta * np.exp(Mt/Mcm) * gammaincc(1-beta,Mt/Mcm)
            ccdf1 = (C**-1) * ((Mt/x)**beta) * np.exp((Mt - x)/Mcm)
            ccdf2 = 1 - ((x/Mcm)**beta) * np.exp(x/Mcm) * gammaincc(1-beta,x/Mcm)
            return (ccdf1*ccdf2)
        
        
class TruncPareto(rv_continuous):
    """ Implementation of a truncated pareto distribution from Kagan, 2002
    
    """
    def _shape_info(self):
        beta = _ShapeInfo("beta", False, (0, np.inf), (False, False))
        Mt = _ShapeInfo("Mt", False, (0, np.inf), (False, False))
        Mx = _ShapeInfo("Mx", False, (0, np.inf), (False, False))
        return [beta, Mt, Mx]
    def _pdf(self,x,beta,Mt,Mx):
        if x<Mt:
            return 0
        elif x>Mx:
            return 0
        else:
            return (((Mx**beta)*(Mt**beta)) / ((Mx**beta)-(Mt**beta))) * (beta * (x**(-1-beta)))
    def _cdf(self,x,beta,Mt,Mx):
        if x<Mt:
            return 0
        elif x>Mx:
            return 1
        else:
            return 1-((((Mt/x)**beta) - ((Mt/Mx)**beta)) / (1 - ((Mt/Mx)**beta))) 
        
    def _sf(self,x,beta,Mt,Mx):
        if x<Mt:
            return 0
        elif x>Mx:
            return 0
        else:
            return ((((Mt/x)**beta) - ((Mt/Mx)**beta)) / (1 - ((Mt/Mx)**beta))) 
        
    def _ppf(self,q,beta,Mt,Mx):
        # M = (Mt/Mx)**beta
        # return Mt / (((1-q)*(1-M) + M)**(1/beta))
        if np.any(q<=0):
            return Mt 
        elif np.any(q>=1):
            return Mx
        else:
            M = (Mt/Mx)**beta
            return Mt / (((1-q)*(1-M) + M)**(1/beta))
    
class Characteristic(rv_continuous):
    """ Implementation of the characteristic distribution from Kagan, 2002
    
    """
    def _shape_info(self):
        beta = _ShapeInfo("beta",False, (0, np.inf), (False,False))
        Mt = _ShapeInfo("Mt", False, (0, np.inf), (False, False))
        Mc = _ShapeInfo("Mc", False, (0, np.inf), (False, False))
    def _sf(self,x,beta,Mt,Mc):
        if x<Mt:
            return 0
        elif x>Mc:
            return 0
        else:
            return (Mt/x)**beta
    def _cdf(self,x,beta,Mt,Mc):
        if x<Mt:
            return 0
        elif x>Mc:
            return 1
        else:
            return 1 - ((Mt/x)**beta)
    ## Defining the ppf makes this quicker, but the result has less of a 
    ## a "sharp" break in distributions of random samples at the characteristic magnitude
    ## which is a hallmark of this distribution and as such, have left just basing this 
    ## on the cdf
    # def _ppf(self,q,beta,Mt,Mc):
    #     if np.any(q<=0):
    #         return Mt 
    #     elif np.any(q>=1):
    #         return Mc 
    #     else:
    #         return Mt / ((1-q)**(1/beta))

        
    
        
class EarthquakeSequence:
    """Monte-Carlo sequence of earthquakes and coseismic deformation with elastic 
    dislocations
    
    This component generates a sequence of earthquakes based on user inputs and
    maps individual ruptures onto a provided Fault object and then solves
    for the coseismic deformation associated with each rupture. Earthquake sequences
    can be generated in a variety of ways, including a simple repeating maximum sequence,
    a repeating (in the sense of event magnitude) sequence, or a pseudo-random sequence.
    The user can control the temporal distribution of earthquakes making them either 
    Poissonian or more clustered. The user can also have the generator produce
    pseudo-realistic aftershock sequences.
    
    The component is designed to precompute the details of an earthquake sequence that
    will last for a user specified time (expected to be the duration of a companion
    landscape evolution model) that is then accessed during the course of a simulation
    with the "run_one_step" method.
    
     References
     ----------

     **Required Software Citation(s) Specific to this Component**

     Romain Jolivet. (2024). jollivetr/okada4py: First release (1.0.0). Zenodo.
     https://doi.org/10.5281/zenodo.14170827

     **Additional References**
     
     Kagan, Y.Y. (2002). Seismic moment distribution revisited: I. Statistical
     results, Geophyiscal Journal International, 148(3), 520-541
     
     Kagan, Y.Y., Jackson, D.D. (2000). Probabilistic forecasting of earthquakes,
     Geophyiscal Journal International, 143(2), 438-453
     
     Langer, L., Ragon, T., Sladen, A., Tromp, J. (2020), Impact of topography
     on earthquake static slip estimates, Tectonophysics, 791, 228566
     
     Leonard, M. (2014). Self-Consistent Earthquake Fault-Scaling Relations: Update
     and Extension to Stable Continental Strike-Slip Faults, Bulletin of the 
     Seismological Society of America, 104(6), 2953-2965
     
     Okada, Y. (1992), Internal deformation due to shear and tensile faults in a
     half-space, Bulletin of the Seismological Society of America, 82(2), 1018-1040
     
     Turcotte, D.L., Holliday, J.R., Rundel, J.B. (2007). BASS, an alternative
     to ETAS, 34(12), 2007GL029696
     

    
    """
    
    _name = 'EarthquakeSequence'

    _time_units = 'y'

    _unit_agnostic = False 
    
    _info = {
        "advection__velocity":{
            "dtype":float,
            "intent":"inout",
            "optional":False,
            "units":"m/y",
            "mapping":"link",
            "doc":"Link-parallel advection velocity"
            },
        "vertical__velocity":{
            "dtype":float,
            "intent":"inout",
            "optional":False,
            "units":"m/y",
            "mapping":"node",
            "doc":"Vertical velocity"
            },
        "total_x__displacement":{
            "dtype":float,
            "intent":"inout",
            "optional":False,
            "units":"m",
            "mapping":"node",
            "doc":"Total accumulated displacement in x direction"},
        "total_y__displacement":{
            "dtype":float,
            "intent":"inout",
            "optional":False,
            "units":"m",
            "mapping":"node",
            "doc":"Total accumulated displacement in y direction"}, 
        "total_z__displacement":{
            "dtype":float,
            "intent":"inout",
            "optional":False,
            "units":"m",
            "mapping":"node",
            "doc":"Total accumulated displacement in z direction"},
        "topographic__elevation":{
            "dtype":float,
            "intent":"inout",
            "optional":False,
            "units":"m",
            "mapping":"node",
            "doc":"Land surface topographic elevation"
            },
        "bedrock__elevation":{
            "dtype":float,
            "intent":"inout",
            "optional":True,
            "units":"m",
            "mapping":"node",
            "doc":"Elevation of the bedrock surface"
            },
        "soil__depth":{
            "dtype":float,
            "intent":"inout",
            "optional":True,
            "units":"m",
            "mapping":"node",
            "doc":"Depth of soil or weathered bedrock"
            },
        }
    
    def __init__(self, grid, fault, clip_to='moment', moment_fraction = 1, parallel = False, num_cores = None,):
        """
        

        Parameters
        ----------
        grid : RasterModelGrid or HexModelGrid
            Landlab model grid.
        fault : Fault
            Fault object created by either the DippingFault or VerticalFault components. 
        clip_to : str, optional
            Choice of quantity to use to clip the earthquake sequence, choices are 'moment'
            or 'displacement'. The default is 'moment', which means that the total accumulated
            moment of all earthquakes will equal or be less than the total accumulated seismic
            moment where total moment is:
            seismogneic fault area * shear modulus * average slip rate * time * moment fraction. Alternatively,
            if 'displacement', the earthquake sequence will be clipped such that the maximum
            displacement from the summed earthquakes on any place on the fault will be equal to
            or less than the total displacement from the maximum displacement * time.
        moment_fraction: float, optional
            Fraction of the total moment to use to clip the earthquake sequence if 'clip_to' method is
            set to 'moment'. Valid values are greater than 0 and less than or equal to 1. A value of 1
            implies that the total moment (seismogneic fault area * shear modulus * average slip rate * time)
            will be used. This is largely a simple fix to scale total displacement, which can exceed the total
            expected accumulated displacement within the seismogenic portion of the fault, that is computationally
            much simpler than the alternative clip to displacement method. 
            Default value is 1.
        parallel : boolean, optional
            Flag to turn on parallelization of the calculation of coseismic 
            displacements during 'run_one_step'. If this is set to true, it is 
            essential that in any script using the EarthquakeSequence component
            that it is protected by a guard, meaning that at minimum any portion
            of the script that invoked the 'run_one_step' method for an instance
            of an EarthquakeSequence should be preceded by an 'if __name__ == "__main__":'
            statement with the call to 'run_one_step' under this guard. Best practice
            would be to place the entirety of the script after imports under the guard.
            Default value is False.
        num_cores : int, optional
            The number of cores to use if parallel = True. This parameter has no effect
            if parallel = False. If left at the default value of None, will default to
            the total number of cores available on the machine being used, but this may
            cause problems if you are trying to run multiple scripts concurrently. If
            a number of cores is provided that exceeds the total number of cores on the
            machine, then a warning will be displayed and the number of cores will be
            set to the maximum available. To query the number of cores on a machine,
            use os.cpu_count() after importing os.

            
        Returns
        -------
        None.

        """
        
        # Check inputs
        if type(grid)==RasterModelGrid:
            pass
        elif type(grid)==HexModelGrid:
            pass
        else:
            raise TypeError('Provided Landlab grid must be either a raster or hex.')
            
        if type(fault) == DippingFault:
            pass
        elif type(fault) == VerticalFault:
            pass
        else:
            raise TypeError('Provided object to "fault" must be generated by either the DippingFault or VerticalFault components')
        
        
        self.grid = grid
        self.fault = fault
        self.clip_to = clip_to
        self.moment_fraction = moment_fraction
        self.parallel = parallel
        self.num_cores = num_cores
        
        # Uses the Leonard 2014 scaling to estimate the maximum moment and magnitude
        # based on a provided total fault area and input fault geometry, i.e., length a
        # and width.
        #
        # Selects the minimum of the three estimates
        
        min_val = ['Area','Length','Width']
        if type(fault) == DippingFault:
            if self.fault._fault_type=='Interplate_DS':
                M0_1 = _X_func(1.5,6.098,self.fault._total_area)
                if self.fault._length < 5360:
                    M0_2 = _X_func(3.0,6.098,self.fault._length[0])
                else:
                    M0_2 = _X_func(2.5,7.963,self.fault._length[0])
                    
                if self.fault._total_width < 5360:
                    M0_3 = _X_func(3.0,6.098,self.fault._length[0])
                else:
                    M0_3 = _X_func(3.75,3.301,self.fault._total_width[0])
                M0 = np.min((M0_1,M0_2,M0_3))
                ix =np.argmin((M0_1,M0_2,M0_3))
            elif self.fault._fault_type=='Interplate_SS':
                M0_1 = _X_func(1.5,6.087,self.fault._total_area)
                if self.fault._length < 3400:
                    M0_2 = _X_func(3.0,6.087,self.fault._length[0])
                elif (self.fault._length >= 3400) & (self.fault._length<40000):
                    M0_2 = _X_func(2.5,7.851,self.fault._length[0])
                elif self.fault._length >= 40000:
                    M0_2 = _X_func(1.5,12.45,self.fault._length[0])
                
                if self.fault._total_width < 3400:
                    M0_3 = _X_func(3.0,6.087,self.fault._length[0])
                elif (self.fault._total_width>=3400) & (self.fault._total_width<17500):
                    M0_3 = _X_func(3.75,3.441,self.fault._total_width[0])
                else:
                    M0_3 = np.inf
                    
                M0 = np.min((M0_1,M0_2,M0_3))
                ix =np.argmin((M0_1,M0_2,M0_3))
            elif self.fault._fault_type=='SCR_DS':
                M0_1 = _X_func(1.5,6.38,self.fault._total_area)
                if self.fault._length < 2500:
                    M0_2 = _X_func(3.0,6.382,self.fault._length[0])
                else:
                    M0_2 = _X_func(2.5,8.077,self.fault._length[0])
                    
                if self.fault._total_width < 2500:
                    M0_3 = _X_func(3.0,6.382,self.fault._length[0])
                else:
                    M0_3 = _X_func(3.75,3.84,self.fault._total_width[0])
                    
                M0 = np.min((M0_1,M0_2,M0_3))
                ix =np.argmin((M0_1,M0_2,M0_3))
            elif self.fault._fault_type=='SCR_SS':
                M0_1 = _X_func(1.5,6.370,self.fault._total_area)
                if self.fault._length < 1600:
                    M0_2 = _X_func(3.0,6.370,self.fault._length[0])
                elif (self.fault._length >= 1600) & (self.fault._length<60000):
                    M0_2 = _X_func(2.5,7.972,self.fault._length[0])
                elif self.fault._length >= 60000:
                    M0_2 = _X_func(1.5,12.750,self.fault._length[0])
                    
                if self.fault._total_width < 1600:
                    M0_3 = _X_func(3.0,6.370,self.fault._length[0])
                elif (self.fault._total_width >= 1600) & (self.fault._total_width < 18000):
                    M0_3 = _X_func(3.75,3.966,self.fault._total_width[0])
                else:
                    M0_3 = np.inf
                    
                M0 = np.min((M0_1,M0_2,M0_3))
                ix =np.argmin((M0_1,M0_2,M0_3))
                
            Mw = _eq_moment_to_magnitude(M0)
            self.fault_M0_max = M0
            self.fault_Mw_max = Mw
            self.fault_max_param = min_val[ix]
            
        elif type(fault) == VerticalFault:
            if self.fault._fault_type=='Interplate_DS':
                M0_1 = _X_func(1.5,6.098,self.fault._total_area)
                if self.fault._total_length < 5360:
                    M0_2 = _X_func(3.0,6.098,self.fault._total_length)
                else:
                    M0_2 = _X_func(2.5,7.963,self.fault._total_length)
                    
                if self.fault._total_width < 5360:
                    M0_3 = _X_func(3.0,6.098,self.fault._total_length)
                else:
                    M0_3 = _X_func(3.75,3.301,self.fault._total_width)
                    
                M0 = np.min((M0_1,M0_2,M0_3))
                ix =np.argmin((M0_1,M0_2,M0_3))
            elif self.fault._fault_type=='Interplate_SS':
                M0_1 = _X_func(1.5,6.087,self.fault._total_area)
                if self.fault._total_length < 3400:
                    M0_2 = _X_func(3.0,6.087,self.fault._total_length)
                elif (self.fault._total_length >= 3400) & (self.fault._total_length<40000):
                    M0_2 = _X_func(2.5,7.851,self.fault._total_length)
                elif self.fault._total_length >= 40000:
                    M0_2 = _X_func(1.5,12.45,self.fault._total_length)
                
                if self.fault._total_width < 3400:
                    M0_3 = _X_func(3.0,6.087,self.fault._total_length)
                elif (self.fault._total_width>=3400) & (self.fault._total_width<17500):
                    M0_3 = _X_func(3.75,3.441,self.fault._total_width)
                else:
                    # M0_3 = np.array([np.inf])
                    M0_3 = np.inf
                
                M0 = np.min((M0_1,M0_2,M0_3))
                ix =np.argmin((M0_1,M0_2,M0_3))
            elif self.fault._fault_type=='SCR_DS':
                M0_1 = _X_func(1.5,6.38,self.fault._total_area)
                if self.fault._total_length < 2500:
                    M0_2 = _X_func(3.0,6.382,self.fault._total_length)
                else:
                    M0_2 = _X_func(2.5,8.077,self.fault._total_length)
                    
                if self.fault._total_width < 2500:
                    M0_3 = _X_func(3.0,6.382,self.fault._total_length)
                else:
                    M0_3 = _X_func(3.75,3.84,self.fault._total_width)
                    
                M0 = np.min((M0_1,M0_2,M0_3))
                ix =np.argmin((M0_1,M0_2,M0_3))
            elif self.fault._fault_type=='SCR_SS':
                M0_1 = _X_func(1.5,6.370,self.fault._total_area)
                if self.fault._total_length < 1600:
                    M0_2 = _X_func(3.0,6.370,self.fault._total_length)
                elif (self.fault._total_length >= 1600) & (self.fault._total_length<60000):
                    M0_2 = _X_func(2.5,7.972,self.fault._total_length)
                elif self.fault._total_length >= 60000:
                    M0_2 = _X_func(1.5,12.750,self.fault._total_length)
                    
                if self.fault._total_width < 1600:
                    M0_3 = _X_func(3.0,6.370,self.fault._total_length)
                elif (self.fault._total_width >= 1600) & (self.fault._total_width < 18000):
                    M0_3 = _X_func(3.75,3.966,self.fault._total_width)
                else:
                    # M0_3 = np.array([np.inf])
                    M0_3 = np.inf
                    
                M0 = np.min((M0_1,M0_2,M0_3))
                ix =np.argmin((M0_1,M0_2,M0_3))
            
            
            Mw = _eq_moment_to_magnitude(M0)
            self.fault_M0_max = M0
            self.fault_Mw_max = Mw
            self.fault_max_param = min_val[ix]


    @property
    def clip_to(self):
        return self._clip_to 

    @clip_to.setter 
    def clip_to(self,new_clip_to):
        if (new_clip_to=='moment') | (new_clip_to=='displacement'):
            self._clip_to = new_clip_to 
        else:
            raise ValueError('Value provided to clip_to must be either "moment" or "displacement"') 

    @property 
    def moment_fraction(self):
        return self._moment_fraction

    @moment_fraction.setter 
    def moment_fraction(self,new_moment_fraction):
        if (new_moment_fraction > 0) & (new_moment_fraction <= 1):
            self._moment_fraction = new_moment_fraction
        else:
            raise ValueError('Value provided to moment_fraction must be a number greater than 0 and less than or equal to 1')
        
    @property
    def num_cores(self):
        return self._num_cores
    
    @num_cores.setter
    def num_cores(self,new_num_cores):
        
        if new_num_cores == None:
            self._num_cores = os.cpu_count()
        else:
            if isinstance(new_num_cores,int):
                if new_num_cores > os.cpu_count():
                    self._num_cores = os.cpu_count()
                    print('Warning: Value provided to num_cores exceeded number of available cores, setting to max for the machine')
                else:
                    self._num_cores = new_num_cores
            else:
                raise ValueError('Value provided to num_cores must be an integer')
        
    # Dump variable names
    def variable_names(self):
        v = vars(self)
        pprint.pprint(list(v.keys()))
    
    def _ruptures_on_vert_fault(self,L,W,A,D,M0,Mw,verbose,seed=1,stay_on_fault=True,
                                rupture_interseismic=False,is_fixed_max=False,
                                center_loc='Uniform'):
        # Establish event details
        num_events = L.shape[0]
        event_id = np.arange(0,num_events,1)
        
        # Start random number generator
        rng = np.random.default_rng(seed=seed)

        # Get indices of A and C panels
        cix = [idx for idx, value in enumerate(self.fault._panel_types[0]) if value =='C'][0]
        bw = self.fault._fz[0,-1] - self.fault._fz[0,-2] # Width below seismogenic zone
        if np.any(np.array(self.fault._panel_types)=='A'):
            above = True
            aix = [idx for idx, value in enumerate(self.fault._panel_types[0]) if value =='A'][0]
            aw = self.fault._fz[0,cix] - self.fault._fz[0,aix] # Width of above seismogenic zone
        else:
            above = False
        
        # Establish a local coordinate system along width of fault where 0 is the center of 
        # coseismic width
        if (is_fixed_max) & (self.fault_max_param=='Width'):
            if above:
                meanW_2 = np.mean(W)/2
                if aw >= meanW_2:
                    wc = rng.uniform(low=-self.fault._total_width/2,high=0.0,size=num_events)
                else:
                    wc = rng.uniform(low=-(self.fault._total_width/2 - (meanW_2-aw)),high=0.0,size=num_events)
            else:
                wc = np.zeros(num_events)
        elif is_fixed_max:
            meanW_2 = np.mean(W)/2
            if above:
                if aw >= meanW_2:
                    wc = rng.uniform(low=-self.fault._total_width/2,high=self.fault._total_width/2 - meanW_2,size=num_events)
                else:
                    wc = rng.uniform(low=-(self.fault._total_width/2 - (meanW_2-aw)),high=self.fault._total_width/2 - meanW_2,size = num_events)
            else:
                wc = rng.uniform(low=-(self.fault._total_width/2 - meanW_2),high=self.fault._total_width/2 - meanW_2,size=num_events)

        elif not(stay_on_fault):
            if np.max(W/2) < self.fault._fz[0,cix]:
                wc = rng.uniform(low=-self.fault._total_width/2,high=self.fault._total_width/2,size=num_events)
            else:
                wc = rng.uniform(low=-(self.fault._total_width/2 - (np.max(W/2)-self.fault._fz[0,cix])),high=self.fault._total_width/2,size=num_events)

        elif (stay_on_fault) & (not(rupture_interseismic)):
            # Find mean half width within bins
            # Originally found mean, but this results in some events that extend 
            # above the zero surface, using max assures this does not happen
            w_bins = np.logspace(np.log10(np.min(W-1)),np.log10(np.max(W+1)),500)
            wix = np.digitize(W,w_bins)-1
            wc = np.zeros(W.shape)
            for i in range(500):
                widx = wix==i
                n = np.sum(widx)
                if n>0:
                    maxW_2 = np.max(W[widx])/2
                    if (above) & (maxW_2 > aw):
                        low = -(self.fault._total_width/2 - (maxW_2-aw))
                        high = self.fault._total_width/2 - maxW_2
                    elif above:
                        low = -self.fault._total_width/2
                        high = self.fault._total_width/2 - maxW_2
                    else:
                        low = -(self.fault._total_width/2 - maxW_2)
                        high = self.fault._total_width/2 - maxW_2
                        
                    wc[widx]= rng.uniform(low=low,high=high,size=n)
                        
        elif (stay_on_fault) & (rupture_interseismic):
            # Find mean half width within bins
            # Originally found mean, but this results in some events that extend 
            # above the zero surface, using max assures this does not happen
            w_bins = np.logspace(np.log10(np.min(W-1)),np.log10(np.max(W+1)),500)
            wix = np.digitize(W,w_bins)-1
            wc = np.zeros(W.shape)
            for i in range(500):
                widx = wix==i
                n = np.sum(widx)
                if n>0:
                    maxW_2 = np.max(W[widx])/2
                    
                    if (above) & (maxW_2 > aw) & (maxW_2 > bw):
                        low = -(self.fault._total_width/2 - (maxW_2-aw))
                        high = self.fault._total_width/2 - (maxW_2-bw)
                    elif (above) & (maxW_2 > aw) & (maxW_2 <= bw):
                        low = -(self.fault._total_width/2 - (maxW_2-aw))
                        high = self.fault._total_width/2
                    elif (above) & (maxW_2 <= aw) & (maxW_2 <= bw):
                        low = -(self.fault._total_width/2 - maxW_2)
                        high = self.fault._total_width/2 
                    elif (not(above)) & (maxW_2 > bw):
                        low = -self.fault._total_width/2
                        high = self.fault._total_width/2 - (maxW_2-bw)
                    elif (not(above)) & (maxW_2 <= bw):
                        low = -self.fault._total_width/2
                        high = self.fault._total_width/2
                    
                    wc[widx] = rng.uniform(low=low,high=high,size=n)
                        

        # Convert to vertical extents of ruptures in fault centered coordinates
        wt = wc - W/2
        wb = wc + W/2
        # Convert to z coordinates
        zt = wt + (self.fault._fz[0,cix] + self.fault._total_width/2)
        zc = wc + (self.fault._fz[0,cix] + self.fault._total_width/2)
        zb = wb + (self.fault._fz[0,cix] + self.fault._total_width/2)
        
        # For lengths, coordinate system is from 0 to total length, in the direction of strikes
        if (is_fixed_max) & (self.fault_max_param=='Length'):
            # For repeating max events that are length limited, set the length center
            # of all events at 0
            lc = np.full(num_events,self.fault._total_length/2)
        elif (center_loc=='Uniform') & (not(stay_on_fault)) :
            lc = rng.uniform(low=0,high=self.fault._total_length,size=num_events)
        elif (center_loc=='Uniform') & (stay_on_fault):
            # If using a uniform distribution and forcing ruptures to stay on fault
            # reduce the range over which centers of ruptures can come from based on mean extent of ruptures
            l_bins = np.logspace(np.log10(np.min(L-1)),np.log10(np.max(L+1)),50)
            lix = np.digitize(L,l_bins)-1
            lc = np.zeros(L.shape)
            for i in range(50):
                lidx = lix==i
                n = np.sum(lidx)
                if n>0:
                    meanL_2 = np.mean(L[lidx])/2
                    lc[lidx] = rng.uniform(low=meanL_2,high=self.fault._total_length-meanL_2,size=n)
        elif center_loc=='Gaussian':
            # Generate a normal distribution centered on 0
            lc_unscale = rng.normal(0,1,num_events)
            # Scale to range defined by -L/2 to L/2
            lc = (self.fault._total_length) * lc_unscale/(np.max(np.abs(lc_unscale)))
        


        # Project ruptures onto fault
        event_id0,panel_ix0,strike0,L0,lc0,ll0,lr0=self._project_length_onto_panels(event_id,L,lc,verbose) 
        
        # Propagate lengths based on event IDs
        c0z = zc[event_id0]
        W0 = W[event_id0]
        zt0 = zt[event_id0]
        zb0 = zb[event_id0]
        D0 = D[event_id0]
        
        
        # Update any magnitudes based on based on updated moments
        Mw=_eq_moment_to_magnitude(M0)
        
        # Convert length positions to x-y
        ll0_x,ll0_y = self.fault._length_to_xy(ll0)
        lr0_x,lr0_y = self.fault._length_to_xy(lr0)
        c0x,c0y = self.fault._length_to_xy(lc0)
        cx,cy = self.fault._length_to_xy(lc)
        
        # Generate array of boundaries
        l=len(c0x)
        bound0x = np.concat((ll0_x.reshape(l,1),lr0_x.reshape(l,1),lr0_x.reshape(l,1),ll0_x.reshape(l,1),ll0_x.reshape(l,1)),axis=1)
        bound0y = np.concat((ll0_y.reshape(l,1),lr0_y.reshape(l,1),lr0_y.reshape(l,1),ll0_y.reshape(l,1),ll0_y.reshape(l,1)),axis=1)
        bound0z = np.concat((zt0.reshape(l,1),zt0.reshape(l,1),zb0.reshape(l,1),zb0.reshape(l,1),zt0.reshape(l,1)),axis=1)
        bound0l = np.concat((ll0.reshape(l,1),lr0.reshape(l,1),lr0.reshape(l,1),ll0.reshape(l,1),ll0.reshape(l,1)),axis=1)
        
        # Parse outputs into dictionaries, one which records whole rupture details and the other that 
        # records sub rupture details
        Events = {'Event_ID':event_id,
                  'Length':L,
                  'Width':W,
                  'Area':A,
                  'Displacement':D,
                  'Moment':M0,
                  'Magnitude':Mw,
                  'Center_X':cx,
                  'Center_Y':cy
                  }
        
        SubEvents ={'Event_ID':event_id0,
                     'Length':L0,
                     'Width':W0,
                     'Displacement':D0,
                     'Panel_IX':panel_ix0,
                     'Strike':strike0,
                     'Center_X':c0x,
                     'Center_Y':c0y,
                     'Center_Z':c0z,
                     'Center_L':lc0,
                     'Bound_X':bound0x,
                     'Bound_Y':bound0y,
                     'Bound_Z':bound0z,
                     'Bound_L':bound0l}
    
        return Events,SubEvents

    def _ruptures_on_vert_fault_af(self,L,W,A,D,M0,Mw,Mw_min,verbose,seed=1,stay_on_fault=True,
                                rupture_interseismic=False,is_fixed_max=False,
                                center_loc='Uniform',t_offset=None,rad=None,
                                parent=None):
        
        # Sub-function for biased radial distance placements for aftershock
        def radial_dist(lcOI,wcOI,minL,maxL,minW,maxW,radii,rng):
            # Count number of aftershocks
            n_a = len(radii)
            
            # Set up unit circle angles
            unit_theta = np.linspace(0,2*np.pi,10000)
            
            # Set up empty coordinate vectors for aftershock centers
            lca = np.full(n_a,np.nan)
            wca = np.full(n_a,np.nan)

            # Iterate through each radius and find range of angles that
            # will lie on the coseismic portion of the fault
            #
            # Originally tried this with a binning approach, which was slightly
            # faster, but made the "edge effect" in terms of rupture placements
            # worse. This did not completely remove the edge effect, but it did
            # improve it a bit.
            for i in range(n_a):
                r = radii[i]
                # Generate unit circle of radius
                ul = r*np.sin(unit_theta)
                uw = r*np.cos(unit_theta)
                # Position relative to center
                ucl = lcOI + ul
                ucw = wcOI + uw
                # Find if any portions of circle intersect with edge of fault
                idx = (ucl > maxL) | (ucl < minL) | (ucw > maxW) | (ucw < minW)
                
                if len(unit_theta[~idx]>0):
                    theta = rng.choice(unit_theta[~idx],1)
                    lo = r * np.sin(theta)
                    wo = r * np.cos(theta)
                    
                    lca[i] = lcOI + lo
                    wca[i] = wcOI + wo
            return lca,wca
        
        
        
        # Find number of parent events and their positions within the input arrays
        pidx = t_offset==-1
        num_parents = np.sum(pidx)
        
        # Establish event details
        num_events = L.shape[0]
        event_id = np.arange(0,num_events,1)
        rng = np.random.default_rng(seed=seed)
        
        # Find direct parent index
        direct_parent_ix, afs_orders,num_afs_orders = _find_parent_index(parent,event_id)
    
        # Get indices of A and C panels
        cix = [idx for idx, value in enumerate(self.fault._panel_types[0]) if value =='C'][0]
        bw = self.fault._fz[0,-1] - self.fault._fz[0,-2] # Width below seismogenic zone
        if np.any(np.array(self.fault._panel_types)=='A'):
            above = True
            aix = [idx for idx, value in enumerate(self.fault._panel_types[0]) if value =='A'][0]
            aw = self.fault._fz[0,cix] - self.fault._fz[0,aix] # Width of above seismogenic zone
        else:
            above = False
        
        # Generate empty containers
        lc = np.zeros(num_events)
        wc = np.zeros(num_events)
        
        # Establish a local coordinate system along width of fault where 0 is the center of 
        # coseismic width
        if (is_fixed_max) & (self.fault_max_param=='Width'):
            if above:
                meanW_2 = np.mean(W[pidx])/2
                if aw >= meanW_2:
                    wc[pidx] = rng.uniform(low=-self.fault._total_width/2,high=0.0,size=num_parents)
                else:
                    wc[pidx] = rng.uniform(low=-(self.fault._total_width/2 - (meanW_2-aw)),high=0.0,size=num_parents)
            else:
                wc[pidx] = np.zeros(num_parents)
        elif is_fixed_max:
            meanW_2 = np.mean(W[pidx])/2
            if above:
                if aw >= meanW_2:
                    wc[pidx] = rng.uniform(low=-self.fault._total_width/2,high=self.fault._total_width/2 - meanW_2,size=num_parents)
                else:
                    wc[pidx] = rng.uniform(low=-(self.fault._total_width/2 - (meanW_2-aw)),high=self.fault._total_width/2 - meanW_2,size = num_parents)
            else:
                wc[pidx] = rng.uniform(low=-(self.fault._total_width/2 - meanW_2),high=self.fault._total_width/2 - meanW_2,size=num_parents)
    
        elif not(stay_on_fault):
            if np.max(W[pidx]/2) < self.fault._fz[0,cix]:
                wc[pidx] = rng.uniform(low=-self.fault._total_width/2,high=self.fault._total_width/2,size=num_parents)
            else:
                wc[pidx] = rng.uniform(low=-(self.fault._total_width/2 - (np.max(W/2)-self.fault._fz[0,cix])),high=self.fault._total_width/2,size=num_parents)
    
        elif (stay_on_fault) & (not(rupture_interseismic)):
            # Find mean half width within bins
            w_bins = np.logspace(np.log10(np.min(W-1)),np.log10(np.max(W+1)),500)
            wix = np.digitize(W,w_bins)-1
            wc = np.zeros(W.shape)
            for i in range(500):
                widx = (wix==i) & (pidx)
                n = np.sum(widx)
                if n>0:
                    maxW_2 = np.max(W[widx])/2
                    if (above) & (maxW_2 > aw):
                        low = -(self.fault._total_width/2 - (maxW_2-aw))
                        high = self.fault._total_width/2 - maxW_2
                    elif above:
                        low = -self.fault._total_width/2
                        high = self.fault._total_width/2 - maxW_2
                    else:
                        low = -(self.fault._total_width/2 - maxW_2)
                        high = self.fault._total_width/2 - maxW_2
                        
                    wc[widx]= rng.uniform(low=low,high=high,size=n)
                        
        elif (stay_on_fault) & (rupture_interseismic):
            # Find mean half width within bins
            w_bins = np.logspace(np.log10(np.min(W-1)),np.log10(np.max(W+1)),500)
            wix = np.digitize(W,w_bins)-1
            wc = np.zeros(W.shape)
            for i in range(500):
                widx = (wix==i) & (pidx)
                n = np.sum(widx)
                if n>0:
                    maxW_2 = np.max(W[widx])/2
                    
                    if (above) & (maxW_2 > aw) & (maxW_2 > bw):
                        low = -(self.fault._total_width/2 - (maxW_2-aw))
                        high = self.fault._total_width/2 - (maxW_2-bw)
                    elif (above) & (maxW_2 > aw) & (maxW_2 <= bw):
                        low = -(self.fault._total_width/2 - (maxW_2-aw))
                        high = self.fault._total_width/2
                    elif (above) & (maxW_2 <= aw) & (maxW_2 <= bw):
                        low = -(self.fault._total_width/2 - maxW_2)
                        high = self.fault._total_width/2 
                    elif (not(above)) & (maxW_2 > bw):
                        low = -self.fault._total_width/2
                        high = self.fault._total_width/2 - (maxW_2-bw)
                    elif (not(above)) & (maxW_2 <= bw):
                        low = -self.fault._total_width/2
                        high = self.fault._total_width/2
                    
                    wc[widx] = rng.uniform(low=low,high=high,size=n)
                        
    
        # Convert to vertical extents of ruptures in fault centered coordinates
        wt = wc - W/2
        wb = wc + W/2
        # Convert to z coordinates
        zt = wt + (self.fault._fz[0,cix] + self.fault._total_width/2)
        zc = wc + (self.fault._fz[0,cix] + self.fault._total_width/2)
        zb = wb + (self.fault._fz[0,cix] + self.fault._total_width/2)
        
        # For lengths, coordinate system is from 0 to total length, in the direction of strikes
        if (is_fixed_max) & (self.fault_max_param=='Length'):
            # For repeating max events that are length limited, set the length center
            # of all events at 0
            lc[pidx] = np.full(num_parents,self.fault._total_length/2)
        elif (center_loc=='Uniform') & (not(stay_on_fault)) :
            lc[pidx] = rng.uniform(low=0,high=self.fault._total_length,size=num_parents)
        elif (center_loc=='Uniform') & (stay_on_fault):
            # If using a uniform distribution and forcing ruptures to stay on fault
            # reduce the range over which centers of ruptures can come from based on mean extent of ruptures
            l_bins = np.logspace(np.log10(np.min(L-1)),np.log10(np.max(L+1)),50)
            lix = np.digitize(L,l_bins)-1
            lc = np.zeros(L.shape)
            for i in range(50):
                lidx = (lix==i) & (pidx)
                n = np.sum(lidx)
                if n>0:
                    meanL_2 = np.mean(L[lidx])/2
                    lc[lidx] = rng.uniform(low=meanL_2,high=self.fault._total_length-meanL_2,size=n)
        elif center_loc=='Gaussian':
            # Generate a normal distribution centered on 0
            lc_unscale = rng.normal(0,1,num_parents)
            # Scale to range defined by -L/2 to L/2
            lc[pidx] = (self.fault._total_length) * lc_unscale/(np.max(np.abs(lc_unscale)))
            
        # Position aftershocks
        if stay_on_fault:
            for i in range(num_afs_orders-1):
                parent_idx = afs_orders==i
                children_idx = afs_orders==i+1
                for j in range(np.sum(parent_idx)):
                    parentOI_ix = event_id[parent_idx][j]
                    childrenOI_ix = event_id[np.logical_and(children_idx,direct_parent_ix==parentOI_ix)]
                    
                    # Add the max half-dimensions of the rupture
                    rads = rad[childrenOI_ix] + np.sqrt(L[childrenOI_ix]**2 + W[childrenOI_ix]**2)/2
                    # Find center relative to parent
                    lc_ = lc[parentOI_ix]
                    wc_ = wc[parentOI_ix]
                    
                    if len(rads)>0:
                        lc[childrenOI_ix],wc[childrenOI_ix] = radial_dist(lc_,wc_,0,self.fault._total_length,
                                                                          -self.fault._total_width/2,self.fault._total_width/2,
                                                                          rads,rng)
        else:
            for i in range(num_afs_orders-1):
                parent_idx = afs_orders==i
                children_idx = afs_orders==i+1
                for j in range(np.sum(parent_idx)):
                    parentOI_ix = event_id[parent_idx][j]
                    childrenOI_ix = event_id[np.logical_and(children_idx,direct_parent_ix==parentOI_ix)]
                    
                    rads = rad[childrenOI_ix]
                    theta_d = rng.uniform(0,2*np.pi,len(rads))
                    
                    x_offset = rads*np.sin(theta_d)
                    y_offset = rads*np.cos(theta_d)
                    
                    lc[childrenOI_ix]=lc[parentOI_ix] + x_offset
                    wc[childrenOI_ix]=wc[parentOI_ix] + x_offset
                    
        # Convert to vertical extents of ruptures in fault centered coordinates
        wt = wc - W/2
        wb = wc + W/2
        # Convert to z coordinates
        zt = wt + (self.fault._fz[0,cix] + self.fault._total_width/2)
        zc = wc + (self.fault._fz[0,cix] + self.fault._total_width/2)
        zb = wb + (self.fault._fz[0,cix] + self.fault._total_width/2)
                

    
        # Project ruptures onto fault
        event_id0,panel_ix0,strike0,L0,lc0,ll0,lr0=self._project_length_onto_panels(event_id,L,lc,verbose) 
        
        # Propagate lengths based on event IDs
        c0z = zc[event_id0]
        W0 = W[event_id0]
        zt0 = zt[event_id0]
        zb0 = zb[event_id0]
        D0 = D[event_id0]
        
        
        # Update any magnitudes based on based on updated moments
        Mw=_eq_moment_to_magnitude(M0)
        
        M0_min = _eq_magnitude_to_moment(Mw_min)
        
        # Find index of events to nan
        zidx = (M0==0) & (np.isnan(lc)) & (M0 < M0_min)
        events_to_remove = event_id[zidx]
        remove_idx = _find_children_to_remove(direct_parent_ix,event_id,events_to_remove)
        
        # Regenerate list of events to remove
        events_to_remove = event_id[remove_idx]
        
        # Propagate to subevent list
        e0idx = np.isin(event_id0,events_to_remove)
        
        # Instead of removing, lets try just setting to nan to preserve event orders
        L[remove_idx] = np.nan
        W[remove_idx] = np.nan
        A[remove_idx] = np.nan
        D[remove_idx] = np.nan
        M0[remove_idx] = np.nan
        Mw[remove_idx] = np.nan
        lc[remove_idx] = np.nan
        wc[remove_idx] = np.nan
        # Do not do t_offset, as we still wish to be able to flag aftershocks
        
        L0[e0idx] = np.nan
        W0[e0idx] = np.nan
        D0[e0idx] = np.nan
        lc0[e0idx] = np.nan
        ll0[e0idx] = np.nan
        lr0[e0idx] = np.nan
        strike0[e0idx] = np.nan
        # Not doing panel since that is an integer        
    
        
        
        # Convert length positions to x-y
        ll0_x,ll0_y = self.fault._length_to_xy(ll0)
        lr0_x,lr0_y = self.fault._length_to_xy(lr0)
        c0x,c0y = self.fault._length_to_xy(lc0)
        cx,cy = self.fault._length_to_xy(lc)
        
        # Generate array of boundaries
        l=len(c0x)
        bound0x = np.concat((ll0_x.reshape(l,1),lr0_x.reshape(l,1),lr0_x.reshape(l,1),ll0_x.reshape(l,1),ll0_x.reshape(l,1)),axis=1)
        bound0y = np.concat((ll0_y.reshape(l,1),lr0_y.reshape(l,1),lr0_y.reshape(l,1),ll0_y.reshape(l,1),ll0_y.reshape(l,1)),axis=1)
        bound0z = np.concat((zt0.reshape(l,1),zt0.reshape(l,1),zb0.reshape(l,1),zb0.reshape(l,1),zt0.reshape(l,1)),axis=1)
        bound0l = np.concat((ll0.reshape(l,1),lr0.reshape(l,1),lr0.reshape(l,1),ll0.reshape(l,1),ll0.reshape(l,1)),axis=1)
        
        af = t_offset > 0
        
        # Parse outputs into dictionaries, one which records whole rupture details and the other that 
        # records sub rupture details
        Events = {'Event_ID':event_id,
                  'Length':L,
                  'Width':W,
                  'Area':A,
                  'Displacement':D,
                  'Moment':M0,
                  'Magnitude':Mw,
                  'Center_X':cx,
                  'Center_Y':cy,
                  'Aftershock':af,
                  'Parent_ID':direct_parent_ix,
                  'Parent_Chain':parent,
                  'Aftershock_Order':afs_orders,
                  'Time_Offset':t_offset
                  }
        
        SubEvents ={'Event_ID':event_id0,
                     'Length':L0,
                     'Width':W0,
                     'Displacement':D0,
                     'Panel_IX':panel_ix0,
                     'Strike':strike0,
                     'Center_X':c0x,
                     'Center_Y':c0y,
                     'Center_Z':c0z,
                     'Center_L':lc0,
                     'Bound_X':bound0x,
                     'Bound_Y':bound0y,
                     'Bound_Z':bound0z,
                     'Bound_L':bound0l}
    
        return Events,SubEvents,num_afs_orders   
    
    def _ruptures_on_fault(self,L,W,A,D,M0,Mw,verbose,seed=1,stay_on_fault=True,
                            rupture_interseismic=False,is_fixed_max=False,
                            center_loc='Uniform'):
        """
        Randomly places ruptures of given size on fault plane

        Parameters
        ----------
        L : array of floats
            Total length of ruptures.
        W : array of floats
            Total width of ruptures.
        A : array of floats
            Total area of ruptures.
        D : array of floats
            Displacements of ruptures.
        M0 : array of floats
            Scalar seismic moment of ruptures.
        Mw : array of floats
            Moment magnitude of ruptures.
        verbose : boolean
            Flag to turn on reporting of status to terminal.
        seed : int, optional
            Seed for random number generation, for reproducibility. The default is 1.
        stay_on_fault : boolean, optional
            Flag to force ruptures to remain on fault surface. The default is True.
        rupture_interseismic : boolean, optional
            Flag to allow ruptures to extend into interseismic fault panels.
            The default is False.
        is_fixed_max : boolean, optional
            Flag to indicate whether rutpures are repeating max type. The default is False.
        center_loc : str, optional
            Controls the distribution of center location sampling along fault length.
            Options are 'Uniform' for a boxcar distribution or 'Gaussian' for a 
            normal distribution. The default is 'Uniform'.

        Returns
        -------
        Events : dict
            Catalog of events.
        SubEvents : dict
            Catalog of subevents.

        """
        # Routine for randomly placing ruptures, defined by their length (L - along strike) 
        # and width (W - down dip) on a fault, returns list of centroids for each rupture.
        # If rupture centroid implies that rupture spans a bend in the fault, then this
        # code will partition the rupture onto the respective panels. Implicitly assumes
        # that the center of ruptures (crude approximations of earthquake hypocenters) 
        # are uniformly distributed in both strike and dip distance within the coseismic
        # portion of the fault.
        #
        # Output will be a list of arrays, one array for each rupture. The first entry
        # in the array is the number of panels spanned by the rupture, followed by the x,y 
        # cooridnate of the centroid of the i-th part of the rupture, the dip of the i-th part of the rupture,
        # the length of the i-th part of the rupture, and the width of the i-th part of the rupture. 
        # If the rupture only spans one panel, then their will be 6 entries in the array and 
        # the length and width will be the same as the input for that rupture.
        #
        # The option "stay_on_fault", if set to true, will force the entire dimensions of ruptures
        # to be within the confines of the fault. Reductions in length required to stay on the fault
        # will trigger reduction of total rupture size and all associated quantities (W, A, D, M0) based
        # on Leonard, 2014 scaling. Reductions in width required to stay on fault will only trigger reductions
        # in other quantities if the rupture is dip-slip as re-scaling for strike-slip ruptures based on width
        # is undefined for portions of parameters space
        #
        # The option "rupture_interseismic", if set to true, will allow ruptures to include portions of
        # the fault that slip interseismically, but the center of the rupture will always be within
        # the coseismic zone. If set to False, will restrict ruptures from including any interseismic slipping areas.
        #
        # If "stay_on_fault" is True and "rupture_interseismic" is False, this will increase processing time.
        
            
        # Generate a fault centered coordinate system for randomly selecting centroids.
        # Origin of "length" coordinate is along the centerline of the fault and is bounded
        # on the fault between +fault length / 2 and - fault length/2. Origin of width
        # Coordinate is at the tip of the fault.  Coordinate stystem is defined on 
        # a horiztonal 0 surface with fault geometry projected onto it.
        
        # Random uniform sampling of center locations occuring within bounded sections 
        # to generate an initial pass of fault center locations, starting with length
        num_events = L.shape[0]
        event_id = np.arange(0,num_events,1)
        rng = np.random.default_rng(seed=seed)
        
        
        if (is_fixed_max) & (self.fault_max_param=='Length'):
            # For repeating max events that are length limited, set the length center
            # of all events at 0
            lc = np.zeros(num_events)
        elif (center_loc=='Uniform') & (not(stay_on_fault)) :
            lc = rng.uniform(low=-self.fault._length[0]/2,high=self.fault._length[0]/2,size=num_events)
        elif (center_loc=='Uniform') & (stay_on_fault):
            # If using a uniform distribution and forcing ruptures to stay on fault
            # reduce the range over which centers of ruptures can come from based on mean extent of ruptures
            meanL = np.mean(L)
            lc = rng.uniform(low=(-self.fault._length[0]/2) + meanL/2,high=(self.fault._length[0]/2) - meanL/2,size=num_events)
        elif center_loc=='Gaussian':
            # Generate a normal distribution centered on 0
            lc_unscale = rng.normal(0,1,num_events)
            # Scale to range defined by -L/2 to L/2
            lc = (self.fault._length[0]/2) * lc_unscale/(np.max(np.abs(lc_unscale)))
        # Generate left and right edges of ruptures based on generated rupture lengths
        ll = lc - L/2
        lr = lc + L/2
        if stay_on_fault:
            # First check if any rupture lengths exceed the length of the fault
            # Set any ruptures that do to the full length of the fault, recalculate the
            # other rupture parameters accordingly and set lc to 0 (i.e., the center of the fault)
            too_long = L > self.fault._length[0]
            if np.any(too_long):
                L[too_long]=self.fault._length[0]
                _,W[too_long],A[too_long],D[too_long],M0[too_long] = _leonard14_scaling(self.fault._fault_type,L=L[too_long]) 
                lc[too_long]=0
                ll[too_long]=-self.fault._length[0]/2
                lr[too_long]=self.fault._length[0]/2
            # Next check left edge and shift if needed
            l_offset = np.abs(ll) - self.fault._length[0]/2
            wide_left = ll < -self.fault._length[0]/2
            ll[wide_left] = ll[wide_left] + l_offset[wide_left]
            lr[wide_left] = lr[wide_left] + l_offset[wide_left]
            lc[wide_left] = lc[wide_left] + l_offset[wide_left]
            # Do the same for the right edge
            r_offset = self.fault._length[0]/2 - lr
            wide_right = lr > self.fault._length[0]/2
            ll[wide_right] = ll[wide_right] + r_offset[wide_right]
            lr[wide_right] = lr[wide_right] + r_offset[wide_right]
            lc[wide_right] = lc[wide_right] + r_offset[wide_right]
            
        # Start mapping width
        # Determine "top" and "bottom" of coseismic zone relative to tip of fault and randomly sample 
        # from within the coseismic zone for the width position of the center
    
        if not(stay_on_fault):
            co_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='C').ravel() # Index of panels that are coseismic
            co_top_h = self.fault._fx[co_panels_ix[0]]
            co_bot_h = self.fault._fx[co_panels_ix[-1]+1]
            wc = rng.uniform(low=co_top_h,high=co_bot_h,size=num_events) # Centers in width dimensions of ruptures in h-space
        
        # Characteristic ruptures have a single width so this is simpler and are forced to not rupture
        # the interseismic portion
        elif (stay_on_fault) & (not(rupture_interseismic)) & (is_fixed_max):
            # Similar procedure as for length, reduce bounds of range by mean half_width of ruptures
            # Find mean half width
            meanW_2 = np.mean(W)/2
            # Index of panels that are coseismic
            co_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='C').ravel() 
            # Range of x nodes on fault
            co_x_nodes=self.fault._fx[co_panels_ix[0]:co_panels_ix[-1]+2]
            # Dip of panels included
            co_dips = self.fault._dip[co_panels_ix]
            # Generate list of width increments along fault, sampled on a dense net of x
            dx = 0.1
            x_vec = np.arange(co_x_nodes[0],co_x_nodes[-1]+dx,dx)
            w_inc = np.zeros(x_vec.shape)
            for i in range(len(co_dips)):
                idx = (x_vec >= co_x_nodes[i]) & (x_vec < co_x_nodes[i+1])
                w_inc[idx] = dx/np.cos(np.radians(co_dips[i]))
            w_top_down = np.cumsum(w_inc)
            w_bot_up = np.flip(np.cumsum(np.flip(w_inc)))
            w_top_ix = np.argmin(np.abs(w_top_down-meanW_2))
            w_bot_ix = np.argmin(np.abs(w_bot_up-meanW_2))
            
            if np.any(np.array(self.fault._panel_types)=='A'):
                # Index of panels that are above coseismic
                ab_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='A').ravel() 
                # Range of x nodes on fault above coseismic
                ab_x_nodes=self.fault._fx[ab_panels_ix[0]:ab_panels_ix[-1]+2]
                # Dip of above panels included
                ab_dips = self.fault._dip[ab_panels_ix]
                dx = 0.1
                x_vec_ab = np.arange(ab_x_nodes[0],ab_x_nodes[-1]+dx,dx)
                w_inc_ab = np.zeros(x_vec_ab.shape)
                for i in range(len(ab_dips)):
                    idx = (x_vec_ab >= ab_x_nodes[i]) & (x_vec_ab < ab_x_nodes[i+1])
                    w_inc_ab[idx] = dx/np.cos(np.radians(ab_dips[i]))
                    
                w_ab_bot_up = np.flip(np.cumsum(np.flip(w_inc_ab)))
                w_ab_top_down = np.cumsum(w_inc_ab)
                if meanW_2 < np.max(w_ab_bot_up):
                    # w_ab_top_ix = np.argmin(np.abs(w_ab_bot_up-meanW_2))
                    w_ab_top_ix = np.argmin(np.abs(w_ab_top_down-meanW_2))
                    min_val = np.min([x_vec_ab[w_ab_top_ix],x_vec[w_top_ix],x_vec[w_bot_ix]])
                else:
                    meanW_2_rem = meanW_2 - np.max(w_ab_top_down)
                    w_rem_top_ix = np.argmin(np.abs(w_top_down-meanW_2_rem))
                    min_val = np.min([x_vec[w_rem_top_ix],x_vec[w_top_ix],x_vec[w_bot_ix]])
            else:
                min_val = np.min([x_vec[w_top_ix],x_vec[w_bot_ix]])
                            
            max_val = np.max([x_vec[w_top_ix],x_vec[w_bot_ix]]) 
            wc = rng.uniform(low=min_val,high=max_val,size=num_events)
        
        # Non repeating max ruptures that are restricted to the coseismic portion only 
        elif (stay_on_fault) & (not(rupture_interseismic)) & (not(is_fixed_max)):
            # Similar procedure as for length, reduce bounds of range by mean half_width of ruptures
            
            # Find mean half width within bins
            w_bins = np.logspace(np.log10(np.min(W-1)),np.log10(np.max(W+1)),50)
            wix = np.digitize(W,w_bins)-1
            wc = np.zeros(W.shape)
            for i in range(50):
                widx = wix==i
                n = np.sum(widx)
                if n > 0:
                    meanW_2 = np.min(W[widx])/2
                    # Index of panels that are coseismic
                    co_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='C').ravel() 
                    # Range of x nodes on fault
                    co_x_nodes=self.fault._fx[co_panels_ix[0]:co_panels_ix[-1]+2]
                    # Dip of panels included
                    co_dips = self.fault._dip[co_panels_ix]
                    # Generate list of width increments along fault, sampled on a dense net of x
                    dx = 0.1
                    x_vec = np.arange(co_x_nodes[0],co_x_nodes[-1]+dx,dx)
                    w_inc = np.zeros(x_vec.shape)
                    for i in range(len(co_dips)):
                        idx = (x_vec >= co_x_nodes[i]) & (x_vec < co_x_nodes[i+1])
                        w_inc[idx] = dx/np.cos(np.radians(co_dips[i]))
                    w_top_down = np.cumsum(w_inc)
                    w_bot_up = np.flip(np.cumsum(np.flip(w_inc)))
                    w_top_ix = np.argmin(np.abs(w_top_down-meanW_2))
                    w_bot_ix = np.argmin(np.abs(w_bot_up-meanW_2))

                    if np.any(np.array(self.fault._panel_types)=='A'):
                        # Index of panels that are above coseismic
                        ab_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='A').ravel() 
                        # Range of x nodes on fault above coseismic
                        ab_x_nodes=self.fault._fx[ab_panels_ix[0]:ab_panels_ix[-1]+2]
                        # Dip of above panels included
                        ab_dips = self.fault._dip[ab_panels_ix]
                        dx = 0.1
                        x_vec_ab = np.arange(ab_x_nodes[0],ab_x_nodes[-1]+dx,dx)
                        w_inc_ab = np.zeros(x_vec_ab.shape)
                        for i in range(len(ab_dips)):
                            idx = (x_vec_ab >= ab_x_nodes[i]) & (x_vec_ab < ab_x_nodes[i+1])
                            w_inc_ab[idx] = dx/np.cos(np.radians(ab_dips[i]))
                            
                        w_ab_top_down = np.cumsum(w_inc_ab)
                        w_ab_top_ix = np.argmin(np.abs(w_ab_top_down-meanW_2))
                        if meanW_2 <  np.max(w_ab_top_down):
                            wc[widx] = rng.uniform(low=x_vec_ab[w_ab_top_ix],high=x_vec[w_bot_ix],size=n)
                        else:
                            meanW_2_rem = meanW_2 - np.max(w_ab_top_down)
                            w_rem_top_ix = np.argmin(np.abs(w_top_down-meanW_2_rem))
                            min_val = np.min([x_vec[w_rem_top_ix],x_vec[w_top_ix],x_vec[w_bot_ix]])
                            wc[widx] = rng.uniform(low=min_val,high=x_vec[w_bot_ix],size=n)
                    else:
                        wc[widx] = rng.uniform(low=x_vec[w_top_ix],high=x_vec[w_bot_ix],size=n)
        
        # Non repeating max ruptures that are allowed to rupture the interseismic section
        elif (stay_on_fault) & (rupture_interseismic) & (not(is_fixed_max)):
            # Find mean half width within bins
            w_bins = np.logspace(np.log10(np.min(W-1)),np.log10(np.max(W+1)),50)
            wix = np.digitize(W,w_bins)-1
            wc = np.zeros(W.shape)
            for i in range(50):
                widx = wix == i
                n = np.sum(widx)
                if n > 0:
                    meanW_2 = np.mean(W[widx])/2
                    # Index of panels that are coseismic
                    co_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='C').ravel() 
                    # Range of x nodes on fault
                    co_x_nodes=self.fault._fx[co_panels_ix[0]:co_panels_ix[-1]+2]
                    # Dip of panels included
                    co_dips = self.fault._dip[co_panels_ix]
                    # Generate list of width increments along fault, sampled on a dense net of x
                    dx = 0.1
                    x_vec = np.arange(co_x_nodes[0],co_x_nodes[-1]+dx,dx)
                    w_inc = np.zeros(x_vec.shape)
                    for i in range(len(co_dips)):
                        idx = (x_vec >= co_x_nodes[i]) & (x_vec < co_x_nodes[i+1])
                        w_inc[idx] = dx/np.cos(np.radians(co_dips[i]))
                    w_top_down = np.cumsum(w_inc)
                    w_top_ix = np.argmin(np.abs(w_top_down-meanW_2))

                    if np.any(np.array(self.fault._panel_types)=='A'):
                        # Index of panels that are above coseismic
                        ab_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='A').ravel() 
                        # Range of x nodes on fault above coseismic
                        ab_x_nodes=self.fault._fx[ab_panels_ix[0]:ab_panels_ix[-1]+2]
                        # Dip of above panels included
                        ab_dips = self.fault._dip[ab_panels_ix]
                        dx = 0.1
                        x_vec_ab = np.arange(ab_x_nodes[0],ab_x_nodes[-1]+dx,dx)
                        w_inc_ab = np.zeros(x_vec_ab.shape)
                        for i in range(len(ab_dips)):
                            idx = (x_vec_ab >= ab_x_nodes[i]) & (x_vec_ab < ab_x_nodes[i+1])
                            w_inc_ab[idx] = dx/np.cos(np.radians(ab_dips[i]))
                            
                        w_ab_top_down = np.cumsum(w_inc_ab)
                        w_ab_top_ix = np.argmin(np.abs(w_ab_top_down-meanW_2))
                        if meanW_2 <  np.max(w_ab_top_down):
                            wc[widx] = rng.uniform(low=x_vec_ab[w_ab_top_ix],high=co_x_nodes[-1],size=n)
                        else:
                            meanW_2_rem = meanW_2 - np.max(w_ab_top_down)
                            w_rem_top_ix = np.argmin(np.abs(w_top_down-meanW_2_rem))
                            min_val = np.min([x_vec[w_rem_top_ix],x_vec[w_top_ix]])
                            wc[widx] = rng.uniform(low=min_val,high=co_x_nodes[-1],size=n)
                    else:
                        wc[widx] = rng.uniform(low=x_vec[w_top_ix],high=co_x_nodes[-1],size=n)

            
        # Project ruptures onto fault
        event_id0,panel_ix0,dip0,W0,wc0,wt0,wb0=self._project_width_onto_panels(event_id,W,wc,verbose)    
    
    
        # Check that any ruptures above fault plane do not go above the zero 
        # surface as this will generate errors in the okada4py routines
        # Update width accordingly and propagate to others
        above_tip = panel_ix0 == -1
        bottom_z = np.interp(wb0,self.fault._fx,self.fault._fz)
        upper_z = bottom_z - W0*np.sin(np.radians(dip0))
        too_high = (upper_z <= 0) & (above_tip)
        if np.any(too_high):
            # Reduce width for relevant panels
            W0[too_high] = (bottom_z[too_high]-0.1)/np.sin(np.radians(dip0[too_high]))
            wt0[too_high] = -W0[too_high]*np.cos(np.radians(dip0[too_high]))
            wc0[too_high] = wt0[too_high]/2
            if (self.fault._fault_type=='Interplate_DS') | (self.fault._fault_type=='SCR_DS'):
                # Updated total widths for each event
                W=np.bincount(event_id0,W0)
                # Update lengths and other values
                events_too_high = event_id0[too_high]
                event_idx = np.isin(event_id,events_too_high)
                L[event_idx],_,A[event_idx],D[event_idx],M0[event_idx] = _leonard14_scaling(self.fault._fault_type,W=W[event_idx])
                # Update half lengths of rupture
                ll = lc - L/2
                lr = lc + L/2
            else:
                print('Warning: Re-scaling by width is not supported for strike-slip faults, some events in catalogue will have mis-matched dimensions')
        
        # Start checks for whether ruptures are restricted to the fault or whether they are allowed to include interseismic portions in ruptures
        if stay_on_fault:
            off_fault = (panel_ix0==-1) | (panel_ix0==self.fault._num_panels)
            if np.any(off_fault):
                events_that_include_off_fault = np.unique(event_id0[off_fault])
                # Remove any portions of ruptures that are off_fault
                event_id0 = event_id0[~off_fault]
                panel_ix0 = panel_ix0[~off_fault]
                dip0 = dip0[~off_fault]
                W0 = W0[~off_fault]
                wc0 = wc0[~off_fault]
                wt0 = wt0[~off_fault]
                wb0 = wb0[~off_fault]
                if (self.fault._fault_type=='Interplate_DS') | (self.fault._fault_type=='SCR_DS'):
                    # Updated total widths for each event
                    W=np.bincount(event_id0,W0)
                    # Update lengths and other values
                    event_idx = np.isin(event_id,events_that_include_off_fault)                    
                    L[event_idx],_,A[event_idx],D[event_idx],M0[event_idx] = _leonard14_scaling(self.fault._fault_type,W=W[event_idx])
                    # Update half lengths of rupture
                    ll = lc - L/2
                    lr = lc + L/2
                else:
                    print('Warning: Re-scaling by width is not supported for strike-slip faults, some events in catalogue will have mis-matched dimensions')
            
        # Start check for interseismic portions 
        if not(rupture_interseismic):
            panel_types_array=np.array(self.fault._panel_types)
            interseismic = (panel_types_array[panel_ix0]=='I')
            if np.any(interseismic):
                # First remove any portions of rupture that extend beyond bottom of fault as these must include interseismic
                # portion and these also need to be removed
                off_fault = (panel_ix0==self.fault._num_panels)
                if np.any(off_fault):
                    # Remove any portions of ruptures that are off_fault
                    event_id0 = event_id0[~off_fault]
                    panel_ix0 = panel_ix0[~off_fault]
                    dip0 = dip0[~off_fault]
                    W0 = W0[~off_fault]
                    wc0 = wc0[~off_fault]
                    wt0 = wt0[~off_fault]
                    wb0 = wb0[~off_fault] 
                
                # Now proceed with removing interseismic portions of ruptures
                events_that_rupture_interseismic = np.unique(event_id0[interseismic])
                # Remove the interseismic portions
                event_id0 = event_id0[~interseismic]
                panel_ix0 = panel_ix0[~interseismic]
                dip0 = dip0[~interseismic]
                W0 = W0[~interseismic]
                wc0 = wc0[~interseismic]
                wt0 = wt0[~interseismic]
                wb0 = wb0[~interseismic]
                if (self.fault._fault_type=='Interplate_DS') | (self.fault._fault_type=='SCR_DS'):
                    # Updated total widths for each event
                    W=np.bincount(event_id0,W0)
                    # Update lengths and other values
                    event_idx = np.isin(event_id,events_that_rupture_interseismic)                    
                    L[event_idx],_,A[event_idx],D[event_idx],M0[event_idx] = _leonard14_scaling(self.fault._fault_type,W=W[event_idx])
                    # Update half lengths of rupture
                    ll = lc - L/2
                    lr = lc + L/2
                else:
                    print('Warning: Re-scaling by width is not supported for strike-slip faults, some events in catalogue will have mis-matched dimensions')                
        
        # Propagate lengths based on event IDs
        lc0 = lc[event_id0]
        L0 = L[event_id0]
        ll0 = ll[event_id0]
        lr0 = lr[event_id0]
        D0 = D[event_id0]
        
        # Update any magnitudes based on based on updated moments
        Mw=_eq_moment_to_magnitude(M0)
        
        # Transform into x-y coordinates
        cx,cy = _rot_coord(wc,lc,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
        c0x,c0y = _rot_coord(wc0,lc0,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
        tr0x,tr0y = _rot_coord(wt0,lr0,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
        br0x,br0y = _rot_coord(wb0,lr0,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
        tl0x,tl0y = _rot_coord(wt0,ll0,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
        bl0x,bl0y = _rot_coord(wb0,ll0,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0]) 
        
        # Generate array of boundaries
        l=len(c0x)
        bound0x = np.concat((tr0x.reshape(l,1),br0x.reshape(l,1),bl0x.reshape(l,1),tl0x.reshape(l,1),tr0x.reshape(l,1)),axis=1)
        bound0y = np.concat((tr0y.reshape(l,1),br0y.reshape(l,1),bl0y.reshape(l,1),tl0y.reshape(l,1),tr0y.reshape(l,1)),axis=1)
        
        # Query depths for individual ruptures
        panel_ix0_=panel_ix0.copy()
        panel_ix0_[panel_ix0==-1]=0
        panel_ix0_[panel_ix0==self.fault._num_panels]=self.fault._num_panels-1
        c0z = np.zeros(c0x.shape)
        for i in range(len(c0x)):
            c0z[i]=self.fault._query_depth(c0x[i], c0y[i], panel_ix0_[i])

        
        # Parse outputs into dictionaries, one which records whole rupture details and the other that 
        # records sub rupture details
        Events = {'Event_ID':event_id,
                  'Length':L,
                  'Width':W,
                  'Area':A,
                  'Displacement':D,
                  'Moment':M0,
                  'Magnitude':Mw,
                  'Center_X':cx,
                  'Center_Y':cy
                  }
        
        SubEvents ={'Event_ID':event_id0,
                     'Length':L0,
                     'Width':W0,
                     'Displacement':D0,
                     'Panel_IX':panel_ix0,
                     'Dip':dip0,
                     'Center_X':c0x,
                     'Center_Y':c0y,
                     'Center_Z':c0z,
                     'Bound_X':bound0x,
                     'Bound_Y':bound0y}
    
        return Events,SubEvents
    
    def _ruptures_on_fault_af(self,L,W,A,D,M0,Mw,Mw_min,verbose,seed=1,stay_on_fault=True,
                              rupture_interseismic=False,is_fixed_max=False,
                              center_loc='Uniform',t_offset=None,rad=None,
                              parent=None):
        """
        Randomly places ruptures of given size on fault plane, if aftershocks
        are generated

        Parameters
        ----------
        L : array of floats
            Total length of ruptures.
        W : array of floats
            Total width of ruptures.
        A : array of floats
            Total area of ruptures.
        D : array of floats
            Displacements of ruptures.
        M0 : array of floats
            Scalar seismic moment of ruptures.
        Mw : array of floats
            Moment magnitude of ruptures.
        verbose : boolean
            Flag to turn on reporting of status to terminal.
        seed : int, optional
            Seed for random number generation, for reproducibility. The default is 1.
        stay_on_fault : boolean, optional
            Flag to force ruptures to remain on fault surface. The default is True.
        rupture_interseismic : boolean, optional
            Flag to allow ruptures to extend into interseismic fault panels.
            The default is False.
        is_fixed_max : boolean, optional
            Flag to indicate whether rutpures are repeating max type. The default is False.
        center_loc : str, optional
            Controls the distribution of center location sampling along fault length.
            Options are 'Uniform' for a boxcar distribution or 'Gaussian' for a 
            normal distribution. The default is 'Uniform'.
        t_offset : array of floats
            Time offsets for child events
        rad : array of floats
            Radial distances for child events
        parent : array of ints
            Records of which events are linked as parent and children

        Returns
        -------
        Events : dict
            Catalog of events.
        SubEvents : dict
            Catalog of subevents.        
        """
        
        # Modified form of ruptures_on_fault method to deal with sequences with aftershocks.
        #
        # Aftershock events will be related to a parent event and have a position relative to the 
        # center of the parent given with the x_offset and y_offset values. These offsets are radially
        # distributed, so we can choose "x" or "y" to be length or width. In this case, x is treated
        # as the length and y will be treated as the width.
        
        # Sub-function for biased radial distance placements for aftershock
        def radial_dist(lcOI,wcOI,minL,maxL,minW,maxW,radii,rng):
            # Count number of aftershocks
            n_a = len(radii)
            
            # Set up unit circle angles
            unit_theta = np.linspace(0,2*np.pi,10000)
            
            # Set up empty coordinate vectors for aftershock centers
            lca = np.full(n_a,np.nan)
            wca = np.full(n_a,np.nan)

            # Iterate through each radius and find range of angles that
            # will lie on the coseismic portion of the fault
            #
            # Originally tried this with a binning approach, which was slightly
            # faster, but made the "edge effect" in terms of rupture placements
            # worse. This did not completely remove the edge effect, but it did
            # improve it a bit.
            for i in range(n_a):
                r = radii[i]
                # Generate unit circle of radius
                ul = r*np.sin(unit_theta)
                uw = r*np.cos(unit_theta)
                # Position relative to center
                ucl = lcOI + ul
                ucw = wcOI + uw
                # Find if any portions of circle intersect with edge of fault
                idx = (ucl > maxL) | (ucl < minL) | (ucw > maxW) | (ucw < minW)
                
                if len(unit_theta[~idx]>0):
                    theta = rng.choice(unit_theta[~idx],1)
                    lo = r * np.sin(theta)
                    wo = r * np.cos(theta)
                    
                    lca[i] = lcOI + lo
                    wca[i] = wcOI + wo
            return lca,wca
        
        
        # Find number of parent events and their positions within the input arrays
        pidx = t_offset==-1
        num_parents = np.sum(pidx)
        
        # Find total events and assign each an ID, this will differ than the ID
        # stored within the "parent" output from the aftershock generator as aftershocks
        # will get unique IDs here.
        num_events = L.shape[0]
        event_id = np.arange(0,num_events,1)
        rng = np.random.default_rng(seed=seed)
        
        # Find direct parent index
        direct_parent_ix, afs_orders, num_afs_orders = _find_parent_index(parent,event_id)
        
        # Generate empty fault centered center coordinate vectors
        lc = np.zeros(num_events)
        wc = np.zeros(num_events)
        
        # Assign length centers for the parents
        if (is_fixed_max) & (self.fault_max_param=='Length'):
            # For repeating max events that are length limited, set the length center
            # of all events at 0
            lc[pidx] = np.zeros(num_parents)
        elif (center_loc=='Uniform') & (not(stay_on_fault)) :
            lc[pidx] = rng.uniform(low=-self.fault._length[0]/2,high=self.fault._length[0]/2,size=num_parents)
        elif (center_loc=='Uniform') & (stay_on_fault):
            # If using a uniform distribution and forcing ruptures to stay on fault
            # reduce the range over which centers of ruptures can come from based on mean extent of ruptures
            meanL = np.mean(L[pidx])
            lc[pidx] = rng.uniform(low=(-self.fault._length[0]/2) + meanL/2,high=(self.fault._length[0]/2) - meanL/2,size=num_parents)
        elif center_loc=='Gaussian':
            # Generate a normal distribution centered on 0
            lc_unscale = rng.normal(0,1,num_parents)
            # Scale to range defined by -L/2 to L/2
            lc[pidx] = (self.fault._length[0]/2) * lc_unscale/(np.max(np.abs(lc_unscale)))
                        
        # Generate left and right edges of ruptures based on generated rupture lengths
        ll = lc - L/2
        lr = lc + L/2
        if stay_on_fault:
            # First check if any rupture lengths exceed the length of the fault
            # Set any ruptures that do to the full length of the fault, recalculate the
            # other rupture parameters accordingly and set lc to 0 (i.e., the center of the fault)
            too_long = L > self.fault._length[0]
            if np.any(too_long):
                L[too_long]=self.fault._length[0]
                _,W[too_long],A[too_long],D[too_long],M0[too_long] = _leonard14_scaling(self.fault._fault_type,L=L[too_long]) 
                lc[too_long]=0
                ll[too_long]=-self.fault._length[0]/2
                lr[too_long]=self.fault._length[0]/2
            # Next check left edge and shift if needed
            l_offset = np.abs(ll) - self.fault._length[0]/2
            wide_left = ll < -self.fault._length[0]/2
            ll[wide_left] = ll[wide_left] + l_offset[wide_left]
            lr[wide_left] = lr[wide_left] + l_offset[wide_left]
            lc[wide_left] = lc[wide_left] + l_offset[wide_left]
            # Do the same for the right edge
            r_offset = self.fault._length[0]/2 - lr
            wide_right = lr > self.fault._length[0]/2
            ll[wide_right] = ll[wide_right] + r_offset[wide_right]
            lr[wide_right] = lr[wide_right] + r_offset[wide_right]
            lc[wide_right] = lc[wide_right] + r_offset[wide_right]
            
        # Start mapping width
        # Determine "top" and "bottom" of coseismic zone relative to tip of fault and randomly sample 
        # from within the coseismic zone for the width position of the center
    
        if not(stay_on_fault):
            co_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='C').ravel() # Index of panels that are coseismic
            co_top_h = self.fault._fx[co_panels_ix[0]]
            co_bot_h = self.fault._fx[co_panels_ix[-1]+1]
            wc[pidx] = rng.uniform(low=co_top_h,high=co_bot_h,size=num_parents) # Centers in width dimensions of ruptures in h-space
        
        # Characteristic ruptures have a single width so this is simpler and are forced to not rupture
        # the interseismic portion
        elif (stay_on_fault) & (not(rupture_interseismic)) & (is_fixed_max):
            # Similar procedure as for length, reduce bounds of range by mean half_width of ruptures
            # Find mean half width
            meanW_2 = np.mean(W[pidx])/2
            # Index of panels that are coseismic
            co_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='C').ravel() 
            # Range of x nodes on fault
            co_x_nodes=self.fault._fx[co_panels_ix[0]:co_panels_ix[-1]+2]
            # Dip of panels included
            co_dips = self.fault._dip[co_panels_ix]
            # Generate list of width increments along fault, sampled on a dense net of x
            dx = 0.1
            x_vec = np.arange(co_x_nodes[0],co_x_nodes[-1]+dx,dx)
            w_inc = np.zeros(x_vec.shape)
            for i in range(len(co_dips)):
                idx = (x_vec >= co_x_nodes[i]) & (x_vec < co_x_nodes[i+1])
                w_inc[idx] = dx/np.cos(np.radians(co_dips[i]))
            w_top_down = np.cumsum(w_inc)
            w_bot_up = np.flip(np.cumsum(np.flip(w_inc)))
            w_top_ix = np.argmin(np.abs(w_top_down-meanW_2))
            w_bot_ix = np.argmin(np.abs(w_bot_up-meanW_2))
            
            if np.any(np.array(self.fault._panel_types)=='A'):
                # Index of panels that are above coseismic
                ab_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='A').ravel() 
                # Range of x nodes on fault above coseismic
                ab_x_nodes=self.fault._fx[ab_panels_ix[0]:ab_panels_ix[-1]+2]
                # Dip of above panels included
                ab_dips = self.fault._dip[ab_panels_ix]
                dx = 0.1
                x_vec_ab = np.arange(ab_x_nodes[0],ab_x_nodes[-1]+dx,dx)
                w_inc_ab = np.zeros(x_vec_ab.shape)
                for i in range(len(ab_dips)):
                    idx = (x_vec_ab >= ab_x_nodes[i]) & (x_vec_ab < ab_x_nodes[i+1])
                    w_inc_ab[idx] = dx/np.cos(np.radians(ab_dips[i]))
                    
                w_ab_bot_up = np.flip(np.cumsum(np.flip(w_inc_ab)))
                w_ab_top_down = np.cumsum(w_inc_ab)
                if meanW_2 < np.max(w_ab_bot_up):
                    # w_ab_top_ix = np.argmin(np.abs(w_ab_bot_up-meanW_2))
                    w_ab_top_ix = np.argmin(np.abs(w_ab_top_down-meanW_2))
                    min_val = np.min([x_vec_ab[w_ab_top_ix],x_vec[w_top_ix],x_vec[w_bot_ix]])
                else:
                    meanW_2_rem = meanW_2 - np.max(w_ab_top_down)
                    w_rem_top_ix = np.argmin(np.abs(w_top_down-meanW_2_rem))
                    min_val = np.min([x_vec[w_rem_top_ix],x_vec[w_top_ix],x_vec[w_bot_ix]])
            else:
                min_val = np.min([x_vec[w_top_ix],x_vec[w_bot_ix]])
                
            max_val = np.max([x_vec[w_top_ix],x_vec[w_bot_ix]]) 
            wc[pidx] = rng.uniform(low=min_val,high=max_val,size=num_parents)
        
        # Non repeating max ruptures that are restricted to the coseismic portion only 
        elif (stay_on_fault) & (not(rupture_interseismic)) & (not(is_fixed_max)):
            # Similar procedure as for length, reduce bounds of range by mean half_width of ruptures
            
            # Find mean half width within bins
            w_bins = np.logspace(np.log10(np.min(W-1)),np.log10(np.max(W+1)),50)
            wix = np.digitize(W,w_bins)-1
            for i in range(50):
                widx = (wix==i) & (pidx)
                n = np.sum(widx)
                if n > 0:
                    meanW_2 = np.mean(W[widx])/2
                    # Index of panels that are coseismic
                    co_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='C').ravel() 
                    # Range of x nodes on fault
                    co_x_nodes=self.fault._fx[co_panels_ix[0]:co_panels_ix[-1]+2]
                    # Dip of panels included
                    co_dips = self.fault._dip[co_panels_ix]
                    # Generate list of width increments along fault, sampled on a dense net of x
                    dx = 0.1
                    x_vec = np.arange(co_x_nodes[0],co_x_nodes[-1]+dx,dx)
                    w_inc = np.zeros(x_vec.shape)
                    for i in range(len(co_dips)):
                        idx = (x_vec >= co_x_nodes[i]) & (x_vec < co_x_nodes[i+1])
                        w_inc[idx] = dx/np.cos(np.radians(co_dips[i]))
                    w_top_down = np.cumsum(w_inc)
                    w_bot_up = np.flip(np.cumsum(np.flip(w_inc)))
                    w_top_ix = np.argmin(np.abs(w_top_down-meanW_2))
                    w_bot_ix = np.argmin(np.abs(w_bot_up-meanW_2))
                    
                    if np.any(np.array(self.fault._panel_types)=='A'):
                        # Index of panels that are above coseismic
                        ab_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='A').ravel() 
                        # Range of x nodes on fault above coseismic
                        ab_x_nodes=self.fault._fx[ab_panels_ix[0]:ab_panels_ix[-1]+2]
                        # Dip of above panels included
                        ab_dips = self.fault._dip[ab_panels_ix]
                        dx = 0.1
                        x_vec_ab = np.arange(ab_x_nodes[0],ab_x_nodes[-1]+dx,dx)
                        w_inc_ab = np.zeros(x_vec_ab.shape)
                        for i in range(len(ab_dips)):
                            idx = (x_vec_ab >= ab_x_nodes[i]) & (x_vec_ab < ab_x_nodes[i+1])
                            w_inc_ab[idx] = dx/np.cos(np.radians(ab_dips[i]))
                            
                        w_ab_top_down = np.cumsum(w_inc_ab)
                        w_ab_top_ix = np.argmin(np.abs(w_ab_top_down-meanW_2))
                
                        if meanW_2 <  np.max(w_ab_top_down):
                            wc[widx] = rng.uniform(low=x_vec_ab[w_ab_top_ix],high=x_vec[w_bot_ix],size=n)
                        else:
                            meanW_2_rem = meanW_2 - np.max(w_ab_top_down)
                            w_rem_top_ix = np.argmin(np.abs(w_top_down-meanW_2_rem))
                            min_val = np.min([x_vec[w_rem_top_ix],x_vec[w_top_ix],x_vec[w_bot_ix]])
                            wc[widx] = rng.uniform(low=min_val,high=x_vec[w_bot_ix],size=n)

                    else:
                        wc[widx] = rng.uniform(low=x_vec[w_top_ix],high=x_vec[w_bot_ix],size=n)
        
        # Non repeating max ruptures that are allowed to rupture the interseismic section
        elif (stay_on_fault) & (rupture_interseismic) & (not(is_fixed_max)):
            # Find mean half width within bins
            w_bins = np.logspace(np.log10(np.min(W-1)),np.log10(np.max(W+1)),50)
            wix = np.digitize(W,w_bins)-1
            for i in range(50):
                widx = (wix == i) & (pidx)
                n = np.sum(widx)
                if n > 0:
                    meanW_2 = np.mean(W[widx])/2
                    # Index of panels that are coseismic
                    co_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='C').ravel() 
                    # Range of x nodes on fault
                    co_x_nodes=self.fault._fx[co_panels_ix[0]:co_panels_ix[-1]+2]
                    # Dip of panels included
                    co_dips = self.fault._dip[co_panels_ix]
                    # Generate list of width increments along fault, sampled on a dense net of x
                    dx = 0.1
                    x_vec = np.arange(co_x_nodes[0],co_x_nodes[-1]+dx,dx)
                    w_inc = np.zeros(x_vec.shape)
                    for i in range(len(co_dips)):
                        idx = (x_vec >= co_x_nodes[i]) & (x_vec < co_x_nodes[i+1])
                        w_inc[idx] = dx/np.cos(np.radians(co_dips[i]))
                    w_top_down = np.cumsum(w_inc)
                    w_top_ix = np.argmin(np.abs(w_top_down-meanW_2))

                    if np.any(np.array(self.fault._panel_types)=='A'):
                        # Index of panels that are above coseismic
                        ab_panels_ix = np.argwhere(np.array(self.fault._panel_types)=='A').ravel() 
                        # Range of x nodes on fault above coseismic
                        ab_x_nodes=self.fault._fx[ab_panels_ix[0]:ab_panels_ix[-1]+2]
                        # Dip of above panels included
                        ab_dips = self.fault._dip[ab_panels_ix]
                        dx = 0.1
                        x_vec_ab = np.arange(ab_x_nodes[0],ab_x_nodes[-1]+dx,dx)
                        w_inc_ab = np.zeros(x_vec_ab.shape)
                        for i in range(len(ab_dips)):
                            idx = (x_vec_ab >= ab_x_nodes[i]) & (x_vec_ab < ab_x_nodes[i+1])
                            w_inc_ab[idx] = dx/np.cos(np.radians(ab_dips[i]))
                            
                        w_ab_top_down = np.cumsum(w_inc_ab)
                        w_ab_top_ix = np.argmin(np.abs(w_ab_top_down-meanW_2))
                        
                        if meanW_2 <  np.max(w_ab_top_down):
                            wc[widx] = rng.uniform(low=x_vec_ab[w_ab_top_ix],high=co_x_nodes[-1],size=n)
                        else:
                            meanW_2_rem = meanW_2 - np.max(w_ab_top_down)
                            w_rem_top_ix = np.argmin(np.abs(w_top_down-meanW_2_rem))
                            min_val = np.min([x_vec[w_rem_top_ix],x_vec[w_top_ix]])
                            wc[widx] = rng.uniform(low=min_val,high=co_x_nodes[-1],size=n)
                    else:
                        wc[widx] = rng.uniform(low=x_vec[w_top_ix],high=co_x_nodes[-1],size=n)
                    
        # Position aftershocks
        if stay_on_fault:
            for i in range(num_afs_orders-1):
                parent_idx = afs_orders==i
                children_idx = afs_orders==i+1
                for j in range(np.sum(parent_idx)):
                    parentOI_ix = event_id[parent_idx][j] 
                    childrenOI_ix = event_id[np.logical_and(children_idx,direct_parent_ix==parentOI_ix)]
                    
                    # Add the max half-dimensions of the rupture to the radius to be conservative
                    rads = rad[childrenOI_ix] + np.sqrt(L[childrenOI_ix]**2 + W[childrenOI_ix]**2)/2
                    # Find center of relative parent
                    lc_ = lc[parentOI_ix]
                    wc_ = wc[parentOI_ix]
                    
                    if len(rads)>0:
                        lc[childrenOI_ix],wc[childrenOI_ix] = radial_dist(lc_,wc_,-self.fault._length[0]/2,self.fault._length[0]/2,
                                                                          co_x_nodes[0],co_x_nodes[-1],rads,rng)
                    
                

        else:
            for i in range(num_afs_orders-1):
                parent_idx = afs_orders==i
                children_idx = afs_orders==i+1
                for j in range(np.sum(parent_idx)):
                    parentOI_ix = event_id[parent_idx][j] 
                    childrenOI_ix = event_id[np.logical_and(children_idx,direct_parent_ix==parentOI_ix)]
                    
                    rads = rad[childrenOI_ix]
                    theta_d = rng.uniform(0,2*np.pi,len(rads))
                    
                    # Find position relative to parent earthquake
                    x_offset = rads*np.sin(theta_d)
                    y_offset = rads*np.cos(theta_d)
                    
                    lc[childrenOI_ix] = lc[parentOI_ix] + x_offset
                    wc[childrenOI_ix] = wc[parentOI_ix] + y_offset

        # Update length extents of rupture
        ll = lc - L/2
        lr = lc + L/2
        # Rerun length check, should be quick as it's vectorized
        too_long = L > self.fault._length[0]
        if np.any(too_long):
            L[too_long]=self.fault._length[0]
            _,W[too_long],A[too_long],D[too_long],M0[too_long] = _leonard14_scaling(self.fault._fault_type,L=L[too_long]) 
            lc[too_long]=0
            ll[too_long]=-self.fault._length[0]/2
            lr[too_long]=self.fault._length[0]/2
        # Next check left edge and shift if needed
        l_offset = np.abs(ll) - self.fault._length[0]/2
        wide_left = ll < -self.fault._length[0]/2
        ll[wide_left] = ll[wide_left] + l_offset[wide_left]
        lr[wide_left] = lr[wide_left] + l_offset[wide_left]
        lc[wide_left] = lc[wide_left] + l_offset[wide_left]
        # Do the same for the right edge
        r_offset = self.fault._length[0]/2 - lr
        wide_right = lr > self.fault._length[0]/2
        ll[wide_right] = ll[wide_right] + r_offset[wide_right]
        lr[wide_right] = lr[wide_right] + r_offset[wide_right]
        lc[wide_right] = lc[wide_right] + r_offset[wide_right]
    
        # # After the placements, some wc and lc might be nan if aftershocks cannot be placed on the fault
        # # Remove them
        # remove_idx = np.logical_or(np.isnan(wc),np.isnan(lc))
        
        # event_id = np.delete(event_id,remove_idx)
        # L = np.delete(L,remove_idx)
        # W = np.delete(W,remove_idx)
        # A = np.delete(A,remove_idx)
        # D = np.delete(D,remove_idx)
        # M0 = np.delete(M0,remove_idx)
        # Mw = np.delete(Mw,remove_idx)
        # lc = np.delete(lc,remove_idx)
        # wc = np.delete(wc,remove_idx)
        # t_offset = np.delete(t_offset,remove_idx)
        # direct_parent_ix = np.delete(direct_parent_ix,remove_idx)
        # afs_orders = np.delete(afs_orders,remove_idx)
        # # Update parent lists
        # parent = [p for (p,remove) in zip(parent,remove_idx) if not remove]
    
        # Project ruptures onto fault
        event_id0,panel_ix0,dip0,W0,wc0,wt0,wb0=self._project_width_onto_panels(event_id,W,wc,verbose)
    
    
        # Check that any ruptures above fault plane do not go above the zero 
        # surface as this will generate errors in the okada4py routines
        # Update width accordingly and propagate to others
        above_tip = panel_ix0 == -1
        bottom_z = np.interp(wb0,self.fault._fx,self.fault._fz)
        upper_z = bottom_z - W0*np.sin(np.radians(dip0))
        too_high = (upper_z <= 0) & (above_tip)
        if np.any(too_high):
            # Reduce width for relevant panels
            W0[too_high] = (bottom_z[too_high]-0.1)/np.sin(np.radians(dip0[too_high]))
            wt0[too_high] = -W0[too_high]*np.cos(np.radians(dip0[too_high]))
            wc0[too_high] = wt0[too_high]/2
            if (self.fault._fault_type=='Interplate_DS') | (self.fault._fault_type=='SCR_DS'):
                # Updated total widths for each event
                W=np.bincount(event_id0,W0,minlength=len(W))
                # Update lengths and other values
                events_too_high = event_id0[too_high]
                event_idx = np.isin(event_id,events_too_high)
                L[event_idx],_,A[event_idx],D[event_idx],M0[event_idx] = _leonard14_scaling(self.fault._fault_type,W=W[event_idx])
                # Update half lengths of rupture
                ll = lc - L/2
                lr = lc + L/2
            else:
                print('Warning: Re-scaling by width is not supported for strike-slip faults, some events in catalogue will have mis-matched dimensions')
        
        # Start checks for whether ruptures are restricted to the fault or whether they are allowed to include interseismic portions in ruptures
        if stay_on_fault:
            off_fault = (panel_ix0==-1) | (panel_ix0==self.fault._num_panels)
            if np.any(off_fault):
                events_that_include_off_fault = np.unique(event_id0[off_fault])
                # Remove any portions of ruptures that are off_fault
                event_id0 = event_id0[~off_fault]
                panel_ix0 = panel_ix0[~off_fault]
                dip0 = dip0[~off_fault]
                W0 = W0[~off_fault]
                wc0 = wc0[~off_fault]
                wt0 = wt0[~off_fault]
                wb0 = wb0[~off_fault]
                if (self.fault._fault_type=='Interplate_DS') | (self.fault._fault_type=='SCR_DS'):
                    # Updated total widths for each event
                    W=np.bincount(event_id0,W0,minlength=len(W))
                    # Update lengths and other values
                    event_idx = np.logical_and(np.isin(event_id,events_that_include_off_fault),W>0)
                    event_idx0 = np.logical_and(np.isin(event_id,events_that_include_off_fault),W==0)
                    if np.sum(event_idx)>0:
                        L[event_idx],_,A[event_idx],D[event_idx],M0[event_idx] = _leonard14_scaling(self.fault._fault_type,W=W[event_idx])
                    if np.sum(event_idx0)>0:
                        L[event_idx0]=0; A[event_idx0]=0; D[event_idx0]=0; M0[event_idx0]=0
                    # Update half lengths of rupture
                    ll = lc - L/2
                    lr = lc + L/2
                else:
                    print('Warning: Re-scaling by width is not supported for strike-slip faults, some events in catalogue will have mis-matched dimensions')
            
        # Start check for interseismic portions 
        if not(rupture_interseismic):
            panel_types_array=np.array(self.fault._panel_types)
            interseismic = (panel_types_array[panel_ix0]=='I')
            if np.any(interseismic):
                # First remove any portions of rupture that extend beyond bottom of fault as these must include interseismic
                # portion and these also need to be removed
                off_fault = (panel_ix0==self.fault._num_panels)
                if np.any(off_fault):
                    # Remove any portions of ruptures that are off_fault
                    event_id0 = event_id0[~off_fault]
                    panel_ix0 = panel_ix0[~off_fault]
                    dip0 = dip0[~off_fault]
                    W0 = W0[~off_fault]
                    wc0 = wc0[~off_fault]
                    wt0 = wt0[~off_fault]
                    wb0 = wb0[~off_fault] 
                
                # Now proceed with removing interseismic portions of ruptures
                events_that_rupture_interseismic = np.unique(event_id0[interseismic])
                # Remove the interseismic portions
                event_id0 = event_id0[~interseismic]
                panel_ix0 = panel_ix0[~interseismic]
                dip0 = dip0[~interseismic]
                W0 = W0[~interseismic]
                wc0 = wc0[~interseismic]
                wt0 = wt0[~interseismic]
                wb0 = wb0[~interseismic]
                if (self.fault._fault_type=='Interplate_DS') | (self.fault._fault_type=='SCR_DS'):
                    # Updated total widths for each event
                    W=np.bincount(event_id0,W0,minlength=len(W))
                    # Update lengths and other values
                    event_idx = np.logical_and(np.isin(event_id,events_that_rupture_interseismic),W>0)
                    event_idx0 = np.logical_and(np.isin(event_id,events_that_rupture_interseismic),W==0)
                    L[event_idx],_,A[event_idx],D[event_idx],M0[event_idx] = _leonard14_scaling(self.fault._fault_type,W=W[event_idx])
                    L[event_idx0]=0;  A[event_idx0]=0; D[event_idx0]=0; M0[event_idx0]=0
                    # Update half lengths of rupture
                    ll = lc - L/2
                    lr = lc + L/2
                else:
                    print('Warning: Re-scaling by width is not supported for strike-slip faults, some events in catalogue will have mis-matched dimensions')                
        
        # Propagate lengths based on event IDs      
        lc0 = lc[event_id0]
        L0 = L[event_id0]
        ll0 = ll[event_id0]
        lr0 = lr[event_id0]
        D0 = D[event_id0]
                
        # Update any magnitudes based on based on updated moments
        Mw=_eq_moment_to_magnitude(M0)

        ## If aftershocks are placed far beyond the extent of the fault, these 
        # will get reduced to zero moment events, which are effectively holes 
        # in the catalog (and generate errors downsteam). Remove these events from 
        # both the event and subevents lists and also remove any "downstream"
        # aftershocks
        # 
        # Some events will also get trimmed to below the imposed minimum for aftershocks,
        # this step will also set these to nans
        M0_min = _eq_magnitude_to_moment(Mw_min)
        
        # Find index of events that should be removed
        zidx = (M0==0) | (np.isnan(lc)) | (M0 < M0_min)
        events_to_remove = event_id[zidx]
        remove_idx = _find_children_to_remove(direct_parent_ix,event_id,events_to_remove)
        
        # Regenerate list of events to remove
        events_to_remove = event_id[remove_idx]
        
        # Propagate to subevent list
        e0idx = np.isin(event_id0,events_to_remove)
        
        
        ### Deleting events with aftershocks causes a lot of issues
        # so for aftershock sequences, we'll instead fill in blanks with nans
        # # Remove these events from the main Event arrays
        # event_id = np.delete(event_id,remove_idx)
        # L = np.delete(L,remove_idx)
        # W = np.delete(W,remove_idx)
        # A = np.delete(A,remove_idx)
        # D = np.delete(D,remove_idx)
        # M0 = np.delete(M0,remove_idx)
        # Mw = np.delete(Mw,remove_idx)
        # lc = np.delete(lc,remove_idx)
        # wc = np.delete(wc,remove_idx)
        # t_offset = np.delete(t_offset,remove_idx)
        # direct_parent_ix = np.delete(direct_parent_ix,remove_idx)
        # afs_orders = np.delete(afs_orders,remove_idx)
        
        # # Update parent lists
        # parent = [p for (p,remove) in zip(parent,remove_idx) if not remove]
        
        # # Remove these events from the SubEvent arrays (most should not exist)
        # event_id0 = np.delete(event_id0,e0idx)
        # L0 = np.delete(L0,e0idx)
        # W0 = np.delete(W0,e0idx)
        # D0 = np.delete(D0,e0idx)
        # wc0 = np.delete(wc0,e0idx)
        # lc0 = np.delete(lc0,e0idx)
        # wb0 = np.delete(wb0,e0idx)
        # wt0 = np.delete(wt0,e0idx)
        # ll0 = np.delete(ll0,e0idx)
        # lr0 = np.delete(lr0,e0idx)
        # panel_ix0 = np.delete(panel_ix0,e0idx)
        # dip0 = np.delete(dip0,e0idx)

        # # Update number of events
        # num_events = len(L)
        
        # Instead of removing, lets try just setting to nan to preserve event orders
        L[remove_idx] = np.nan
        W[remove_idx] = np.nan
        A[remove_idx] = np.nan
        D[remove_idx] = np.nan
        M0[remove_idx] = np.nan
        Mw[remove_idx] = np.nan
        lc[remove_idx] = np.nan
        wc[remove_idx] = np.nan
        # Do not do t_offset, as we still wish to be able to flag aftershocks
        
        L0[e0idx] = np.nan
        W0[e0idx] = np.nan
        D0[e0idx] = np.nan
        wc0[e0idx] = np.nan
        lc0[e0idx] = np.nan
        wb0[e0idx] = np.nan
        wt0[e0idx] = np.nan
        ll0[e0idx] = np.nan
        lr0[e0idx] = np.nan
        dip0[e0idx] = np.nan
        # Not doing panel since that is an integer
        
        # Transform into x-y coordinates
        cx,cy = _rot_coord(wc,lc,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
        c0x,c0y = _rot_coord(wc0,lc0,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
        tr0x,tr0y = _rot_coord(wt0,lr0,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
        br0x,br0y = _rot_coord(wb0,lr0,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
        tl0x,tl0y = _rot_coord(wt0,ll0,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
        bl0x,bl0y = _rot_coord(wb0,ll0,self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0]) 
        
        # Generate array of boundaries
        l=len(c0x)
        bound0x = np.concat((tr0x.reshape(l,1),br0x.reshape(l,1),bl0x.reshape(l,1),tl0x.reshape(l,1),tr0x.reshape(l,1)),axis=1)
        bound0y = np.concat((tr0y.reshape(l,1),br0y.reshape(l,1),bl0y.reshape(l,1),tl0y.reshape(l,1),tr0y.reshape(l,1)),axis=1)
        
        # Query depths for individual ruptures
        panel_ix0_=panel_ix0.copy()
        panel_ix0_[panel_ix0==-1]=0
        panel_ix0_[panel_ix0==self.fault._num_panels]=self.fault._num_panels-1
        c0z = np.zeros(c0x.shape)
        for i in range(len(c0x)):
            c0z[i]=self.fault._query_depth(c0x[i], c0y[i], panel_ix0_[i])
        
        # Generate boolean list of events that are aftershocks
        af = t_offset > 0

        # Parse outputs into dictionaries, one which records whole rupture details and the other that 
        # records sub rupture details
        Events = {'Event_ID':event_id,
                  'Length':L,
                  'Width':W,
                  'Area':A,
                  'Displacement':D,
                  'Moment':M0,
                  'Magnitude':Mw,
                  'Center_X':cx,
                  'Center_Y':cy,
                  'Aftershock':af,
                  'Parent_ID':direct_parent_ix,
                  'Parent_Chain':parent,
                  'Aftershock_Order':afs_orders,
                  'Time_Offset':t_offset
                  }
        
        SubEvents ={'Event_ID':event_id0.astype(int),
                     'Length':L0,
                     'Width':W0,
                     'Displacement':D0,
                     'Panel_IX':panel_ix0,
                     'Dip':dip0,
                     'Center_X':c0x,
                     'Center_Y':c0y,
                     'Center_Z':c0z,
                     'Bound_X':bound0x,
                     'Bound_Y':bound0y}
    
        return Events,SubEvents,num_afs_orders

    def _project_length_onto_panels(self,event_id,L,lc,verbose):
        # Determine positions of rupture edges
        ll = lc - L/2
        lr = lc + L/2
        
        # Find any ruptures that extend beyond tips
        beyond_left = ll < 0
        beyond_right = lr > np.max(self.fault._fy)
        
        # If aftershocks are generated, some lc values may be nans, which will generate
        # an error downstream. Flag these and deal with them separately
        nan_idx = np.isnan(lc)
        
        
        # Find panel index of center, left, and right edges
        lc_panel = np.digitize(lc,self.fault._fy)-1
        ll_panel = np.digitize(ll,self.fault._fy)-1
        lr_panel = np.digitize(lr,self.fault._fy)-1
        
        # Determine single panel ruptures
        single_panel = (lc_panel==ll_panel) & (lc_panel==lr_panel) & (~nan_idx)
        
        # Generate list of single panel events
        eid_sp = event_id[single_panel]
        pix_sp = lc_panel[single_panel]        
        strike_sp = self.fault._strike[lc_panel[single_panel]]
        lc_sp = lc[single_panel]
        ll_sp = ll[single_panel]
        lr_sp = lr[single_panel]
        L_sp = L[single_panel]
        
        if verbose:
            print('Step 2 of 4 - Substep 1 of 5: Mapping of initial rupture lengths completed')
        
        # Iterate through events that span panels but don't extend beyond tips
        idx = (~single_panel) & (~beyond_left) & (~beyond_right) & (~nan_idx)
        # Generate empty containers for outputs
        eid_mp1=[]; pix_mp1=[]; strike_mp1=[]; lc_mp1=[]; ll_mp1=[]; lr_mp1=[]; L_mp1=[]
        
        for i in range(len(lc[idx])):
            eidOI = event_id[idx][i]
            ll_panelOI = ll_panel[idx][i]
            lr_panelOI = lr_panel[idx][i]
            # Generate vector of lateral positions of either rupture end or bends
            fyOI = self.fault._fy[ll_panelOI:lr_panelOI+2]
            l_vec = np.concat(([np.max((ll[idx][i],fyOI[0]))],fyOI[1:-1],[np.min((lr[idx][i],fyOI[-1]))]),axis=0)
            # Extract strikes
            strike_vec = self.fault._strike[ll_panelOI:lr_panelOI+1]
            strike_mp1.append(strike_vec)
            # Calculate widths of sub ruptures
            L_mp1.append(np.diff(l_vec))
            # Calculate centers of sub ruptures
            lc_mp1.append(l_vec[0:-1]+np.diff(l_vec)/2)
            # Convert l_vec into sides (mainly used for plotting)
            ll_mp1.append(l_vec[0:-1])
            lr_mp1.append(l_vec[1:])
            # Record event ID that is shared between rupture componets
            eid_mp1.append(np.tile(eidOI,strike_vec.shape))
            # Establish panel index for each sub rupture
            pix_mp1.append(np.digitize(lc_mp1[i],self.fault._fy)-1)
        
        # Concatenate lists from the above loop
        if len(eid_mp1)>0:
            eid_mp1=np.concat(eid_mp1)
            pix_mp1=np.concat(pix_mp1)
            
            strike_mp1=np.concat(strike_mp1,axis=0)
            L_mp1=np.concat(L_mp1)
            lc_mp1=np.concat(lc_mp1)
            ll_mp1=np.concat(ll_mp1)
            lr_mp1=np.concat(lr_mp1)


        if verbose:
            print('Step 2 of 4 - Substep 2 of 5: Initial parsing of ruptures onto fault panels completed')
        
        # Iterate though events that extend beyond upper tip
        idx = (beyond_left) & (~beyond_right) & (~nan_idx)
        # Generate empty containers for outputs
        eid_mp2=[]; pix_mp2=[]; strike_mp2=[]; lc_mp2=[]; ll_mp2=[]; lr_mp2=[]; L_mp2=[]
        for i in range(len(lc[idx])):
            eidOI = event_id[idx][i]
            ll_panelOI = 0 # Set panel to the left most
            lr_panelOI = lr_panel[idx][i]
            # Generate vector of horizontal positions of either rupture end or bends
            fyOI = self.fault._fy[ll_panelOI:lr_panelOI+2]
            l_vec = np.concat(([np.max((ll[idx][i],fyOI[0]))],fyOI[1:-1],[np.min((lr[idx][i],fyOI[-1]))]),axis=0)
            # Extract dips
            strike_vec = self.fault._strike[ll_panelOI:lr_panelOI+1]
            # Calculate lengths of sub ruptures (not including portion beyond edge)
            LOI=np.diff(l_vec)
            # Determine the remainder length and then concat this to the length array
            # If the tip past the fault is very close to the tip, then WR can be negative
            # set absolute value here as a catch
            LR = np.abs(L[idx][i] - np.sum(LOI))                 
            LOI = np.concat(([LR],LOI))           
            L_mp2.append(LOI)
            # Assume rupture beyond tip extends at same strike as the left panel
            # Update l_vec with the remiander
            l_vec=np.concat(([-LR],l_vec),axis=0)
            # Update strike
            strike_vec = np.concat(([strike_vec[0]],strike_vec),axis=0)
            strike_mp2.append(strike_vec)
            # Calculate centers of sub ruptures
            lc_mp2.append(l_vec[0:-1]+np.diff(l_vec)/2)
            # Convert l_vec into lefts and rights (mainly used for plotting)
            ll_mp2.append(l_vec[0:-1])
            lr_mp2.append(l_vec[1:])
            # Record event ID that is shared between rupture componets
            eid_mp2.append(np.tile(eidOI,strike_vec.shape))
            # Establish panel index for each sub rupture
            pix_mp2.append(np.digitize(lc_mp2[i],self.fault._fy)-1)
            
        # Concatenate lists from the above loop
        if len(eid_mp2)>0:
            eid_mp2=np.concat(eid_mp2)
            pix_mp2=np.concat(pix_mp2)
            strike_mp2=np.concat(strike_mp2)
            L_mp2=np.concat(L_mp2)
            lc_mp2=np.concat(lc_mp2)
            ll_mp2=np.concat(ll_mp2)
            lr_mp2=np.concat(lr_mp2)
            
        if verbose:
            print('Step 2 of 4 - Substep 3 of 5: Identification of ruptures extending beyond left fault tip completed')
    
        # Iterate though events that extend beyond lower tip only
        idx = (~beyond_left) & (beyond_right) & (~nan_idx)
        # Generate empty containers for outputs
        eid_mp3=[]; pix_mp3=[]; strike_mp3=[]; lc_mp3=[]; ll_mp3=[]; lr_mp3=[]; L_mp3=[]
        for i in range(len(lc[idx])):
            eidOI = event_id[idx][i]
            ll_panelOI = ll_panel[idx][i]
            lr_panelOI = lr_panel[idx][i]
            # Generate vector of horizontal positions of either rupture end or bends
            fyOI = self.fault._fy[ll_panelOI:lr_panelOI+2]
            l_vec = np.concat(([np.max((ll[idx][i],fyOI[0]))],fyOI[1:-1],[np.min((lr[idx][i],fyOI[-1]))]),axis=0)
            # Extract strikes
            strike_vec = self.fault._strike[ll_panelOI:lr_panelOI+1]
            # Calculate lengths of sub ruptures (not including portion beyond tip)
            LOI=np.diff(l_vec)
            # Determine the remainder length and then concat this to the width array
            LR = np.abs(L[idx][i] - np.sum(LOI))
            LOI = np.concat((LOI,[LR]))
            L_mp3.append(LOI)
            # Assume rupture beyond tip extends at same strike as the right panel
            # Update l_vec
            l_vec=np.concat((l_vec,[LR]),axis=0)
            # Update strike
            strike_vec = np.concat((strike_vec,[strike_vec[-1]]),axis=0)
            strike_mp3.append(strike_vec)
            # Calculate centers of sub ruptures
            lc_mp3.append(l_vec[0:-1]+np.diff(l_vec)/2)
            # Convert l_vec into left and right (mainly used for plotting)
            ll_mp3.append(l_vec[0:-1])
            lr_mp3.append(l_vec[1:])
            # Record event ID that is shared between rupture componets
            eid_mp3.append(np.tile(eidOI,strike_vec.shape))
            # Establish panel index for each sub rupture
            pix_mp3.append(np.digitize(lc_mp3[i],self.fault._fy)-1)
            
        # Concatenate lists from the above loop
        if len(eid_mp3)>0:
            eid_mp3=np.concat(eid_mp3)
            pix_mp3=np.concat(pix_mp3)
            strike_mp3=np.concat(strike_mp3)
            L_mp3=np.concat(L_mp3)
            lc_mp3=np.concat(lc_mp3)
            ll_mp3=np.concat(ll_mp3)
            lr_mp3=np.concat(lr_mp3)

        if verbose:
            print('Step 2 of 4 - Substep 4 of 5: Identification of ruptures extending beyond right fault tip completed')
    
        # Iterate though events that extend both upper and lower tip
        idx = (beyond_left) & (beyond_right) & (~nan_idx)
        # Generate empty containers for outputs
        eid_mp4=[]; pix_mp4=[]; strike_mp4=[]; lc_mp4=[]; ll_mp4=[]; lr_mp4=[]; L_mp4=[]
        for i in range(len(lc[idx])):
            eidOI = event_id[idx][i]
            ll_panelOI = ll_panel[idx][i]
            lr_panelOI = lr_panel[idx][i]
            # Generate vector of horizontal positions of either rupture end or bends
            fyOI = self.fault._fy[ll_panelOI:lr_panelOI+2]
            l_vec = np.concat(([np.max((ll[idx][i],fyOI[0]))],fyOI[1:-1],[np.min((lr[idx][i],fyOI[-1]))]),axis=0)
            # Extract dips
            strike_vec = self.fault._strike[ll_panelOI:lr_panelOI+1]
            # Calculate lengths of sub ruptures (not including portion beyond tip)
            LOI=np.diff(l_vec)
            # Determine the remainder length
            LR = np.abs(L[idx][i] - np.sum(LOI))
            # Use the relative position of the original center with respect to the 
            # edges of the fault projected to partition the remainder
            loc_ratio = self.fault._fy[-1]/lc[idx][i]
            LRR = LR*loc_ratio
            LRL = LR*(1-loc_ratio)
            LOI = np.concat(([LRL],LOI,[LRR]))
            L_mp4.append(LOI)
            # Assume rupture beyond tip extends at same strike 
            # Update l_vec
            l_vec=np.concat(([LRL],l_vec,[LRR]),axis=0)
            # Update strike
            strike_vec = np.concat(([strike_vec[0]],strike_vec,[strike_vec[-1]]),axis=0)
            strike_mp4.append(strike_vec)
            # Calculate centers of sub ruptures
            lc_mp4.append(l_vec[0:-1]+np.diff(l_vec)/2)
            # Convert l_vec into left and right (mainly used for plotting)
            ll_mp4.append(l_vec[0:-1])
            lr_mp4.append(l_vec[1:])
            # Record event ID that is shared between rupture componets
            eid_mp4.append(np.tile(eidOI,strike_vec.shape))
            # Establish panel index for each sub rupture
            pix_mp4.append(np.digitize(lc_mp4[i],self.fault._fy)-1)
            
        # Concatenate lists from the above loop
        if len(eid_mp4)>0:
            eid_mp4=np.concat(eid_mp4)
            pix_mp4=np.concat(pix_mp4)
            strike_mp4=np.concat(strike_mp4)
            L_mp4=np.concat(L_mp4)
            lc_mp4=np.concat(lc_mp4)
            ll_mp4=np.concat(ll_mp4)
            lr_mp4=np.concat(lr_mp4)
            
        idx = nan_idx
        eid_mp5=[]; pix_mp5=[]; strike_mp5=[]; lc_mp5=[]; ll_mp5=[]; lr_mp5=[]; L_mp5=[]
        for i in range(len(lc[idx])):
            eidOI = event_id[idx][i]
            eid_mp5.append([eidOI])
            pix_mp5.append([-1])
            strike_mp5.append([np.nan])
            L_mp5.append([np.nan])
            lc_mp5.append([np.nan])
            ll_mp5.append([np.nan])
            lr_mp5.append([np.nan])
            
        if len(eid_mp5)>0:
            eid_mp5=np.concat(eid_mp5)
            pix_mp5=np.concat(pix_mp5)
            strike_mp5=np.concat(strike_mp5)
            L_mp5=np.concat(L_mp5)
            lc_mp5=np.concat(lc_mp5)
            ll_mp5=np.concat(ll_mp5)
            lr_mp5=np.concat(lr_mp5)
        
            
        if verbose:
            print('Step 2 of 4 - Substep 5 of 5: Identification of ruptures extending beyond both fault tips completed')

        # Concatenate for output        
        eid_out = np.concat((eid_sp,eid_mp1,eid_mp2,eid_mp3,eid_mp4,eid_mp5),axis=0).astype(int)
        pix_out = np.concat((pix_sp,pix_mp1,pix_mp2,pix_mp3,pix_mp4,pix_mp5),axis=0).astype(int)
        strike_out = np.concat((strike_sp,strike_mp1,strike_mp2,strike_mp3,strike_mp4,strike_mp5),axis=0)
        L_out = np.concat((L_sp,L_mp1,L_mp2,L_mp3,L_mp4,L_mp5),axis=0)
        lc_out = np.concat((lc_sp,lc_mp1,lc_mp2,lc_mp3,lc_mp4,lc_mp5),axis=0)
        ll_out = np.concat((ll_sp,ll_mp1,ll_mp2,ll_mp3,ll_mp4,ll_mp5),axis=0)
        lr_out = np.concat((lr_sp,lr_mp1,lr_mp2,lr_mp3,lr_mp4,lr_mp5),axis=0)
        
        return eid_out,pix_out,strike_out,L_out,lc_out,ll_out,lr_out

    def _project_width_onto_panels(self,event_id,W,wc,verbose):
        """
        Partitions events and ruptures into sub-events and sub-ruptures along 
        fault plane with bends down-dip.

        Parameters
        ----------
        event_id : array of ints
            Event IDs.
        W : array of floats
            Full width of events.
        wc : array of floats
            Starting location of rupture centers in fault centered coordinates.
        verbose : boolean
            Flag to report progress to the terminal window.

        Returns
        -------
        eid_out : array of ints
            Event IDs for sub-ruptures.
        pix_out : array of ints
            Fault panel index for each sub-rupture.
        dip_out : array of floats
            Dip of each sub-rupture, dictated by the fault panel on which it occurs.
        W_out : array of floats
            Width of sub-ruptures.
        wc_out : array of floats
            Center location of sub-rupture along width in fault centered coordinates.
        wt_out : array of floats
            Top location of sub-ruptures along width in fault centered coordinates.
        wb_out : array of floats
            Bottom location of sub-ruptures along width in fault centered coordinates.

        """
        
        # Partially non-vectorized version of mapping individual ruptures onto fault plane
        # slower as requires looping, but more consistent than attempts 
        # at fully vectorized solutions
        
        # Generate a dense linear interpolated fault plane
        x = np.arange(self.fault._fx[0],self.fault._fx[-1],0.1)
        z = np.interp(x,self.fault._fx,self.fault._fz)
        # Calculate cumulative distance along the fault plane
        d = np.concat(([0],np.sqrt(np.diff(x)**2 + np.diff(z)**2)),axis=0)
        cd = np.cumsum(d)
                
        # # Iterate through to establish positions of the top and bottom coordinates
        # wt=np.zeros(len(wc))
        # wb=np.zeros(len(wc))
        # for i in range(len(wc)):
        #     # Find index of x position closest to wc
        #     ix = np.argmin(np.abs(wc[i]-x))
        #     cd_at_ix = cd[ix]
        #     # Find indices of positions closet to W/2 up or down the fault
        #     above_ix = np.argmin(np.abs( (cd_at_ix-(W[i]/2)) - cd ))
        #     below_ix = np.argmin(np.abs( (cd_at_ix+(W[i]/2)) - cd ))
        #     # Find x coordinate of those positions
        #     wt[i]=x[above_ix]
        #     wb[i]=x[below_ix]
        

        
        
        ## Significantly faster vectorized solution for initial step
        # Find index of x position closest to wc
        ix = np.searchsorted(x,wc)
        
        # If aftershocks are generated, some wc values may be nans, which will generate
        # an error downstream. Flag these and deal with them separately
        nan_idx = np.isnan(wc)
        ix[nan_idx] = ix[nan_idx]-1 #
        
        cd_at_ix = cd[ix]
        # Find indices of positions closet to W/2 up or down the fault
        above_ix = np.searchsorted(cd,cd_at_ix-(W/2))
        below_ix = np.searchsorted(cd,cd_at_ix+(W/2))
        
        above_ix[nan_idx] = above_ix[nan_idx] - 1
        below_ix[nan_idx] = below_ix[nan_idx] - 1
        
        # Find x coordinate of those positions
        wt = x[above_ix]
        wb = x[below_ix]
            
        # Determine if any tops and bottoms imply that the rupture extends 
        # beyond the fault tip
        above_tip = wt==0
        below_tip = wb==x[-1]    
        
        # Determine index of panel for center and edges of ruptures
        wc_panel = np.digitize(wc,self.fault._fx)-1
        wt_panel = np.digitize(wt,self.fault._fx)-1
        wb_panel = np.digitize(wb,self.fault._fx)-1
        
        # Determine single panel ruptures
        # Last terms are checking to see if any ruptures extend beyond the tips of the fault
        single_panel = (wc_panel==wt_panel) & (wc_panel==wb_panel) & (cd_at_ix-(W/2)>=0) & (cd_at_ix+(W/2)<=np.max(cd)) & (~nan_idx)
        
        # Generate list of single panel events
        eid_sp = event_id[single_panel]
        pix_sp = wc_panel[single_panel]
        dip_sp = self.fault._dip[wc_panel[single_panel]]
        wc_sp = wc[single_panel]
        wt_sp = wt[single_panel]
        wb_sp = wb[single_panel]
        W_sp = W[single_panel]        
        
        if verbose:
            print('Step 2 of 4 - Substep 1 of 5: Mapping of initial rupture widths completed')
        
        # Iterate through events that span panels but don't extend beyond tips
        idx = (~single_panel) & (~above_tip) & (~below_tip) & (~nan_idx)
        # Generate empty containers for outputs
        eid_mp1=[]; pix_mp1=[]; dip_mp1=[]; wc_mp1=[]; wt_mp1=[]; wb_mp1=[]; W_mp1=[]
        
        for i in range(len(wc[idx])):
            eidOI = event_id[idx][i]
            wt_panelOI = wt_panel[idx][i]
            wb_panelOI = wb_panel[idx][i]
            # Generate vector of horizontal positions of either rupture end or bends
            fxOI = self.fault._fx[wt_panelOI:wb_panelOI+2]
            w_vec = np.concat(([np.max((wt[idx][i],fxOI[0]))],fxOI[1:-1],[np.min((wb[idx][i],fxOI[-1]))]),axis=0)
            # Extract dips
            dip_vec = self.fault._dip[wt_panelOI:wb_panelOI+1]
            dip_mp1.append(dip_vec)
            # Calculate widths of sub ruptures
            W_mp1.append(np.diff(w_vec)/np.cos(np.radians(dip_vec)))
            # Calculate centers of sub ruptures
            wc_mp1.append(w_vec[0:-1]+np.diff(w_vec)/2)
            # Convert w_vec into tops and bottoms (mainly used for plotting)
            wt_mp1.append(w_vec[0:-1])
            wb_mp1.append(w_vec[1:])
            # Record event ID that is shared between rupture componets
            eid_mp1.append(np.tile(eidOI,dip_vec.shape))
            # Establish panel index for each sub rupture
            pix_mp1.append(np.digitize(wc_mp1[i],self.fault._fx)-1)
        
        # Concatenate lists from the above loop
        if len(eid_mp1)>0:
            eid_mp1=np.concat(eid_mp1)
            pix_mp1=np.concat(pix_mp1)
            dip_mp1=np.concat(dip_mp1)
            W_mp1=np.concat(W_mp1)
            wc_mp1=np.concat(wc_mp1)
            wt_mp1=np.concat(wt_mp1)
            wb_mp1=np.concat(wb_mp1)
                
        if verbose:
            print('Step 2 of 4 - Substep 2 of 5: Initial parsing of ruptures onto fault panels completed')
        
        # Iterate though events that extend beyond upper tip
        idx = (above_tip) & (~below_tip) & (~nan_idx)
        # Generate empty containers for outputs
        eid_mp2=[]; pix_mp2=[]; dip_mp2=[]; wc_mp2=[]; wt_mp2=[]; wb_mp2=[]; W_mp2=[]
        for i in range(len(wc[idx])):
            eidOI = event_id[idx][i]
            wt_panelOI = 0 # Set upper panel to the upper most
            wb_panelOI = wb_panel[idx][i]
            # Generate vector of horizontal positions of either rupture end or bends
            fxOI = self.fault._fx[wt_panelOI:wb_panelOI+2]
            w_vec = np.concat(([np.max((wt[idx][i],fxOI[0]))],fxOI[1:-1],[np.min((wb[idx][i],fxOI[-1]))]),axis=0)
            # Extract dips
            dip_vec = self.fault._dip[wt_panelOI:wb_panelOI+1]
            # Calculate widths of sub ruptures (not including portion beyond tip)
            WOI=np.diff(w_vec)/np.cos(np.radians(dip_vec))
            # Determine the remainder width and then concat this to the width array
            # If the tip past the fault is very close to the tip, then WR can be negative
            # set absolute value here as a catch
            WR = np.abs(W[idx][i] - np.sum(WOI))                 
            WOI = np.concat(([WR],WOI))           
            W_mp2.append(WOI)
            # Assume rupture beyond tip extends at same dip as the top panel
            # Calculate the position of the end of the rupture
            wt_tip = np.cos(np.radians(dip_vec[0]))* WR
            # Update w_vec
            w_vec=np.concat(([-wt_tip],w_vec),axis=0)
            # Update dip
            dip_vec = np.concat(([dip_vec[0]],dip_vec),axis=0)
            dip_mp2.append(dip_vec)
            # Calculate centers of sub ruptures
            wc_mp2.append(w_vec[0:-1]+np.diff(w_vec)/2)
            # Convert w_vec into tops and bottoms (mainly used for plotting)
            wt_mp2.append(w_vec[0:-1])
            wb_mp2.append(w_vec[1:])
            # Record event ID that is shared between rupture componets
            eid_mp2.append(np.tile(eidOI,dip_vec.shape))
            # Establish panel index for each sub rupture
            pix_mp2.append(np.digitize(wc_mp2[i],self.fault._fx)-1)
            
        # Concatenate lists from the above loop
        if len(eid_mp2)>0:
            eid_mp2=np.concat(eid_mp2)
            pix_mp2=np.concat(pix_mp2)
            dip_mp2=np.concat(dip_mp2)
            W_mp2=np.concat(W_mp2)
            wc_mp2=np.concat(wc_mp2)
            wt_mp2=np.concat(wt_mp2)
            wb_mp2=np.concat(wb_mp2)
            
        if verbose:
            print('Step 2 of 4 - Substep 3 of 5: Identification of ruptures extending beyond upper fault tip completed')
    
        # Iterate though events that extend beyond lower tip only
        idx = (~above_tip) & (below_tip) & (~nan_idx)
        # Generate empty containers for outputs
        eid_mp3=[]; pix_mp3=[]; dip_mp3=[]; wc_mp3=[]; wt_mp3=[]; wb_mp3=[]; W_mp3=[]
        for i in range(len(wc[idx])):
            eidOI = event_id[idx][i]
            wt_panelOI = wt_panel[idx][i]
            wb_panelOI = wb_panel[idx][i]
            # Generate vector of horizontal positions of either rupture end or bends
            fxOI = self.fault._fx[wt_panelOI:wb_panelOI+2]
            w_vec = np.concat(([np.max((wt[idx][i],fxOI[0]))],fxOI[1:-1],[np.min((wb[idx][i],fxOI[-1]))]),axis=0)
            # Extract dips
            dip_vec = self.fault._dip[wt_panelOI:wb_panelOI+1]
            # Calculate widths of sub ruptures (not including portion beyond tip)
            WOI=np.diff(w_vec)/np.cos(np.radians(dip_vec))
            # Determine the remainder width and then concat this to the width array
            WR = np.abs(W[idx][i] - np.sum(WOI))
            WOI = np.concat((WOI,[WR]))
            W_mp3.append(WOI)
            # Assume rupture beyond tip extends at same dip as the bottom panel
            # Calculate the position of the end of the rupture
            wb_tip = self.fault._fx[-1]+np.cos(np.radians(dip_vec[-1]))* WR
            # Update w_vec
            w_vec=np.concat((w_vec,[wb_tip]),axis=0)
            # Update dip
            dip_vec = np.concat((dip_vec,[dip_vec[-1]]),axis=0)
            dip_mp3.append(dip_vec)
            # Calculate centers of sub ruptures
            wc_mp3.append(w_vec[0:-1]+np.diff(w_vec)/2)
            # Convert w_vec into tops and bottoms (mainly used for plotting)
            wt_mp3.append(w_vec[0:-1])
            wb_mp3.append(w_vec[1:])
            # Record event ID that is shared between rupture componets
            eid_mp3.append(np.tile(eidOI,dip_vec.shape))
            # Establish panel index for each sub rupture
            pix_mp3.append(np.digitize(wc_mp3[i],self.fault._fx)-1)
            
        # Concatenate lists from the above loop
        if len(eid_mp3)>0:
            eid_mp3=np.concat(eid_mp3)
            pix_mp3=np.concat(pix_mp3)
            dip_mp3=np.concat(dip_mp3)
            W_mp3=np.concat(W_mp3)
            wc_mp3=np.concat(wc_mp3)
            wt_mp3=np.concat(wt_mp3)
            wb_mp3=np.concat(wb_mp3)

        if verbose:
            print('Step 2 of 4 - Substep 4 of 5: Identification of ruptures extending beyond lower fault tip completed')
    
        # Iterate though events that extend both upper and lower tip
        idx = (above_tip) & (below_tip) & (~nan_idx)
        # Generate empty containers for outputs
        eid_mp4=[]; pix_mp4=[]; dip_mp4=[]; wc_mp4=[]; wt_mp4=[]; wb_mp4=[]; W_mp4=[]
        for i in range(len(wc[idx])):
            eidOI = event_id[idx][i]
            wt_panelOI = wt_panel[idx][i]
            wb_panelOI = wb_panel[idx][i]
            # Generate vector of horizontal positions of either rupture end or bends
            fxOI = self.fault._fx[wt_panelOI:wb_panelOI+2]
            w_vec = np.concat(([np.max((wt[idx][i],fxOI[0]))],fxOI[1:-1],[np.min((wb[idx][i],fxOI[-1]))]),axis=0)
            # Extract dips
            dip_vec = self.fault._dip[wt_panelOI:wb_panelOI+1]
            # Calculate widths of sub ruptures (not including portion beyond tip)
            WOI=np.diff(w_vec)/np.cos(np.radians(dip_vec))
            # Determine the remainder width
            WR = np.abs(W[idx][i] - np.sum(WOI))
            # Use the relative position of the original center with respect to the 
            # edges of the fault projected to the surface to partition the remainder
            loc_ratio = self.fault._fx[-1]/wc[idx][i]
            WRB = WR*loc_ratio
            WRT = WR*(1-loc_ratio)
            WOI = np.concat(([WRT],WOI,[WRB]))
            W_mp4.append(WOI)
            # Assume rupture beyond tip extends at same dip as the bottom panel
            # Calculate the position of the end of the rupture
            wb_tip = self.fault._fx[-1]+np.cos(np.radians(dip_vec[-1]))* WRB
            wt_tip = self.fault._fx[0]+np.cos(np.radians(dip_vec[0]))* WRT
            # Update w_vec
            w_vec=np.concat(([wt_tip],w_vec,[wb_tip]),axis=0)
            # Update dip
            dip_vec = np.concat(([dip_vec[0]],dip_vec,[dip_vec[-1]]),axis=0)
            dip_mp4.append(dip_vec)
            # Calculate centers of sub ruptures
            wc_mp4.append(w_vec[0:-1]+np.diff(w_vec)/2)
            # Convert w_vec into tops and bottoms (mainly used for plotting)
            wt_mp4.append(w_vec[0:-1])
            wb_mp4.append(w_vec[1:])
            # Record event ID that is shared between rupture componets
            eid_mp4.append(np.tile(eidOI,dip_vec.shape))
            # Establish panel index for each sub rupture
            pix_mp4.append(np.digitize(wc_mp4[i],self.fault._fx)-1)
            
        # Concatenate lists from the above loop
        if len(eid_mp4)>0:
            eid_mp4=np.concat(eid_mp4)
            pix_mp4=np.concat(pix_mp4)
            dip_mp4=np.concat(dip_mp4)
            W_mp4=np.concat(W_mp4)
            wc_mp4=np.concat(wc_mp4)
            wt_mp4=np.concat(wt_mp4)
            wb_mp4=np.concat(wb_mp4)
            
        idx = nan_idx
        # Generate empty containers for outputs
        eid_mp5=[]; pix_mp5=[]; dip_mp5=[]; wc_mp5=[]; wt_mp5=[]; wb_mp5=[]; W_mp5=[]
        for i in range(len(wc[idx])):
            eidOI = event_id[idx][i]
            eid_mp5.append([eidOI])
            pix_mp5.append([-1])
            dip_mp5.append([np.nan])
            W_mp5.append([np.nan])
            wc_mp5.append([np.nan])
            wt_mp5.append([np.nan])
            wb_mp5.append([np.nan])
            
        if len(eid_mp5)>0:
            eid_mp5=np.concat(eid_mp5)
            pix_mp5=np.concat(pix_mp5)
            dip_mp5=np.concat(dip_mp5)
            W_mp5=np.concat(W_mp5)
            wc_mp5=np.concat(wc_mp5)
            wt_mp5=np.concat(wt_mp5)
            wb_mp5=np.concat(wb_mp5)
            
        
        
        if verbose:
            print('Step 2 of 4 - Substep 5 of 5: Identification of ruptures extending beyond both fault tips completed')
            
        # Concatenate for output
        eid_out = np.concat((eid_sp,eid_mp1,eid_mp2,eid_mp3,eid_mp4,eid_mp5),axis=0).astype(int)
        pix_out = np.concat((pix_sp,pix_mp1,pix_mp2,pix_mp3,pix_mp4,pix_mp5),axis=0).astype(int)
        dip_out = np.concat((dip_sp,dip_mp1,dip_mp2,dip_mp3,dip_mp4,dip_mp5),axis=0)
        W_out = np.concat((W_sp,W_mp1,W_mp2,W_mp3,W_mp4,W_mp5),axis=0)
        wc_out = np.concat((wc_sp,wc_mp1,wc_mp2,wc_mp3,wc_mp4,wc_mp5),axis=0)
        wt_out = np.concat((wt_sp,wt_mp1,wt_mp2,wt_mp3,wt_mp4,wt_mp5),axis=0)
        wb_out = np.concat((wb_sp,wb_mp1,wb_mp2,wb_mp3,wb_mp4,wb_mp5),axis=0)
        
        return eid_out,pix_out,dip_out,W_out,wc_out,wt_out,wb_out

    def _clip_sequence_to_disp(self,E,SE,T,simulate_aftershocks):

        # Find the maximum slip based on creep rate
        max_slip = self.fault._slip_rate*T

        if type(self.fault)==DippingFault:
            # Sort by event id
            six = np.argsort(SE['Event_ID'])
            # Translate all ruptures into rotated coordinates
            bxp = SE['Bound_X'][six]*np.cos(np.radians(-self.fault._strike+90)) + SE['Bound_Y'][six]*np.sin(np.radians(-self.fault._strike+90))
            byp = -SE['Bound_X'][six]*np.sin(np.radians(-self.fault._strike+90)) + SE['Bound_Y'][six]*np.cos(np.radians(-self.fault._strike+90))
            # Extract upper left and lower right corners
            lxp = bxp[:,3]; lyp = byp[:,3]
            rxp = bxp[:,1]; ryp = byp[:,1]
            # Translate all fault points into rotated coordinates
            mx = self.fault._MX.ravel()
            my = self.fault._MY.ravel()
            xp = mx*np.cos(np.radians(-self.fault._strike+90)) + my*np.sin(np.radians(-self.fault._strike+90))
            yp = -mx*np.sin(np.radians(-self.fault._strike+90)) + my*np.cos(np.radians(-self.fault._strike+90))

            # Iterate through each rupture and assign displacements
            # Calculate running maximum sum
            D = np.zeros(xp.shape)
            D_cumsum = np.zeros(lxp.shape)
            for i in range(len(lxp)):
                D0 = np.zeros(xp.shape)
                idx = (xp>=lxp[i]) & (xp<=rxp[i]) & (yp<=lyp[i]) & (yp>=ryp[i])
                D0[idx]=SE['Displacement'][six][i]
                D += D0 
                D_cumsum[i]=np.max(D)

            # Find where the maximum cumulative displacement is just under the maximum slip
            # from creep
            didx = D_cumsum <= max_slip
            # Find the event ID where this occurs
            last_event = SE['Event_ID'][six][didx][-1]
            # Regenerate index based on event ID
            idx = E['Event_ID']<=last_event
            ridx = ~idx
        elif type(self.fault)==VerticalFault:
            # Sort by event id
            six = np.argsort(SE['Event_ID'])
            # Extract upper left and lower right 
            bx = SE['Bound_L']; by=SE['Bound_Y']
            lx = bx[:,3]; ly=by[:,3]
            rx = bx[:,1]; ry=by[:,1]
            # Extract fault points
            x = self.fault._FY.ravel()
            y = self.fault._FZ.ravel()

            # Iterate through each rupture and assign displacements
            # Calculate running maximum sum
            D = np.zeros(x.shape)
            D_cumsum = np.zeros(lx.shape)
            for i in range(len(lx)):
                D0 = np.zeros(x.shape)
                idx = (x>=lx[i]) & (x<=rx[i]) & (y<=ly[i]) & (y>=ry[i])
                D0[idx]=SE['Displacement'][six][i]
                D += D0 
                D_cumsum[i]=np.max(D)
            # Find where the maximum cumulative displacement is just under the maximum slip
            # from creep
            didx = D_cumsum <= max_slip
            # Find the event ID where this occurs
            last_event = SE['Event_ID'][six][didx][-1]
            # Regenerate index based on event ID
            idx = E['Event_ID']<=last_event
            ridx = ~idx

        # Remove and propagate
        event_remove = E['Event_ID'][ridx]
        sub_event_remove_idx = np.isin(SE['Event_ID'],event_remove)
        
        # Filter Events dictionary
        E['Event_ID'] = E['Event_ID'][idx]
        E['Length'] = E['Length'][idx]
        E['Width'] = E['Width'][idx]
        E['Area'] = E['Area'][idx]
        E['Displacement'] = E['Displacement'][idx]
        E['Moment'] = E['Moment'][idx]
        E['Magnitude'] = E['Magnitude'][idx]
        E['Center_X'] = E['Center_X'][idx]
        E['Center_Y'] = E['Center_Y'][idx]
        if simulate_aftershocks:
            E['Aftershock'] = E['Aftershock'][idx]
            E['Parent_ID'] = E['Parent_ID'][idx]
            E['Parent_Chain'] = [p for (p,remove) in zip(E['Parent_Chain'],ridx) if not remove]
            E['Aftershock_Order'] = E['Aftershock_Order'][idx]
            E['Time_Offset'] = E['Time_Offset'][idx]

        # Filter SubEvent Dictionary
        SE['Event_ID'] = SE['Event_ID'][~sub_event_remove_idx]
        SE['Length'] = SE['Length'][~sub_event_remove_idx]
        SE['Width'] = SE['Width'][~sub_event_remove_idx]
        SE['Displacement'] = SE['Displacement'][~sub_event_remove_idx]
        SE['Panel_IX'] = SE['Panel_IX'][~sub_event_remove_idx]
        if type(self.fault)==DippingFault:
            SE['Dip'] = SE['Dip'][~sub_event_remove_idx]
        elif type(self.fault)==VerticalFault:
            SE['Strike'] = SE['Strike'][~sub_event_remove_idx]
            SE['Center_L'] = SE['Center_L'][~sub_event_remove_idx]
            SE['Bound_Z'] = SE['Bound_Z'][~sub_event_remove_idx]
            SE['Bound_L'] = SE['Bound_L'][~sub_event_remove_idx]
        SE['Center_X'] = SE['Center_X'][~sub_event_remove_idx]
        SE['Center_Y'] = SE['Center_Y'][~sub_event_remove_idx]
        SE['Center_Z'] = SE['Center_Z'][~sub_event_remove_idx]            
        SE['Bound_X'] = SE['Bound_X'][~sub_event_remove_idx]
        SE['Bound_Y'] = SE['Bound_Y'][~sub_event_remove_idx]

        return E,SE


    def _clip_sequence_to_moment(self,E,SE,T,simulate_aftershocks):
        """
        Clips input earthquake catalog so that the total accumulated seismic moment
        of the sequence does not exceed the expected total accumulated moment
        given the fault slip rate and the area of the fault that can experience
        rupture.

        Parameters
        ----------
        E : dict
            Event dictionary output from _ruptures_on_fault.
        SE : dict
            SubEvent dictionary output from _ruptures_on_fault.
        T : int
            Length of simulation in years.
        simulate_aftershocks : boolean
            Flag to indicate whehter aftershocks were included.

        Returns
        -------
        E : dict
            Clipped version of the Event dictionary.
        SE : dict
            Clipped version of the SubEvent dictionary.

        """
        
        # Calculate total moment represented by sequence
        m0 = E['Moment'].copy()
        m0[np.isnan(m0)]=0
        M0_cumsum = np.cumsum(m0)
        
        # Generate 
        idx = M0_cumsum <= self.M0_total
        ridx = ~idx
        
        event_remove = E['Event_ID'][ridx]
        sub_event_remove_idx = np.isin(SE['Event_ID'],event_remove)
        
        # Filter Events dictionary
        E['Event_ID'] = E['Event_ID'][idx]
        E['Length'] = E['Length'][idx]
        E['Width'] = E['Width'][idx]
        E['Area'] = E['Area'][idx]
        E['Displacement'] = E['Displacement'][idx]
        E['Moment'] = E['Moment'][idx]
        E['Magnitude'] = E['Magnitude'][idx]
        E['Center_X'] = E['Center_X'][idx]
        E['Center_Y'] = E['Center_Y'][idx]
        if simulate_aftershocks:
            E['Aftershock'] = E['Aftershock'][idx]
            E['Parent_ID'] = E['Parent_ID'][idx]
            E['Parent_Chain'] = [p for (p,remove) in zip(E['Parent_Chain'],ridx) if not remove]
            E['Aftershock_Order'] = E['Aftershock_Order'][idx]
            E['Time_Offset'] = E['Time_Offset'][idx]

        # Filter SubEvent Dictionary
        SE['Event_ID'] = SE['Event_ID'][~sub_event_remove_idx]
        SE['Length'] = SE['Length'][~sub_event_remove_idx]
        SE['Width'] = SE['Width'][~sub_event_remove_idx]
        SE['Displacement'] = SE['Displacement'][~sub_event_remove_idx]
        SE['Panel_IX'] = SE['Panel_IX'][~sub_event_remove_idx]
        if type(self.fault)==DippingFault:
            SE['Dip'] = SE['Dip'][~sub_event_remove_idx]
        elif type(self.fault)==VerticalFault:
            SE['Strike'] = SE['Strike'][~sub_event_remove_idx]
            SE['Center_L'] = SE['Center_L'][~sub_event_remove_idx]
            SE['Bound_Z'] = SE['Bound_Z'][~sub_event_remove_idx]
            SE['Bound_L'] = SE['Bound_L'][~sub_event_remove_idx]
        SE['Center_X'] = SE['Center_X'][~sub_event_remove_idx]
        SE['Center_Y'] = SE['Center_Y'][~sub_event_remove_idx]
        SE['Center_Z'] = SE['Center_Z'][~sub_event_remove_idx]            
        SE['Bound_X'] = SE['Bound_X'][~sub_event_remove_idx]
        SE['Bound_Y'] = SE['Bound_Y'][~sub_event_remove_idx]
        
        return E,SE
        
    ## Generators
    def generate_fixed_max_mag_eq_sequence(self,T,dt,seed=1,constant_recurrence=True,stay_on_fault=True,rupture_interseismic=False,verbose=True,
                                            simulate_aftershocks=False,Mw_min=4,b_d = 1,delta_m_star = 1.25, c = 0.1, p = 1.25,d = 4,
                                            q = 1.35):
        """
        Method for generating an earthquake sequence where every earthquake 
        that occurs will represent the maximum earthquake allowable by 
        the coseismic portion of the fault.

        Parameters
        ----------
        T : int
            Total model time. (yrs)
        dt : int
            Time step for the model that will use the earthquake sequence.
        seed : int, optional
            Seed for the random number generation within the sequence
            generator, provided for reproducibility. The default is 1.
        constant_recurrence : boolean, optional
            Indicates whether recurrence interval between the earthquakes
            should be exactly the same if True. If set to false, recurrence
            interval will be Poissonian. The default is True.
        stay_on_fault : Boolean, optional
            If True, ruptures cannot extend beyond the boundaries of the fault. 
            If False, ruptures will nucleate on fault, but can extend beyond the 
            dimensions of the fault. Parameter is ignored unless 'simulate_aftershocks'
            is set to True. The default is True, but is effectively false if aftershocks
            are not turned on.
        rupture_interseismic : Boolean, optional
            If True, ruptures can extend onto interseismic portion, but can still only 
            nuclear in seismogenic zone. If False, ruptures cannot break the 
            portion of the fault below the seismogenic zone. This parameter only applies to
            aftershocks for repating max ruptures. The default is False.
        verbose : Boolean, optional
            Flag to print out progress in generating the earthquake sequence. If model time
            is long, can be useful as this process can be lengthy. The default is True.
        simulate_aftershocks : Boolean, optional
            Flag to simulate aftershocks using BASS algorithm from Turcotte et al., 2007.
            The default is False.
        Mw_min : float, optional
            Magnitude of minimum earthquake to generate in an aftershock sequence. Parameter is
            only used if 'simulate_aftershocks' is True.
            The default value is 4.0
        b_d : float, optional
            The b sub d parameter in the modified Bath's law, see Turcotte et al., 2007 for 
            more discussion. Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.
        delta_m_star : float, optional
            The delta m star parameter in the modified Bath's law, see Turcotte et al., 2007
            for more details. Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.25.
        c : float, optional
            The c parameter in Omori's law, see Turcotte et al., 2007 for more details.
            Paramater is only used if 'simulate_aftershocks' is True.
            The default is 0.1.
        p : float, optional
            The p parameter in Omori's law, see Turcotte et al., 2007 for more details.
            Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.25.
        d : float, optional
            The d parameter in the spatial Omori's law, see Turcotte et al., 2007 
            for more detail. Paramater is only used if 'simulate_aftershocks' is True. 
            The default is 4.
        q : float, optional
            The q parameter in the spatial Omori's law, see Turcotte et al., 2007
            for more detail. Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.35.

        Returns
        -------
        None.

        """

        # The AdvectionSolverTVD does not enforce stability checks, so
        # this is a crude fix such that it calculates the maximum timestep 
        # that should be stable given the grid size and the horizontal 
        # component of the maximum displacement of any single event where
        # the max allowable timestep is dt = dx/displacement. Raises
        # a value error if the dt is too long.

        # Find total displacement for largest earthquake
        M0 = self.fault_M0_max
        _,_,_,D,_ = _leonard14_scaling(self.fault._fault_type,M0=M0)

        # Determine the horizontal (strike-slip) component of the displacement
        horz_part = self.fault._ss[0] / (self.fault._ss[0] + self.fault._ds[0])
        horz_d = np.abs(D * horz_part)

        # Check if the input timestep is likely to run into stability problems
        if horz_d>0:
            if type(self.grid)==RasterModelGrid:
                dt_max = self.grid.dx/horz_d 
            elif type(self.grid)==HexModelGrid:
                dt_max = self.grid.spacing/horz_d 

            if dt >= dt_max:
                raise ValueError('Input dt is too long for the maximum expected horizontal displacement of a single event to keep AdvectionSolverTVD stable, reduce the timestep.')        
        
        # Store sequence input parameters
        self.eq_sequence_params = {'Type':'fixed_max',
                                   'T':T,
                                   'dt':dt,
                                   'seed':seed,
                                   'constant_recurrence':constant_recurrence,
                                   'stay_on_fault':stay_on_fault,
                                   'rupture_interseismic':rupture_interseismic,
                                   'simulate_aftershocks':simulate_aftershocks,
                                   'Mw_min':Mw_min,
                                   'b_d':b_d,
                                   'delta_m_star':delta_m_star,
                                   'c':c,
                                   'p':p,
                                   'd':d,
                                   'q':q
                                   } 
        
        ###################################################
        # Generate magnitudes of Earthquakes within sequence
        
        # Define event size
        Mw_char = self.fault_Mw_max
        M0_char = _eq_magnitude_to_moment(Mw_char)
        
        # Calculate total seismic moment that should be accommodated over duration of sequence
        L,W,A,D,_ = _leonard14_scaling(self.fault._fault_type,M0=M0_char)
        self.M0_total = A * self.fault._mu * self.fault._mean_slip_rate * T * self._moment_fraction
        
        # Determine the number of repeating max earthquakes to more of the moment (sequence will be clipped later)
        num_events = np.ceil(self.M0_total/M0_char).astype(int)
        M0 = np.full(num_events,M0_char)
        Mw = np.full(num_events,Mw_char)  
        
        if simulate_aftershocks:
            if verbose:
                print('Beginning aftershock generation')
            Mw,M0,t_offset,rad,parent = _aftershocks(Mw,M0,Mw_min,self.fault_Mw_max,seed,
                                                          b_d,delta_m_star,c,p,d,q)
            
        if verbose:
            print('Step 1 of 4: Generation of earthquake moments within sequence completed')        
        
        ################################################################################ 
        # Extrapolate rupture details for each earthquake based on scalar seismic moment
        # and randomly place on fault plane
        
        if simulate_aftershocks:
            L,W,A,D,_ = _leonard14_scaling(self.fault._fault_type,M0=M0)
            
            # Map ruptures onto the fault
            if type(self.fault)==DippingFault:
                E,SubEvents,num_afs_orders = self._ruptures_on_fault_af(L,W,A,D,M0,Mw,Mw_min,verbose,seed=seed,stay_on_fault=stay_on_fault,
                                                         rupture_interseismic=rupture_interseismic,
                                                         is_fixed_max=True,
                                                         t_offset=t_offset,rad=rad,parent=parent)
            elif type(self.fault)==VerticalFault:
                E,SubEvents,num_afs_orders = self._ruptures_on_vert_fault_af(L,W,A,D,M0,Mw,Mw_min,verbose,seed=seed,stay_on_fault=True,
                                                           rupture_interseismic=rupture_interseismic,is_fixed_max=True,
                                                           t_offset=t_offset,rad=rad,parent=parent)
            
        else:
            L = np.full(num_events,L)
            W = np.full(num_events,W)
            A = np.full(num_events,A)
            D = np.full(num_events,D)
            
            # Map ruptures onto the fault
            if type(self.fault)==DippingFault:
                E,SubEvents = self._ruptures_on_fault(L,W,A,D,M0,Mw,verbose,seed=seed,stay_on_fault=True,
                                                       rupture_interseismic=False,is_fixed_max=True)
            elif type(self.fault)==VerticalFault:
                E,SubEvents = self._ruptures_on_vert_fault(L,W,A,D,M0,Mw,verbose,seed=seed,stay_on_fault=True,
                                                           rupture_interseismic=False,is_fixed_max=True)
            
        if verbose:
            print('Step 2 of 4: Calculation of rupture dimensions and locations completed')
            
        #######################################
        # Clip the sequence
        if self._clip_to=='moment':
            [E,SubEvents] = self._clip_sequence_to_moment(E,SubEvents,T,simulate_aftershocks)
        elif self._clip_to=='displacement':
            [E,SubEvents] = self._clip_sequence_to_disp(E,SubEvents,T,simulate_aftershocks)
        # Reset number of events
        if simulate_aftershocks:
            num_events = np.sum(E['Time_Offset']==-1)
        else:
            num_events = len(E['Magnitude'])
        
        if verbose:
            print('Step 3 of 4: Sequence clipped')
        
        
        #####################################
        # Assign times to events
        if constant_recurrence:
            t_r = T/num_events
            t_r = np.full(num_events,t_r)
            t_of_e = np.cumsum(t_r)-1 # Shift by one year to avoid right edge
        else:
            # Poisson distribution of events
            rng = np.random.default_rng(seed=seed)
            t_of_e = rng.uniform(low=0,high=T,size=num_events)
            # Sort
            t_of_e = np.sort(t_of_e)
            a_t_r = np.diff(t_of_e)
            t_r = np.append(a_t_r,np.mean(a_t_r))
            
        # Propogate time offsets and sort by time
        if simulate_aftershocks:
            t_of_all_e = np.zeros(len(E['Event_ID']))
            parent_event = E['Time_Offset']==-1
            t_of_all_e[parent_event] = t_of_e
            
            
            for i in range(num_afs_orders-1):
                parent_idx = E['Aftershock_Order']==i
                children_idx = E['Aftershock_Order']==i+1
                for j in range(np.sum(parent_idx)):
                    parentOI_ix = E['Event_ID'][parent_idx][j]
                    childrenOI_ix = E['Event_ID'][np.logical_and(children_idx,E['Parent_ID']==parentOI_ix)]
                    t_of_all_e[childrenOI_ix] = t_of_all_e[parentOI_ix] + E['Time_Offset'][childrenOI_ix]
            
            sidx = np.argsort(t_of_all_e)
            t_of_e = t_of_all_e[sidx]
            
            E['Event_ID'] = E['Event_ID'][sidx]
            E['Length'] = E['Length'][sidx]
            E['Width'] = E['Width'][sidx]
            E['Area'] = E['Area'][sidx]
            E['Displacement'] = E['Displacement'][sidx]
            E['Moment'] = E['Moment'][sidx]
            E['Magnitude'] = E['Magnitude'][sidx]
            E['Center_X'] = E['Center_X'][sidx]
            E['Center_Y'] = E['Center_Y'][sidx]
            E['Aftershock'] = E['Aftershock'][sidx]
            E['Parent_ID'] = E['Parent_ID'][sidx]
            E['Parent_Chain'] = [E['Parent_Chain'][i] for i in sidx]
            E['Aftershock_Order'] = E['Aftershock_Order'][sidx]
            E['Time_Offset'] = E['Time_Offset'][sidx]
            
            
        # Calculate recurrence intervals
        if simulate_aftershocks:    
            # Estimate recurrence interval of earthquake by magnitude bins
            mag_bins = np.arange(Mw_min,self.fault_Mw_max+0.1,0.1)
            
            mag_ix = np.digitize(E['Magnitude'],mag_bins)-1
            t_r = np.zeros(E['Magnitude'].shape)
            for i in range(len(mag_bins)-1):
                idx = mag_ix==i
                a_t_r = np.diff(t_of_e[idx])
                if a_t_r.shape[0]>0:
                    a_t_r = np.append(a_t_r,np.mean(a_t_r))
                    t_r[idx]=a_t_r
            # Recurrence time of 0 implies a single event, set recurrence time of these to the duration of the record
            # where true recurrence time would likely be longer
            t_r[np.isclose(t_r,0)]=T 

        
        # Generate a dictionary with times and append output dictionary
        Events = {'Cumulative_Time':t_of_e,
                  'Event_Return_Time':t_r,
                  'Number_SubEvents':np.bincount(SubEvents['Event_ID'])}
        Events.update(E)
        
        self.Events = Events
        self.SubEvents = SubEvents
        
        # Generate bin edges that stretch across whole time domain at the step of dt
        time_bins=np.arange(0,T+dt,dt)
        # Find index of time bin for each event (subtract 1 to convert to index)
        time_ix=np.digitize(t_of_e,time_bins,right=True)-1
        # Count events in each bin
        num_bins=len(time_bins)-1
        event_per_dt=np.bincount(time_ix,minlength=num_bins)
        
        # Store counter and time details for use within run_one_step()
        self.model_time = T
        self.dt = dt
        self.time_bins = time_bins
        self.current_model_time = 0
        self.time_ix = time_ix
        self.event_per_dt = event_per_dt 
        
        if verbose:
            print('Step 4 of 4: Calculation of time of events completed')

        # Final stability check to see if the max of the summed horizontal components of displacements 
        # in any timestep would lead to stability issues in AdvectionSolverTVD. This is overly conservative
        # in that it does not check whether the dislocations necessarily overlap and does not consider what
        # the actual displacement at the surface would be, so the reported maximum timestep is not necessarily
        # a hard limit, but it does inform the user that there could be problems if all ruptures were shallow and
        # overlapped
        #
        # Sum displacements in each timestep
        disp = Events['Displacement']
        summed_disp = np.bincount(time_ix,weights=disp)
        max_horz_disp = np.max(np.abs(summed_disp))*horz_part

        if max_horz_disp>0:
            if type(self.grid)==RasterModelGrid:
                dt_max = self.grid.dx/max_horz_disp 
            elif type(self.grid)==HexModelGrid:
                dt_max = self.grid.spacing/max_horz_disp 

            if dt >= dt_max:
                str = f'Maximum possible horizontal displacement in a time step exceeds stability criteria for advection, consider reducing the timestep to be equal or less than {np.floor(dt_max):.0f}'
                warnings.resetwarnings()
                warnings.warn(str,UserWarning)
    
    
    def generate_fixed_mag_eq_sequence(self,T,dt,Mw_event,seed=1,annual_rate_dist='Poisson',rate_variance_mag=5,
                                       stay_on_fault=True,rupture_interseismic=False,center_loc='Uniform',verbose=True,
                                       simulate_aftershocks=False,Mw_min=4,b_d = 1,delta_m_star = 1.25, c = 0.1, p = 1.25,d = 4,
                                       q = 1.35):
        """
        Method for generating an earthquake sequence where every
        earthquake that occurs will have a fixed magnitude based on the provided
        event moment magnitude (Mw_event), that will be randomly placed on 
        the fault.

        Parameters
        ----------
        T : int
            Total model time. (yrs)
        dt : int
            Time step for the model that will use the earthquake sequence.
        Mw_event : float
            Moment magntude of the size of the repeating event. If this magnitude
            exceeds the maximum magnitude that can be hosted on the fault, then 
            a warning will appear but the sequence will still be generated. In this
            event, if 'stay_on_fault' is True, then earthquake magnitudes will generally
            be trimmed to stay below the maximum magnitude, but the assumption of 
            complete moment release will be violated.
        seed : int, optional
            Seed for the random number generation within the sequence
            generator, provided for reproducibility. The default is 1.
        annual_rate_dist : str, optional
            Assumed statistical model for the variation of the annual earthquake rate.
            Valid inputs are 'Poisson' or 'NegativeBinomial'. Setting this
            parameter to 'NegativeBinomial' will result in more clustering of 
            earthquakes in time. The default is 'Poisson'.
        rate_variance_mag : float, optional
            Parameter that functions as multiplicative value for how much larger
            the variance of the annual earthquake rate is compared to the mean. This 
            parameter is only used if 'annual_rate_dist' is set to 'NegativeBinomial'.
            Setting this parameter to 1 will generate a result that is equivalent to 
            a Poisson distribution. Value cannot be below 1. The default is 5.
        stay_on_fault : Boolean, optional
            If True, ruptures cannot extend beyond the boundaries of the fault. 
            If False, ruptures will nucleate on fault, but can extend beyond the 
            dimensions of the fault. The default is True.
        rupture_interseismic : Boolean, optional
            If True, ruptures can extend onto interseismic portion, but can still only 
            nuclear in seismogenic zone. If False, ruptures cannot break the 
            portion of the fault below the seismogenic zone. The default is False.
        center_loc : str, optional
            Parameter that describes the sampling space for rupture centers along the
            strike of fault. If set to 'Uniform', effectively a boxcar probability 
            for rupture centers along strike, but will be trimmed inward if 'stay_on_fault'
            is set to True. Alternatively, if set to 'Gaussian', the probability of 
            rupture centers being located near the center of the fault will be higher.
            The default is 'Uniform'.
        verbose : Boolean, optional
            Flag to print out progress in generating the earthquake sequence. If model time
            is long, can be useful as this process can be lengthy. The default is True.
        simulate_aftershocks : Boolean, optional
            Flag to simulate aftershocks using BASS algorithm from Turcotte et al., 2007.
            The default is False.
        Mw_min : float, optional
            Magnitude of minimum earthquake to generate in an aftershock sequence. Parameter is
            only used if 'simulate_aftershocks' is True.
            The default value is 4.0
        b_d : float, optional
            The b sub d parameter in the modified Bath's law, see Turcotte et al., 2007 for 
            more discussion. Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.
        delta_m_star : float, optional
            The delta m star parameter in the modified Bath's law, see Turcotte et al., 2007
            for more details. Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.25.
        c : float, optional
            The c parameter in Omori's law, see Turcotte et al., 2007 for more details.
            Paramater is only used if 'simulate_aftershocks' is True.
            The default is 0.1.
        p : float, optional
            The p parameter in Omori's law, see Turcotte et al., 2007 for more details.
            Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.25.
        d : float, optional
            The d parameter in the spatial Omori's law, see Turcotte et al., 2007 
            for more detail. Paramater is only used if 'simulate_aftershocks' is True. 
            The default is 4.
        q : float, optional
            The q parameter in the spatial Omori's law, see Turcotte et al., 2007
            for more detail. Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.35.

        Returns
        -------
        None.

        """

        # The AdvectionSolverTVD does not enforce stability checks, so
        # this is a crude fix such that it calculates the maximum timestep 
        # that should be stable given the grid size and the horizontal 
        # component of the maximum displacement of any single event where
        # the max allowable timestep is dt = dx/displacement. Raises
        # a value error if the dt is too long.
        # 
        # This still uses the maximum earthquake in case this generator
        # is used in concert with the aftershock module as that could still
        # produce earthquakes that are the maximum supported by the fault.

        # Find total displacement for largest earthquake
        M0 = self.fault_M0_max
        _,_,_,D,_ = _leonard14_scaling(self.fault._fault_type,M0=M0)

        # Determine the horizontal (strike-slip) component of the displacement
        horz_part = self.fault._ss[0] / (self.fault._ss[0] + self.fault._ds[0])
        horz_d = np.abs(D * horz_part)

        # Check if the input timestep is likely to run into stability problems
        if horz_d>0:
            if type(self.grid)==RasterModelGrid:
                dt_max = self.grid.dx/horz_d 
            elif type(self.grid)==HexModelGrid:
                dt_max = self.grid.spacing/horz_d 

            if dt >= dt_max:
                raise ValueError('Input dt is too long for the maximum expected horizontal displacement of a single event to keep AdvectionSolverTVD stable, reduce the timestep.')        
                
        
        # Store sequence input parameters
        self.eq_sequence_params = {'Type':'fixed',
                                   'T':T,
                                   'dt':dt,
                                   'Mw_event':Mw_event,
                                   'seed':seed,
                                   'annual_rate_dist':annual_rate_dist,
                                   'rate_variance_mag':rate_variance_mag,
                                   'stay_on_fault':stay_on_fault,
                                   'rupture_interseismic':rupture_interseismic,
                                   'center_loc':center_loc,
                                   'verbose':verbose,
                                   'simulate_aftershocks':simulate_aftershocks,
                                   'Mw_min':Mw_min,
                                   'b_d':b_d,
                                   'delta_m_star':delta_m_star,
                                   'c':c,
                                   'p':p,
                                   'd':d,
                                   'q':q
                                   }
        
        ###################################################
        # Generate magnitudes of Earthquakes within sequence
        if Mw_event>self.fault_Mw_max:
            print('Warning: Provided Mw for the repeating event is greater than what can be phyiscally allowed for ruptures that stay on the fault')

        M0_event = _eq_magnitude_to_moment(Mw_event)
            
        # Calculate total seismic moment that should be accommodated over duration of sequence
        self.M0_total = self.fault._total_area * self.fault._mu * self.fault._mean_slip_rate * T * self._moment_fraction
        
        # Determine the number of repeating earthquakes to accommodate nearly all total moment and event rate
        num_events = np.floor(self.M0_total/M0_event).astype(int)
        mean_epa = num_events/T
        M0 = np.full(num_events,M0_event)
        Mw = np.full(num_events,Mw_event)
        
        if simulate_aftershocks:
            if verbose:
                print('Beginning aftershock generation')
            Mw,M0,t_offset,rad,parent = _aftershocks(Mw,M0,Mw_min,self.fault_Mw_max,seed,
                                                          b_d,delta_m_star,c,p,d,q)
            
        if verbose:
            print('Step 1 of 4: Generation of earthquake moments within sequence completed')
         
            
        ################################################################################ 
        # Extrapolate rupture details for each earthquake based on scalar seismic moment
        # and randomly place on fault plane
        
        if simulate_aftershocks:
            L,W,A,D,_ = _leonard14_scaling(self.fault._fault_type,M0=M0)
            
            # Map ruptures onto the fault
            if type(self.fault)==DippingFault:
                E,SubEvents,num_afs_orders = self._ruptures_on_fault_af(L,W,A,D,M0,Mw,Mw_min,verbose,seed=seed,stay_on_fault=stay_on_fault,
                                                         rupture_interseismic=rupture_interseismic,
                                                         center_loc=center_loc,is_fixed_max=False,
                                                         t_offset=t_offset,rad=rad,parent=parent)
            elif type(self.fault)==VerticalFault:
                E,SubEvents,num_afs_orders = self._ruptures_on_vert_fault_af(L,W,A,D,M0,Mw,Mw_min,verbose,seed=seed,stay_on_fault=stay_on_fault,
                                                           rupture_interseismic=rupture_interseismic,
                                                           center_loc=center_loc,is_fixed_max=False,
                                                           t_offset=t_offset,rad=rad,parent=parent)
                
            
        else:
            L,W,A,D,_ = _leonard14_scaling(self.fault._fault_type,M0=M0_event)
            L = np.full(num_events,L)
            W = np.full(num_events,W)
            A = np.full(num_events,A)
            D = np.full(num_events,D)
            
            # Map ruptures onto the fault
            if type(self.fault)==DippingFault:
                E,SubEvents = self._ruptures_on_fault(L,W,A,D,M0,Mw,verbose,seed=seed,stay_on_fault=stay_on_fault,
                                                       rupture_interseismic=rupture_interseismic,
                                                       center_loc=center_loc,is_fixed_max=False)
            elif type(self.fault)==VerticalFault:
                E,SubEvents = self._ruptures_on_vert_fault(L,W,A,D,M0,Mw,verbose,seed=seed,stay_on_fault=stay_on_fault,
                                                           rupture_interseismic=rupture_interseismic,
                                                           center_loc=center_loc,is_fixed_max=False)
            
        
        if verbose:
            print('Step 2 of 4: Calculation of rupture dimensions and locations completed')            
         
            
        #######################################
        # Clip the sequence
        if self._clip_to=='moment':
            [E,SubEvents] = self._clip_sequence_to_moment(E,SubEvents,T,simulate_aftershocks)
        elif self._clip_to=='displacement':
            [E,SubEvents] = self._clip_sequence_to_disp(E,SubEvents,T,simulate_aftershocks)
        
        if verbose:
            print('Step 3 of 4: Sequence clipped')
         
           
        #####################################
        # Assign times to events
        if simulate_aftershocks:
            num_events = np.sum(E['Time_Offset']==-1)
            
        if annual_rate_dist == 'Poisson':
            # Generate time of events through uniform sampling of an underlying time vector
            # This produces a result that is equivalent to a poisson distribution of 
            # annual rates
            rng = np.random.default_rng(seed=seed)
            t_of_e = rng.uniform(low=0,high=T,size=num_events)
            # Sort
            t_of_e = np.sort(t_of_e)
    
            # Bin by single years to consider event rate / year
            t_bin = np.arange(0,T+1,1)
            tix = np.digitize(t_of_e,t_bin)-1 # Minus 1 so membership in the first bin has an index of 0
            epa = np.bincount(tix,minlength=len(t_bin)-1) # Events per year
        elif annual_rate_dist == 'NegativeBinomial':
            if rate_variance_mag < 1:
                rate_variance_mag = 1
                print('Warning: rate_variance_mag cannot be below 1, setting to 1 which will produce a Poisson distribution')
            # Negative binomial sampling of the time vector for events
            #
            # This follows suggestions that non-declustered catalogs (i.e., those for which aftershocks have not been removed)
            # should have a distribution of annual occurence rates that follows a negative binomial distribution 
            # (e.g. Kagan & Jackson, 2000, GJI). Choosing this option will produce a more "clustered" time 
            # series of earthquakes, but makes no attempts to assure that periods with higher annual rates include a large 
            # magnitude earthquake, so this is not formally considering aftershock sequences.
            #
            # To establish parameters for the negative binomial distribution, this uses the implied mean rate from the long time series
            # such that mean rate = total number of events / total time. It then takes a parameter 'rate_variance_mag' which is
            # interpreted as how much larger the variance of the annual rate is compared to the mean. If the variance equals the mean
            # then the negative binomial will produce a poisson distribution. Variances less than the mean will produce errors.
            #
            # Assert variance in terms of how much larger it is than mean
            nu = 1 / rate_variance_mag # Equivalent to mean / variance where variance = mean * rate_variance_mag
            tau = mean_epa / ((1-nu)/nu)
            
            # Generate a long sequence of event rates based on the negative binomial parameters
            # Using the number of events as the length *should* be sufficient as compared to the poisson,
            # as the nature of the distribution is such that this will generate more years with higher than average rates
            #
            # For short time series and depending on seed, this may fail because the total number of entries will exceed the 
            # number of years so set up an iterative behavior where the seed is varied until a valid sequence is found
            num_epa = T+1
            nseed = seed
            while num_epa > T:
                rng = np.random.default_rng(seed=nseed)
                epa = rng.negative_binomial(tau,nu,size=num_events*2).astype(int) # Force these to be integers
                # Set any negative events to zeros
                epa[epa<0] = 0
                # Trim such that the sum of the number of events approximates the total number of events
                epa = epa[np.cumsum(epa)<=num_events]
                # Append the remainder so that summed number of events will equal total number of events
                epa = np.append(epa,num_events-np.sum(epa)).astype(int)
                
                num_epa = epa.shape[0]
                nseed += 1

           
            # Pad with zeros so that there is a earthquake rate per year for full duration and then shuffle
            epa = np.pad(epa, (0,T - epa.shape[0]),'constant',constant_values=(0,0))
            rng.shuffle(epa)
            # Iterate through by year and generate a time of event vector
            t_of_e=[]
            for i in range(T):
                if epa[i]>0:
                    t_of_e.append(i+rng.uniform(low=0,high=1,size=epa[i]))
            t_of_e = np.concat(t_of_e,axis=0)
            # Sort
            t_of_e = np.sort(t_of_e) 
            
        # Propogate time offsets and sort by time
        if simulate_aftershocks:
            t_of_all_e = np.zeros(len(E['Event_ID']))
            parent_event = E['Time_Offset']==-1
            t_of_all_e[parent_event] = t_of_e
            
            for i in range(num_afs_orders-1):
                parent_idx = E['Aftershock_Order']==i
                children_idx = E['Aftershock_Order']==i+1
                for j in range(np.sum(parent_idx)):
                    parentOI_ix = E['Event_ID'][parent_idx][j]
                    childrenOI_ix = E['Event_ID'][np.logical_and(children_idx,E['Parent_ID']==parentOI_ix)]
                    t_of_all_e[childrenOI_ix] = t_of_all_e[parentOI_ix] + E['Time_Offset'][childrenOI_ix]
            
            sidx = np.argsort(t_of_all_e)
            t_of_e = t_of_all_e[sidx]
            
            E['Event_ID'] = E['Event_ID'][sidx]
            E['Length'] = E['Length'][sidx]
            E['Width'] = E['Width'][sidx]
            E['Area'] = E['Area'][sidx]
            E['Displacement'] = E['Displacement'][sidx]
            E['Moment'] = E['Moment'][sidx]
            E['Magnitude'] = E['Magnitude'][sidx]
            E['Center_X'] = E['Center_X'][sidx]
            E['Center_Y'] = E['Center_Y'][sidx]
            E['Aftershock'] = E['Aftershock'][sidx]
            E['Parent_ID'] = E['Parent_ID'][sidx]
            E['Parent_Chain'] = [E['Parent_Chain'][i] for i in sidx]
            E['Aftershock_Order'] = E['Aftershock_Order'][sidx]
            E['Time_Offset'] = E['Time_Offset'][sidx]
            
            
        # Calculate recurrence intervals
        if simulate_aftershocks:    
            # Estimate recurrence interval of earthquake by magnitude bins
            mag_bins = np.arange(Mw_min,self.fault_Mw_max+0.1,0.1)
            
            mag_ix = np.digitize(E['Magnitude'],mag_bins)-1
            t_r = np.zeros(E['Magnitude'].shape)
            for i in range(len(mag_bins)-1):
                idx = mag_ix==i
                a_t_r = np.diff(t_of_e[idx])
                if a_t_r.shape[0]>0:
                    a_t_r = np.append(a_t_r,np.mean(a_t_r))
                    t_r[idx]=a_t_r
            # Recurrence time of 0 implies a single event, set recurrence time of these to the duration of the record
            # where true recurrence time would likely be longer
            t_r[np.isclose(t_r,0)]=T 
        else:
            a_t_r = np.diff(t_of_e)
            t_r = np.append(a_t_r,np.mean(a_t_r))
            

        # Generate a dictionary with times and append output dictionary
        Events = {'Cumulative_Time':t_of_e,
                  'Event_Return_Time':t_r,
                  'Number_SubEvents':np.bincount(SubEvents['Event_ID'])}
        Events.update(E)
        
        self.Events = Events
        self.SubEvents = SubEvents
    
        # Generate bin edges that stretch across whole time domain at the step of dt
        time_bins=np.arange(0,T+dt,dt)
        # Find index of time bin for each event (subtract 1 to convert to index)
        time_ix=np.digitize(t_of_e,time_bins,right=True)-1
        # Count events in each bin
        num_bins=len(time_bins)-1
        event_per_dt=np.bincount(time_ix,minlength=num_bins)
        
        # Store counter and time details for use within run_one_step()
        self.model_time = T
        self.dt = dt
        self.time_bins = time_bins
        self.current_model_time = 0
        self.time_ix = time_ix
        self.event_per_dt = event_per_dt
        
        if verbose:
            print('Step 4 of 4: Calculation of time of events completed')

        # Final stability check to see if the max of the summed horizontal components of displacements 
        # in any timestep would lead to stability issues in AdvectionSolverTVD. This is overly conservative
        # in that it does not check whether the dislocations necessarily overlap and does not consider what
        # the actual displacement at the surface would be, so the reported maximum timestep is not necessarily
        # a hard limit, but it does inform the user that there could be problems if all ruptures were shallow and
        # overlapped
        #
        # Sum displacements in each timestep
        disp = Events['Displacement']
        summed_disp = np.bincount(time_ix,weights=disp)
        max_horz_disp = np.max(np.abs(summed_disp))*horz_part

        if max_horz_disp>0:
            if type(self.grid)==RasterModelGrid:
                dt_max = self.grid.dx/max_horz_disp 
            elif type(self.grid)==HexModelGrid:
                dt_max = self.grid.spacing/max_horz_disp 

            if dt >= dt_max:
                str = f'Maximum possible horizontal displacement in a time step exceeds stability criteria for advection, consider reducing the timestep to be equal or less than {np.floor(dt_max):.0f}'
                warnings.resetwarnings()
                warnings.warn(str,UserWarning)

    def generate_variable_mag_eq_sequence(self,T,dt,num_events=10000,seed=1,freq_moment_dist='TrPR',
                                        Mw_min=4.0,Mw_max=None,Mw_cm=None,Mw_x=None,Mw_c=None,beta=2/3,over_max='remove',
                                        fill_method='repeat',annual_rate_dist='Poisson',rate_variance_mag=5,
                                        stay_on_fault=True,rupture_interseismic=False,center_loc='Uniform',verbose=True,
                                        simulate_aftershocks=False,b_d = 1,delta_m_star = 1.25, 
                                        c = 0.1, p = 1.25,d = 4,q = 1.35):
        """
        Method for generating a pseudo-random earthquake sequence where earthquake 
        magnitudes will vary between a provided minimum (Mw_min) and
        maximum (Mw_max) magnitude and where the distribution of event sizes
        will approximate a realistic frequency-moment relationship. Earthquakes
        will be randomly placed on the fault and in time.

        Parameters
        ----------
        T : int
            Total model time. (yrs)
        dt : int
            Time step for the model that will use the earthquake sequence.
        num_events : int, optional
            Original number of events to sample. The default is 10000.
        seed : int, optional
            Seed for the random number generation within the sequence
            generator, provided for reproducibility. The default is 1.
        freq_moment_dist : str, optional
            Frequency - moment relationship used to generate earthquakes. The
            options are:
            'Char' - Characteristic distribution
            'TrPR' - Truncated Pareto distribution 
            'TGR' - Tapered Pareto distribution
            'Gamma' - Modified Gamma distribution. 
            These are mathematically defined and discussed in Kagan, 2002, 
            doi: 10.1046/j.1365-246x.2002.01594.x. Ultimately, for moment magnitudes
            below ~8.2, the majority of the distributions are similar and the truncated
            Pareto (the default) is preferred as it will prevent generation of earthquakes
            above the maximum magnitude (which will be removed from the catalog). If dealing
            with a large fault where magnitude > ~8.2 are allowable, either the Tapered Pareto
            or Gamma would be more appropriate choices. The default is 'TrPR'.
        Mw_min : float, optional
            Minimum moment magntiude for the distributions. In general, no earthquakes 
            smaller than this minimum magnitude will be included in the earthquake catalog.
            If 'simulate_aftershocks' is set to True, this will also be used as the minimum
            cutoff for generated aftershocks.
            The default is 4.0.
        Mw_max : float, optional
            Maximum moment magnitude allowable in the catalog, but not a formal 
            input to any of the frequency-moment distributions. If 'None' is provided,
            this will default to the maximum allowable magnitude on the fault.
            The default is None.
        Mw_cm : float, optional
            Corner moment magnitude, which for both the Tapered Pareto and Gamma
            distributions controls the form of the relationship at high magnitudes. If
            set to 'None', it will default to the recommended corner magnitude as defined
            in Kagan, 2002 for the respective distributions. The default is None.
        Mw_x : float, optional
            Magnitude above which the distribution is truncated if using the Truncated 
            Pareto distribution. If set to 'None', this value defaults to the maximum magnitude 
            allowable on the fault.
            The default is None.
        Mw_c : float, optional
            Magnitude above which the distribution is truncated if using the Characteristic 
            distribution. If set to 'None', this value defaults to the maximum magnitude
            allowable on the fault.
            The default is none.
        beta : float, optional
            Shape parameter for the frequency-moment distributions. For all distributions,
            the default is 2/3, which is close to the accepted value in Kagan, 2002 
            for all frequency-moment relationships. The default is 2/3.
        over_max : str, optional
            Method for how randomly selected earthquakes that exceed the maximum allowable
            moment for the provided fault are dealt with. If set to 'remove', then any event
            that exceeds the maximum is removed from the catalog. If set to 'reset', then any
            event that exceeds the maximum is reset to be equal to the maximum allowable. 
            The default is 'remove'. 
        fill_method : str, optional
            Method for how the sequence should be "filled" to extend across the entire
            model time and such that the total moment is nearly accommodated. The 
            valid options are 'repeat' and 'new'. If set to 'repeat', the exact sequence
            generated, containing the number of events specified in 'num_events', will be
            repeated until the total moment is reached. Locations and occurrence times will
            still vary randomly for all events, only the magnitudes will be repeated. If set
            to 'new', then new sequences, 'num_events' long, will be generated where the 
            seed value is incremented by one each time, until the total moment is approximately 
            reached. Setting the parameter to 'new' will take significantly longer
            than 'repeat'. The default is 'repeat'.
        annual_rate_dist : str, optional
            Assumed statistical model for the variation of the annual earthquake rate.
            Valid inputs are 'Poisson' or 'NegativeBinomial'. Setting this
            parameter to 'NegativeBinomial' will result in more clustering of 
            earthquakes in time. The default is 'Poisson'.
        rate_variance_mag : float, optional
            Parameter that functions as multiplicative value for how much larger
            the variance of the annual earthquake rate is compared to the mean. This 
            parameter is only used if 'annual_rate_dist' is set to 'NegativeBinomial'.
            Setting this parameter to 1 will generate a result that is equivalent to 
            a Poisson distribution. Value cannot be below 1. The default is 5.
        stay_on_fault : Boolean, optional
            If True, ruptures cannot extend beyond the boundaries of the fault. 
            If False, ruptures will nucleate on fault, but can extend beyond the 
            dimensions of the fault. The default is True.
        rupture_interseismic : Boolean, optional
            If True, ruptures can extend onto interseismic portion, but can still only 
            nuclear in seismogenic zone. If False, ruptures cannot break the 
            portion of the fault below the seismogenic zone. The default is False.
        center_loc : str, optional
            Parameter that describes the sampling space for rupture centers along the
            strike of fault. If set to 'Uniform', effectively a boxcar probability 
            for rupture centers along strike, but will be trimmed inward if 'stay_on_fault'
            is set to True. Alternatively, if set to 'Gaussian', the probability of 
            rupture centers being located near the center of the fault will be higher.
            The default is 'Uniform'.
        verbose : Boolean, optional
            Flag to print out progress in generating the earthquake sequence. If model time
            is long, can be useful as this process can be lengthy. The default is True.
        simulate_aftershocks : Boolean, optional
            Flag to simulate aftershocks using BASS algorithm from Turcotte et al., 2007.
            The default is False.
        b_d : float, optional
            The b sub d parameter in the modified Bath's law, see Turcotte et al., 2007 for 
            more discussion. Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.
        delta_m_star : float, optional
            The delta m star parameter in the modified Bath's law, see Turcotte et al., 2007
            for more details. Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.25.
        c : float, optional
            The c parameter in Omori's law, see Turcotte et al., 2007 for more details.
            Paramater is only used if 'simulate_aftershocks' is True.
            The default is 0.1.
        p : float, optional
            The p parameter in Omori's law, see Turcotte et al., 2007 for more details.
            Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.25.
        d : float, optional
            The d parameter in the spatial Omori's law, see Turcotte et al., 2007 
            for more detail. Paramater is only used if 'simulate_aftershocks' is True. 
            The default is 4.
        q : float, optional
            The q parameter in the spatial Omori's law, see Turcotte et al., 2007
            for more detail. Paramater is only used if 'simulate_aftershocks' is True.
            The default is 1.35.

        Returns
        -------
        None.

        """

        # The AdvectionSolverTVD does not enforce stability checks, so
        # this is a crude fix such that it calculates the maximum timestep 
        # that should be stable given the grid size and the horizontal 
        # component of the maximum displacement of any single event where
        # the max allowable timestep is dt = dx/displacement. Raises
        # a value error if the dt is too long.

        # Find total displacement for largest earthquake
        M0 = self.fault_M0_max
        _,_,_,D,_ = _leonard14_scaling(self.fault._fault_type,M0=M0)

        # Determine the horizontal (strike-slip) component of the displacement
        horz_part = self.fault._ss[0] / (self.fault._ss[0] + self.fault._ds[0])
        horz_d = np.abs(D * horz_part)

        # Check if the input timestep is likely to run into stability problems
        if horz_d>0:
            if type(self.grid)==RasterModelGrid:
                dt_max = self.grid.dx/horz_d 
            elif type(self.grid)==HexModelGrid:
                dt_max = self.grid.spacing/horz_d 

            if dt >= dt_max:
                raise ValueError('Input dt is too long for the maximum expected horizontal displacement of a single event to keep AdvectionSolverTVD stable, reduce the timestep.')        
        
        # Store sequence input parameters
        self.eq_sequence_params = {'Type':'variable',
                                   'T':T,
                                   'dt':dt,
                                   'num_events':num_events,
                                   'seed':seed,
                                   'freq_moment_dist':freq_moment_dist,
                                   'Mw_min':Mw_min,
                                   'Mw_max':Mw_max,
                                   'Mw_cm':Mw_cm,
                                   'Mw_x':Mw_x,
                                   'Mw_c':Mw_c,
                                   'beta':beta,
                                   'fill_method':fill_method,
                                   'annual_rate_dist':annual_rate_dist,
                                   'rate_variance_mag':rate_variance_mag,
                                   'stay_on_fault':stay_on_fault,
                                   'rupture_interseismic':rupture_interseismic,
                                   'center_loc':center_loc,
                                   'verbose':verbose,
                                   'simulate_aftershocks':simulate_aftershocks,
                                   'b_d':b_d,
                                   'delta_m_star':delta_m_star,
                                   'c':c,
                                   'p':p,
                                   'd':d,
                                   'q':q}
        
        
        ###################################################
        # Generate magnitudes of Earthquakes within sequence
        
        # If no maximum magnitude is provided, then default to the maximum allowable based
        # on the geometry of the fault
        if Mw_max==None:
            Mw_max=self.fault_Mw_max
        M0_max = _eq_magnitude_to_moment(Mw_max)
            
        # Calculate total seismic moment that should be accommodated over duration of sequence
        self.M0_total = self.fault._total_area * self.fault._mu * self.fault._mean_slip_rate * T * self._moment_fraction
        
        # Generate an original series of random events drawn from provided distribution
        if freq_moment_dist=='Gamma':
            if Mw_cm==None:
                Mw_cm=8.36
            M0,Mw = _eq_moment_gamma(num_events,seed=seed,m_t=Mw_min,m_cm=Mw_cm,beta=beta)
            # Filter events that exceed maximum for fault
            if over_max=='remove':
                M0 = M0[Mw<=Mw_max]
                Mw = Mw[Mw<=Mw_max]  
            elif over_max=='reset':
                M0[Mw>Mw_max] = M0_max 
                Mw[Mw>Mw_max] = Mw_max 
            
        elif freq_moment_dist=='TGR':
            if Mw_cm==None:
                Mw_cm=8.1
            M0,Mw = _eq_moment_tapered_pareto(num_events,seed=seed,m_t=Mw_min,m_cm=Mw_cm,beta=beta)
            # Filter events that exceed maximum for fault
            if over_max=='remove':
                M0 = M0[Mw<=Mw_max]
                Mw = Mw[Mw<=Mw_max]  
            elif over_max=='reset':
                M0[Mw>Mw_max] = M0_max 
                Mw[Mw>Mw_max] = Mw_max 
            
        elif freq_moment_dist=='TrPR':
            if Mw_x==None:
                Mw_x=Mw_max
            M0,Mw = _eq_moment_truncated_pareto(num_events,seed=seed,m_t=Mw_min,m_x=Mw_x,beta=beta)
            # Filter events that exceed maximum for fault
            if over_max=='remove':
                M0 = M0[Mw<=Mw_max]
                Mw = Mw[Mw<=Mw_max]  
            elif over_max=='reset':
                M0[Mw>Mw_max] = M0_max 
                Mw[Mw>Mw_max] = Mw_max 

        elif freq_moment_dist=='Char':
            if Mw_c==None:
                Mw_c=Mw_max 
            M0,Mw = _eq_moment_characteristic(num_events,seed=seed,m_t=Mw_min,m_c=Mw_c,beta=beta)
            # Filter events that exceed maximum for fault
            if over_max=='remove':
                M0 = M0[Mw<=Mw_max]
                Mw = Mw[Mw<=Mw_max]  
            elif over_max=='reset':
                M0[Mw>Mw_max] = M0_max 
                Mw[Mw>Mw_max] = Mw_max 
            
        # Caclculate the total seismic moment within the sequence and determine number of sequences
        # that are required to reach the total model time seismic moment expected based on slip rate
        M0_total_events = np.sum(M0)
        num_sequences = np.ceil(self.M0_total/M0_total_events).astype(int)[0]
        
        # Repeat the sequence based on the defined fill method
        if fill_method=='repeat':
            M0 = np.tile(M0,(num_sequences,))
            Mw = np.tile(Mw,(num_sequences,))
        elif fill_method=='new':
            M0list=[M0]; Mwlist=[Mw]
            for i in range(num_sequences-1):
                seed+=1
                if freq_moment_dist=='Gamma':
                    M0,Mw = _eq_moment_gamma(num_events,seed=seed,m_t=Mw_min,m_cm=Mw_cm,beta=beta)
                    # Filter events that exceed maximum for fault
                    if over_max=='remove':
                        M0 = M0[Mw<=Mw_max]
                        Mw = Mw[Mw<=Mw_max]  
                    elif over_max=='reset':
                        M0[Mw>Mw_max] = M0_max 
                        Mw[Mw>Mw_max] = Mw_max  
                elif freq_moment_dist=='TGR':
                    M0,Mw = _eq_moment_tapered_pareto(num_events,seed=seed,m_t=Mw_min,m_cm=Mw_cm,beta=beta)
                    # Filter events that exceed maximum for fault
                    if over_max=='remove':
                        M0 = M0[Mw<=Mw_max]
                        Mw = Mw[Mw<=Mw_max]  
                    elif over_max=='reset':
                        M0[Mw>Mw_max] = M0_max 
                        Mw[Mw>Mw_max] = Mw_max
                elif freq_moment_dist=='TrPR':
                    M0,Mw = _eq_moment_truncated_pareto(num_events,seed=seed,m_t=Mw_min,m_x=Mw_x,beta=beta)
                    # Filter events that exceed maximum for fault
                    if over_max=='remove':
                        M0 = M0[Mw<=Mw_max]
                        Mw = Mw[Mw<=Mw_max]  
                    elif over_max=='reset':
                        M0[Mw>Mw_max] = M0_max 
                        Mw[Mw>Mw_max] = Mw_max
                elif freq_moment_dist=='Char':
                    M0,Mw = _eq_moment_characteristic(num_events,seed=seed,m_t=Mw_min,m_c=Mw_c,beta=beta)
                    # Filter events that exceed maximum for fault
                    if over_max=='remove':
                        M0 = M0[Mw<=Mw_max]
                        Mw = Mw[Mw<=Mw_max]  
                    elif over_max=='reset':
                        M0[Mw>Mw_max] = M0_max 
                        Mw[Mw>Mw_max] = Mw_max
                M0list.append(M0)
                Mwlist.append(Mw)
            M0=np.concat(M0list,axis=0)
            Mw=np.concat(Mwlist,axis=0)
        
        if simulate_aftershocks:
            if verbose:
                print('Beginning aftershock generation')
            Mw,M0,t_offset,rad,parent = _aftershocks(Mw,M0,Mw_min,self.fault_Mw_max,seed,
                                                          b_d,delta_m_star,c,p,d,q)
            
        if verbose:
            print('Step 1 of 4: Generation of earthquake moments within sequence completed')
    
    

        ################################################################################ 
        # Extrapolate rupture details for each earthquake based on scalar seismic moment
        # and randomly place on fault plane
        
        if simulate_aftershocks:
            L,W,A,D,_ = _leonard14_scaling(self.fault._fault_type,M0=M0)
            
            # Map ruptures onto the fault
            if type(self.fault)==DippingFault:
                E,SubEvents,num_afs_orders = self._ruptures_on_fault_af(L,W,A,D,M0,Mw,Mw_min,verbose,seed=seed,stay_on_fault=stay_on_fault,
                                                         rupture_interseismic=rupture_interseismic,
                                                         center_loc=center_loc,is_fixed_max=False,
                                                         t_offset=t_offset,rad=rad,parent=parent)
            elif type(self.fault)==VerticalFault:
                E,SubEvents,num_afs_orders = self._ruptures_on_vert_fault_af(L,W,A,D,M0,Mw,Mw_min,verbose,seed=seed,stay_on_fault=stay_on_fault,
                                                           rupture_interseismic=rupture_interseismic,
                                                           center_loc=center_loc,is_fixed_max=False,
                                                           t_offset=t_offset,rad=rad,parent=parent) 
                
            
        else:
            L,W,A,D,_ = _leonard14_scaling(self.fault._fault_type,M0=M0)  
            
            # Map ruptures onto the fault
            if type(self.fault)==DippingFault:
                E,SubEvents = self._ruptures_on_fault(L,W,A,D,M0,Mw,verbose,seed=seed,stay_on_fault=stay_on_fault,
                                                       rupture_interseismic=rupture_interseismic,
                                                       center_loc=center_loc,is_fixed_max=False)
            elif type(self.fault)==VerticalFault:
                E,SubEvents = self._ruptures_on_vert_fault(L,W,A,D,M0,Mw,verbose,seed=seed,stay_on_fault=stay_on_fault,
                                                           rupture_interseismic=rupture_interseismic,
                                                           center_loc=center_loc,is_fixed_max=False)            
            
        
        if verbose:
            print('Step 2 of 4: Calculation of rupture dimensions and locations completed') 
            
        #######################################
        # Clip the sequence
        if self._clip_to=='moment':
            [E,SubEvents] = self._clip_sequence_to_moment(E,SubEvents,T,simulate_aftershocks)
        elif self._clip_to=='displacement':
            [E,SubEvents] = self._clip_sequence_to_disp(E,SubEvents,T,simulate_aftershocks)
        
        if verbose:
            print('Step 3 of 4: Sequence clipped')


        #####################################
        # Assign times to events
        
        # Calculate number of events and expected event rate per year
        if simulate_aftershocks:
            num_events = np.sum(E['Time_Offset']==-1)
        else:
            num_events = len(E['Moment'])
        mean_epa = num_events/T
        
        if annual_rate_dist == 'Poisson':
            # Generate time of events through uniform sampling of an underlying time vector
            # This produces a result that is equivalent to a poisson distribution of 
            # annual rates
            rng = np.random.default_rng(seed=seed)
            t_of_e = rng.uniform(low=0,high=T,size=num_events)
            # Sort
            t_of_e = np.sort(t_of_e)
    
            # Bin by single years to consider event rate / year
            t_bin = np.arange(0,T+1,1)
            tix = np.digitize(t_of_e,t_bin)-1 # Minus 1 so membership in the first bin has an index of 0
            epa = np.bincount(tix,minlength=len(t_bin)-1) # Events per year
        elif annual_rate_dist == 'NegativeBinomial':
            # Negative binomial sampling of the time vector for events
            #
            # This follows suggestions that non-declustered catalogs (i.e., those for which aftershocks have not been removed)
            # should have a distribution of annual occurence rates that follows a negative binomial distribution 
            # (e.g. Kagan & Jackson, 2000, GJI). Choosing this option will produce a more "clustered" time 
            # series of earthquakes, but makes no attempts to assure that periods with higher annual rates include a large 
            # magnitude earthquake, so this is not formally considering aftershock sequences.
            #
            # To establish parameters for the negative binomial distribution, this uses the implied mean rate from the long time series
            # such that mean rate = total number of events / total time. It then takes a parameter 'rate_variance_mag' which is
            # interpreted as how much larger the variance of the annual rate is compared to the mean. If the variance equals the mean
            # then the negative binomial will produce a poisson distribution. Variances less than the mean will produce errors.
            #
            # Assert variance in terms of how much larger it is than mean
            nu = 1 / rate_variance_mag # Equivalent to mean / variance where variance = mean * rate_variance_mag
            tau = mean_epa / ((1-nu)/nu)
            
            # Generate a long sequence of event rates based on the negative binomial parameters
            # Using the number of events as the length *should* be sufficient as compared to the poisson,
            # as the nature of the distribution is such that this will generate more years with higher than average rates
            #
            # For short time series and depending on seed, this may fail because the total number of entries will exceed the 
            # number of years so set up an iterative behavior where the seed is varied until a valid sequence is found
            num_epa = T+1
            nseed = seed
            while num_epa > T:
                rng = np.random.default_rng(seed=nseed)
                epa = rng.negative_binomial(tau,nu,size=num_events*2).astype(int) # Force these to be integers
                # Set any negative events to zeros
                epa[epa<0] = 0
                # Trim such that the sum of the number of events approximates the total number of events
                epa = epa[np.cumsum(epa)<=num_events]
                # Append the remainder so that summed number of events will equal total number of events
                epa = np.append(epa,num_events-np.sum(epa)).astype(int)
                
                num_epa = epa.shape[0]
                nseed += 1
           
            # Pad with zeros so that there is a earthquake rate per year for full duration and then shuffle
            epa = np.pad(epa, (0,T - epa.shape[0]),'constant',constant_values=(0,0))
            rng.shuffle(epa)
            # Iterate through by year and generate a time of event vector
            t_of_e=[]
            for i in range(T):
                if epa[i]>0:
                    t_of_e.append(i+rng.uniform(low=0,high=1,size=epa[i]))
            t_of_e = np.concat(t_of_e,axis=0)
            # Sort
            t_of_e = np.sort(t_of_e) 
            
        # Propogate time offsets and sort by time
        if simulate_aftershocks:
            t_of_all_e = np.zeros(len(E['Event_ID']))
            parent_event = E['Time_Offset']==-1
            t_of_all_e[parent_event] = t_of_e
            
            for i in range(num_afs_orders-1):
                parent_idx = E['Aftershock_Order']==i
                children_idx = E['Aftershock_Order']==i+1
                for j in range(np.sum(parent_idx)):
                    parentOI_ix = E['Event_ID'][parent_idx][j]
                    childrenOI_ix = E['Event_ID'][np.logical_and(children_idx,E['Parent_ID']==parentOI_ix)]
                    t_of_all_e[childrenOI_ix] = t_of_all_e[parentOI_ix] + E['Time_Offset'][childrenOI_ix]
            
            sidx = np.argsort(t_of_all_e)
            t_of_e = t_of_all_e[sidx]
            
            E['Event_ID'] = E['Event_ID'][sidx]
            E['Length'] = E['Length'][sidx]
            E['Width'] = E['Width'][sidx]
            E['Area'] = E['Area'][sidx]
            E['Displacement'] = E['Displacement'][sidx]
            E['Moment'] = E['Moment'][sidx]
            E['Magnitude'] = E['Magnitude'][sidx]
            E['Center_X'] = E['Center_X'][sidx]
            E['Center_Y'] = E['Center_Y'][sidx]
            E['Aftershock'] = E['Aftershock'][sidx]
            E['Parent_ID'] = E['Parent_ID'][sidx]
            E['Parent_Chain'] = [E['Parent_Chain'][i] for i in sidx]
            E['Aftershock_Order'] = E['Aftershock_Order'][sidx]
            E['Time_Offset'] = E['Time_Offset'][sidx]

            
        # Estimate recurrence interval of earthquake by magnitude bins
        mag_bins = np.arange(Mw_min,Mw_max+0.1,0.1)
        mag_ix = np.digitize(E['Magnitude'],mag_bins)-1
        t_r = np.zeros(E['Moment'].shape)
        for i in range(len(mag_bins)-1):
            idx = mag_ix==i
            a_t_r = np.diff(t_of_e[idx])
            if a_t_r.shape[0]>0:
                a_t_r = np.append(a_t_r,np.mean(a_t_r))
                t_r[idx]=a_t_r
        # Recurrence time of 0 implies a single event, set recurrence time of these to the duration of the record
        # where true recurrence time would likely be longer
        t_r[np.isclose(t_r,0)]=T  
        
        # Generate a dictionary with times and append output dictionary
        Events = {'Cumulative_Time':t_of_e,
                  'Event_Return_Time':t_r,
                  'Number_SubEvents':np.bincount(SubEvents['Event_ID'])}
        Events.update(E)
        
        self.Events = Events
        self.SubEvents = SubEvents
    
        # Generate bin edges that stretch across whole time domain at the step of dt
        time_bins=np.arange(0,T+dt,dt)
        # Find index of time bin for each event (subtract 1 to convert to index)
        time_ix=np.digitize(t_of_e,time_bins,right=True)-1        
        # Count events in each bin
        num_bins=len(time_bins)-1
        event_per_dt=np.bincount(time_ix,minlength=num_bins)
        
        # Store counter and time details for use within run_one_step()
        self.model_time = T
        self.dt = dt
        self.time_bins = time_bins
        self.current_model_time = 0
        self.time_ix = time_ix
        self.event_per_dt = event_per_dt
        
        if verbose:
            print('Step 4 of 4: Calculation of time of events completed')

        # Final stability check to see if the max of the summed horizontal components of displacements 
        # in any timestep would lead to stability issues in AdvectionSolverTVD. This is overly conservative
        # in that it does not check whether the dislocations necessarily overlap and does not consider what
        # the actual displacement at the surface would be, so the reported maximum timestep is not necessarily
        # a hard limit, but it does inform the user that there could be problems if all ruptures were shallow and
        # overlapped
        #
        # Sum displacements in each timestep
        disp = Events['Displacement']
        summed_disp = np.bincount(time_ix,weights=disp)
        max_horz_disp = np.max(np.abs(summed_disp))*horz_part

        if max_horz_disp>0:
            if type(self.grid)==RasterModelGrid:
                dt_max = self.grid.dx/max_horz_disp 
            elif type(self.grid)==HexModelGrid:
                dt_max = self.grid.spacing/max_horz_disp 

            if dt >= dt_max:
                str = f'Maximum possible horizontal displacement in a time step exceeds stability criteria for advection, consider reducing the timestep to be equal or less than {np.floor(dt_max):.0f}'
                warnings.resetwarnings()
                warnings.warn(str,UserWarning)

    def run_one_step(self,dt):
        """
        Primary method for running a single step. Requires that an earthquake
        sequence was generated.

        Parameters
        ----------
        dt : int
            Timestep in years.

        """
        
        # At each timestep, check whether there are any earthquakes, if there
        # are no earthquakes during the timestep then nothing other than the
        # internal counter is updated in the timestep
        
        try:
            self.time_ix
        except AttributeError:
            raise AttributeError('An earthquake catalog must be first generated to use "run_one_step"')

        # Check if dt has changed, if yes, update
        # Then determine index within time vector
        if dt==self.dt:
            ix = np.argwhere(self.time_bins==self.current_model_time)[0][0]
        else:
            time_bins=np.arange(0,self.model_time+dt,dt)
            # Find index of time bin for each event (subtract 1 to convert to index)
            time_ix=np.digitize(self.Events['Cumulative_Time'],time_bins,right=True)-1
            # Count events in each bin
            num_bins=len(time_bins)-1
            event_per_dt=np.bincount(time_ix,minlength=num_bins)

            self.dt = dt 
            self.time_bins = time_bins
            self.time_ix = time_ix
            self.event_per_dt = event_per_dt

            ix = np.argwhere(self.time_bins==self.current_model_time)[0][0]

        # Determine if any events occur in this timestep
        if np.any(self.time_ix==ix):
            # Extract vents that occur in the time block
            event_ids = self.Events['Event_ID'][self.time_ix==ix]
            # Extract moments to occur
            moments = self.Events['Moment'][self.time_ix==ix]
            # Check that not all events in the timestep are nan, this should only occur
            # if aftershocks are being simulated
            if not np.all(np.isnan(moments)):
                # Filter out any nans from list of events, 
                # only relevant if aftershocks are included
                event_ids = event_ids[~np.isnan(moments)]
                # Store the list of events that occur in this timestep for the 
                # coseismic landslide component if being used
                self.events_to_occur = event_ids
                # Calculate a summed coseismic velociy field for all events
                # which occur in the timestep - this is the main bottle neck in terms of speed
                # so parallelization here can significantly speed things up if multiple earthquakes
                # occur in a single timestep. 
                if self.parallel:
                    if not(self.fault._topographic_correction):
                        if type(self.fault)==DippingFault:
                            cvx,cvy,cvz = _calc_elastic_dipping_mp(self.fault._xs,self.fault._ys,self.fault._zs,
                                                                   self.fault._strike,self.fault._ss,self.fault._ds,
                                                                   self.fault._mu,self.fault._nu,
                                                                   self.Events,self.SubEvents,event_ids,self._num_cores,
                                                                   self.fault._topographic_correction,None)
                        elif type(self.fault)==VerticalFault:
                            cvx,cvy,cvz = _calc_elastic_vertical_mp(self.fault._xs,self.fault._ys,self.fault._zs,
                                                                    90.,self.fault._ss,self.fault._ds,
                                                                    self.fault._mu,self.fault._nu,
                                                                    self.Events,self.SubEvents,event_ids,self._num_cores,
                                                                    self.fault._topographic_correction,None)                        
                    elif self.fault._topographic_correction:
                        # Extract current topographic surface at both nodes and links
                        zl_nodes = self.grid.at_node['topographic__elevation'][self.grid.core_nodes].copy()
                        zl_links = map_mean_of_link_nodes_to_link(self.grid, 'topographic__elevation').copy()
                        zl = np.concat((zl_links,zl_nodes),axis=0).astype(float)

                        ## Need to account for if any of the topographic surface being passed to okada4py to use
                        ## for the topographic correction is below the upper tip of the fault, if so, this will
                        ## cause an error. Original strategy was to simply raise any points that fell below the upper
                        ## tip an elevatin just above the tip via replacement, but this was causing strange errors
                        ## in cases of extreme subsidence. The more convoluted normalizing and raising method that 
                        ## remains was the best alternative option.

                        ## This causes cascading NaNs within the topographic__elevation for some reason when
                        ## subsidence is high
                        # # zl[zl <= -1*self.fault._tip_location[2]] = -1*self.fault._tip_location[2]+0.5

                        ## This works consistently with high rates of subsidence. 
                        if np.any(zl <= -1*self.fault._tip_location[2]):
                            tip = -1*self.fault._tip_location[2]
                            orig_rng = np.max(zl) - np.min(zl)
                            new_rng = np.max(zl) - (tip + 0.1)
                            zl = zl * (new_rng/orig_rng)
                            zl += (tip - np.min(zl)) + 0.1           
                        
                        if type(self.fault)==DippingFault:
                            cvx,cvy,cvz = _calc_elastic_dipping_mp(self.fault._xs,self.fault._ys,self.fault._zs,
                                                                   self.fault._strike,self.fault._ss,self.fault._ds,
                                                                   self.fault._mu,self.fault._nu,
                                                                   self.Events,self.SubEvents,event_ids,self._num_cores,
                                                                   self.fault._topographic_correction,zl)
                        elif type(self.fault)==VerticalFault:
                            cvx,cvy,cvz = _calc_elastic_vertical_mp(self.fault._xs,self.fault._ys,self.fault._zs,
                                                                    90.,self.fault._ss,self.fault._ds,
                                                                    self.fault._mu,self.fault._nu,
                                                                    self.Events,self.SubEvents,event_ids,self._num_cores,
                                                                    self.fault._topographic_correction,zl)
                else:
                    cvx=[]; cvy=[]; cvz=[]
                    for event in event_ids:
                        cvx0,cvy0,cvz0 = self._calc_coseismic_vel(event)
                        cvx.append(cvx0); cvy.append(cvy0); cvz.append(cvz0)
                    cvx = sum(cvx); cvy=sum(cvy); cvz=sum(cvz)
    
                # Check stability of AdvectionSolverTVD
                max_horz_disp = np.max(np.sqrt(cvx**2 + cvy**2))
                if max_horz_disp>0:
                    if type(self.grid)==RasterModelGrid:
                        dt_max = self.grid.dx/max_horz_disp 
                    elif type(self.grid)==HexModelGrid:
                        dt_max = self.grid.spacing/max_horz_disp 

                    if self.dt >= dt_max:
                        str = f'Maximum horizontal displacement exceeded stability at model time {self.current_model_time:.0f}'
                        warnings.resetwarnings()
                        warnings.warn(str,UserWarning)


                # Update horizontal velocity field to coseismic and apply
                if type(self.grid)==RasterModelGrid:
                    self.fault._vel[self.grid.horizontal_links]=cvx[self.fault._horz_link_idx]
                    self.fault._vel[self.grid.vertical_links]=cvy[self.fault._vert_link_idx]
                    self.fault._adv.run_one_step(1) 
                    # Apply vertical component
                    if 'bedrock__elevation' in self.grid.at_node.keys():
                        self.fault._br_elev[self.grid.core_nodes] += cvz[self.fault._node_idx]
                        self.fault._elev[self.grid.core_nodes] = self.fault._br_elev[self.grid.core_nodes] + self.fault._sd[self.grid.core_nodes]
                    else:
                        self.fault._elev[self.grid.core_nodes] += cvz[self.fault._node_idx]
                    # Update total displacements
                    [x_comp,y_comp] = self.grid.map_link_vector_components_to_node('advection__velocity')
                    self.fault._tx_disp[self.grid.core_nodes] += x_comp[self.grid.core_nodes] # These should be instantaneous displacements from EQs so don't need to consider timestep
                    self.fault._ty_disp[self.grid.core_nodes] += y_comp[self.grid.core_nodes]
                    self.fault._tz_disp[self.grid.core_nodes] += cvz[self.fault._node_idx]
                    # Reset velocity back to interseismic for next iteration
                    # We don't need to worry about whether topographic corrections are being applied because
                    # new interseismic velocities will be calculated before the advection occurs 
                    # if this is the case within the fault run_one_step method
                    self.fault._vel[self.grid.horizontal_links]=self.fault._ivx[self.fault._horz_link_idx]
                    self.fault._vel[self.grid.vertical_links]=self.fault._ivy[self.fault._vert_link_idx]
                elif type(self.grid)==HexModelGrid:
                    self.grid.map_vectors_to_links(cvx[self.fault._link_idx],cvy[self.fault._link_idx],out=self.fault._vel)
                    self.fault._adv.run_one_step(1)
                    # Apply vertical component
                    if 'bedrock__elevation' in self.grid.at_node.keys():
                        self.fault._br_elev[self.grid.core_nodes] += cvz[self.fault._node_idx]
                        self.fault._elev[self.grid.core_nodes] = self.fault._br_elev[self.grid.core_nodes] + self.fault._sd[self.grid.core_nodes]
                    else:
                        self.fault._elev[self.grid.core_nodes] += cvz[self.fault._node_idx]
                    # Update total displacements
                    [x_comp,y_comp] = self.grid.map_link_vector_components_to_node('advection__velocity')
                    self.fault._tx_disp[self.grid.core_nodes] += x_comp[self.grid.core_nodes] # These should be instantaneous displacements from EQs so don't need to consider timestep
                    self.fault._ty_disp[self.grid.core_nodes] += y_comp[self.grid.core_nodes]
                    self.fault._tz_disp[self.grid.core_nodes] += cvz[self.fault._node_idx]
                    # Reset velocity back to interseismic for next iteration
                    # We don't need to worry about whether topographic corrections are being applied because
                    # new interseismic velocities will be calculated before the advection occurs 
                    # if this is the case within the fault run_one_step method
                    self.grid.map_vectors_to_links(self.fault._ivx[self.fault._link_idx],self.fault._ivy[self.fault._link_idx],out=self.fault._vel)
        else:
            self.events_to_occur=np.array([])
        # Update tracking of the running model time
        self.current_model_time += dt
    
    ## Plotting
    def plot_eq_catalog(self,num_mag_bins=5,cmap='magma',return_handles=False,fig1size=(10,10),fig2size=(10,5)):
        """
        Method to visualize the details of a generated earthquake catalog. 
        Produces two main plots. One shows a standard distribution of moment
        and magnitude by cumulative number along with histograms of
        recurrence interval by magnitude ranges and displacement per event. The
        other generated plot shows the frequency of earthquakes by magnitude 
        through time, binned by the timestep of the model.

        Parameters
        ----------
        num_mag_bins : integer or 'auto', optional
            The number of magnitude bins for considering distributions
            of return times and displacements. If 'auto' is provided,
            the number of bins will be determined automatically. The default is 5.
        cmap : str or colormap, optional
            Expects the name of a valid colormap or a valid colormap object. Sets
            the colormap of the magnitude vs time plot. The default is 'magma'.
        return_handles : boolean, optional
            Flag to return the figure handles of the generated figures. The default
            is False.

        Returns
        -------
        f1 : figure handle, optional
            Handle to the figure displaying the earthquake catalog distribution
        f2 : figure handle, optional
            Handle to the figure displaying the time occurence of the events

        """
        
        nidx = ~np.isnan(self.Events['Magnitude'])
        
        Mw_sort,Mw_count = _cumcount(self.Events['Magnitude'][nidx])
        M0_sort = _eq_magnitude_to_moment(Mw_sort)
        
        if num_mag_bins=='auto':
            m_bins = np.histogram_bin_edges(self.Events['Magnitude'][nidx],'auto')
            num_mag_bins = len(m_bins)
        else:
            m_bins = np.histogram_bin_edges(self.Events['Magnitude'][nidx],num_mag_bins) 
        
        # Add a small amount to the right most edge because the behavior of histogram_bin_edges
        # is for some ridiculous reasons not compatible with digitize because the developers of 
        # numpy hate joy
        m_bins[-1] = m_bins[-1]+0.1
        
        f1 = plt.figure(figsize=fig1size,layout='tight')
        ax1=f1.add_subplot(2,1,1)
  
        ax1.set_xlabel('Seismic Moment (N-m)')
        ax1.set_ylabel('Earthquake Cumulative Number')
        ax1.set_xlim((_eq_magnitude_to_moment(m_bins[0]),_eq_magnitude_to_moment(m_bins[-1])))
        ax1.set_yscale('log')
        ax1.set_xscale('log')
        
        ax2 = ax1.twiny()
        ax2.set_xlabel('Moment Magnitude',color='k')
        ax2.set_xlim((m_bins[0],m_bins[-1]))
        
        ax3=f1.add_subplot(2,2,3)
        ax3.set_xlabel('Return Time (a)')
        ax3.set_ylabel('Count')
        ax3.set_yscale('log')

        ax4=f1.add_subplot(2,2,4)   
        ax4.set_xlabel('Displacements (m)')
        ax4.set_ylabel('Count')       
        
        for i in range(len(m_bins)-1):
            idx = (self.Events['Magnitude'][nidx]>=m_bins[i]) & (self.Events['Magnitude'][nidx]<m_bins[i+1])
            idx2 = (Mw_sort>=m_bins[i]) * (Mw_sort<m_bins[i+1])

            ax2.scatter(Mw_sort[idx2],Mw_count[idx2],s=5)
            ax1.scatter(M0_sort[idx2],Mw_count[idx2],s=5)
            
            rt = self.Events['Event_Return_Time'][nidx][idx]
            d = self.Events['Displacement'][nidx][idx]
            m_bin_center = m_bins[i] + (m_bins[i+1]-m_bins[i])/2
            
            rt_bins = np.histogram_bin_edges(rt,'doane')
            d_bins = np.histogram_bin_edges(d,'doane')

            ax3.hist(rt,rt_bins,histtype='step',label='Mw = '+str(np.round(m_bin_center,2)))
            ax4.hist(d,d_bins,histtype='step')        

        ax3.legend(loc='best')
        
        f2 = plt.figure(figsize=fig2size,layout='tight')
        ax = plt.subplot()
        im = np.zeros((num_mag_bins,len(self.event_per_dt)))

        for i in range(len(self.event_per_dt)):
            MwOI = self.Events['Magnitude'][nidx][self.time_ix[nidx]==i]
            im[:,i]=np.bincount(np.digitize(MwOI,m_bins)-1,minlength=num_mag_bins)
        
        m_bin_centers = m_bins[0:-1]+np.diff(m_bins)
        # scale = ((self.model_time - self.dt)/1000) / (m_bin_centers[-1] - m_bin_centers[0])
        scale = (self.model_time/1000)/m_bin_centers[-1]

        
        if num_mag_bins>1:
            im1=plt.imshow(im,origin='lower',aspect=scale,
                           extent=(self.dt/1000,self.model_time/1000,m_bin_centers[0],m_bin_centers[-1]),cmap=cmap)
        else:
            im1=plt.imshow(im,origin='lower',aspect=scale,
                           extent=(self.dt/1000,self.model_time/1000,m_bins[0],m_bins[-1]),cmap=cmap)
        plt.xlabel('Model Time (ka)')
        plt.ylabel('Moment Magnitude')
        cbar = plt.colorbar(im1,ax=ax,orientation='horizontal')
        cbar.ax.set_xlabel('Number Events Per Timestep')
        
        if return_handles:
            return f1,f2

    def plot_ruptures(self,plot_rupture_centers=True,cmap='plasma',return_handles=False,fig1size=(10,10),fig2size=(10,10)):
        """
        Method for visualizing distribution of earthquake ruptures. Plot will
        have two subplots, one showing outlines of ruptures and the other showing
        cumulative amounts of slip on the fault plane.

        Parameters
        ----------
        plot_rupture_centers : boolean, optional
            Flag to turn on the plotting of the centers of individual ruptures
            as dots. Turning these off by setting this parameter to False can
            help to declutter the diagram if there are many ruptures.
            The default is True.
        cmap : str or colormap, optional
            Expects the name of a valid colormap or a valid colormap object. Sets
            the colormap the cumulative slip plot. The default is 'plasma'.
        return_handles : boolean, optional
            Flag to return the figure handles of the generated figures. The default
            is False.

        Returns
        -------
        f1 : figure handle, optional
            Handle to the produced figure.

        """
        
        # Define polygon that outlines LEM domain
        if type(self.grid)==RasterModelGrid:
            ext_y=self.grid.extent[0]
            ext_x=self.grid.extent[1]
        elif type(self.grid)==HexModelGrid:
            ext_y = np.max(self.grid.y_of_node)
            ext_x = np.max(self.grid.x_of_node)
        
        if type(self.fault)==DippingFault:
            MX = self.fault._MX
            MY = self.fault._MY
            mx = MX.ravel()
            my = MY.ravel()
            m = np.hstack((mx.reshape((len(mx),1)),my.reshape((len(my),1))))
            D = np.zeros(MX.shape)
            
            f1=plt.figure(figsize=fig1size,layout='tight')
            f2=plt.figure(figsize=fig2size,layout='tight')
            
            sim_time = self.model_time
            plt.suptitle('Length of Sequence : '+str(np.round(sim_time/1000,2))+' ka')
            
            # Plot ruptures extents
            ax1=f1.add_subplot(1,1,1)
            ax1.set_aspect('equal')
            ax1.set_xlabel('X (m)')
            ax1.set_ylabel('Y (m)')
            
            ax2=f2.add_subplot(1,1,1)
            ax2.set_aspect('equal')
            ax2.set_xlabel('X (m)')
            ax2.set_ylabel('Y (m)')
                 
            ax1.plot([0,ext_x,ext_x,0,0],[0,0,ext_y,ext_y,0],c='k',linestyle=':',linewidth=2,label='LEM Boundary')
            ax2.plot([0,ext_x,ext_x,0,0],[0,0,ext_y,ext_y,0],c='k',linestyle=':',linewidth=2,label='LEM Boundary')
            for i in range(self.fault._num_panels):
                if self.fault._panel_types!=None:
                    if self.fault._panel_types[i]=='A':
                        ax1.plot(self.fault._panel_boundaries[i][0],self.fault._panel_boundaries[i][1],c='b',linestyle=':')
                        ax2.plot(self.fault._panel_boundaries[i][0],self.fault._panel_boundaries[i][1],c='b',linestyle=':',zorder=1)
                    elif self.fault._panel_types[i]=='C':
                        ax1.plot(self.fault._panel_boundaries[i][0],self.fault._panel_boundaries[i][1],c='r',linestyle=':')
                        ax2.plot(self.fault._panel_boundaries[i][0],self.fault._panel_boundaries[i][1],c='r',linestyle=':',zorder=1)
                    elif self.fault._panel_types[i]=='I':
                        ax1.plot(self.fault._panel_boundaries[i][0],self.fault._panel_boundaries[i][1],c='k',linestyle=':')
                        ax2.plot(self.fault._panel_boundaries[i][0],self.fault._panel_boundaries[i][1],c='k',linestyle=':',zorder=1)
                        if self.fault._slip_rate_function == 'boxcar':
                            # Generate displacements on interseismic section based on slip rate
                            d = sim_time * self.fault._slip_rate
                            pbx = self.fault._panel_boundaries[i][0]
                            pby = self.fault._panel_boundaries[i][1]
                            p = path.Path([[pbx[0],pby[0]],[pbx[1],pby[1]],[pbx[2],pby[2]],[pbx[3],pby[3]],[pbx[4],pby[4]]])
                            idx = p.contains_points(m)
                            IDX = idx.reshape(MX.shape)
                            D0 =np.zeros(MX.shape)
                            D0[IDX] = d
                            D += D0 
                        else:
                            # Generate displacements on interseismic section based on slip rate
                            d = sim_time * self.fault._slip_rate_along_fault
                            pbx = self.fault._panel_boundaries[i][0]
                            pby = self.fault._panel_boundaries[i][1]
                            p = path.Path([[pbx[0],pby[0]],[pbx[1],pby[1]],[pbx[2],pby[2]],[pbx[3],pby[3]],[pbx[4],pby[4]]])
                            idx = p.contains_points(m)
                            IDX = idx.reshape(MX.shape)
                            D0 = np.transpose(np.matlib.repmat(d,self.fault._MY.shape[1],1))
                            D0[~IDX] = 0.
                            D += D0
                            
                else:
                    ax1.plot(self.fault._panel_boundaries[i][0],self.fault._panel_boundaries[i][1],c='k',linestyle=':')  
                    ax2.plot(self.fault._panel_boundaries[i][0],self.fault._panel_boundaries[i][1],c='k',linestyle=':',zorder=1)
                    
            if plot_rupture_centers:
                ax1.scatter(self.SubEvents['Center_X'],self.SubEvents['Center_Y'],c='g',s=1)
            for i in range(len(self.SubEvents['Event_ID'])):
                bx=self.SubEvents['Bound_X'][i,:]
                by=self.SubEvents['Bound_Y'][i,:]
                ax1.plot(bx,by,c='g',linewidth=0.25) 
                
                # Populate displacement patches on fault
                p = path.Path([[bx[0],by[0]],[bx[1],by[1]],[bx[2],by[2]],[bx[3],by[3]],[bx[4],by[4]]])
                idx = p.contains_points(m)
                IDX = idx.reshape(MX.shape)
                D0 =np.zeros(MX.shape)
                D0[IDX] = self.SubEvents['Displacement'][i]
                D += D0
            if (np.isclose(self.fault._strike,0)) | (np.isclose(self.fault._strike,90)) | (np.isclose(self.fault._strike,180)) | (np.isclose(self.fault._strike,270)) | (np.isclose(self.fault._strike,360)):
                im=ax2.imshow(D,origin='lower',extent=(np.min(mx),np.max(mx),np.min(my),np.max(my)),cmap=cmap)
                # imshow doesn't work well for anything but a fault with a strike of 0/90/180/270/360
            else:
                im = ax2.scatter(mx,my,c=D.ravel(),cmap=cmap,s=1,zorder=0)
            cbar=plt.colorbar(im,ax=ax2)
            cbar.ax.set_ylabel('Total Displacement (m)')
            
            ax2.set_xlim(ax1.get_xlim())
            ax2.set_ylim(ax1.get_ylim())
        elif type(self.fault)==VerticalFault:            
            FZ = self.fault._FZ # Width (Depth)
            FY = self.fault._FY # Length
            fz = FZ.ravel()
            fy = FY.ravel()
            f = np.hstack((fy.reshape((len(fy),1)),fz.reshape((len(fz),1))))
            D = np.zeros(FY.shape)
            
            f1=plt.figure(figsize=fig1size,layout='tight')
            f2=plt.figure(figsize=fig2size,layout='tight')
            
            sim_time = self.model_time
            
            # Plot ruptures extents
            ax1=f1.add_subplot(1,1,1)
            # LandEvolve patch: this set_title used to sit above the line that
            # creates ax1 (UnboundLocalError for every vertical fault).
            ax1.set_title('Length of Sequence : '+str(np.round(sim_time/1000,2))+' ka')
            ax1.set_aspect('equal')
            ax1.set_xlabel('Length (m)')
            ax1.set_ylabel('Depth (m)')
            
            ax2=f2.add_subplot(1,1,1)
            ax2.set_aspect('equal')
            ax2.set_xlabel('Length (m)')
            ax2.set_ylabel('Depth (m)')
                 
            
            for i in range(self.fault._num_panels):
                for j in range(self.fault._num_sub_panels):
                    if self.fault._panel_types[i][j]=='A': 
                        xp = [self.fault._fy[i],self.fault._fy[i+1],self.fault._fy[i+1],self.fault._fy[i],self.fault._fy[i]]
                        yp = [self.fault._fz[i,j],self.fault._fz[i,j],self.fault._fz[i,j+1],self.fault._fz[i,j+1],self.fault._fz[i,j]]
                        ax1.plot(xp,yp,c='b')
                        ax2.plot(xp,yp,c='b',zorder=2)
                    elif self.fault._panel_types[i][j]=='C':
                        xp = [self.fault._fy[i],self.fault._fy[i+1],self.fault._fy[i+1],self.fault._fy[i],self.fault._fy[i]]
                        yp = [self.fault._fz[i,j],self.fault._fz[i,j],self.fault._fz[i,j+1],self.fault._fz[i,j+1],self.fault._fz[i,j]]
                        ax1.plot(xp,yp,c='r')
                        ax2.plot(xp,yp,c='r',zorder=2)
                    elif self.fault._panel_types[i][j]=='I':
                        xp = [self.fault._fy[i],self.fault._fy[i+1],self.fault._fy[i+1],self.fault._fy[i],self.fault._fy[i]]
                        yp = [self.fault._fz[i,j],self.fault._fz[i,j],self.fault._fz[i,j+1],self.fault._fz[i,j+1],self.fault._fz[i,j]]
                        ax1.plot(xp,yp,c='k')
                        ax2.plot(xp,yp,c='k',zorder=2)
                        if self.fault._slip_rate_function=='boxcar':
                            d = sim_time * self.fault._slip_rate
                            # Generate displacements on interseismic section based on slip rate
                            # The small nudges in the x positions are to avoid overlaps (that don't really exist)
                            p = path.Path([[xp[0]+0.1,yp[0]],[xp[1]-0.1,yp[1]],[xp[2]-0.1,yp[2]],[xp[3]+0.1,yp[3]],[xp[4]+0.1,yp[4]]])
                            idx = p.contains_points(f)
                            IDX = idx.reshape(FZ.shape)
                            D0 =np.zeros(FZ.shape)
                            D0[IDX] = d
                            D += D0
                        else:
                            d = sim_time * self.fault._slip_rate_along_fault
                            # Generate displacements on interseismic section based on slip rate
                            # The small nudges in the x positions are to avoid overlaps (that don't really exist)
                            p = path.Path([[xp[0]+0.1,yp[0]],[xp[1]-0.1,yp[1]],[xp[2]-0.1,yp[2]],[xp[3]+0.1,yp[3]],[xp[4]+0.1,yp[4]]])
                            idx = p.contains_points(f)
                            IDX = idx.reshape(FZ.shape)
                            D0 = np.matlib.repmat(d,self.fault._FZ.shape[0],1)
                            D0[~IDX] = 0.
                            D += D0
                            
                    
            if plot_rupture_centers:
                ax1.scatter(self.SubEvents['Center_L'],self.SubEvents['Center_Z'],c='g',s=1)
            for i in range(len(self.SubEvents['Event_ID'])):
                bx=self.SubEvents['Bound_L'][i,:]
                by=self.SubEvents['Bound_Z'][i,:]
                ax1.plot(bx,by,c='g',linewidth=0.25) 
                
                # Populate displacement patches on fault
                # The small nudges in the x positions are to avoid overlaps (that don't really exist)
                p = path.Path([[bx[0]+0.1,by[0]],[bx[1]-0.1,by[1]],[bx[2]-0.1,by[2]],[bx[3]+0.1,by[3]],[bx[4]+0.1,by[4]]])
                idx = p.contains_points(f)
                IDX = idx.reshape(FY.shape)
                D0 =np.zeros(FY.shape)
                D0[IDX] = self.SubEvents['Displacement'][i]
                D += D0
            
            im=ax2.imshow(D,origin='lower',extent=(np.min(fy),np.max(fy),np.min(fz),np.max(fz)),cmap=cmap)
            cbar=plt.colorbar(im,ax=ax2)
            cbar.ax.set_ylabel('Total Displacement (m)')
            
            ax1.yaxis.set_inverted(True)
            ax1.set_aspect('equal')
            
            ax2.yaxis.set_inverted(True)
            ax2.set_aspect('equal')
            
            ax2.set_xlim(ax1.get_xlim())
            ax2.set_ylim(ax1.get_ylim())
            
        if return_handles:
            return f1,f2
        
 
    def plot_moment_release(self,return_handles=False,figsize=(12,5)):
        """
        Method for visualizing the history of moment release within the sequence.
        Plot will have two subplots, one showing the moment released by earthquakes
        through time compared to the expected moment accumulation rate. The other
        subplot shows the earthquake moment released normalized by the expected
        accumulation rate.
        
        Parameters
        ----------
        return_handles : boolean, optional
            Flag to return the figure handles of the generated figures. The default
            is False.
        figsize : tuple, optional
            Size of the figure in inches of the form (width, height). Default is (12,5)

        Returns
        -------
        f1 : figure handle, optional
            Handle to the produced figure.

        """
        
        nidx = (~np.isnan(self.Events['Moment'])) & (self.Events['Cumulative_Time']<=self.model_time)
        
        M0 = self.Events['Moment'][nidx]
        T_cm = self.Events['Cumulative_Time'][nidx]
        M0_cum = np.cumsum(M0)
        
        if self.eq_sequence_params['Type']=='fixed_max':
            # Define event size
            M0_char = _eq_magnitude_to_moment(self.fault_Mw_max)
            # Extrapolate rupture details for each earthquake based on scalar seismic moment
            _,_,A,_,_ = _leonard14_scaling(self.fault._fault_type,M0=M0_char)
            M0_rate = A * self.fault._mu * self.fault._mean_slip_rate * T_cm
        else:
            M0_rate = self.fault._total_area * self.fault._mu * self.fault._mean_slip_rate * T_cm
        
        
        f1 = plt.figure(figsize=figsize,layout='tight')
        
        plt.subplot(1,2,1)
        plt.plot(T_cm/1000,M0_cum,c='r',label='Coseismic Release')
        plt.plot(T_cm/1000,M0_rate,c='k',label='Background Accumulation')
        plt.xlabel('Time (ka)')
        plt.ylabel('Cumulative Moment (N-m)')
        plt.legend(loc='best')
        
        plt.subplot(1,2,2)
        plt.plot(T_cm/1000,M0_cum/M0_rate,c='r')
        plt.axhline(1,c='k')
        plt.xlabel('Time (ka)')
        plt.ylabel('Coseismic/Background')
        plt.yscale('log')
        
        if return_handles:
            return f1

    def plot_max_displacement(self,return_handles=False,figsize=(12,5)):
        
        # Establish max and average slip rate vectors
        nidx = (~np.isnan(self.Events['Displacement'])) & (self.Events['Cumulative_Time']<=self.model_time)
        T_cm = self.Events['Cumulative_Time'][nidx]
        if self.fault._slip_rate_function=='boxcar':
            max_slip_T = self.fault._slip_rate*T_cm
        else:
            max_slip_T = self.fault._slip_rate*T_cm
            mean_slip_T = self.fault._mean_slip_rate*T_cm

        SE = self.SubEvents
        if type(self.fault)==DippingFault:
            # Sort by event id
            six = np.argsort(SE['Event_ID'])
            # Translate all ruptures into rotated coordinates
            bxp = SE['Bound_X'][six]*np.cos(np.radians(-self.fault._strike+90)) + SE['Bound_Y'][six]*np.sin(np.radians(-self.fault._strike+90))
            byp = -SE['Bound_X'][six]*np.sin(np.radians(-self.fault._strike+90)) + SE['Bound_Y'][six]*np.cos(np.radians(-self.fault._strike+90))
            # Extract upper left and lower right corners
            lxp = bxp[:,3]; lyp = byp[:,3]
            rxp = bxp[:,1]; ryp = byp[:,1]
            # Translate all fault points into rotated coordinates
            mx = self.fault._MX.ravel()
            my = self.fault._MY.ravel()
            xp = mx*np.cos(np.radians(-self.fault._strike+90)) + my*np.sin(np.radians(-self.fault._strike+90))
            yp = -mx*np.sin(np.radians(-self.fault._strike+90)) + my*np.cos(np.radians(-self.fault._strike+90))
        
            # Iterate through each rupture and assign displacements
            # Calculate running maximum sum
            D = np.zeros(xp.shape)
            D_cum = np.zeros(lxp.shape)
            for i in range(len(lxp)):
                D0 = np.zeros(xp.shape)
                idx = (xp>=lxp[i]) & (xp<=rxp[i]) & (yp<=lyp[i]) & (yp>=ryp[i])
                D0[idx]=SE['Displacement'][six][i]
                D += D0 
                D_cum[i]=np.max(D)
            # Convert to per event
            D_cumsum = np.bincount(SE['Event_ID'][six],weights=D_cum)/np.bincount(SE['Event_ID'][six])
                
            
        
        elif type(self.fault)==VerticalFault:
            # Sort by event id
            six = np.argsort(SE['Event_ID'])
            # Extract upper left and lower right 
            bx = SE['Bound_L']; by=SE['Bound_Y']
            lx = bx[:,3]; ly=by[:,3]
            rx = bx[:,1]; ry=by[:,1]
            # Extract fault points
            x = self.fault._FY.ravel()
            y = self.fault._FZ.ravel()
        
            # Iterate through each rupture and assign displacements
            # Calculate running maximum sum
            D = np.zeros(x.shape)
            D_cum = np.zeros(lx.shape)
            for i in range(len(lx)):
                D0 = np.zeros(x.shape)
                idx = (x>=lx[i]) & (x<=rx[i]) & (y<=ly[i]) & (y>=ry[i])
                D0[idx]=SE['Displacement'][six][i]
                D += D0 
                D_cum[i]=np.max(D)
            # Convert to per event
            D_cumsum = np.bincount(SE['Event_ID'][six],weights=D_cum)/np.bincount(SE['Event_ID'][six])
                
        f1 = plt.figure(figsize=figsize,layout='tight')
        
        plt.subplot(1,2,1)
        plt.plot(T_cm/1000,D_cumsum,c='r',label='Max Coseismic Displacement')
        if self.fault._slip_rate_function=='boxcar':
            plt.plot(T_cm/1000,max_slip_T,c='k',label='Average Creeping Slip Rate')
        else:
            plt.plot(T_cm/1000,max_slip_T,c='k',label='Max Creeping Slip Rate') 
            plt.plot(T_cm/1000,mean_slip_T,c='k',linestyle=':',label='Average Slip Rate')            
        plt.xlabel('Time (ka)')
        plt.ylabel('Cumulative Displacement (m)')
        plt.legend(loc='best')
        
        plt.subplot(1,2,2)
        if self.fault._slip_rate_function=='boxcar':
            plt.plot(T_cm/1000,D_cumsum/max_slip_T,c='r')
        else:
            plt.plot(T_cm/1000,D_cumsum/max_slip_T,c='r')
            plt.plot(T_cm/1000,D_cumsum/mean_slip_T,c='r',linestyle=':')            
        plt.axhline(1,c='k')
        plt.xlabel('Time (ka)')
        plt.ylabel('Coseismic/Creeping')
        plt.yscale('log')
        
        if return_handles:
            return f1

    def plot_displacement_vs_time(self,location_in_coseismic=0.5,num_samples=10,section_at=None,
                                  return_handles=False,figsize=(12,5)):
        """
        Method to visualize along-strike displacement through time and simulated slip history 
        along-strike.

        Parameters
        ----------
        location_in_coseismic : float between 0 and 1, optional
            Fractional location within the coseismic portion of the fault to sample
            the slip history along-strike. Setting this parameter to 0 will sample the 
            tip of the fault, setting it to 1 will sample the base of the seismogenic zone.
            The default is 0.5.
        num_samples : integer, optional
            Number of timesteps to display the along-strike displacement pattern. These will
            be equally distributed in time. The default is 10.
        section_at : float or list of floats, optional
            Locations along the fault length, in fault length units (m) to generate slip
            per time plots. This samples the slip per time at the depth of the fault that
            is set by the 'location_in_coseismic' parameter. If None is provided, a single
            section will be taken at the center of the fault length. The default is None.
        return_handles : boolean, optional
            Flag to return the figure handles of the generated figures. The default
            is False.

        Returns
        -------
        f1 : figure handle, optional
            Handle of produced figure

        """
        
        # The parameter 'location_in_coseismic' is a fractional location within the portion of the fault that can rupture, 
        # from the tip down to the base of the seismogenic zone. Setting this to 0 will then sample the tip of the fault, 
        # setting it to 1, will set it to the base of the seismogenic zone.
        #
        # The parameter 'num_samples' is how many along-strike total displacement profiles will be drawn
        
        E=self.Events
        SE=self.SubEvents
        
        # Total time
        # Necessary for when aftershocks occur long after end of model time
        Tidx = E['Cumulative_Time']<= self.model_time
        Tc_m=E['Cumulative_Time'][Tidx]
        T = self.model_time
        norm = Normalize(vmin=0,vmax=T/1000)
        
        
        if type(self.fault)==DippingFault:
            # Prepare empty cumulative displacement array in fault aligned coordinates
            FX = self.fault._FX # Width
            FY = self.fault._FY # Length
            fx = FX.ravel()
            fy = FY.ravel()
            f = np.hstack((fx.reshape((len(fx),1)),fy.reshape((len(fy),1))))
            D = np.zeros(FX.shape)
            
            # Determine location within "width" for sample along length of fault
            PWT = []; PWB = []
            for i in range(self.fault._num_panels):
                if self.fault._panel_types!=None:
                    if self.fault._panel_types[i]=='A':
                        pwt,_ = _rot_coord_inv(self.fault._panel_boundaries[i][0][0],
                                                     self.fault._panel_boundaries[i][1][0],
                                                     self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
                        pwb,_ = _rot_coord_inv(self.fault._panel_boundaries[i][0][2],
                                                     self.fault._panel_boundaries[i][1][2],
                                                     self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0]) 
                        PWT.append(pwt)
                        PWB.append(pwb)
                    elif self.fault._panel_types[i]=='C':
                        pwt,_ = _rot_coord_inv(self.fault._panel_boundaries[i][0][0],
                                                     self.fault._panel_boundaries[i][1][0],
                                                     self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
                        pwb,_ = _rot_coord_inv(self.fault._panel_boundaries[i][0][2],
                                                     self.fault._panel_boundaries[i][1][2],
                                                     self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
                        PWT.append(pwt)
                        PWB.append(pwb)
            
            T_PWT = min(PWT)
            B_PWB = max(PWB)
            sample_loc = (B_PWB - T_PWT)*location_in_coseismic + T_PWT
            sample_ix = np.argmin(np.abs(FX[0,:]-sample_loc))
            
            # Convert num_samples to a frequency to plot
            plot_every = len(Tc_m) // num_samples
            if plot_every == 0:
                plot_every = 1
            
            
            # Extract length vector from FY along sample location
            #  and transform so that origin is on "left" side of fault
            lv = FY[:,sample_ix] + self.fault._length/2
            
            # Generate cumulative displacement along sample vector
            cum_disp = np.zeros(lv.shape)
            
            # Generate mappable
            sm = plt.cm.ScalarMappable(norm=norm,cmap='cividis')
    
            # Turn on tracking for section
            if section_at==None:
                section_at=lv[-1]/2
                ix = np.argmin(np.abs(lv-section_at))
                disp = np.zeros(Tc_m.shape)
                t=1
            elif type(section_at)==int:
                ix = np.argmin(np.abs(lv-section_at))
                disp = np.zeros(Tc_m.shape)
                t=1
            elif (type(section_at)==list) | (type(section_at)==np.ndarray):
                ix=np.zeros(len(section_at)).astype(int)
                disp=[]
                t=2
                num_ = len(section_at)
                for i in range(num_):
                    ix[i] = np.argmin(np.abs(lv-section_at[i]))
                    disp.append(np.zeros(Tc_m.shape))
                    
            f1= plt.figure(figsize=figsize,layout='tight')
            
            ax=plt.subplot(1,2,1)
            plt.xlabel('Fault Length (km)')
            plt.ylabel('Cumulative Displacement (m)')
            for i in range(len(Tc_m)):
                evnt_idx = SE['Event_ID']==i
                
                # Rotate individual ruptures for fault back into fault aligned coordinates
                bound_x = SE['Bound_X'][evnt_idx]
                bound_y = SE['Bound_Y'][evnt_idx]
                wt,lr = _rot_coord_inv(bound_x[:,0],bound_y[:,0],self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0])
                wb,ll = _rot_coord_inv(bound_x[:,2],bound_y[:,2],self.fault._tip_location[0],self.fault._tip_location[1],self.fault._strike[0]) 
    
                de = np.zeros(lv.shape)
                for j in range(len(wt)):
                    if (wt[j] <= sample_loc) & (wb[j] >= sample_loc):
                        idx = (lv > ll[j]+self.fault._length/2) & (lv < lr[j]+self.fault._length/2)
                        do = np.zeros(lv.shape)
                        do[idx]=SE['Displacement'][evnt_idx][0]
                        de += do # Total displacement for event along fault
    
                if t==1:
                    disp[i]=de[ix]
                elif t==2:
                    for j in range(num_):
                        disp[j][i]=de[ix[j]]
                        
                # Calculate cumulative displacement
                cum_disp+=de
                
                if np.mod(i,plot_every)==0:
                    plt.plot(lv/1000,cum_disp,color=cm.cividis(norm(Tc_m[i]/1000)))
                # Force plot the last one
                if i==len(Tc_m)-1:
                    plt.plot(lv/1000,cum_disp,color=cm.cividis(norm(Tc_m[i]/1000)))               
                    
            # plt.axhline(T*self.fault._slip_rate,c='k',linestyle=':',linewidth=2,label='Total Interseismic Displacement')
            plt.plot(lv/1000,self.fault._slip_rate_along_fault*T,c='k',linestyle=':',linewidth=2,label='Total Interseismic Displacement')
            ax.legend(loc='best')
                    
            cbar=plt.colorbar(sm,ax=ax)
            cbar.ax.set_ylabel('Model Time (ka)')
            
            ax2=plt.subplot(1,2,2)
            inter_event_time = np.diff(Tc_m)
            inter_event_time = np.concat(([0],inter_event_time),axis=0)  
            zeros = np.zeros(inter_event_time.shape)
            if t==1:
                ax.axvline(section_at/1000)
                # Interleave zeros
                cumt_i=np.concatenate(([0],np.cumsum(np.ravel(np.column_stack((inter_event_time,zeros))))))
                cumd_i=np.concatenate(([0],np.cumsum(np.ravel(np.column_stack((zeros,disp))))))
                ax2.plot(cumt_i/1000,cumd_i,label='Slip history at '+str(section_at/1000)+' km')
            elif t==2:
                for i in range(num_):
                    # Interleave zeros
                    cumt_i=np.concatenate(([0],np.cumsum(np.ravel(np.column_stack((inter_event_time,zeros))))))
                    cumd_i=np.concatenate(([0],np.cumsum(np.ravel(np.column_stack((zeros,disp[i]))))))
                    line,=ax2.plot(cumt_i/1000,cumd_i,label='Slip history at '+str(section_at[i]/1000)+' km')
                    ax.axvline(section_at[i]/1000,color=line.get_color())
            
            if self.fault._slip_rate_function=='boxcar':
                plt.plot(Tc_m/1000,self.fault._slip_rate*Tc_m,c='k',linestyle=':',label='Average Slip Rate')
            else:
                plt.plot(Tc_m/1000,self.fault._mean_slip_rate*Tc_m,c='k',linestyle=':',label='Average Slip Rate' )
                plt.plot(Tc_m/1000,self.fault._slip_rate*Tc_m,c='k',linestyle='--',label='Maximum Slip Rate' ) 
            plt.xlabel('Time [ka]')
            plt.ylabel('Displacement [m]')
            plt.legend(loc='best')
            
        elif type(self.fault)==VerticalFault:
            # Prepare empty cumulative displacement array in fault aligned coordinates
            FZ = self.fault._FZ # Width
            FY = self.fault._FY # Length
            fz = FZ.ravel()
            fy = FY.ravel()
            f = np.hstack((fz.reshape((len(fz),1)),fy.reshape((len(fy),1))))
            D = np.zeros(FY.shape)
            
            # Determine location within "width" for sample along length of fault
            PWT = []; PWB = []
            
            
            cix = [idx for idx, value in enumerate(self.fault._panel_types[0]) if value =='C'][0]
            PWT.append(self.fault._fz[0,cix])
            PWB.append(self.fault._fz[0,cix+1])
            if np.any(np.array(self.fault._panel_types)=='A'):
                aix = [idx for idx, value in enumerate(self.fault._panel_types[0]) if value =='A'][0]
                PWT.append(self.fault._fz[0,aix])
                PWB.append(self.fault._fz[0,aix+1])
            
            T_PWT = min(PWT)
            B_PWB = max(PWB)
            sample_loc = (B_PWB - T_PWT)*location_in_coseismic + T_PWT
            sample_ix = np.argmin(np.abs(FZ[0,:]-sample_loc))

            # Convert num_samples to a frequency to plot
            plot_every = len(Tc_m) // num_samples
            if plot_every == 0:
                plot_every = 1
            
            # Extract length vector from FY along sample location
            lv = FY[sample_ix,:] 
            
            # Generate cumulative displacement along sample vector
            cum_disp = np.zeros(lv.shape)
            
            # Generate mappable
            sm = plt.cm.ScalarMappable(norm=norm,cmap='cividis')
    
            # Turn on tracking for section
            if section_at==None:
                section_at=lv[-1]/2
                ix = np.argmin(np.abs(lv-section_at))
                disp = np.zeros(Tc_m.shape)
                t=1
            elif type(section_at)==int:
                ix = np.argmin(np.abs(lv-section_at))
                disp = np.zeros(Tc_m.shape)
                t=1
            elif (type(section_at)==list) | (type(section_at)==np.ndarray):
                ix=np.zeros(len(section_at)).astype(int)
                disp=[]
                t=2
                num_ = len(section_at)
                for i in range(num_):
                    ix[i] = np.argmin(np.abs(lv-section_at[i]))
                    disp.append(np.zeros(Tc_m.shape))
                    
            f1= plt.figure(figsize=figsize,layout='tight')
            
            ax=plt.subplot(1,2,1)
            plt.xlabel('Fault Length (km)')
            plt.ylabel('Cumulative Displacement (m)')
            for i in range(len(Tc_m)):
                evnt_idx = SE['Event_ID']==i
                
                # Grab event boundaries
                bound_l = SE['Bound_L'][evnt_idx]
                bound_z = SE['Bound_Z'][evnt_idx]
                
                ll = bound_l[:,0]
                lr = bound_l[:,1]
                
                wt = bound_z[:,0]
                wb = bound_z[:,2]
                
                
                de = np.zeros(lv.shape)
                for j in range(len(wt)):
                    if (wt[j] <= sample_loc) & (wb[j] >= sample_loc):
                        idx = (lv > ll[j]) & (lv < lr[j])
                        do = np.zeros(lv.shape)
                        do[idx]=SE['Displacement'][evnt_idx][0]
                        de += do # Total displacement for event along fault
    
                if t==1:
                    disp[i]=de[ix]
                elif t==2:
                    for j in range(num_):
                        disp[j][i]=de[ix[j]]
                        
                # Calculate cumulative displacement
                cum_disp+=de
                
                if np.mod(i,plot_every)==0:
                    plt.plot(lv/1000,cum_disp,color=cm.cividis(norm(Tc_m[i]/1000)))
                # Force plot the last one
                if i==len(Tc_m)-1:
                    plt.plot(lv/1000,cum_disp,color=cm.cividis(norm(Tc_m[i]/1000)))               
                    
            # plt.axhline(T*self.fault._slip_rate,c='k',linestyle=':',linewidth=2,label='Total Interseismic Displacement')
            plt.plot(lv/1000,self.fault._slip_rate_along_fault*T,c='k',linestyle=':',linewidth=2,label='Total Interseismic Displacement')
            ax.legend(loc='best')
                    
            cbar=plt.colorbar(sm,ax=ax)
            cbar.ax.set_ylabel('Model Time (ka)')
            
            ax2=plt.subplot(1,2,2)
            inter_event_time = np.diff(Tc_m)
            inter_event_time = np.concat(([0],inter_event_time),axis=0)  
            zeros = np.zeros(inter_event_time.shape)
            if t==1:
                ax.axvline(section_at/1000)
                # Interleave zeros
                cumt_i=np.concatenate(([0],np.cumsum(np.ravel(np.column_stack((inter_event_time,zeros))))))
                cumd_i=np.concatenate(([0],np.cumsum(np.ravel(np.column_stack((zeros,disp))))))
                ax2.plot(cumt_i/1000,cumd_i,label='Slip history at '+str(section_at/1000)+' km')
            elif t==2:
                for i in range(num_):
                    # Interleave zeros
                    cumt_i=np.concatenate(([0],np.cumsum(np.ravel(np.column_stack((inter_event_time,zeros))))))
                    cumd_i=np.concatenate(([0],np.cumsum(np.ravel(np.column_stack((zeros,disp[i]))))))
                    line,=ax2.plot(cumt_i/1000,cumd_i,label='Slip history at '+str(section_at[i]/1000)+' km')
                    ax.axvline(section_at[i]/1000,color=line.get_color())
                    
            if self.fault._slip_rate_function=='boxcar':
                plt.plot(Tc_m/1000,self.fault._slip_rate*Tc_m,c='k',linestyle=':',label='Average Slip Rate')
            else:
                plt.plot(Tc_m/1000,self.fault._mean_slip_rate*Tc_m,c='k',linestyle=':',label='Average Slip Rate' )
                plt.plot(Tc_m/1000,self.fault._slip_rate*Tc_m,c='k',linestyle='--',label='Maximum Slip Rate' ) 
            plt.xlabel('Time [ka]')
            plt.ylabel('Displacement [m]')
            plt.legend(loc='best')
        
        if return_handles:
            return f1

    def plot_coseismic_velocity_field(self,event_id,cmap='Spectral_r',return_handles=False,figsize=(15,3),
                                    fig_type='individual',quiver_interval=1000,shrink=0.75):
        """
        Plots the x, y, and z components of the coseismic velocity field for a specific event within an
        earthquake catalog

        Parameters
        ----------
        event_id : int
            A valid event id for an event within a generated earthquake catalog
        cmap : name of a valid colormap or a valid colormap, optional
            Colormap to use of the velocity field. The default is 'Spectral_r'.
        return_handles : boolean, optional
            Flag to return the figure handles of the generated figures. The default
            is False.
        figsize : tuple, optional
            Dimensions in inches of the figure to generate as a tuple of the form
            (width, height). The default is (15,3)
        fig_type: str, optional
            Type of figure to generate. If 'individual', will produce a three panel 
            figure where the velocity in the X, Y, and Z directions will be displayed. 
            If 'combined', will produce a single panel figure where the X and Y velocities 
            are displayed as vectors overlain a raster of the Z velocity.
        quiver_interval: int, optional
            If fig_type is 'combined', this value will set the spacing of individual plotted
            vectors where the depending on the grid size, generally, the value of this parameters
            will set where vectors originate from. E.g., if set to 1000, then vectors would be located
            where (x,y)  = (1000,1000) | (1000,2000) | (1000,3000), etc.  Default value is 1000.
        shrink: float, optional
            Value to shrink the colorbar as used in the Landlab call to imshow. Default value is 0.75 

        Returns
        -------
        f1 : figure handle, optional
            Handle to the produced figure.

        """
        cvx_EI,cvy_EI,cvz_EI = self._calc_coseismic_vel(event_id)

         # Generate a deep copy of the grid to not modify the stored one
        _grid = copy.deepcopy(self.grid)

        if fig_type=='individual':

            cvx = np.zeros(self.grid.nodes.shape).ravel()
            cvy = np.zeros(self.grid.nodes.shape).ravel()
            cvz = np.zeros(self.grid.nodes.shape).ravel()
            
            # Assign core nodes values in m
            cvx[self.grid.core_nodes]=cvx_EI[self.fault._node_idx]
            cvy[self.grid.core_nodes]=cvy_EI[self.fault._node_idx]
            cvz[self.grid.core_nodes]=cvz_EI[self.fault._node_idx]

            # Assign values to nodes in copied grid
            _grid.add_field('cvx',cvx,at='node')
            _grid.add_field('cvy',cvy,at='node')
            _grid.add_field('cvz',cvz,at='node')
            
            f1= plt.figure(figsize=figsize,layout='tight')
            
            plt.subplot(1,3,1)
            plt.title('Displacement in X')
            _grid.imshow('cvx',shrink=shrink,
                         cmap=cmap,grid_units=('m','m'))
            
            plt.subplot(1,3,2)
            plt.title('Displacement in Y')
            _grid.imshow('cvy',shrink=shrink,
                         cmap=cmap,grid_units=('m','m'))
            
            plt.subplot(1,3,3)
            plt.title('Displacement in Z')
            _grid.imshow('cvz',colorbar_label='(m)',shrink=shrink,
                         cmap=cmap,grid_units=('m','m'))

        elif fig_type=='combined':
            # Prepare Z displacement
            cvz = np.zeros(self.grid.nodes.shape).ravel()
            cvz[self.grid.core_nodes]=cvz_EI[self.fault._node_idx]
            _grid.add_field('cvz',cvz,at='node')

            # Prepare X and Y displacement
            xn = self.grid.x_of_node[self.grid.core_nodes]
            yn = self.grid.y_of_node[self.grid.core_nodes]
            xu = cvx_EI[self.fault._node_idx]
            yu = cvy_EI[self.fault._node_idx]

            idx = (np.mod(xn,quiver_interval)==0) & (np.mod(yn,quiver_interval)==0)

            horz_v = np.sqrt(xu[idx]**2 + yu[idx]**2)
            key_v = np.percentile(horz_v,90)

            f1 = plt.figure(figsize=figsize,layout='tight')
            ax1 = f1.add_subplot(111)

            _grid.imshow('cvz',colorbar_label='Z Displacement (m)',shrink=shrink,
                        cmap=cmap,grid_units=('m','m'))
            q = ax1.quiver(xn[idx],yn[idx],xu[idx],yu[idx],color='k')
            qk = ax1.quiverkey(q,0.05,1.05,key_v,fr'{key_v:.2e} (m)',
                                labelpos='E',coordinates='axes')

        else: 
            raise ValueError("Argument for 'fig_type' must be either 'individual' or 'combined'.")

        if return_handles:
            return f1
    
    ## Elastic dislocation methods
    def _ok(self,xs,ys,zs,xc,yc,d,l,w,dip,strike,ss,ds,ts):
        # Wrapper for okada4py
        d, _, _, _, _ = ok92.okada92(xs, ys, zs, np.array([xc]), np.array([yc]),
                                     np.array([d]), np.array([l]), np.array([w]), 
                                     np.array([dip]), np.array(strike), 
                                     np.array([ss]), np.array([ds]), 
                                     np.array([ts]), self.fault._mu, self.fault._nu)
        d = d.reshape((xs.shape[0], 3))
        return d[:,0],d[:,1],d[:,2]  
    
    def _ok_topo(self,xs,ys,zs,xc,yc,d,l,w,dip,strike,ss,ds,ts,zsr):
        # Wrapper for okada4py
        d, _, _, _, _ = ok92.okada92(xs, ys, zs, np.array([xc]), np.array([yc]),
                                     np.array([d]), np.array([l]), np.array([w]), 
                                     np.array([dip]), np.array(strike), 
                                     np.array([ss]), np.array([ds]), 
                                     np.array([ts]), self.fault._mu, self.fault._nu,zsr)
        d = d.reshape((xs.shape[0], 3))
        return d[:,0],d[:,1],d[:,2]

        
    def _calc_coseismic_vel(self,event_ID):
        # Generates the coseismic velocity field for a single earthquake event
        
        # Determine whether the node list for Okada has been generated
        try:
            self.fault._xs
        except AttributeError:
            if type(self.grid)==RasterModelGrid:
                self.fault._generate_ok_xy_raster()
            elif type(self.grid)==HexModelGrid:
                self.fault._generate_ok_xy_hex()
            self._zs=np.zeros(self.fault._xs.shape)
        # Extract subevent detail list
        SE = self.SubEvents
        # Determine slip rate partition and sign
        ss_part = self.fault._ss[0] / (self.fault._ss[0] + self.fault._ds[0])
        ds_part = self.fault._ds[0] / (self.fault._ss[0] + self.fault._ds[0])
        ss_sign = np.sign(self.fault._ss[0])
        ds_sign = np.sign(self.fault._ds[0])
        # Generate empty containers
        vx=[]; vy=[]; vz=[];
        # Index for components of event
        idx=SE['Event_ID']==event_ID
        # Iterate through subevents
        
        if not(self.fault._topographic_correction):
            for i in range(np.sum(idx)):
                if type(self.fault)==DippingFault:
                    vx0,vy0,vz0=self._ok(self.fault._xs,self.fault._ys,self.fault._zs,SE['Center_X'][idx][i],SE['Center_Y'][idx][i],
                                        SE['Center_Z'][idx][i],SE['Length'][idx][i],SE['Width'][idx][i],
                                        SE['Dip'][idx][i],self.fault._strike[0],SE['Displacement'][idx][i]*ss_part*ss_sign,
                                        SE['Displacement'][idx][i]*ds_part*ds_sign,0)
                elif type(self.fault)==VerticalFault:
                    vx0,vy0,vz0=self._ok(self.fault._xs,self.fault._ys,self.fault._zs,SE['Center_X'][idx][i],SE['Center_Y'][idx][i],
                                        SE['Center_Z'][idx][i],SE['Length'][idx][i],SE['Width'][idx][i],
                                        90.,SE['Strike'][idx][i],SE['Displacement'][idx][i]*ss_part*ss_sign,
                                        SE['Displacement'][idx][i]*ds_part*ds_sign,0)
                    
                vx.append(vx0)
                vy.append(vy0)
                vz.append(vz0)
            cvx=sum(vx)
            cvy=sum(vy)
            cvz=sum(vz)
            
        elif self.fault._topographic_correction:
            # Extract current topographic surface at both nodes and links
            zl_nodes = self.grid.at_node['topographic__elevation'][self.grid.core_nodes].copy()
            zl_links = map_mean_of_link_nodes_to_link(self.grid, 'topographic__elevation').copy()
            zl = np.concat((zl_links,zl_nodes),axis=0).astype(float)

            ## Need to account for if any of the topographic surface being passed to okada4py to use
            ## for the topographic correction is below the upper tip of the fault, if so, this will
            ## cause an error. Original strategy was to simply raise any points that fell below the upper
            ## tip an elevatin just above the tip via replacement, but this was causing strange errors
            ## in cases of extreme subsidence. The more convoluted normalizing and raising method that 
            ## remains was the best alternative option.

            ## This causes cascading NaNs within the topographic__elevation for some reason when
            ## subsidence is high
            # # zl[zl <= -1*self.fault._tip_location[2]] = -1*self.fault._tip_location[2]+0.5

            ## This works consistently with high rates of subsidence. 
            if np.any(zl <= -1*self.fault._tip_location[2]):
                tip = -1*self.fault._tip_location[2]
                orig_rng = np.max(zl) - np.min(zl)
                new_rng = np.max(zl) - (tip + 0.1)
                zl = zl * (new_rng/orig_rng)
                zl += (tip - np.min(zl)) + 0.1

            for i in range(np.sum(idx)):
                if type(self.fault)==DippingFault:
                    vx0,vy0,vz0=self._ok_topo(self.fault._xs,self.fault._ys,self.fault._zs,SE['Center_X'][idx][i],SE['Center_Y'][idx][i],
                                             SE['Center_Z'][idx][i],SE['Length'][idx][i],SE['Width'][idx][i],
                                             SE['Dip'][idx][i],self.fault._strike[0],SE['Displacement'][idx][i]*ss_part*ss_sign,
                                             SE['Displacement'][idx][i]*ds_part*ds_sign,0,zl)
                elif type(self.fault)==VerticalFault:
                    vx0,vy0,vz0=self._ok_topo(self.fault._xs,self.fault._ys,self.fault._zs,SE['Center_X'][idx][i],SE['Center_Y'][idx][i],
                                             SE['Center_Z'][idx][i],SE['Length'][idx][i],SE['Width'][idx][i],
                                             90.,SE['Strike'][idx][i],SE['Displacement'][idx][i]*ss_part*ss_sign,
                                             SE['Displacement'][idx][i]*ds_part*ds_sign,0,zl)
                    
                vx.append(vx0)
                vy.append(vy0)
                vz.append(vz0)
            cvx=sum(vx)
            cvy=sum(vy)
            cvz=sum(vz)
            
        return cvx,cvy,cvz

            

                
        
            
        
            

            
        

    
        
        
        
        
    
        
            
        
        
        
      
        

        
        
        
        
        
        