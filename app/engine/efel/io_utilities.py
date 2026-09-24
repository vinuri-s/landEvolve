#!/usr/bin/env python3
"""
Functions for saving or loading EarthquakeSequences

@author: amforte
"""

from .fault_generator import DippingFault, VerticalFault
from .eq_generator import EarthquakeSequence
from landlab import RasterModelGrid, HexModelGrid
import pickle
import os


def save_eq_sequence(eqObj,file_name):
    '''
    Saves out an instance of EarthquakeSequence as a pickle (.pkl) file,
    if called after generating an earthquake sequence, these will be stored

    Parameters
    ----------
    eqObj : EarthquakeSequence
        The instance of EarthquakeSequence to be saved.
    file_name : str
        File path, including name of the EarthquakeSequence to be saved. Do not
        include a file extension, the function will append '.pkl' to the provided
        file string.

    Returns
    -------
    None.

    '''
    # Save out an EarthquakeSequence instance
    fname = os.path.join(file_name+'.pkl')
    with open(fname,'wb') as f:
        pickle.dump(eqObj,f)
        
def load_eq_sequence(file_name,grid=None,current_model_time=None):
    '''
    Load a saved instance of EarthquakeSequence and stored versions of a fault
    instance and Landlab grid that were used to instantiate the EarthquakeSequence

    Parameters
    ----------
    file_name : str
        Path to saved EarthquakeSequence you wish to load. Do not include the 
        '.pkl' file extension in this path.
    grid : Landlab RasterModelGrid or HexModelGrid, optional
        If you wish to replace the Landlab grid within the saved EarthquakeSequence,
        provide that grid here. This is primarily provided if you wish to restart 
        a run from a previous run. The default is None.
    current_model_time : int, optional
        The new model time to store within the EarthquakeSequence instance if you
        are restarting a model from a previous state, i.e., the model time you 
        wish to start from. The default is None.

    Returns
    -------
    gridObj : Landlab RasterModelGrid or HexModelGrid
        The Landlab grid associated with the loaded EarthquakeSequence. If 
        an alternative grid was provided to the optional 'grid' input, then
        this will be indentical to that input.
    fltObj : DippingFault or VerticalFault
        The instance of either DippingFault or VerticalFault associated with the
        loaded EarthquakeSequence.
    eqObj : EarthquakeSequence
        The saved EarthquakeSequence.

    '''

    # Load a saved EarthquakeSequence instance
    fname = os.path.join(file_name+'.pkl')
    with open(fname,'rb') as f:
        eqObj=pickle.load(f)
    # Extract relevant pieces from saved EarthquakeSequence
    gridObj = eqObj.grid
    fltObj = eqObj.fault
    
    if (grid!=None) & (type(grid)==RasterModelGrid):
        gridObj = grid
        fltObj.grid = grid
        eqObj.grid = grid
        
        # Update current state of  bindings within loaded fault component
        if 'topographic__elevation' in grid.at_node.keys():
            fltObj._elev = grid.at_node['topographic__elevation']
    
        if 'bedrock__elevation' in grid.at_node.keys():
            fltObj._br_elev = grid.at_node['bedrock__elevation']
            
        if 'soil__depth' in grid.at_node.keys():
            fltObj._sd = grid.at_node['soil__depth']
            
        fltObj._tx_disp = grid.at_node['total_x__displacement']
        fltObj._ty_disp = grid.at_node['total_y__displacement']
        fltObj._tz_disp = grid.at_node['total_z__displacement']
        fltObj._vel = grid.at_link['advection__velocity']
        fltObj._u = grid.at_node['vertical__velocity']
        
    elif (grid!=None) & (type(grid)==HexModelGrid):
        gridObj = grid
        fltObj.grid = grid
        eqObj.grid = grid
        
        # Update current state of bindings within loaded fault component
        if 'topographic__elevation' in grid.at_node.keys():
            fltObj._elev = grid.at_node['topographic__elevation']
    
        if 'bedrock__elevation' in grid.at_node.keys():
            fltObj._br_elev = grid.at_node['bedrock__elevation']
            
        if 'soil__depth' in grid.at_node.keys():
            fltObj._sd = grid.at_node['soil__depth']
            
        fltObj._tx_disp = grid.at_node['total_x__displacement']
        fltObj._ty_disp = grid.at_node['total_y__displacement']
        fltObj._tz_disp = grid.at_node['total_z__displacement']
        fltObj._vel = grid.at_link['advection__velocity']
        fltObj._u = grid.at_node['vertical__velocity']  
        
    elif grid!=None:
        raise ValueError('The argument passed to grid was not recognized as either a RasterModelGrid or HexModelGrid')
        
    
    if current_model_time!=None:
        eqObj.current_model_time = current_model_time
    
    return gridObj,fltObj,eqObj
