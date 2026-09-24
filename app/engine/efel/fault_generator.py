#!/usr/bin/env python3
"""
Define fault geometry and drive landscape evolution with 
interseismic creep.

@author: amforte
"""

import numpy as np
import multiprocessing as mp
from landlab import RasterModelGrid, HexModelGrid
from landlab.grid.mappers import map_mean_of_link_nodes_to_link
from landlab.components import AdvectionSolverTVD
import okada4py as ok92
import matplotlib.pyplot as plt
from matplotlib import path
import copy
import os


def _fit_plane(x1,x2,x3,y1,y2,y3,z1,z2,z3):
    """
    Fits equation to a plane that passes through three points of the form
    d = a*x + b*y + c*d

    Parameters
    ----------
    x1 : float
        x-coordinate of point 1.
    x2 : float
        x-coordinate of point 2.
    x3 : float
        x-coordinate of point 3.
    y1 : float
        y-coordinate of point 1.
    y2 : float
        y-coordinate of point 2.
    y3 : float
        y-coordinate of point 3.
    z1 : float
        z-coordinate of point 1.
    z2 : float
        z-coordinate of point 2.
    z3 : float
        z-coordinate of point 3.

    Returns
    -------
    a : float
        Coefficient on x term.
    b : float
        Coefficent on y term.
    c : float
        Coefficeint on z term.
    d : float
        Value.

    """
    v1 = np.array([x2-x1,y2-y1,z2-z1]).reshape((1,3))
    v2 = np.array([x3-x1,y3-y1,z3-z1]).reshape((1,3))
    norm=np.cross(v1,v2)
    a=norm[0][0]; b=norm[0][1]; c=norm[0][2];

    d = (a * x1 + b * y1 + c * z1)
    return a,b,c,d

def _ok(xs,ys,zs,xc,yc,d,l,w,dip,strike,ss,ds,ts,mu,nu):
    """
    Wrapper for okada4py

    Parameters
    ----------
    xs : array of floats
        x-coordinate of recievers.
    ys : array of floats
        y-coordnate of recievers.
    zs : array of floats
        z-coordinate of recievers, should generally be zero.
    xc : float
        x-coordinate of the center of the dislocation.
    yc : float
        y-coordinate of the center of the dislocation.
    d : float
        depth of the center of the dislocation.
    l : float
        length of the dislocation in the strike direction.
    w : float
        width of the dislocation along the dip of the dislocation.
    dip : float
        dip of the dislocation.
    strike : float
        strike of the dislocation in azimuth using right hand rule.
    ss : float
        strike-slip component of dislocation movement.
    ds : float
        dip-slip component of dislocation movement.
    ts : float
        tensile component of dislocation movement.
    mu : float
        Shear modulus (Pa).
    nu : float
        Poissons ratio.

    Returns
    -------
    array of floats
        velocity in x-direction.
    array of floats
        velocity in y-direction.
    array of floats
        velocity in z-direction.

    """
    d, _, _, _, _ = ok92.okada92(xs, ys, zs, np.array([xc]), np.array([yc]),
                                 np.array([d]), np.array([l]), np.array([w]), 
                                 np.array([dip]), np.array(strike), 
                                 np.array([ss]), np.array([ds]), 
                                 np.array([ts]), mu, nu)
    d = d.reshape((xs.shape[0], 3))
    return d[:,0],d[:,1],d[:,2]

def _ok_topo(xs,ys,zs,xc,yc,d,l,w,dip,strike,ss,ds,ts,mu,nu,zsr):
    """
    Wrapper for okada4py including topographic correction

    Parameters
    ----------
    xs : array of floats
        x-coordinate of recievers.
    ys : array of floats
        y-coordnate of recievers.
    zs : array of floats
        z-coordinate of recievers, should generally be zero.
    xc : float
        x-coordinate of the center of the dislocation.
    yc : float
        y-coordinate of the center of the dislocation.
    d : float
        depth of the center of the dislocation.
    l : float
        length of the dislocation in the strike direction.
    w : float
        width of the dislocation along the dip of the dislocation.
    dip : float
        dip of the dislocation.
    strike : float
        strike of the dislocation in azimuth using right hand rule.
    ss : float
        strike-slip component of dislocation movement.
    ds : float
        dip-slip component of dislocation movement.
    ts : float
        tensile component of dislocation movement.
    mu : float
        Shear modulus (Pa).
    nu : float
        Poissons ratio.
    zsr : array of floats
        z-coordinate of topographic surface

    Returns
    -------
    array of floats
        velocity in x-direction.
    array of floats
        velocity in y-direction.
    array of floats
        velocity in z-direction.

    """
    # Wrapper for okada4py
    d, _, _, _, _ = ok92.okada92(xs, ys, zs, np.array([xc]), np.array([yc]),
                                 np.array([d]), np.array([l]), np.array([w]), 
                                 np.array([dip]), np.array(strike), 
                                 np.array([ss]), np.array([ds]), 
                                 np.array([ts]), mu, nu, zsr)
    d = d.reshape((xs.shape[0], 3))
    return d[:,0],d[:,1],d[:,2]    


class DippingFault:
    """ Fault geometry and interseismic creep using elastic dislocations

     This component generates a fault with an arbitrary geometry as specified by
     the user and then allows the calculation of surface deformation assuming
     interseismic creep where the velocity calculation uses an elastic dislocation.
     This component includes a wrapper for 'okada4py', which implements the 
     3D solution of Okada, 1992 for dislocation in an elastic half space. A separate
     installation and compilation of okada4py is required for this component to 
     function.
     
     There is no specific requirement that the dimensions or extent of the fault
     are confined to, or even overlap with, the provided Landlab grid, but x-y 
     coordinates for the fault are specified with respect to the Landlab grid
     coordinate system.

     The component is designed for use in conjunction with the EarthquakeSequence component,
     but strictly does not require that you pair it with an earthquake sequence if you
     want to drive a model with interseismic creep only.

     Examples
     --------


     References
     ----------

     **Required Software Citation(s) Specific to this Component**

     Romain Jolivet. (2024). jollivetr/okada4py: First release (1.0.0). Zenodo.
     https://doi.org/10.5281/zenodo.14170827

     **Additional References**

     Okada, Y. (1992), Internal deformation due to shear and tensile faults in a
     half-space, Bulletin of the Seismological Society of America, 82(2), 1018-1040
     
     Langer, L., Ragon, T., Sladen, A., Tromp, J. (2020), Impact of topography
     on earthquake static slip estimates, Tectonophysics, 791, 228566

    """

    _name = 'DippingFault'

    _time_units = 'y'

    _unit_agnostic = False 
    
    _info = {
        "advection__velocity":{
            "dtype":float,
            "intent":"out",
            "optional":False,
            "units":"m/y",
            "mapping":"link",
            "doc":"Link-parallel advection velocity"
            },
        "vertical__velocity":{
            "dtype":float,
            "intent":"out",
            "optional":False,
            "units":"m/y",
            "mapping":"node",
            "doc":"Vertical velocity"
            },
        "total_x__displacement":{
            "dtype":float,
            "intent":"out",
            "optional":False,
            "units":"m",
            "mapping":"node",
            "doc":"Total accumulated displacement in x direction"},
        "total_y__displacement":{
            "dtype":float,
            "intent":"out",
            "optional":False,
            "units":"m",
            "mapping":"node",
            "doc":"Total accumulated displacement in y direction"},
        "total_z__displacement":{
            "dtype":float,
            "intent":"out",
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

    def __init__(self, grid, fields_to_advect=['bedrock__elevation'],
                 length=10000, 
                 width=1000, dip=45, strike=0, tip_location=[0,0,10],
                 ss_rate=0.0, ds_rate=0.001, u_rate=0.0, 
                 mu=3.3e10, nu=0.25,
                 panel_types=None,  
                 fault_dx=100,
                 seismogenic_zone=[1000,5000],
                 slip_rate_function='boxcar',
                 fraction_blunt=0.5,
                 along_fault_segments=11,
                 fault_type='Interplate_DS',
                 topographic_correction=False,
                 parallel=False,num_cores=None):
        """
        

        Parameters
        ----------
        grid : RasterModelGrid
            A landlab grid.
        fields_to_advect : list of str, optional
            List of names of fields to be advected. The default is ['bedrock__elevation'].
        length : float, optional
            Along-strike length of fault (m). The default is 10000.
        width : float or list of floats, optional
            Along-dip width of fault panels, starting from the upper tip of the fault
            and progressing down-dip (m). The default is 1000.
        dip : float or list of floats, optional
            Dip of each fault panel, must be the same number of entries as provided
            to 'width' (degrees). The default is 45.
        strike : float, optional
            Strike of fault in azimuth, follows right hand rule (degrees). The default is 0.
        tip_location : list of floats, optional
            X, Y, Z and location of center of fault tip. X and Y are in the same coordinates
            as the input landlab grid, but it does not have to lie within the landlab grid. 
            Z is depth and is positive downward. Depth cannot be set to a value above the zero 
            surface, so depths cannot be negative. (m) The default is [0,0,10].
        ss_rate : float, optional
            Strike-slip component of fault slip rate. (m/yr) The default is 0.0.
        ds_rate : float, optional
            Dip-slip component of fault slip rate. Positive values imply thrust motion.
            (m/yr) The default is 0.001.
        u_rate: float, optional
            Background vertical uplift rate to apply across the domain. Velocities calculated
            from the elastic dislocations will be superimposed on this rate. (m/yr)
            The default is 0.0.
        mu : float, optional
            Shear modulus. (Pa) The default is 3.3e10. It is not recommended that you change
            this value.
        nu : float, optional
            Poissons ratio. The default is 0.25. It is not recommended that you change this
            value
        panel_types : str or list of str, optional
            Behavior of each fault panel, valid entries are "A" indicating the
            panel should be treated as above the seismogenic zone, "C" indicating
            the panel should be treated as within the seismogenic zone, or "I"
            indicating that the panel should be treated as below the seismogenic zone.
            Panels above the seismogenic zone can fail during earthquakes, but earthquakes cannot
            nucleate within them. Earthquakes can nucleate within the seismogenic zone
            Panels below the seismogenic zone will creep at the fault rate. If no entry
            is provided, then the behavior of fault panels will be determined by the input
            seismogenic zone depths given to "seismogenic_zone". Number of entries within the list
            must equal the number of values provided to "width" and "dip". The default is None.
            Providing None uses the depths provided to "seismogenic_zone" to assign panel
            types to each fault panel.
        fault_dx : int, optional
            Horizontal increment for interpolating the fault surface. Within the fault component,
            this is primarily used for plotting, but it is also used in the related EarthquakeSequence
            and CoseismicLandslider component to produce a "grid" of points on the fault to calculate
            various quantities. As such, increasing this value will increase the resolution of these 
            calculations but will increase computation time.  (m) The default is 100.
        seismogenic_zone : list of floats, optional
            The top and bottom of the seismogenic zone given as positive depths.
            This value is effectively ignored if panel behaviors are defined by 
            "panel_types" (m) The default is [1000,5000].
        slip_rate_function : str, optional
            Function that defines how the slip rate varies as a function of fault length,
            options are:
                "boxcar" - slip-rate is constant along the entire length of the fault, the 
                    stored parameter _slip_rate and _mean_slip_rate will be equal and will be 
                    sqrt(ss_rate^2 + ds_rate^2)
                "parabolic" - slip-rate will have a parabolic shape along the length of the fault
                    reaching a maximum at the center of the fault and zeros at the tips. The maximum
                    will be given by sqrt(ss_rate^2 + ds_rate^2) and stored as _slip_rate, but 
                    _mean_slip_rate will be the average of the function, where the the choice of 
                    fault_dx will control the spacing of the points to approximate the mean of the
                    function.
                "blunt_parabolic" - slip-rate will have a partial parabolic shape along the length 
                    of the fault reaching a maximum at the center of the fault and zeros at the tips.
                    In detail, a portion of the fault, specified as a fraction of the length given by
                    the parameter 'fraction_blunt', will be at the maximum and then will decrease
                    via parabolic functions to zero at the tips. The maximum will be given by 
                    sqrt(ss_rate^2 + ds_rate^2) and stored as _slip_rate, but _mean_slip_rate 
                    will be the average of the function, where the the choice of fault_dx will 
                    control the spacing of the points to approximate the mean of the function.
                "triangular" - slip-rate will have a triangular shape along the length of the fault
                    reaching a maximum at the center of the fault and zeros at the tips. The maximum
                    will be given by sqrt(ss_rate^2 + ds_rate^2) and stored as _slip_rate, but 
                    _mean_slip_rate will be the average of the function, where the the choice of 
                    fault_dx will control the spacing of the points to approximate the mean of the
                    function.
                "blunt_triangular" - slip-rate will have a partial triangular shape along the length 
                    of the fault reaching a maximum at the center of the fault and zeros at the tips.
                    In detail, a portion of the fault, specified as a fraction of the length given by
                    the parameter 'fraction_blunt', will be at the maximum and then will decrease
                    via triangular functions to zero at the tips. The maximum will be given by 
                    sqrt(ss_rate^2 + ds_rate^2) and stored as _slip_rate, but _mean_slip_rate 
                    will be the average of the function, where the the choice of fault_dx will 
                    control the spacing of the points to approximate the mean of the function.  
            The default is "boxcar".
        fraction_blunt : float, optional
            The fraction of the total length to be at the maximum slip-rate if slip_rate_function is
            either "blunt_parabolic" or "blunt_triangular". Otherwise this parameter is unused.
            The default is 0.5.
        along_fault_segments : int, optional
            If the slip_rate_function is not a "boxcar", it is necessary to break the interseismic
            panels into equal "segments" to have the along-strike variation in slip-rate approximated
            in the interseismic velocity. This parameter specifies the number of segments to split the 
            fault into. Larger numbers will more faithfully represent the along-strike variation in slip-rate
            but will increase in computation time. This can be an even or odd number, but odd numbers tend
            to produce more smoothly varying approximations.
            The default value is 11.
        fault_type : str, optional
            The type of fault for earthquake scaling relationships. Valid values arguments are:
                "Interplate_DS"  - interplate dip-slip fault,
                "SCR_DS" - stable continental region dip-slip fault,
                "Interplate_SS" - interplate strike-slip fault,
                "SCR_SS" - stable continental region strike-slip fault.
            The default is 'Interplate_DS'.
        topographic_correction : boolean, optional
            If False (default), uplift and advection velocities used to deform the surface will
            be calculated at a "zero surface" regardless of the actual topography. If set to True
            then the current topography at each timestep will be used to "correct" the uplift
            and advection velocities. This is not formally changing anything about the fault or
            the solution of the elastic half space, it's effectively just accounting for greater
            distance between the dislocation and the "observer" in the form of individual spots in
            the topography.
        parallel : boolean, optional
            Flag to turn on parallelization of the calculation of interseismic
            displacements. If this is set to true, it is essential that in any script using 
            the relevant fault component that it is protected by a guard, meaning that at 
            minimum any portion of the script that invoked the original instantation should be 
            preceded by an 'if __name__ == "__main__":'statement with the instantiation under 
            this guard. Best practice would be to place the entirety of the script after imports
            under the guard. Note, running in parallel is only considered if the slip_rate_function 
            is something other than "boxcar". Turning on parallel processing for the fault component
            is also really only needed if topographic_correction is set to True because otherwise the
            interseismic velocities are only calculated once.
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
        
        # Check values
        if type(grid)==RasterModelGrid:
            pass
        elif type(grid)==HexModelGrid:
            pass
        else:
            raise TypeError('Provided Landlab grid must be either a raster or hex.')
            
        # Check that fault panels are fully parameterized
        if np.logical_and(len(dip)==len(width),panel_types==None):
            pass
        elif np.logical_and(len(dip)==len(width),len(width)==len(panel_types)):
            pass
        else:
            raise ValueError('Number of elements of "width", "dip", and "panel_types" arguments must be the same')
        
        
        self.grid = grid
        self.fields_to_advect = fields_to_advect
        # Set static values
        self._mu = mu # shear modulus
        self._nu = nu # poissons ratio
        self._fault_dx = fault_dx
        self._topographic_correction = topographic_correction
        # Use setters for properties that require validation
        self.length = length
        self.width = width
        self.dip = dip
        self.strike = strike
        self.tip_location = tip_location
        self.ss = ss_rate
        self.ds = ds_rate
        self.bu = u_rate
        self.seismogenic_zone = seismogenic_zone
        self.slip_rate_function = slip_rate_function
        self.fraction_blunt = fraction_blunt
        self.along_fault_segments = along_fault_segments
        self.panel_types = panel_types
        self.fault_type = fault_type
        self.parallel = parallel
        self.num_cores = num_cores

        
        # Extract needed fields from grid
        if 'topographic__elevation' in self.grid.at_node.keys():
            self._elev = self.grid.at_node['topographic__elevation']
            
        if 'bedrock__elevation' in self.grid.at_node.keys():
            self._br_elev = self.grid.at_node['bedrock__elevation']
            
        if 'soil__depth' in self.grid.at_node.keys():
            self._sd = self.grid.at_node['soil__depth']
            
        # Generate empty field for total horizontal displacements
        if 'total_x__displacement' not in self.grid.at_node.keys():
            self._tx_disp = self.grid.add_zeros('total_x__displacement',at='node',clobber=True)
        else:
            self._tx_disp = self.grid.at_node['total_x__displacement']
            
        if 'total_y__displacement' not in self.grid.at_node.keys():
            self._ty_disp = self.grid.add_zeros('total_y__displacement',at='node',clobber=True)
        else:
            self._ty_disp = self.grid.at_node['total_y__displacement']
            
        if 'total_z__displacement' not in self.grid.at_node.keys():
            self._tz_disp = self.grid.add_zeros('total_z__displacement',at='node',clobber=True)
        else:
            self._tz_disp = self.grid.at_node['total_z__displacement']
            
        
        # Determine the slip rate, this only considers strike slip or dip slip 
        # mechanisms, tensile failures, though possible to generate with the Okada
        # codes, are not defined for other earthquake details that use the slip rate
        #
        # This also considers whether there is a "shape" imposed on the slip rate
        # as a function of distance along the trace of the fault
        self._slip_rate = np.sqrt(self._ss**2 + self._ds**2)
        if self._slip_rate_function == 'boxcar':
            self._boxcar()
        elif self._slip_rate_function == 'parabolic':
            self._parabolic()
            self._discretize_slip_rate()
        elif self._slip_rate_function == 'blunt_parabolic':
            self._blunt_parabolic()
            self._discretize_slip_rate()
        elif self._slip_rate_function == 'triangular':
            self._triangular()
            self._discretize_slip_rate()
        elif self._slip_rate_function == 'blunt_triangular':
            self._blunt_triangular()
            self._discretize_slip_rate()
        
        # Finish running required methods, these are setup as methods as
        # they get called multiple times depending on inputs
        self._calc_panel_geoms()
        self._calc_fault_surface()
        self._generate_ok_grid()
        self._establish_advection_and_uplift()
  
    @property
    def length(self):
        """
        Length of fault along strike

        """
        return self._length
    
    @length.setter
    def length(self,new_length):
        if (type(new_length)!=np.ndarray) & (type(new_length)==list):
            self._length=np.array(new_length).astype(float)
        elif (type(new_length)!=np.ndarray) & (type(new_length)!=list):
            self._length=np.array([new_length]).astype(float)
        else:
            self._length=new_length.astype(float)
            
        if len(self._length)>1:
            raise ValueError('Entry provided for "length" must be a single value or single element array')
            
    @property
    def width(self):
        """
        Width of fault panels down dip, in direction of dip

        """
        return self._width
    
    @width.setter
    def width(self,new_width):
        if (type(new_width)!=np.ndarray) & (type(new_width)==list):
            self._width=np.array(new_width).astype(float)
        elif (type(new_width)!=np.ndarray) & (type(new_width)!=list):
            self._width=np.array([new_width]).astype(float)
        else:
            self._width=new_width.astype(float)
            
    @property
    def dip(self):
        """
        Dip of fault panels

        """
        return self._dip
    
    @dip.setter
    def dip(self,new_dip):
        if (type(new_dip)!=np.ndarray) & (type(new_dip)==list):
            self._dip=np.array(new_dip).astype(float)
        elif (type(new_dip)!=np.ndarray) & (type(new_dip)!=list):
            self._dip=np.array([new_dip]).astype(float)
        else:
            self._dip=new_dip.astype(float)
            
    @property
    def strike(self):
        """
        Strike of fault as azimuth using right hand rule

        """
        return self._strike
    
    @strike.setter
    def strike(self,new_strike):
        if (type(new_strike)!=np.ndarray) & (type(new_strike)==list):
            self._strike=np.array(new_strike).astype(float)
        elif (type(new_strike)!=np.ndarray) & (type(new_strike)!=list):
            self._strike=np.array([new_strike]).astype(float)            
        else:
            self._strike=new_strike.astype(float)
            
        if len(self._strike) > 1:
            raise ValueError('Entry provided for "strike" must be a single value or single element array')
            
    @property
    def tip_location(self):
        """
        Location of center of fault tip as x, y, z coordinate

        """
        return self._tip_location
    
    @tip_location.setter
    def tip_location(self,new_tip_location):
        if (type(new_tip_location)!=np.ndarray) & (len(new_tip_location)==3):
            self._tip_location=np.array(new_tip_location).astype(float)
        elif len(new_tip_location)==3:
            if new_tip_location[2] < 0:
                raise ValueError('Third item in "tip_location" which sets the upper fault tip depth must be greater than or equal to zero')
            else:
                self._tip_location=new_tip_location.astype(float)
        else:
            raise ValueError('Entry provided for "tip_location" must be an array or list with 3 entries')
            
            
    @property
    def ss(self):
        """
        Slip-rate of strike-slip component in m/yr

        """
        return self._ss
    
    @ss.setter
    def ss(self,new_ss):
        if (type(new_ss)!=np.ndarray) & (type(new_ss)==list):
            self._ss=np.array(new_ss).astype(float)
        elif (type(new_ss)!=np.ndarray) & (type(new_ss)!=list):
            self._ss=np.array([new_ss]).astype(float)            
        else:
            self._ss=new_ss.astype(float)
            
    @property
    def ds(self):
        """
        Slip-rate of dip-slip component in m/y

        """
        return self._ds
    
    @ds.setter
    def ds(self,new_ds):
        if (type(new_ds)!=np.ndarray) & (type(new_ds)==list):
            self._ds=np.array(new_ds).astype(float)
        elif (type(new_ds)!=np.ndarray) & (type(new_ds)!=list):
            self._ds=np.array([new_ds]).astype(float)            
        else:
            self._ds=new_ds.astype(float)
            
    @property
    def bu(self):
        """
        Background uplift rate in m/y

        """
        return self._bu
    
    @bu.setter
    def bu(self,new_bu):
        if (type(new_bu)!=np.ndarray) & (type(new_bu)==list):
            self._bu=np.array(new_bu).astype(float)
        elif (type(new_bu)!=np.ndarray) & (type(new_bu)!=list):
            self._bu=np.array([new_bu]).astype(float)            
        else:
            self._bu=new_bu.astype(float)
        

    @property
    def slip_rate_function(self):
        return self._slip_rate_function
    
    @slip_rate_function.setter
    def slip_rate_function(self,new_slip_rate_func):
        if (new_slip_rate_func=='boxcar') | (new_slip_rate_func=='parabolic') | (new_slip_rate_func=='blunt_parabolic') | (new_slip_rate_func=='triangular') | (new_slip_rate_func=='blunt_triangular'):
            self._slip_rate_function = new_slip_rate_func
        else:
            raise ValueError('Entry provided for "slip_rate_function" must be "boxcar", "parabolic", "blunt_parabolic", "triangular", or "blunt_triangular"')
    
    @property
    def fraction_blunt(self):
        return self._fraction_blunt
    
    @fraction_blunt.setter
    def fraction_blunt(self,new_fraction_blunt):
        if (new_fraction_blunt > 0) & (new_fraction_blunt < 1):
            self._fraction_blunt = new_fraction_blunt
        else:
            raise ValueError('Entry provided to "fraction_blunt" must be between 0 and 1')
    
    @property
    def along_fault_segments(self):
        return self._along_fault_segments
    
    @along_fault_segments.setter
    def along_fault_segments(self,new_along_fault_seg):
        self._along_fault_segments = int(new_along_fault_seg)
        
   
    @property
    def panel_types(self):
        """
        List of strings defining fault panels as above the seismogenic zone "A",
        within the seismogenic zone "C", or below the seismogenic zone "I"

        """
        return self._panel_types
    
    @panel_types.setter
    def panel_types(self,new_panel_types):
        allowed_elements = {'A','C','I'}
        if new_panel_types==None:
            # Calculate  and store temporary number of panels
            self._num_panels=len(self.width)
            # Set panel types to none temporarily
            self._panel_types=None
            self._calc_panel_geoms()
            self._calc_fault_surface()
            self._calc_seismogenic_panels()
        elif all(item in allowed_elements for item in new_panel_types):
            self._panel_types = new_panel_types
        else:
            raise ValueError('Entries provided to "panel_types" must only be "A", "C", or "I"')
            
    @property
    def fault_type(self):
        """
        String defining the type of fault

        """
        return self._fault_type
    
    @fault_type.setter
    def fault_type(self,new_fault_type):
        if (new_fault_type=='Interplate_DS') | (new_fault_type=='Interplate_SS') | (new_fault_type=='SCR_DS') | (new_fault_type=='SCR_SS'):
            self._fault_type = new_fault_type
        else:
            raise ValueError('Entry provided for "fault_type" must be "Interplate_DS", "Interplate_SS", "SCR_DS", or "SCR_SS"')
        
    @property
    def seismogenic_zone(self):
        """
        Numpy array defining top and bottom of seismogenic zone

        """
        return self._seismogenic_zone
    
    @seismogenic_zone.setter
    def seismogenic_zone(self,new_seismogenic_zone):
        if (len(new_seismogenic_zone)==2) & (new_seismogenic_zone[0] < new_seismogenic_zone[1]):
            self._seismogenic_zone = new_seismogenic_zone
        else:
            raise ValueError('Entry provided for "seismogenic_zone" must be a list or array with 2 elements that increase monotonically')
 
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

    def _calc_panel_geoms(self):
        '''
        Calculate geometry components of individual fault panels including
        dimensions, projected locations of corners and center at the surface,
        and areas.
        

        '''
        # Calculate number of panels
        self._num_panels=len(self.width)
        # Panel Parallel Coordinates
        self._width_h=np.zeros(self._num_panels)
        self._width_v=np.zeros(self._num_panels)
        # Panel Center Locations
        self._xc=np.zeros(self._num_panels)
        self._yc=np.zeros(self._num_panels)
        self._zc=np.zeros(self._num_panels)
        # Panel Bend Locations
        self._x_tops=np.zeros(self._num_panels)
        self._y_tops=np.zeros(self._num_panels)
        self._z_tops=np.zeros(self._num_panels)
        self._x_bots=np.zeros(self._num_panels)
        self._y_bots=np.zeros(self._num_panels)
        self._z_bots=np.zeros(self._num_panels)
        
        # Convert strike to dip direction
        dip_direction = self.strike + 90
        if dip_direction > 360:
            dip_direction = dip_direction - 360
        self._dip_direction=dip_direction
        
        # Calculate the horizontal and vertical components of the panel widths
        for i in range(self._num_panels):
            self._width_h[i]=np.cos(np.radians(self._dip[i]))*self._width[i]
            self._width_v[i]=np.sin(np.radians(self._dip[i]))*self._width[i]
        
        # Calculate areas
        self._panel_areas=self._width*self._length
        
        # Calculate cross section positions
        for i in range(self._num_panels):
            if i==0:
                self._x_tops[i]=self._tip_location[0]
                self._y_tops[i]=self._tip_location[1]
                self._z_tops[i]=self._tip_location[2]
            else:
                self._x_tops[i]=self._x_bots[i-1]
                self._y_tops[i]=self._y_bots[i-1]
                self._z_tops[i]=self._z_bots[i-1]
                
            # Calculate positions for each panel
            self._x_bots[i]=(np.sin(np.radians(self._dip_direction[0]))*self._width_h[i]) + self._x_tops[i]
            self._y_bots[i]=(np.cos(np.radians(self._dip_direction[0]))*self._width_h[i]) + self._y_tops[i]
            self._z_bots[i]=self._z_tops[i]+self._width_v[i]
            self._xc[i]=(np.sin(np.radians(self._dip_direction[0]))*self._width_h[i]/2) + self._x_tops[i]
            self._yc[i]=(np.cos(np.radians(self._dip_direction[0]))*self._width_h[i]/2) + self._y_tops[i]
            self._zc[i]=self._z_tops[i]+self._width_v[i]/2
            
        # Calculate boundaries of panels
        self._panel_boundaries=[]
        for i in range(self._num_panels):
            x1=self._x_tops[i] + (np.sin(np.radians(self._strike[0]))*self._length[0]/2)
            y1=self._y_tops[i] + (np.cos(np.radians(self._strike[0]))*self._length[0]/2)
            x2=self._x_bots[i] + (np.sin(np.radians(self._strike[0]))*self._length[0]/2)
            y2=self._y_bots[i] + (np.cos(np.radians(self._strike[0]))*self._length[0]/2)            
            x3=self._x_bots[i] - (np.sin(np.radians(self._strike[0]))*self._length[0]/2)
            y3=self._y_bots[i] - (np.cos(np.radians(self._strike[0]))*self._length[0]/2)
            x4=self._x_tops[i] - (np.sin(np.radians(self._strike[0]))*self._length[0]/2)
            y4=self._y_tops[i] - (np.cos(np.radians(self._strike[0]))*self._length[0]/2)
            
            x_bounds=np.array([x1,x2,x3,x4,x1])
            y_bounds=np.array([y1,y2,y3,y4,y1])
            self._panel_boundaries.append([x_bounds,y_bounds])
        
        # Calculate piecewise locations of fault panels in xsections
        self._fx=np.concat(([0],np.cumsum(self._width_h)),axis=0)
        self._fz=np.concat(([self._z_tops[0]],self._z_tops[0]+np.cumsum(self._width_v)),axis=0)
        
        # Calculate the total area of the fault that can experience rupture, this
        # includes panel areas that are considered above ("A") the seismogenic depth
        # and within ("C") the seismogenic depth.
        if self._panel_types!=None:
            total_area=[]
            total_width=[]
            for i in range(self._num_panels):
                # if (self._panel_types[i]=='A') | (self._panel_types[i]=='C'):
                #     total_area.append(self._panel_areas[i])
                if self._panel_types[i]=='C':
                    total_area.append(self._panel_areas[i])
                    total_width.append(self._panel_areas[i]/self._length)
            self._total_area=sum(total_area)
            self._total_width=sum(total_width)
            self._total_length=sum(self._length) # This is to be similar to vertical faults
                               
    def _calc_fault_surface(self):
        '''
        Calculate a gridded version of the fault surface in both fault aligned
        coordinates and Landlab grid coordinates. Also fits a plane to each
        fault panel so that positions on the fault plane can be easily querried.


        '''
        # Interpolate along x-section line
        fix = np.arange(0,self._fx.max(),self._fault_dx)
        fiz = np.interp(fix,self._fx,self._fz)
        fiy = np.arange(-self._length[0]/2,self._length[0]/2,self._fault_dx)
        
        # Fault top tip centered coordinates
        self._FX,self._FY = np.meshgrid(fix,fiy)
        self._FZ = np.tile(fiz,(len(fiy),1))
        
        # Rotate into model coordinates
        self._MX = (self._FX * np.cos(np.radians(self.strike[0])) + self._FY * np.sin(np.radians(self.strike[0]))) + self.tip_location[0]
        self._MY = (-self._FX * np.sin(np.radians(self.strike[0])) + self._FY * np.cos(np.radians(self.strike[0]))) + self.tip_location[1]
        
        # Also define plane equations for each panel
        fault_plane_coeffs=[]
        for i in range(self._num_panels):
            xb = self._panel_boundaries[i][0]
            yb = self._panel_boundaries[i][1]
            x_ur = xb[0]; x_lr=xb[1]; x_ll=xb[2]; x_ul=xb[3]
            y_ur = yb[0]; y_lr=yb[1]; y_ll=yb[2]; y_ul=yb[3]
            z_ur =self._fz[i]; z_lr=self._fz[i+1]; z_ll=self._fz[i+1]; z_ul=self._fz[i]
 
            a,b,c,d=_fit_plane(x_ur,x_ul,x_lr,y_ur,y_ul,y_lr,z_ur,z_ul,z_lr)
            fault_plane_coeffs.append(np.array([a,b,c,d]))
        self._fault_plane_coeffs=fault_plane_coeffs
        
    def _boxcar(self):
        self._mean_slip_rate = self._slip_rate
        fy = np.arange(-self._length/2,self._length/2,self._fault_dx)
        self._slip_rate_along_fault = np.full(fy.shape,self._slip_rate)
        self._ss_rate_along_fault = np.full(fy.shape,self._ss)
        self._ds_rate_along_fault = np.full(fy.shape,self._ds)
        
    def _parabolic(self):
        # Solve for coefficient such that peak of parabola is the slip_rate
        # and it reaches 0 at half length
        a = self._slip_rate / ((self._length/2)**2)
        a_ss = self._ss / ((self._length/2)**2)
        a_ds = self._ds / ((self._length/2)**2)        
        # Fault length aligend coordinates
        fy = np.arange(-self._length/2,self._length/2,self._fault_dx)
        self._slip_rate_along_fault = -a*fy**2+self._slip_rate
        self._ss_rate_along_fault = -a_ss*fy**2+self._ss
        self._ds_rate_along_fault = -a_ds*fy**2+self._ds        
        # Calculate mean slip rate
        self._mean_slip_rate = np.array([np.mean(self._slip_rate_along_fault)])
        
    def _blunt_parabolic(self):
        # Define length of blunt section
        hl_of_flat = (self._length * self._fraction_blunt)/2 
        # Define parabolic constants
        a = self._slip_rate / (-(hl_of_flat)**2 + (self._length/2)**2)
        k = a * (self._length/2)**2
        a_ss = self._ss/ (-(hl_of_flat)**2 + (self._length/2)**2)
        k_ss = a_ss * (self._length/2)**2
        a_ds = self._ds / (-(hl_of_flat)**2 + (self._length/2)**2)
        k_ds = a_ds * (self._length/2)**2        
        # Fault length aligned coordinates
        fy = np.arange(-self._length/2,self._length/2,self._fault_dx)  
        # Piecewise along fault slip rate
        self._slip_rate_along_fault = np.zeros(fy.shape)
        self._slip_rate_along_fault[fy < -hl_of_flat] = -a*(fy[fy < - hl_of_flat])**2 + k
        self._slip_rate_along_fault[fy > hl_of_flat] = -a*(fy[fy > hl_of_flat])**2 + k
        self._slip_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._slip_rate
        self._ss_rate_along_fault = np.zeros(fy.shape)
        self._ss_rate_along_fault[fy < -hl_of_flat] = -a_ss*(fy[fy < - hl_of_flat])**2 + k_ss
        self._ss_rate_along_fault[fy > hl_of_flat] = -a_ss*(fy[fy > hl_of_flat])**2 + k_ss
        self._ss_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._ss
        self._ds_rate_along_fault = np.zeros(fy.shape)
        self._ds_rate_along_fault[fy < -hl_of_flat] = -a_ds*(fy[fy < - hl_of_flat])**2 + k_ds
        self._ds_rate_along_fault[fy > hl_of_flat] = -a_ds*(fy[fy > hl_of_flat])**2 + k_ds
        self._ds_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._ds
        # Calculate mean slip rate
        self._mean_slip_rate = np.array([np.mean(self._slip_rate_along_fault)])
        
    def _triangular(self):
        # Fault length aligned coordinates
        fy = np.arange(-self._length/2,self._length/2,self._fault_dx) 
        # Piecewise along fault slip rate
        self._slip_rate_along_fault = np.zeros(fy.shape)
        self._slip_rate_along_fault[fy >= 0] = (-self._slip_rate/ (self._length/2)) * fy[fy >= 0] + self._slip_rate 
        self._slip_rate_along_fault[fy < 0] = (self._slip_rate/ (self._length/2)) * fy[fy < 0] + self._slip_rate
        self._ss_rate_along_fault = np.zeros(fy.shape)
        self._ss_rate_along_fault[fy >= 0] = (-self._ss/ (self._length/2)) * fy[fy >= 0] + self._ss 
        self._ss_rate_along_fault[fy < 0] = (self._ss/ (self._length/2)) * fy[fy < 0] + self._ss
        self._ds_rate_along_fault = np.zeros(fy.shape)
        self._ds_rate_along_fault[fy >= 0] = (-self._ds/ (self._length/2)) * fy[fy >= 0] + self._ds 
        self._ds_rate_along_fault[fy < 0] = (self._ds/ (self._length/2)) * fy[fy < 0] + self._ds
        # Calculate mean slip rate
        self._mean_slip_rate = np.array([np.mean(self._slip_rate_along_fault)]) 
        
    def _blunt_triangular(self):
        # Define length of blunt section
        hl_of_flat = (self._length * self._fraction_blunt)/2 
        # Solve for coefficients
        m = self._slip_rate / (hl_of_flat - self._length/2)
        b = -m*(self._length/2)
        m_ss = self._ss / (hl_of_flat - self._length/2)
        b_ss = -m_ss*(self._length/2)
        m_ds= self._ds / (hl_of_flat - self._length/2)
        b_ds = -m_ds*(self._length/2)
        # Fault length aligned coordinates
        fy = np.arange(-self._length/2,self._length/2,self._fault_dx)  
        # Piecewise along fault slip rate
        self._slip_rate_along_fault = np.zeros(fy.shape)
        self._slip_rate_along_fault[fy < -hl_of_flat] = -m*(fy[fy < - hl_of_flat]) + b
        self._slip_rate_along_fault[fy > hl_of_flat] = m*(fy[fy > hl_of_flat]) + b
        self._slip_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._slip_rate
        self._ss_rate_along_fault = np.zeros(fy.shape)
        self._ss_rate_along_fault[fy < -hl_of_flat] = -m_ss*(fy[fy < - hl_of_flat]) + b_ss
        self._ss_rate_along_fault[fy > hl_of_flat] = m_ss*(fy[fy > hl_of_flat]) + b_ss
        self._ss_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._ss
        self._ds_rate_along_fault = np.zeros(fy.shape)
        self._ds_rate_along_fault[fy < -hl_of_flat] = -m_ds*(fy[fy < - hl_of_flat]) + b_ds
        self._ds_rate_along_fault[fy > hl_of_flat] = m_ds*(fy[fy > hl_of_flat]) + b_ds
        self._ds_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._ds
        # Calculate mean slip rate
        self._mean_slip_rate = np.array([np.mean(self._slip_rate_along_fault)])
        
    def _discretize_slip_rate(self):
        fy = np.arange(-self._length/2,self._length/2,self._fault_dx) 
        sr_bins = np.linspace(-self.length[0]/2,self._length[0]/2,self._along_fault_segments+1)
        ix = np.digitize(fy,sr_bins)-1 # Subtract 1 so that this is an index
        # Find means within bins and bin locations in fault length coordinates
        binned_mean_sr = np.bincount(ix,self._slip_rate_along_fault) / np.bincount(ix)
        binned_mean_ss = np.bincount(ix,self._ss_rate_along_fault) / np.bincount(ix)
        binned_mean_ds = np.bincount(ix,self._ds_rate_along_fault) / np.bincount(ix)
        binned_mean_l = np.bincount(ix,fy) / np.bincount(ix)
        # Determine bin centers location in grid coordinates for decimated interseismic panels
        # Also store the slip rate in each bin and the width and length of the patch
        ixc = []
        iyc = []
        izc = []
        isr = []
        iss = []
        ids = []
        iwi = []
        ile = []
        idi = []
        for i in range(self._num_panels):
            if self._panel_types[i]=='I':
                # Center of individual patches in fault centered coordinates along dip
                cfx = (self._fx[i+1] + self._fx[i])/2 
                for j in range(self._along_fault_segments):
                    # Center of individual patches in fault centered coordinates along strike
                    cfy = binned_mean_l[j]
                    # Transform into model coordinates
                    ixc0 = (cfx * np.cos(np.radians(self.strike[0])) + cfy * np.sin(np.radians(self.strike[0]))) + self.tip_location[0]
                    iyc0 = (-cfx * np.sin(np.radians(self.strike[0])) + cfy * np.cos(np.radians(self.strike[0]))) + self.tip_location[1]
                    ixc.append(ixc0)
                    iyc.append(iyc0)
                    # Get depth
                    izc.append(self._zc[i])
                    # Get length (in strike direction) of individual patches
                    ile.append(sr_bins[j+1]-sr_bins[j])
                    # Get width (in dip direction) of individual patches
                    iwi.append(self.width[i])
                    # Append slip rate for patch
                    isr.append(binned_mean_sr[j])
                    iss.append(binned_mean_ss[j])
                    ids.append(binned_mean_ds[j])
                    # Append dips
                    idi.append(self.dip[i])
        ixc = np.array(ixc)
        iyc = np.array(iyc)
        izc = np.array(izc)
        isr = np.array(isr)
        iss = np.array(iss)
        ids = np.array(ids)
        iwi = np.array(iwi)
        ile = np.array(ile)
        idi = np.array(idi)
        
        self._interseismic_patches = [ixc,iyc,izc,isr,iss,ids,ile,iwi,idi]
                
        # ## PLOTTING
        # approx_sr = np.zeros(fy.shape)
        # for i in range(self._along_fault_segments):
        #     approx_sr[ix==i] = binned_mean_sr[i]
        
        # plt.figure()
        # plt.plot(fy,self._slip_rate_along_fault*100*10,c='gray',linestyle=':',label='True Along-Strike Slip Rate')
        # plt.plot(fy,approx_sr*100*10,c='k',label='Approximated Along-Strike Slip Rate')
        # plt.xlabel('Distance Along Fault Length (m)')
        # plt.ylabel('Slip Rate (mm/yr)')
        # plt.legend(loc='best')

    
    def _generate_ok_grid(self):
        """
        Helper function to call the appropriate sub function to generate the array of 
        "recievers" for which the elastic dislocation is solved

        """
        if type(self.grid)==RasterModelGrid:
            self._generate_ok_xy_raster()
        elif type(self.grid)==HexModelGrid:
            self._generate_ok_xy_hex()
        
    def _generate_ok_xy_raster(self):
        """
        Generates an appropriate list of recievers for a Landlad RasterModelGrid

        """
        # Extract x-y coordinates of links for calculating horizontal velocities
        xyl = self.grid.xy_of_link
        xl = xyl[:,0].ravel()
        yl = xyl[:,1].ravel()
        # Extract x-y coordinates of core nodes for calculating vertical velocities
        xn = self.grid.x_of_node[self.grid.core_nodes]
        yn = self.grid.y_of_node[self.grid.core_nodes]
        # Concatenate links and nodes for single calculation of velocities
        # Generate index for determining which are horizontal links, 
        # vertical links, and which are nodes
        horz_links = np.zeros(xl.shape).astype(bool)
        vert_links = np.zeros(xl.shape).astype(bool)
        horz_links[self.grid.horizontal_links]=True
        vert_links[self.grid.vertical_links]=True
        self._horz_link_idx = np.concat((horz_links,np.zeros(xn.shape)),axis=0).astype(bool)
        self._vert_link_idx = np.concat((vert_links,np.zeros(xn.shape)),axis=0).astype(bool)
        self._node_idx = np.concat((np.zeros(xl.shape),np.ones(xn.shape)),axis=0).astype(bool)
        self._xs = np.concat((xl,xn),axis=0)
        self._ys = np.concat((yl,yn),axis=0)
        
    def _generate_ok_xy_hex(self):
        """
        Generates an appropriate list of recievers for a Landlab HexModelGrid

        """
        # Extract x-y coordinates of links for calculating horizontal velocities
        xyl = self.grid.xy_of_link
        xl = xyl[:,0].ravel()
        yl = xyl[:,1].ravel()
        # Extract x-y coordinates of core nodes for calculating vertical velocities
        xn = self.grid.x_of_node[self.grid.core_nodes]
        yn = self.grid.y_of_node[self.grid.core_nodes]
        links = np.ones(xl.shape).astype(bool)
        nodes = np.ones(xn.shape).astype(bool)
        self._link_idx = np.concat((links,np.zeros(xn.shape)),axis=0).astype(bool)
        self._node_idx = np.concat((np.zeros(xl.shape),nodes),axis=0).astype(bool)
        self._xs = np.concat((xl,xn),axis=0)
        self._ys = np.concat((yl,yn),axis=0)
        
        
    def _establish_advection_and_uplift(self):
        """
        Instantiates an instance of the AdvectionTVD component and set ups the 
        interseismic velocity field within the instance along with a vertical velocity
        at each grid node.

        """
        self._vel=self.grid.add_zeros('advection__velocity',at='link',clobber=True)
        self._adv = AdvectionSolverTVD(self.grid,fields_to_advect=self.fields_to_advect,advection_direction_is_steady=False)
        self._u = self.grid.add_zeros('vertical__velocity',at='node',clobber=True)
        # Calculate interseismic velocities
        self._calc_interseismic_vel()
        if type(self.grid)==RasterModelGrid:
            # Load interseismic velocities into horizontal velocity and uplift
            self._vel[self.grid.horizontal_links] = self._ivx[self._horz_link_idx]
            self._vel[self.grid.vertical_links] = self._ivy[self._vert_link_idx]
            self._u[self.grid.core_nodes]=self._ivz[self._node_idx]
        elif type(self.grid)==HexModelGrid:
            # Load interseismic velocities into horizontal velocity and uplift
            self.grid.map_vectors_to_links(self._ivx[self._link_idx],self._ivy[self._link_idx],out=self._vel)
            self._u[self.grid.core_nodes]=self._ivz[self._node_idx]
            
    def _update_advection_and_uplift(self):
        """
        Updates the advection and vertical velocities

        """
        if type(self.grid)==RasterModelGrid:
            # Load interseismic velocities into horizontal velocity and uplift
            self._vel[self.grid.horizontal_links] = self._ivx[self._horz_link_idx]
            self._vel[self.grid.vertical_links] = self._ivy[self._vert_link_idx]
            self._u[self.grid.core_nodes]=self._ivz[self._node_idx]
        elif type(self.grid)==HexModelGrid:
            # Load interseismic velocities into horizontal velocity and uplift
            self.grid.map_vectors_to_links(self._ivx[self._link_idx],self._ivy[self._link_idx],out=self._vel)
      

    def _query_depth(self,x,y,ix):
        """
        Query the depth on the fault plane within a given panel based on the fit
        plane

        Parameters
        ----------
        x : float
            x-coordinate of interest.
        y : float
            y-coordinate of interest.
        ix : int
            index of the fault panel to check.

        Returns
        -------
        z : float
            depth of fault panel.

        """
        fpc = self._fault_plane_coeffs[ix]
        z= (fpc[3] - fpc[0]*x - fpc[1]*y)/fpc[2]
        return z
    
    def _calc_seismogenic_panels(self):
        """
        Function to automatically determine which parts of fault can fail 
        coseismically (within seismogenic zone),  will slip interseismically 
        (below seismogenic zone), or are above the seismogenic zone.
        
        When run, this will recalculate the number of panels and overwrite any
        assignments made for 'panel_types'.

        """
        
        # Extract boundaries on seismogenic zone
        usz = self._seismogenic_zone[0]
        lsz = self._seismogenic_zone[1]
        # Determine where current panels sit with respect to seismogenic zone
        # and partition
        panel_types = []
        new_widths = []
        new_dips = []
        for i in range(self._num_panels):
            fz0 = self._fz[i] # Depth at top of panel
            fz1 = self._fz[i+1] # Depth at bottom of panel
            if (fz1 < usz):
                # Existing panel is completely above seismogenic zone
                panel_types.append('A')
                new_widths.append(self._width[i])
                new_dips.append(self._dip[i])
            elif (fz0 > usz) & (fz1 < lsz):
                # Existing panel is completely within seismogenic zone
                panel_types.append('C')
                new_widths.append(self._width[i])
                new_dips.append(self._dip[i])
            elif (fz0 > lsz):
                # Existing panel is completely below seismogenic zone
                panel_types.append('I')
                new_widths.append(self._width[i])
                new_dips.append(self._dip[i])
            else:
                if (fz0 < usz) & (fz1 > usz) & (fz1 < lsz):
                    # Panel to be split between A and C
                    w1 = (usz-fz0)/np.sin(np.radians(self._dip[i]))
                    new_widths.append(w1)
                    panel_types.append('A')
                    new_dips.append(self._dip[i])
                    w2 = (fz1 - usz)/np.sin(np.radians(self._dip[i]))
                    new_widths.append(w2)
                    panel_types.append('C')
                    new_dips.append(self._dip[i])
                elif (fz0 > usz) & (fz1 > lsz):
                    # Panel to be split between C and I
                    w1 = (lsz-fz0)/np.sin(np.radians(self._dip[i]))
                    new_widths.append(w1)
                    panel_types.append('C')
                    new_dips.append(self._dip[i])
                    w2 = (fz1-lsz)/np.sin(np.radians(self._dip[i]))
                    new_widths.append(w2)
                    panel_types.append('I')
                    new_dips.append(self._dip[i]) 
                elif (fz0 < usz) & (fz1 > lsz):
                    # Panel to be split between A, C, and I
                    w1 = (usz-fz0)/np.sin(np.radians(self._dip[i]))
                    new_widths.append(w1)
                    panel_types.append('A')
                    new_dips.append(self._dip[i])
                    w2 = (lsz - usz)/np.sin(np.radians(self._dip[i]))
                    new_widths.append(w2)
                    panel_types.append('C')
                    new_dips.append(self._dip[i])
                    w2 = (fz1-lsz)/np.sin(np.radians(self._dip[i]))
                    new_widths.append(w2)
                    panel_types.append('I')
                    new_dips.append(self._dip[i])
                
        if 'I' not in panel_types:
            raise ValueError('Fault depth is insufficient to reach base of seismogenic zone')
        
        # Store new width, dips, and panel types into object using setters
        self.dip=np.array(new_dips)
        self.width=np.array(new_widths)
        self.panel_types=panel_types
        # Rerun generators
        self._calc_panel_geoms()
        self._calc_fault_surface()
        
        
    def _calc_interseismic_vel(self):
        """
        Calculates interseismic velocities

        """
        if not(self._topographic_correction):
            self._zs=np.zeros(self._xs.shape)        
            if self._slip_rate_function=='boxcar':
                vx=[]; vy=[]; vz=[];
                for i in range(self._num_panels):
                    if self._panel_types[i]=='I':
                        vx0,vy0,vz0=_ok(self._xs,self._ys,self._zs,self._xc[i],self._yc[i],self._zc[i],
                                        self.length[0],self.width[i],self.dip[i],
                                        self.strike[0],self.ss[0],self.ds[0],0,self._mu,self._nu)
                        vx.append(vx0)
                        vy.append(vy0)
                        vz.append(vz0)
                self._ivx = sum(vx)
                self._ivy = sum(vy)
                self._ivz = sum(vz)
            else:
                ixc = self._interseismic_patches[0]
                iyc = self._interseismic_patches[1]
                izc = self._interseismic_patches[2]
                iss = self._interseismic_patches[4]
                ids = self._interseismic_patches[5]
                ilengths = self._interseismic_patches[6]
                iwidths = self._interseismic_patches[7]
                idips = self._interseismic_patches[8]
                if not(self.parallel):
                    vx=[]; vy=[]; vz=[];
                    for i in range(len(ixc)):
                        vx0,vy0,vz0=_ok(self._xs,self._ys,self._zs,ixc[i],iyc[i],izc[i],
                                        ilengths[i],iwidths[i],idips[i],
                                        self.strike[0],iss[i],ids[i],0,self._mu,self._nu)
                        vx.append(vx0)
                        vy.append(vy0)
                        vz.append(vz0)
                        
                    self._ivx = sum(vx)
                    self._ivy = sum(vy)
                    self._ivz = sum(vz)
                else:
                    items = [(self._xs,self._ys,self._zs,ixc[i],iyc[i],izc[i],ilengths[i],iwidths[i],idips[i],self.strike[0],iss[i],ids[i],0,self._mu,self._nu) for i in range(len(ixc))]
                    with mp.Pool(self._num_cores) as pool:
                        res = pool.starmap(_ok,items)
                        res = np.sum(list(zip(*res)),axis=1)
                        self._ivx = res[0,:].ravel()
                        self._ivy = res[1,:].ravel()
                        self._ivz = res[2,:].ravel()
        elif self._topographic_correction:
            # Zero surface
            self._zs=np.zeros(self._xs.shape)  

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
            # # zl[zl <= -1*self._tip_location[2]] = -1*self._tip_location[2]+0.5

            ## This works consistently with high rates of subsidence. 
            if np.any(zl <= -1*self._tip_location[2]):
                tip = -1*self._tip_location[2]
                orig_rng = np.max(zl) - np.min(zl)
                new_rng = np.max(zl) - (tip + 0.1)
                zl = zl * (new_rng/orig_rng)
                zl += (tip - np.min(zl)) + 0.1

            if self._slip_rate_function=='boxcar':
                vx=[]; vy=[]; vz=[];
                for i in range(self._num_panels):
                    if self._panel_types[i]=='I':
                        vx0,vy0,vz0=_ok_topo(self._xs,self._ys,self._zs,self._xc[i],self._yc[i],self._zc[i],
                                                 self.length[0],self.width[i],self.dip[i],
                                                 self.strike[0],self.ss[0],self.ds[0],0,self._mu,self._nu,zl)
                        vx.append(vx0)
                        vy.append(vy0)
                        vz.append(vz0)
                self._ivx = sum(vx)
                self._ivy = sum(vy)
                self._ivz = sum(vz)
            else:
                ixc = self._interseismic_patches[0]
                iyc = self._interseismic_patches[1]
                izc = self._interseismic_patches[2]
                iss = self._interseismic_patches[4]
                ids = self._interseismic_patches[5]
                ilengths = self._interseismic_patches[6]
                iwidths = self._interseismic_patches[7]
                idips = self._interseismic_patches[8]
                if not(self.parallel):
                    vx=[]; vy=[]; vz=[];
                    for i in range(len(ixc)):
                        vx0,vy0,vz0=_ok_topo(self._xs,self._ys,self._zs,ixc[i],iyc[i],izc[i],
                                                  ilengths[i],iwidths[i],idips[i],
                                                  self.strike[0],iss[i],ids[i],0,self._mu,self._nu,zl)
                        vx.append(vx0)
                        vy.append(vy0)
                        vz.append(vz0)
                    
                    self._ivx = sum(vx)
                    self._ivy = sum(vy)
                    self._ivz = sum(vz)
                else:
                    items = [(self._xs,self._ys,self._zs,ixc[i],iyc[i],izc[i],ilengths[i],iwidths[i],idips[i],self.strike[0],iss[i],ids[i],0,self._mu,self._nu,zl) for i in range(len(ixc))]
                    with mp.Pool(self._num_cores) as pool:
                        res = pool.starmap(_ok_topo,items)
                        res = np.sum(list(zip(*res)),axis=1)
                        self._ivx = res[0,:].ravel()
                        self._ivy = res[1,:].ravel()
                        self._ivz = res[2,:].ravel()
                    


    def on_fault(self,x,y):
        '''
        Function that determines whether an x,y coordinate pair is "on" the fault
        in the sense of whether when projected downward from the surface would this
        coordinate encounter the fault. If coordinate pair is on the fault,
        returns the depth (positive downward) of the fault at that location. If
        coordinate pair is not on fault, returns np.nan. Output will be a 
        np array of size (N,) where N is the number of fault panels.

        Parameters
        ----------
        x : float
            x-coordinate of point of interest
        y : float
            y-coordinate of point of interest.

        Returns
        -------
        z : array
            z-coordinate of point of interest on fault or nan if not on fault

        
        '''
        
        z=np.zeros(self._num_panels)
        
        for i in range(self._num_panels):
            xb = self._panel_boundaries[i][0]
            yb = self._panel_boundaries[i][1]
            x_ur = xb[0]; x_lr=xb[1]; x_ll=xb[2]; x_ul=xb[3]
            y_ur = yb[0]; y_lr=yb[1]; y_ll=yb[2]; y_ul=yb[3]
            p=path.Path([[x_ur,y_ur],[x_lr,y_lr],[x_ll,y_ll],[x_ul,y_ul]])
            
            r=p.contains_point([x,y])
            if r:
                fpc = self._fault_plane_coeffs[i]
                z[i]= (fpc[3] - fpc[0]*x - fpc[1]*y)/fpc[2]
            else:
                z[i]=np.nan
                
        return z        
        
    def plot_fault_geometry(self,plot_seismogenic=False,cmap='viridis',return_handles=False,fig1size=(10,10),fig2size=(10,10)):
        """
        Plots map view of fault depth with respect to the bounds of the Landlab
        grid and cross-section of the fault

        Parameters
        ----------
        plot_seismogenic : boolean, optional
            Flag to plot the seismogenic zone (True) or not (False). The default is False.
        cmap : name of valid colormap or valid colormap, optional
            Colormap for the fault depth. The default is 'viridis'.
        return_handles : boolean, optional
            Flag to return the figure handles of the generated figures. The default
            is False.

        Returns
        -------
        f1 : figure handle, optional
            Handle to the produced figure.

        """
        
        f1=plt.figure(figsize=fig1size,layout='tight')
        

        # Define polygon that outlines LEM domain
        if type(self.grid)==RasterModelGrid:
            ext_y=self.grid.extent[0]
            ext_x=self.grid.extent[1]
        elif type(self.grid)==HexModelGrid:
            ext_y = np.max(self.grid.y_of_node)
            ext_x = np.max(self.grid.x_of_node)
        
        ax1=f1.add_subplot(1,1,1)
        if (np.isclose(self._strike,0)) | (np.isclose(self._strike,90)) | (np.isclose(self._strike,180)) | (np.isclose(self._strike,270)) | (np.isclose(self._strike,360)):
            im1=ax1.imshow(self._FZ,origin='lower',extent=(np.min(self._MX.ravel()),
                                                          np.max(self._MX.ravel()),
                                                          np.min(self._MY.ravel()),
                                                          np.max(self._MY.ravel())),cmap=cmap)
        else:
            im1 = ax1.scatter(self._MX.ravel(),self._MY.ravel(),c=self._FZ.ravel(),s=1,cmap=cmap)
        
        ax1.plot([0,ext_x,ext_x,0,0],[0,0,ext_y,ext_y,0],c='k',linestyle=':',linewidth=2,label='LEM Boundary')
        
        for i in range(self._num_panels):
            if self._panel_types!=None:
                if self._panel_types[i]=='A':
                    ax1.plot(self._panel_boundaries[i][0],self._panel_boundaries[i][1],c='b')
                    ax1.scatter(self._xc[i],self._yc[i],s=50,c='b')
                elif self._panel_types[i]=='C':
                    ax1.plot(self._panel_boundaries[i][0],self._panel_boundaries[i][1],c='r')
                    ax1.scatter(self._xc[i],self._yc[i],s=50,c='r')
                elif self._panel_types[i]=='I':
                    ax1.plot(self._panel_boundaries[i][0],self._panel_boundaries[i][1],c='k')
                    ax1.scatter(self._xc[i],self._yc[i],s=50,c='k')
            else:
                ax1.plot(self._panel_boundaries[i][0],self._panel_boundaries[i][1],c='k')
                ax1.scatter(self._xc[i],self._yc[i],s=50,c='k')  
                
        if not(self._slip_rate_function=='boxcar'):
            ax1.scatter(self._interseismic_patches[0],self._interseismic_patches[1],s=10,
                        edgecolor='k',facecolor='w')
                
        ax1.set_aspect('equal')
        ax1.legend(loc='best')
        ax1.set_xlabel('X (m)')
        ax1.set_ylabel('Y (m)')
        cbar=plt.colorbar(im1,ax=ax1)
        cbar.ax.set_ylabel('Depth (m)')
        cbar.ax.invert_yaxis()
        
        f2=plt.figure(figsize=fig2size,layout='tight')
        ax2=f2.add_subplot(1,1,1)
        A_count = 0
        C_count = 0 
        I_count = 0
        for i in range(self._num_panels):
            if self.panel_types!=None:
                if self.panel_types[i]=='A':
                    if A_count == 0:
                        ax2.plot(self._fx[i:i+2],self._fz[i:i+2],c='b',label='Above Seismogenic')
                        A_count += 1
                    else:
                        ax2.plot(self._fx[i:i+2],self._fz[i:i+2],c='b')
                elif self.panel_types[i]=='C':
                    if C_count == 0:
                        ax2.plot(self._fx[i:i+2],self._fz[i:i+2],c='r',label='Within Seismogenic')
                        C_count += 1
                    else:
                        ax2.plot(self._fx[i:i+2],self._fz[i:i+2],c='r')
                elif self.panel_types[i]=='I':
                    if I_count == 0:
                        ax2.plot(self._fx[i:i+2],self._fz[i:i+2],c='k',label='Below Seismogenic')
                        I_count += 1
                    else:
                        ax2.plot(self._fx[i:i+2],self._fz[i:i+2],c='k')
            else:
                ax2.plot(self._fx[i:i+2],self._fz[i:i+2],c='k')
        
        if plot_seismogenic:
            ax2.axhline(self._seismogenic_zone[0],c='r',linestyle=':')
            ax2.axhline(self._seismogenic_zone[1],c='r',linestyle=':')
        
        ax2.yaxis.set_inverted(True)
        ax2.set_aspect('equal')
        ax2.set_ylabel('Depth (m)')
        ax2.set_xlabel('Along Dip Distance (m)')
        ax2.legend(loc='best')  

        if return_handles:
            return f1,f2
        
    def plot_slip_rate_along_fault(self,plot_components=False,return_handles=False,figsize=(10,10)):
        fy = np.arange(-self._length[0]/2,self._length[0]/2,self._fault_dx) 
        sr_bins = np.linspace(-self.length[0]/2,self._length[0]/2,self._along_fault_segments+1)
        ix = np.digitize(fy,sr_bins)-1 # Subtract 1 so that this is an index
        # Find means within bins and bin locations in fault length coordinates
        binned_mean_sr = np.bincount(ix,self._slip_rate_along_fault) / np.bincount(ix)
        binned_mean_ss = np.bincount(ix,self._ss_rate_along_fault) / np.bincount(ix)
        binned_mean_ds = np.bincount(ix,self._ds_rate_along_fault) / np.bincount(ix)
        binned_mean_l = np.bincount(ix,fy) / np.bincount(ix)
        
        
        approx_sr = np.zeros(fy.shape)
        approx_ss = np.zeros(fy.shape)
        approx_ds = np.zeros(fy.shape)
        for i in range(self._along_fault_segments):
            approx_sr[ix==i] = binned_mean_sr[i]
            approx_ss[ix==i] = binned_mean_ss[i]
            approx_ds[ix==i] = binned_mean_ds[i]
        
        if plot_components:
            f1 = plt.figure(figsize=figsize,layout='tight')
            
            plt.subplot(3,1,1)
            plt.plot((fy+self._length/2)/1000,self._slip_rate_along_fault*100*10,c='gray',linestyle=':',label='True Along-Strike Slip Rate')
            plt.plot((fy+self._length/2)/1000,approx_sr*100*10,c='k',label='Approximated Along-Strike Slip Rate')
            plt.xlabel('Distance Along Fault Length (km)')
            plt.ylabel('Total Slip Rate (mm/yr)')
            plt.legend(loc='best')
            
            plt.subplot(3,1,2)
            plt.plot((fy+self._length/2)/1000,self._ds_rate_along_fault*100*10,c='gray',linestyle=':')
            plt.plot((fy+self._length/2)/1000,approx_ds*100*10,c='k')
            plt.xlabel('Distance Along Fault Length (km)')
            plt.ylabel('Dip Slip Component (mm/yr)')       
    
            plt.subplot(3,1,3)
            plt.plot((fy+self._length/2)/1000,self._ss_rate_along_fault*100*10,c='gray',linestyle=':')
            plt.plot((fy+self._length/2)/1000,approx_ss*100*10,c='k')
            plt.xlabel('Distance Along Fault Length (km)')
            plt.ylabel('Strike Slip Component (mm/yr)')
        else:
            f1 = plt.figure(figsize=figsize,layout='tight')
            
            plt.plot((fy+self._length/2)/1000,self._slip_rate_along_fault*100*10,c='gray',linestyle=':',label='True Along-Strike Slip Rate')
            plt.plot((fy+self._length/2)/1000,approx_sr*100*10,c='k',label='Approximated Along-Strike Slip Rate')
            plt.xlabel('Distance Along Fault Length (km)')
            plt.ylabel('Total Slip Rate (mm/yr)')
            plt.legend(loc='best')  
            
        if return_handles:
            return f1
            
    
    def plot_interseismic_velocity_field(self,cmap='Spectral_r',return_handles=False,figsize=(15,3),
                                        fig_type='individual',quiver_interval=1000,shrink=0.75):
        """
        Plots the x, y, and z components of the interseismic velocity field

        Parameters
        ----------
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
        # This should works whether the grid is raster or hex since it uses
        # the built in landlab grid methods
        
        # Generate a deep copy of the grid to not modify the stored one
        _grid = copy.deepcopy(self.grid)

        if fig_type=='individual':
        
            ivx = np.zeros(self.grid.nodes.shape).ravel()
            ivy = np.zeros(self.grid.nodes.shape).ravel()
            ivz = np.zeros(self.grid.nodes.shape).ravel()
            
            # Assign core nodes values in mm/yr
            ivx[self.grid.core_nodes]=self._ivx[self._node_idx]*100*10
            ivy[self.grid.core_nodes]=self._ivy[self._node_idx]*100*10
            ivz[self.grid.core_nodes]=self._ivz[self._node_idx]*100*10
            
            # Assign values to nodes in copied grid
            _grid.add_field('ivx',ivx,at='node')
            _grid.add_field('ivy',ivy,at='node')
            _grid.add_field('ivz',ivz,at='node')
            
            # Use imshow to display values
            f1 = plt.figure(figsize=figsize,layout='tight')
            
            plt.subplot(1,3,1)
            plt.title('Displacement in X')
            _grid.imshow('ivx',shrink=shrink,
                         cmap=cmap,grid_units=('m','m'))
            
            plt.subplot(1,3,2)
            plt.title('Displacement in Y')
            _grid.imshow('ivy',shrink=shrink,
                         cmap=cmap,grid_units=('m','m'))
            
            plt.subplot(1,3,3)
            plt.title('Displacement in Z')
            _grid.imshow('ivz',colorbar_label='(mm/yr)',shrink=shrink,
                         cmap=cmap,grid_units=('m','m'))
        elif fig_type=='combined': 

            # Prepare Z velocity
            ivz = np.zeros(self.grid.nodes.shape).ravel()
            ivz[self.grid.core_nodes]=self._ivz[self._node_idx]*100*10
            _grid.add_field('ivz',ivz,at='node')

            # Prepare X and Y velocity
            xn = self.grid.x_of_node[self.grid.core_nodes]
            yn = self.grid.y_of_node[self.grid.core_nodes]
            xu = self._ivx[self._node_idx]*100*10
            yu = self._ivy[self._node_idx]*100*10

            idx = (np.mod(xn,quiver_interval)==0) & (np.mod(yn,quiver_interval)==0)

            horz_v = np.sqrt(xu[idx]**2 + yu[idx]**2)
            key_v = np.percentile(horz_v,90)

            f1 = plt.figure(figsize=figsize,layout='tight')
            ax1 = f1.add_subplot(111)

            _grid.imshow('ivz',colorbar_label='(mm/yr)',shrink=shrink,
                         cmap=cmap,grid_units=('m','m'))
            q = ax1.quiver(xn[idx],yn[idx],xu[idx],yu[idx],color='k')
            qk = ax1.quiverkey(q,0.05,1.05,key_v,f'{key_v:.2e} '+r'$\frac{mm}{yr}$',
                                labelpos='E',coordinates='axes')

        else: 
            raise ValueError("Argument for 'fig_type' must be either 'individual' or 'combined'.")

        if return_handles:
            return f1

    def run_one_step(self,dt):
        """
        Perform interseismic advection and uplift
        
        If topographic correction is turned on, recalculate interseismic velocity

        Parameters
        ----------
        dt : int
            Timestep.

        """

        # based on updated topography
        if self._topographic_correction:
            self._calc_interseismic_vel()
            self._update_advection_and_uplift()
        
        # Advect
        self._adv.run_one_step(dt)
        
        # Uplift 
        if 'bedrock__elevation' in self.grid.at_node.keys():
            # Add background elevation if it exists
            self._br_elev[self.grid.core_nodes] += self._bu*dt
            # Then deal with insterseismic uplift
            self._br_elev[self.grid.core_nodes] += self._u[self.grid.core_nodes]*dt
            self._elev[self.grid.core_nodes] = self._br_elev[self.grid.core_nodes] + self._sd[self.grid.core_nodes]
        else:
            # Add background elevation if it exists
            self._elev[self.grid.core_nodes] += self._bu*dt
            # Then deal with insterseismic uplift
            self._elev[self.grid.core_nodes] += self._u[self.grid.core_nodes]*dt
            
        # Update total displacements
        [x_comp,y_comp] = self.grid.map_link_vector_components_to_node('advection__velocity')
        self._tx_disp[self.grid.core_nodes] += x_comp[self.grid.core_nodes]*dt
        self._ty_disp[self.grid.core_nodes] += y_comp[self.grid.core_nodes]*dt
        self._tz_disp[self.grid.core_nodes] += self._bu*dt
        self._tz_disp[self.grid.core_nodes] += self._u[self.grid.core_nodes]*dt
        

class VerticalFault:
    """ Fault geometry and interseismic creep using elastic dislocations

     This component generates a fault with an arbitrary geometry as specified by
     the user and then allows the calculation of surface deformation assuming
     interseismic creep where the velocity calculation uses an elastic dislocation.
     This component includes a wrapper for 'okada4py', which implements the 
     3D solution of Okada, 1992 for dislocation in an elastic half space. A separate
     installation and compilation of okada4py is required for this component to 
     function.
     
     There is no specific requirement that the dimensions or extent of the fault
     are confined to, or even overlap with, the provided Landlab grid, but x-y 
     coordinates for the fault are specified with respect to the Landlab grid
     coordinate system.

     The component is designed for use in conjunction with the EarthquakeSequence component,
     but strictly does not require that you pair it with an earthquake sequence if you
     want to drive a model with interseismic creep only.

     Examples
     --------


     References
     ----------

     **Required Software Citation(s) Specific to this Component**

     Romain Jolivet. (2024). jollivetr/okada4py: First release (1.0.0). Zenodo.
     https://doi.org/10.5281/zenodo.14170827

     **Additional References**

     Okada, Y. (1992), Internal deformation due to shear and tensile faults in a
     half-space, Bulletin of the Seismological Society of America, 82(2), 1018-1040
     
     Langer, L., Ragon, T., Sladen, A., Tromp, J. (2020), Impact of topography
     on earthquake static slip estimates, Tectonophysics, 791, 228566

    """

    _name = 'VerticalFault'

    _time_units = 'y'

    _unit_agnostic = False 
    
    _info = {
        "advection__velocity":{
            "dtype":float,
            "intent":"out",
            "optional":False,
            "units":"m/y",
            "mapping":"link",
            "doc":"Link-parallel advection velocity"
            },
        "vertical__velocity":{
            "dtype":float,
            "intent":"out",
            "optional":False,
            "units":"m/y",
            "mapping":"node",
            "doc":"Vertical velocity"
            },
        "total_x__displacement":{
            "dtype":float,
            "intent":"out",
            "optional":False,
            "units":"m",
            "mapping":"node",
            "doc":"Total accumulated displacement in x direction"},
        "total_y__displacement":{
            "dtype":float,
            "intent":"out",
            "optional":False,
            "units":"m",
            "mapping":"node",
            "doc":"Total accumulated displacement in y direction"}, 
        "total_z__displacement":{
            "dtype":float,
            "intent":"out",
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

    def __init__(self, grid, fields_to_advect=['bedrock__elevation'],
                 length=10000, 
                 width=1000, strike=0, tip_location=[0,0,10],
                 ss_rate=0.001, ds_rate=0.0, u_rate=0.0, 
                 mu=3.3e10, nu=0.25,
                 creeping=False,  
                 fault_dx=100,
                 seismogenic_zone=[1000,5000],
                 slip_rate_function='boxcar',
                 fraction_blunt=0.5,
                 along_fault_segments=11,
                 fault_type='Interplate_SS',
                 topographic_correction=False,
                 parallel=False,num_cores=None):
        """
        

        Parameters
        ----------
        grid : RasterModelGrid
            A landlab grid.
        fields_to_advect : list of str, optional
            List of names of fields to be advected. The default is ['bedrock__elevation'].
        length : float or array/list of floats, optional
            Along-strike lengths of vertical fault segments (m). The default is 10000.
        width : float, optional
            Width of fault panel, starting from the upper tip of the fault
            and progressing down-dip (m). As the fault is restricted to being vertical
            this is equivalent to depth. The default is 1000.
        strike : float or array/list of floats, optional
            Strike of fault segmetns in azimuth, follows right hand rule. If multiple
            fault segments are specified, the location of the segments will progress from the
            first segment (the center of which is specified by tip_location) and then
            in the direction of strike. (degrees) 
            The default is 0.
        tip_location : list of floats, optional
            X, Y, Z and location of center of the first fault segement. X and 
            Y are in the same coordinates as the input landlab grid, but it does
            not have to lie within the landlab grid. Z is depth and is 
            positive downward. (m) The default is [0,0,10].
        ss_rate : float, optional
            Strike-slip component of fault slip rate. (m/yr) The default is 0.001.
        ds_rate : float, optional
            Dip-slip component of fault slip rate. Positive values imply thrust motion.
            (m/yr) The default is 0.0.
        u_rate: float, optional
            Background vertical uplift rate to apply across the domain. Velocities calculated
            from the elastic dislocations will be superimposed on this rate. (m/yr)
            The default is 0.0.
        mu : float, optional
            Shear modulus. (Pa) The default is 3.3e10. It is not recommended that you change
            this value.
        nu : float, optional
            Poissons ratio. The default is 0.25. It is not recommended that you change this
            value
        creeping : boolean, optional
            If False (default), the seismogenic zone depths provided to seismogenic_zone
            will be used to divide the fault vertically into areas above the seismogenic zone
            (cannot nucleate a rupture, but ruptures can extend into it), within the seismogenic
            zone (can nucleate ruptures), or below the seismogenic zone (cannot nucleate ruptures,
            will experience interseismic creep). If True, instead the entire fault is considered
            creeping and no part of it can nucleate earthquakes.
        fault_dx : int, optional
            Vertical increment for interpolating the fault surface. Within the fault component,
            this is primarily used for plotting, but it is also used in the related EarthquakeSequence
            and CoseismicLandslider component to produce a "grid" of points on the fault to calculate
            various quantities. As such, increasing this value will increase the resolution of these 
            calculations but will increase computation time.  (m) The default is 100.
        seismogenic_zone : list of floats, optional
            The top and bottom of the seismogenic zone given as positive depths.
            This value is effectively ignored if panel behaviors are defined by 
            "panel_types" (m) The default is [1000,5000].
        slip_rate_function : str, optional
            Function that defines how the slip rate varies as a function of fault length,
            options are:
                "boxcar" - slip-rate is constant along the entire length of the fault, the 
                    stored parameter _slip_rate and _mean_slip_rate will be equal and will be 
                    sqrt(ss_rate^2 + ds_rate^2)
                "parabolic" - slip-rate will have a parabolic shape along the length of the fault
                    reaching a maximum at the center of the fault and zeros at the tips. The maximum
                    will be given by sqrt(ss_rate^2 + ds_rate^2) and stored as _slip_rate, but 
                    _mean_slip_rate will be the average of the function, where the the choice of 
                    fault_dx will control the spacing of the points to approximate the mean of the
                    function.
                "blunt_parabolic" - slip-rate will have a partial parabolic shape along the length 
                    of the fault reaching a maximum at the center of the fault and zeros at the tips.
                    In detail, a portion of the fault, specified as a fraction of the length given by
                    the parameter 'fraction_blunt', will be at the maximum and then will decrease
                    via parabolic functions to zero at the tips. The maximum will be given by 
                    sqrt(ss_rate^2 + ds_rate^2) and stored as _slip_rate, but _mean_slip_rate 
                    will be the average of the function, where the the choice of fault_dx will 
                    control the spacing of the points to approximate the mean of the function.
                "triangular" - slip-rate will have a triangular shape along the length of the fault
                    reaching a maximum at the center of the fault and zeros at the tips. The maximum
                    will be given by sqrt(ss_rate^2 + ds_rate^2) and stored as _slip_rate, but 
                    _mean_slip_rate will be the average of the function, where the the choice of 
                    fault_dx will control the spacing of the points to approximate the mean of the
                    function.
                "blunt_triangular" - slip-rate will have a partial triangular shape along the length 
                    of the fault reaching a maximum at the center of the fault and zeros at the tips.
                    In detail, a portion of the fault, specified as a fraction of the length given by
                    the parameter 'fraction_blunt', will be at the maximum and then will decrease
                    via triangular functions to zero at the tips. The maximum will be given by 
                    sqrt(ss_rate^2 + ds_rate^2) and stored as _slip_rate, but _mean_slip_rate 
                    will be the average of the function, where the the choice of fault_dx will 
                    control the spacing of the points to approximate the mean of the function.  
            The default is "boxcar".
        fraction_blunt : float, optional
            The fraction of the total length to be at the maximum slip-rate if slip_rate_function is
            either "blunt_parabolic" or "blunt_triangular". Otherwise this parameter is unused.
            The default is 0.5.
        along_fault_segments : int, optional
            If the slip_rate_function is not a "boxcar", it is necessary to break the interseismic
            panels into "segments" to have the along-strike variation in slip-rate approximated
            in the interseismic velocity. This parameter specifies the number of segments to split the 
            fault into. Larger numbers will more faithfully represent the along-strike variation in slip-rate
            but will increase in computation time. This can be an even or odd number, but odd numbers tend
            to produce more smoothly varying approximations. Note that if the fault has multiple panels, 
            i.e., it has segments with different strikes, the number of fault segments may differ than
            the input value and not all segments may be the same width. This is because the code will also
            use the location of bends as boundaries of segments.
            The default value is 11.
        fault_type : str, optional
            The type of fault for earthquake scaling relationships. Valid values arguments are:
            "Interplate_DS"  - interplate dip-slip fault,
            "SCR_DS" - stable continental region dip-slip fault,
            "Interplate_SS" - interplate strike-slip fault,
            "SCR_SS" - stable continental region strike-slip fault.
            The default is 'Interplate_SS'.
        topographic_correction : boolean, optional
            If False (default), uplift and advection velocities used to deform the surface will
            be calculated at a "zero surface" regardless of the actual topography. If set to True
            then the current topography at each timestep will be used to "correct" the uplift
            and advection velocities. This is not formally changing anything about the fault or
            the solution of the elastic half space, it's effectively just accounting for greater
            distance between the dislocation and the "observer" in the form of individual spots in
            the topography.
        parallel : boolean, optional
            Flag to turn on parallelization of the calculation of interseismic
            displacements. If this is set to true, it is essential that in any script using 
            the relevant fault component that it is protected by a guard, meaning that at 
            minimum any portion of the script that invoked the original instantation should be 
            preceded by an 'if __name__ == "__main__":'statement with the instantiation under 
            this guard. Best practice would be to place the entirety of the script after imports
            under the guard. Note, running in parallel is only considered if the slip_rate_function 
            is something other than "boxcar". Turning on parallel processing for the fault component
            is also really only needed if topographic_correction is set to True because otherwise the
            interseismic velocities are only calculated once.
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
        
        # Check values
        if type(grid)==RasterModelGrid:
            pass
        elif type(grid)==HexModelGrid:
            pass
        else:
            raise TypeError('Provided Landlab grid must be either a raster or hex.')
            
        # Check that fault panels are fully parameterized
        if len(length)==len(strike):
            pass
        else:
            raise ValueError('Number of elements of "length" and "strike" must be the same')
        
        # Set dip to vertical
        self._dip = np.array([90.])
        
        self.grid = grid
        self.fields_to_advect = fields_to_advect
        # Set static values
        self._mu = mu # shear modulus
        self._nu = nu # poissons ratio
        self._fault_dx = fault_dx
        self._topographic_correction = topographic_correction
        # Use setters for properties that require validation
        self.length = length
        self.width = width
        self.strike = strike
        self.tip_location = tip_location
        self.ss = ss_rate
        self.ds = ds_rate
        self.bu = u_rate
        self.seismogenic_zone = seismogenic_zone
        self.slip_rate_function = slip_rate_function
        self.fraction_blunt = fraction_blunt
        self.along_fault_segments = along_fault_segments
        self.creeping = creeping
        self.fault_type = fault_type
        self.parallel = parallel
        self.num_cores = num_cores

        if self.creeping:
            self.panel_types=['I']*len(self._length)
        else:
            self.panel_types=None
            # This will force the use of the seismogenic zone depths
            # to auto generate the vertical panel divisions

        # Extract needed fields from grid
        if 'topographic__elevation' in self.grid.at_node.keys():
            self._elev = self.grid.at_node['topographic__elevation']
            
        if 'bedrock__elevation' in self.grid.at_node.keys():
            self._br_elev = self.grid.at_node['bedrock__elevation']
            
        if 'soil__depth' in self.grid.at_node.keys():
            self._sd = self.grid.at_node['soil__depth']
            
        # Generate empty field for total horizontal displacements
        if 'total_x__displacement' not in self.grid.at_node.keys():
            self._tx_disp = self.grid.add_zeros('total_x__displacement',at='node',clobber=True)
        else:
            self._tx_disp = self.grid.at_node['total_x__displacement']
            
        if 'total_y__displacement' not in self.grid.at_node.keys():
            self._ty_disp = self.grid.add_zeros('total_y__displacement',at='node',clobber=True)
        else:
            self._ty_disp = self.grid.at_node['total_y__displacement']
            
        if 'total_z__displacement' not in self.grid.at_node.keys():
            self._tz_disp = self.grid.add_zeros('total_z__displacement',at='node',clobber=True)
        else:
            self._tz_disp = self.grid.at_node['total_z__displacement']
        
        # Determine the slip rate, this only considers strike slip or dip slip 
        # mechanisms, tensile failures, though possible to generate with the Okada
        # codes, are not defined for other earthquake details that use the slip rate
        #
        # This also considers whether there is a "shape" imposed on the slip rate
        # as a function of distance along the trace of the fault
        self._slip_rate = np.sqrt(self._ss**2 + self._ds**2)
        if self._slip_rate_function == 'boxcar':
            self._boxcar()
        elif self._slip_rate_function == 'parabolic':
            self._parabolic()
            self._discretize_slip_rate()
        elif self._slip_rate_function == 'blunt_parabolic':
            self._blunt_parabolic()
            self._discretize_slip_rate()
        elif self._slip_rate_function == 'triangular':
            self._triangular()
            self._discretize_slip_rate()
        elif self._slip_rate_function == 'blunt_triangular':
            self._blunt_triangular()
            self._discretize_slip_rate()
        
        # Finish running required methods, these are setup as methods as
        # they get called multiple times depending on inputs
        # self._calc_panel_geoms()
        # self._calc_fault_surface()
        self._generate_ok_grid()
        self._establish_advection_and_uplift()
  
    @property
    def length(self):
        """
        Lengths of fault segments along strike

        """
        return self._length
    
    @length.setter
    def length(self,new_length):
        if (type(new_length)!=np.ndarray) & (type(new_length)==list):
            self._length=np.array(new_length).astype(float)
        elif (type(new_length)!=np.ndarray) & (type(new_length)!=list):
            self._length=np.array([new_length]).astype(float)
        else:
            self._length=new_length.astype(float)
            
            
    @property
    def width(self):
        """
        Width of fault panels down dip, in direction of dip

        """
        return self._width
    
    @width.setter
    def width(self,new_width):
        if (type(new_width)!=np.ndarray) & (type(new_width)==list):
            self._width=np.array(new_width).astype(float)
        elif (type(new_width)!=np.ndarray) & (type(new_width)!=list):
            self._width=np.array([new_width]).astype(float)
        else:
            self._width=new_width.astype(float)

        if len(self._width)>1:
            raise ValueError('Entry provided for "width" must be a single value or single element array')
        # Store an original width
        self._owidth = self._width.copy()
            
            
    @property
    def strike(self):
        """
        Strike of fault as azimuth using right hand rule

        """
        return self._strike
    
    @strike.setter
    def strike(self,new_strike):
        if (type(new_strike)!=np.ndarray) & (type(new_strike)==list):
            self._strike=np.array(new_strike).astype(float)
        elif (type(new_strike)!=np.ndarray) & (type(new_strike)!=list):
            self._strike=np.array([new_strike]).astype(float)            
        else:
            self._strike=new_strike.astype(float)
            
            
    @property
    def tip_location(self):
        """
        Location of center of fault tip as x, y, z coordinate

        """
        return self._tip_location
    
    @tip_location.setter
    def tip_location(self,new_tip_location):
        if (type(new_tip_location)!=np.ndarray) & (len(new_tip_location)==3):
            self._tip_location=np.array(new_tip_location).astype(float)
        elif len(new_tip_location)==3:
            self._tip_location=new_tip_location.astype(float)
        else:
            raise ValueError('Entry provided for "tip_location" must be an array or list with 3 entries')
            
    @property
    def ss(self):
        """
        Slip-rate of strike-slip component in m/yr

        """
        return self._ss
    
    @ss.setter
    def ss(self,new_ss):
        if (type(new_ss)!=np.ndarray) & (type(new_ss)==list):
            self._ss=np.array(new_ss).astype(float)
        elif (type(new_ss)!=np.ndarray) & (type(new_ss)!=list):
            self._ss=np.array([new_ss]).astype(float)            
        else:
            self._ss=new_ss.astype(float)
            
    @property
    def ds(self):
        """
        Slip-rate of dip-slip component in m/y

        """
        return self._ds
    
    @ds.setter
    def ds(self,new_ds):
        if (type(new_ds)!=np.ndarray) & (type(new_ds)==list):
            self._ds=np.array(new_ds).astype(float)
        elif (type(new_ds)!=np.ndarray) & (type(new_ds)!=list):
            self._ds=np.array([new_ds]).astype(float)            
        else:
            self._ds=new_ds.astype(float)
        
    @property
    def bu(self):
        """
        Background uplift rate in m/y

        """
        return self._bu
    
    @bu.setter
    def bu(self,new_bu):
        if (type(new_bu)!=np.ndarray) & (type(new_bu)==list):
            self._bu=np.array(new_bu).astype(float)
        elif (type(new_bu)!=np.ndarray) & (type(new_bu)!=list):
            self._bu=np.array([new_bu]).astype(float)            
        else:
            self._bu=new_bu.astype(float)
            
    @property
    def panel_types(self):
        """
        List of strings defining fault panels as above the seismogenic zone "A",
        within the seismogenic zone "C", or below the seismogenic zone "I"

        """
        return self._panel_types
    
    @panel_types.setter
    def panel_types(self,new_panel_types):
        allowed_elements = {'A','C','I'}
        if new_panel_types==None:
            # Calculate  and store temporary number of panels
            self._num_panels=len(self._length)
            # Set panel types to none temporarily
            self._panel_types=None
            self._calc_panel_geoms()
            self._calc_fault_surface()
            self._calc_seismogenic_panels()
        else:
            self._panel_types = new_panel_types
            self._calc_panel_geoms()
            self._calc_fault_surface()

    @property
    def slip_rate_function(self):
        return self._slip_rate_function
    
    @slip_rate_function.setter
    def slip_rate_function(self,new_slip_rate_func):
        if (new_slip_rate_func=='boxcar') | (new_slip_rate_func=='parabolic') | (new_slip_rate_func=='blunt_parabolic') | (new_slip_rate_func=='triangular') | (new_slip_rate_func=='blunt_triangular'):
            self._slip_rate_function = new_slip_rate_func
        else:
            raise ValueError('Entry provided for "slip_rate_function" must be "boxcar", "parabolic", "blunt_parabolic", "triangular", or "blunt_triangular"')
    
    @property
    def fraction_blunt(self):
        return self._fraction_blunt
    
    @fraction_blunt.setter
    def fraction_blunt(self,new_fraction_blunt):
        if (new_fraction_blunt > 0) & (new_fraction_blunt < 1):
            self._fraction_blunt = new_fraction_blunt
        else:
            raise ValueError('Entry provided to "fraction_blunt" must be between 0 and 1')
    
    @property
    def along_fault_segments(self):
        return self._along_fault_segments
    
    @along_fault_segments.setter
    def along_fault_segments(self,new_along_fault_seg):
        self._along_fault_segments = int(new_along_fault_seg)
            
    @property
    def fault_type(self):
        """
        String defining the type of fault

        """
        return self._fault_type
    
    @fault_type.setter
    def fault_type(self,new_fault_type):
        if (new_fault_type=='Interplate_DS') | (new_fault_type=='Interplate_SS') | (new_fault_type=='SCR_DS') | (new_fault_type=='SCR_SS'):
            self._fault_type = new_fault_type
        else:
            raise ValueError('Entry provided for "fault_type" must be "Interplate_DS", "Interplate_SS", "SCR_DS", or "SCR_SS"')
        
    @property
    def seismogenic_zone(self):
        """
        Numpy array defining top and bottom of seismogenic zone

        """
        return self._seismogenic_zone
    
    @seismogenic_zone.setter
    def seismogenic_zone(self,new_seismogenic_zone):
        if (len(new_seismogenic_zone)==2) & (new_seismogenic_zone[0] < new_seismogenic_zone[1]):
            self._seismogenic_zone = new_seismogenic_zone
        else:
            raise ValueError('Entry provided for "seismogenic_zone" must be a list or array with 2 elements that increase monotonically')

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

    def _calc_panel_geoms(self):
        '''
        Calculate geometry components of individual fault panels including
        dimensions, projected locations of corners and center at the surface,
        and areas. For vertical faults with multiple panels along fault length.

        '''
        
        # Calculate number of panels
        self._num_panels=len(self._length)
        
        # Before seismogenic zones are set
        if len(self._width.shape)==1:
            self._num_sub_panels = 0
            # Panel Parallel Coordinates
            self._width_h=np.zeros(self._num_panels)
            self._width_v=np.zeros(self._num_panels)
            # Panel Center Locations
            self._xc=np.zeros(self._num_panels)
            self._yc=np.zeros(self._num_panels)
            self._zc=np.zeros(self._num_panels)
            # Panel Bend Locations
            self._x_tops=np.zeros(self._num_panels)
            self._y_tops=np.zeros(self._num_panels)
            self._z_tops=np.zeros(self._num_panels)
            self._x_bots=np.zeros(self._num_panels)
            self._y_bots=np.zeros(self._num_panels)
            self._z_bots=np.zeros(self._num_panels)
            
            # Calculate the horizontal and vertical components of the panel widths
            for i in range(self._num_panels):
                self._width_h[i]=0
                self._width_v[i]=self._width[0]
            
            # Calculate areas
            self._panel_areas=self._width*self._length
            
            for i in range(self._num_panels):
                if i==0:
                    self._x_tops[i]=self._tip_location[0]
                    self._y_tops[i]=self._tip_location[1]
                    self._z_tops[i]=self._tip_location[2]
                    self._x_bots[i]=self._tip_location[0]
                    self._y_bots[i]=self._tip_location[1]
                    self._z_bots[i]=self.tip_location[2]+self._width_v[i]
                else:
                    self._x_tops[i] = self._x_tops[i-1] + (np.sin(np.radians(self._strike[i-1]))*self._length[i-1]/2) + (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                    self._y_tops[i] = self._y_tops[i-1] + (np.cos(np.radians(self._strike[i-1]))*self._length[i-1]/2) + (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                    self._z_tops[i] = self._tip_location[2]
                    self._x_bots[i] = self._x_tops[i]
                    self._y_bots[i] = self._y_tops[i]
                    self._z_bots[i] = self.tip_location[2]+self._width_v[i]
                    
                self._xc[i]=self._x_tops[i]
                self._yc[i]=self._y_tops[i]
                self._zc[i]=self._z_tops[i]+self._width_v[i]/2
                
            # Calculate boundaries of panels
            self._panel_boundaries=[]
            for i in range(self._num_panels):
                x1=self._x_tops[i] + (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                y1=self._y_tops[i] + (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                z1=self._z_tops[i]
                x2=self._x_bots[i] + (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                y2=self._y_bots[i] + (np.cos(np.radians(self._strike[i]))*self._length[i]/2) 
                z2=self._z_bots[i]
                x3=self._x_bots[i] - (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                y3=self._y_bots[i] - (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                z3=self._z_bots[i]
                x4=self._x_tops[i] - (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                y4=self._y_tops[i] - (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                z4=self._z_bots[i]
                
                x_bounds=np.array([x1,x2,x3,x4,x1])
                y_bounds=np.array([y1,y2,y3,y4,y1])
                z_bounds=np.array([z1,z2,z3,z4])
                self._panel_boundaries.append([x_bounds,y_bounds,z_bounds])
                    
            
            # Calculate piecewise locations of fault panels in xsections
            self._fy=np.concat(([0],np.cumsum(self._length)),axis=0)
            self._fz=np.tile(np.concat(([self._z_tops[0]],self._z_tops[0]+np.cumsum(self._width_v[0])),axis=0),(self._num_panels,1))
            
            # Calculate the total area of the fault that can experience rupture, this
            # includes panel areas that are considered above ("A") the seismogenic depth
            # and within ("C") the seismogenic depth.
            if self._panel_types!=None:
                total_area=[]
                for i in range(self._num_panels):
                    # if (self._panel_types[i]=='A') | (self._panel_types[i]=='C'):
                    #     total_area.append(self._panel_areas[i])
                    if self._panel_types[i]=='C':
                        total_area.append(self._panel_areas[i])
                self._total_area=sum(total_area)
        elif len(self._width.shape)==2:
            self._num_sub_panels = self._width.shape[1]
            
            # Panel Parallel Coordinates
            self._width_h=np.zeros(self._width.shape)
            self._width_v=np.zeros(self._width.shape)
            # Panel Center Locations
            self._xc=np.zeros(self._width.shape)
            self._yc=np.zeros(self._width.shape)
            self._zc=np.zeros(self._width.shape)
            # Panel Bend Locations
            self._x_tops=np.zeros(self._width.shape)
            self._y_tops=np.zeros(self._width.shape)
            self._z_tops=np.zeros(self._width.shape)
            self._x_bots=np.zeros(self._width.shape)
            self._y_bots=np.zeros(self._width.shape)
            self._z_bots=np.zeros(self._width.shape)
            # Panel areas
            self._panel_areas=np.zeros(self._width.shape)
            
            # Calculate the horizontal and vertical components of the panel widths
            for i in range(self._num_panels):
                for j in range(self._num_sub_panels):
                    self._width_h[i,j]=0
                    self._width_v[i,j]=self._width[i,j]
                    
            # Calculate areas
            for i in range(self._num_sub_panels):
                self._panel_areas[:,i] = self._width[:,i]*self._length
                
            # Determine locations of centers 
            for i in range(self._num_panels):
                for j in range(self._num_sub_panels):
                    if (i==0) & (j==0):
                        self._x_tops[i,j]=self._tip_location[0]
                        self._y_tops[i,j]=self._tip_location[1]
                        self._z_tops[i,j]=self._tip_location[2]
                        self._x_bots[i,j]=self._tip_location[0]
                        self._y_bots[i,j]=self._tip_location[1]
                        self._z_bots[i,j]=self.tip_location[2]+self._width_v[i,j]
                    elif (j==0) & (i>0):
                        self._x_tops[i,j] = self._x_tops[i-1,j] + (np.sin(np.radians(self._strike[i-1]))*self._length[i-1]/2) + (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                        self._y_tops[i,j] = self._y_tops[i-1,j] + (np.cos(np.radians(self._strike[i-1]))*self._length[i-1]/2) + (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                        self._z_tops[i,j] = self._tip_location[2]
                        self._x_bots[i,j] = self._x_tops[i,j]
                        self._y_bots[i,j] = self._y_tops[i,j]
                        self._z_bots[i,j] = self._z_tops[i,j]+self._width_v[i,j]
                    else:
                        self._x_tops[i,j] = self._x_tops[i,j-1]
                        self._y_tops[i,j] = self._y_tops[i,j-1]
                        self._x_bots[i,j] = self._x_bots[i,j-1]
                        self._y_bots[i,j] = self._y_bots[i,j-1]
                        self._z_tops[i,j] = self._z_bots[i,j-1]
                        self._z_bots[i,j] = self._z_tops[i,j]+self._width_v[i,j]
                    
                    self._xc[i,j]=self._x_tops[i,j]
                    self._yc[i,j]=self._y_tops[i,j]
                    self._zc[i,j]=self._z_tops[i,j]+self._width_v[i,j]/2
            
            # Calculate boundaries of panels
            self._panel_boundaries=[]
            for i in range(self._num_panels):
                bounds = []
                for j in range(self._num_sub_panels):
                    x1=self._x_tops[i,j] + (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                    y1=self._y_tops[i,j] + (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                    z1=self._z_tops[i,j]
                    x2=self._x_bots[i,j] + (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                    y2=self._y_bots[i,j] + (np.cos(np.radians(self._strike[i]))*self._length[i]/2) 
                    z2=self._z_bots[i,j]
                    x3=self._x_bots[i,j] - (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                    y3=self._y_bots[i,j] - (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                    z3=self._z_bots[i,j]
                    x4=self._x_tops[i,j] - (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                    y4=self._y_tops[i,j] - (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                    z4=self._z_bots[i,j]
                
                    x_bounds=np.array([x1,x2,x3,x4,x1])
                    y_bounds=np.array([y1,y2,y3,y4,y1])
                    z_bounds=np.array([z1,z2,z3,z4])
                    bounds.append([x_bounds,y_bounds,z_bounds])
                    
                self._panel_boundaries.append(bounds)
            
            # Calculate piecewise locations of fault panels in xsections
            self._fy=np.concat(([0],np.cumsum(self._length)),axis=0)
            self._fz=np.tile(np.concat((self._z_tops[0],[self._z_bots[0][-1]]),axis=0),(self._num_panels,1))
                
            if self._panel_types!=None:
                total_area=[]
                for i in range(self._num_panels):
                    for j in range(self._num_sub_panels):
                        # if (self._panel_types[i]=='A') | (self._panel_types[i]=='C'):
                        #     total_area.append(self._panel_areas[i])
                        if self._panel_types[i][j]=='C':
                            total_area.append(self._panel_areas[i,j])
                self._total_area=sum(total_area)
                self._total_length=np.max(self._fy)
                if self._num_sub_panels==0:
                    ix = [idx for idx, value in enumerate(self._panel_types) if value =='C'][0]
                    self._total_width=self._fz[ix+1]-self._fz[ix]
                else:
                    ix = [idx for idx, value in enumerate(self._panel_types[0]) if value =='C'][0]
                    self._total_width=self._fz[0][ix+1]-self._fz[0][ix]
                               
    def _length_to_xy(self,l):
        
        if (type(l)==int) | (type(l)==float):
            x = np.zeros(1)
            y = np.zeros(1)
            l = np.array([l])
        elif type(l)==list:
            l = np.array(l)
            x = np.zeros(l.shape)
            y = np.zeros(l.shape)
        else:
            x = np.zeros(l.shape)
            y = np.zeros(l.shape)
            
            
        # Within range
        idx = (l>=0) & (l < np.max(self._fy))
        if np.any(idx):
            ix = np.digitize(l[idx],self._fy)-1
            # Find center and total length of panel
            if not(self.creeping):
                xc = self._xc[ix,0]
                yc = self._yc[ix,0]
            else:
                xc = self._xc[ix]
                yc = self._yc[ix]
            # Find distance relative to "start" of segment
            l0 = l[idx] - self._fy[ix]
            # Find x,y position of "start" of segment
            x0 = xc - (np.sin(np.radians(self._strike[ix]))*self._length[ix]/2)
            y0 = yc - (np.cos(np.radians(self._strike[ix]))*self._length[ix]/2)
            # FInd x, y coordinate of position
            x[idx] = x0 + (np.sin(np.radians(self._strike[ix]))*l0)
            y[idx] = y0 + (np.cos(np.radians(self._strike[ix]))*l0)
        
        # At right edge of range
        idx = l==np.max(self._fy)
        if np.any(idx):
            ix = np.digitize(l[idx],self._fy,right=True)-1
            # Find center and total length of panel
            if not(self.creeping):
                xc = self._xc[ix,0]
                yc = self._yc[ix,0]
            else:
                xc = self._xc[ix]
                yc = self._yc[ix]
            # Find distance relative to "start" of segment
            l0 = l[idx] - self._fy[ix]
            # Find x,y position of "start" of segment
            x0 = xc - (np.sin(np.radians(self._strike[ix]))*self._length[ix]/2)
            y0 = yc - (np.cos(np.radians(self._strike[ix]))*self._length[ix]/2)
            # FInd x, y coordinate of position
            x[idx] = x0 + (np.sin(np.radians(self._strike[ix]))*l0)
            y[idx] = y0 + (np.cos(np.radians(self._strike[ix]))*l0)
            
        # Beyond left edge of range
        idx = l<0
        if np.any(idx):
            ix = np.full(np.sum(idx),0)
            # Find center and total length of panel
            if not(self.creeping):
                xc = self._xc[ix,0]
                yc = self._yc[ix,0]
            else:
                xc = self._xc[ix]
                yc = self._yc[ix]
            # Find distance relative to "start" of segment
            l0 = l[idx] - self._fy[ix]
            # Find x,y position of "start" of segment
            x0 = xc - (np.sin(np.radians(self._strike[ix]))*self._length[ix]/2)
            y0 = yc - (np.cos(np.radians(self._strike[ix]))*self._length[ix]/2)
            # FInd x, y coordinate of position
            x[idx] = x0 + (np.sin(np.radians(self._strike[ix]))*l0)
            y[idx] = y0 + (np.cos(np.radians(self._strike[ix]))*l0)
            
        # Beyond right edge of range
        idx = l>np.max(self._fy)
        if np.any(idx):
            ix = np.full(np.sum(idx),-1)
            # Find center and total length of panel
            if not(self.creeping):
                xc = self._xc[ix,0]
                yc = self._yc[ix,0]
            else:
                xc = self._xc[ix]
                yc = self._yc[ix]
            # Find distance relative to "start" of segment
            l0 = l[idx] - self._fy[ix-1]
            # Find x,y position of "start" of segment
            x0 = xc - (np.sin(np.radians(self._strike[ix]))*self._length[ix]/2)
            y0 = yc - (np.cos(np.radians(self._strike[ix]))*self._length[ix]/2)
            # FInd x, y coordinate of position
            x[idx] = x0 + (np.sin(np.radians(self._strike[ix]))*l0)
            y[idx] = y0 + (np.cos(np.radians(self._strike[ix]))*l0)
        
        return x,y
    
    def _calc_fault_surface(self):
        '''
        Calculate a gridded version of the fault surface in both fault aligned
        coordinates and Landlab grid coordinates. Also fits a plane to each
        fault panel so that positions on the fault plane can be easily querried.


        '''
        
        # For consistency, y-coordinates are along fault length (strike) and 
        # x-coordinates are along fault width (dip). Because the fault is vertical
        # x-coordinates and z-coordinates are the same, so we will ignore the 
        # x- coordinates.
        fiz = np.arange(0,np.sum(self._owidth),self._fault_dx)
        fiy = np.arange(0,self._fy.max(),self._fault_dx)
        
        # Fault top tip centered coordinates
        self._FY,self._FZ = np.meshgrid(fiy,fiz)

    def _boxcar(self):
        self._mean_slip_rate = self._slip_rate
        fy = np.arange(0,self._fy.max(),self._fault_dx)
        self._slip_rate_along_fault = np.full(fy.shape,self._slip_rate)
        self._ss_rate_along_fault = np.full(fy.shape,self._ss)
        self._ds_rate_along_fault = np.full(fy.shape,self._ds)
        
    def _parabolic(self):
        # Solve for coefficient such that peak of parabola is the slip_rate
        # and it reaches 0 at half length
        a = self._slip_rate / ((self._fy.max()/2)**2)
        a_ss = self._ss / ((self._fy.max()/2)**2)
        a_ds = self._ds / ((self._fy.max()/2)**2)        
        # Fault length aligend coordinates
        fy = np.arange(0,self._fy.max(),self._fault_dx) - self._fy.max()/2
        self._slip_rate_along_fault = -a*fy**2+self._slip_rate
        self._ss_rate_along_fault = -a_ss*fy**2+self._ss
        self._ds_rate_along_fault = -a_ds*fy**2+self._ds        
        # Calculate mean slip rae
        self._mean_slip_rate = np.array([np.mean(self._slip_rate_along_fault)])
        
    def _blunt_parabolic(self):
        # Define length of blunt section
        hl_of_flat = (self._fy.max() * self._fraction_blunt)/2 
        # Define parabolic constants
        a = self._slip_rate / (-(hl_of_flat)**2 + (self._fy.max()/2)**2)
        k = a * (self._fy.max()/2)**2
        a_ss = self._ss/ (-(hl_of_flat)**2 + (self._fy.max()/2)**2)
        k_ss = a_ss * (self._fy.max()/2)**2
        a_ds = self._ds / (-(hl_of_flat)**2 + (self._fy.max()/2)**2)
        k_ds = a_ds * (self._fy.max()/2)**2        
        # Fault length aligned coordinates
        fy = np.arange(0,self._fy.max(),self._fault_dx)  - self._fy.max()/2
        # Piecewise along fault slip rate
        self._slip_rate_along_fault = np.zeros(fy.shape)
        self._slip_rate_along_fault[fy < -hl_of_flat] = -a*(fy[fy < - hl_of_flat])**2 + k
        self._slip_rate_along_fault[fy > hl_of_flat] = -a*(fy[fy > hl_of_flat])**2 + k
        self._slip_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._slip_rate
        self._ss_rate_along_fault = np.zeros(fy.shape)
        self._ss_rate_along_fault[fy < -hl_of_flat] = -a_ss*(fy[fy < - hl_of_flat])**2 + k_ss
        self._ss_rate_along_fault[fy > hl_of_flat] = -a_ss*(fy[fy > hl_of_flat])**2 + k_ss
        self._ss_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._ss
        self._ds_rate_along_fault = np.zeros(fy.shape)
        self._ds_rate_along_fault[fy < -hl_of_flat] = -a_ds*(fy[fy < - hl_of_flat])**2 + k_ds
        self._ds_rate_along_fault[fy > hl_of_flat] = -a_ds*(fy[fy > hl_of_flat])**2 + k_ds
        self._ds_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._ds
        # Calculate mean slip rate
        self._mean_slip_rate = np.array([np.mean(self._slip_rate_along_fault)])
        
    def _triangular(self):
        # Fault length aligned coordinates
        fy = np.arange(0,self._fy.max(),self._fault_dx) - self._fy.max()/2
        # Piecewise along fault slip rate
        self._slip_rate_along_fault = np.zeros(fy.shape)
        self._slip_rate_along_fault[fy >= 0] = (-self._slip_rate/ (self._fy.max()/2)) * fy[fy >= 0] + self._slip_rate 
        self._slip_rate_along_fault[fy < 0] = (self._slip_rate/ (self._fy.max()/2)) * fy[fy < 0] + self._slip_rate
        self._ss_rate_along_fault = np.zeros(fy.shape)
        self._ss_rate_along_fault[fy >= 0] = (-self._ss/ (self._fy.max()/2)) * fy[fy >= 0] + self._ss 
        self._ss_rate_along_fault[fy < 0] = (self._ss/ (self._fy.max()/2)) * fy[fy < 0] + self._ss
        self._ds_rate_along_fault = np.zeros(fy.shape)
        self._ds_rate_along_fault[fy >= 0] = (-self._ds/ (self._fy.max()/2)) * fy[fy >= 0] + self._ds 
        self._ds_rate_along_fault[fy < 0] = (self._ds/ (self._fy.max()/2)) * fy[fy < 0] + self._ds
        # Calculate mean slip rate
        self._mean_slip_rate = np.array([np.mean(self._slip_rate_along_fault)])
        
    def _blunt_triangular(self):
        # Define length of blunt section
        hl_of_flat = (self._fy.max() * self._fraction_blunt)/2 
        # Solve for coefficients
        m = self._slip_rate / (hl_of_flat - self._fy.max()/2)
        b = -m*(self._fy.max()/2)
        m_ss = self._ss / (hl_of_flat - self._fy.max()/2)
        b_ss = -m_ss*(self._fy.max()/2)
        m_ds= self._ds / (hl_of_flat - self._fy.max()/2)
        b_ds = -m_ds*(self._fy.max()/2)
        # Fault length aligned coordinates
        fy = np.arange(0,self._fy.max(),self._fault_dx) - self._fy.max()/2
        # Piecewise along fault slip rate
        self._slip_rate_along_fault = np.zeros(fy.shape)
        self._slip_rate_along_fault[fy < -hl_of_flat] = -m*(fy[fy < - hl_of_flat]) + b
        self._slip_rate_along_fault[fy > hl_of_flat] = m*(fy[fy > hl_of_flat]) + b
        self._slip_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._slip_rate
        self._ss_rate_along_fault = np.zeros(fy.shape)
        self._ss_rate_along_fault[fy < -hl_of_flat] = -m_ss*(fy[fy < - hl_of_flat]) + b_ss
        self._ss_rate_along_fault[fy > hl_of_flat] = m_ss*(fy[fy > hl_of_flat]) + b_ss
        self._ss_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._ss
        self._ds_rate_along_fault = np.zeros(fy.shape)
        self._ds_rate_along_fault[fy < -hl_of_flat] = -m_ds*(fy[fy < - hl_of_flat]) + b_ds
        self._ds_rate_along_fault[fy > hl_of_flat] = m_ds*(fy[fy > hl_of_flat]) + b_ds
        self._ds_rate_along_fault[(fy >= -hl_of_flat) & (fy <= hl_of_flat)] = self._ds
        # Calculate mean slip rate
        self._mean_slip_rate = np.array([np.mean(self._slip_rate_along_fault)])
        
    def _discretize_slip_rate(self):
        # Generate initial bin edges based on number of divisions
        fy = np.arange(0,self._fy.max(),self._fault_dx)
        sr_bins = np.linspace(0,self._fy.max(),self._along_fault_segments+1)
        # Interleave any bends in the fault, remove any duplicates,
        # and sort so bins are still ascending
        if self._num_panels>1:
            sr_bins = np.append(sr_bins,self._fy[1:-1])
            sr_bins = np.unique(sr_bins) # numpy unique returns sorted result
        ix = np.digitize(fy,sr_bins)-1 # Subtract 1 so that this is an index
        # Find means within bins and bin locations in fault length coordinates
        isr = np.bincount(ix,self._slip_rate_along_fault) / np.bincount(ix)
        iss = np.bincount(ix,self._ss_rate_along_fault) / np.bincount(ix)
        ids = np.bincount(ix,self._ds_rate_along_fault) / np.bincount(ix)
        binned_mean_l = np.bincount(ix,fy) / np.bincount(ix)
        
        # Convert bin centers in fault length coordinates to model coordinates 
        ixc,iyc = self._length_to_xy(binned_mean_l)
        
        # Find strikes of patches
        strike_ix = np.digitize(binned_mean_l,self._fy)-1
        ist = self._strike[strike_ix]
        
        # Calculate bins lengths
        ile = np.diff(sr_bins)
        
        # Find center depths and widths (down dip) 
        if self.creeping:
            izc =np.full(ixc.shape,self._zc[0])
            iwi = np.full(ixc.shape,self._width[0])

        else:
            pt = np.array(self._panel_types).ravel()
            zc = self._zc.ravel()
            wi = self._width.ravel()
            izc = np.full(ixc.shape,zc[pt=='I'][0])
            iwi = np.full(ixc.shape,wi[pt=='I'][0])
            
        self._interseismic_patches = [ixc,iyc,izc,isr,iss,ids,ile,iwi,ist]
        
    def _generate_ok_grid(self):
        """
        Helper function to call the appropriate sub function to generate the array of 
        "recievers" for which the elastic dislocation is solved

        """
        if type(self.grid)==RasterModelGrid:
            self._generate_ok_xy_raster()
        elif type(self.grid)==HexModelGrid:
            self._generate_ok_xy_hex()
        
    def _generate_ok_xy_raster(self):
        """
        Generates an appropriate list of recievers for a Landlad RasterModelGrid

        """
        # Extract x-y coordinates of links for calculating horizontal velocities
        xyl = self.grid.xy_of_link
        xl = xyl[:,0].ravel()
        yl = xyl[:,1].ravel()
        # Extract x-y coordinates of core nodes for calculating vertical velocities
        xn = self.grid.x_of_node[self.grid.core_nodes]
        yn = self.grid.y_of_node[self.grid.core_nodes]
        # Concatenate links and nodes for single calculation of velocities
        # Generate index for determining which are horizontal links, 
        # vertical links, and which are nodes
        horz_links = np.zeros(xl.shape).astype(bool)
        vert_links = np.zeros(xl.shape).astype(bool)
        horz_links[self.grid.horizontal_links]=True
        vert_links[self.grid.vertical_links]=True
        self._horz_link_idx = np.concat((horz_links,np.zeros(xn.shape)),axis=0).astype(bool)
        self._vert_link_idx = np.concat((vert_links,np.zeros(xn.shape)),axis=0).astype(bool)
        self._node_idx = np.concat((np.zeros(xl.shape),np.ones(xn.shape)),axis=0).astype(bool)
        self._xs = np.concat((xl,xn),axis=0)
        self._ys = np.concat((yl,yn),axis=0)
        
    def _generate_ok_xy_hex(self):
        """
        Generates an appropriate list of recievers for a Landlab HexModelGrid

        """
        # Extract x-y coordinates of links for calculating horizontal velocities
        xyl = self.grid.xy_of_link
        xl = xyl[:,0].ravel()
        yl = xyl[:,1].ravel()
        # Extract x-y coordinates of core nodes for calculating vertical velocities
        xn = self.grid.x_of_node[self.grid.core_nodes]
        yn = self.grid.y_of_node[self.grid.core_nodes]
        links = np.ones(xl.shape).astype(bool)
        nodes = np.ones(xn.shape).astype(bool)
        self._link_idx = np.concat((links,np.zeros(xn.shape)),axis=0).astype(bool)
        self._node_idx = np.concat((np.zeros(xl.shape),nodes),axis=0).astype(bool)
        self._xs = np.concat((xl,xn),axis=0)
        self._ys = np.concat((yl,yn),axis=0)
        
        
    def _establish_advection_and_uplift(self):
        """
        Instantiates an instance of the AdvectionTVD component and set ups the 
        interseismic velocity field within the instance along with a vertical velocity
        at each grid node.

        """
        self._vel=self.grid.add_zeros('advection__velocity',at='link',clobber=True)
        self._adv = AdvectionSolverTVD(self.grid,fields_to_advect=self.fields_to_advect,advection_direction_is_steady=False)
        self._u = self.grid.add_zeros('vertical__velocity',at='node',clobber=True)
        # Calculate interseismic velocities
        self._calc_interseismic_vel()
        if type(self.grid)==RasterModelGrid:
            # Load interseismic velocities into horizontal velocity and uplift
            self._vel[self.grid.horizontal_links] = self._ivx[self._horz_link_idx]
            self._vel[self.grid.vertical_links] = self._ivy[self._vert_link_idx]
            self._u[self.grid.core_nodes]=self._ivz[self._node_idx]
        elif type(self.grid)==HexModelGrid:
            # Load interseismic velocities into horizontal velocity and uplift
            self.grid.map_vectors_to_links(self._ivx[self._link_idx],self._ivy[self._link_idx],out=self._vel)
            self._u[self.grid.core_nodes]=self._ivz[self._node_idx]
            
    def _update_advection_and_uplift(self):
        """
        Updates the advection and vertical velocities

        """
        if type(self.grid)==RasterModelGrid:
            # Load interseismic velocities into horizontal velocity and uplift
            self._vel[self.grid.horizontal_links] = self._ivx[self._horz_link_idx]
            self._vel[self.grid.vertical_links] = self._ivy[self._vert_link_idx]
            self._u[self.grid.core_nodes]=self._ivz[self._node_idx]
        elif type(self.grid)==HexModelGrid:
            # Load interseismic velocities into horizontal velocity and uplift
            self.grid.map_vectors_to_links(self._ivx[self._link_idx],self._ivy[self._link_idx],out=self._vel)
            self._u[self.grid.core_nodes]=self._ivz[self._node_idx]
 
    def _calc_seismogenic_panels(self):
        """
        Function to automatically determine which parts of fault can fail 
        coseismically (within seismogenic zone),  will slip interseismically 
        (below seismogenic zone), or are above the seismogenic zone.
        
        When run, this will recalculate the number of panels and overwrite any
        assignments made for 'panel_types'.
       
        """
        
        # Extract boundaries on seismogenic zone
        usz = self._seismogenic_zone[0]
        lsz = self._seismogenic_zone[1]
        # Determine where current panels sit with respect to seismogenic zone
        # and partition
        panel_types = []
        new_widths = []
        new_dips = []

        for i in range(self._num_panels):
            fz0 = self._z_tops[i]
            fz1 = self._z_bots[i]
            
            if (fz1 < usz):
                # Existing panel is completely above seismogenic zone
                panel_types.append('A')
                new_widths.append(self._width_v[i])
                new_dips.append(self._dip[0])
            elif (fz0 < usz) & (fz1 < lsz):
                # Existing panel is completely within seismogenic zone
                panel_types.append('C')
                new_widths.append(self._width_v[i])
                new_dips.append(self._dip[0])
            elif (fz0 > lsz):
                panel_types.append('I')
                new_widths.append(self._width_v[i])
                new_dips.append(self._dip[0])
            else:
                if (fz0 < usz) & (fz1 > usz) & (fz1 < lsz):
                    # Panel to be split between A and C
                    w1 = (usz-fz0)
                    w2 = (fz1 - usz)
                    new_widths.append([w1,w2])
                    panel_types.append(['A','C'])
                    new_dips.append([self._dip[0],self._dip[0]])
                elif (fz0 > usz) & (fz1 > lsz):
                    # Panel to be split between C and I
                    w1 = (lsz-fz0)
                    w2 = (fz1-lsz)
                    new_widths.append([w1,w2])
                    panel_types.append(['C','I'])
                    new_dips.append([self._dip[0],self._dip[0]])
                    
                elif (fz0 < usz) & (fz1 > lsz):
                    # Panel to be split between A, C, and I
                    w1 = (usz-fz0)
                    w2 = (lsz - usz)
                    w3 = (fz1-lsz)   
                    new_widths.append([w1,w2,w3])
                    panel_types.append(['A','C','I'])
                    new_dips.append([self._dip[0],self._dip[0],self._dip[0]])
        
        for panels in panel_types:      
            if 'I' not in panels:
                raise ValueError('Fault depth is insufficient to reach base of seismogenic zone')
        
        # Store new width, dips, and panel types into object bypassing setters
        self._dip=np.array(new_dips)
        self._width=np.array(new_widths)
        self._panel_types=panel_types
        # # Rerun generators
        self._calc_panel_geoms()
        self._calc_fault_surface()  
        
    
    def _calc_interseismic_vel(self):
        """
        Calculates interseismic velocities

        """
        # Zero surface
        self._zs=np.zeros(self._xs.shape)   
        if (not(self._topographic_correction)) & (self._num_sub_panels>0) & (self._slip_rate_function=='boxcar'):    
            vx=[]; vy=[]; vz=[];
            for i in range(self._num_panels):
                for j in range(self._num_sub_panels):
                    if self._panel_types[i][j]=='I':
                        vx0,vy0,vz0=_ok(self._xs,self._ys,self._zs,self._xc[i,j],self._yc[i,j],self._zc[i,j],
                                        self._length[i],self._width[i,j],self._dip[i,j],
                                        self._strike[i],self._ss[0],self._ds[0],0,self._mu,self._nu)
                        vx.append(vx0)
                        vy.append(vy0)
                        vz.append(vz0)
            self._ivx = sum(vx)
            self._ivy = sum(vy)
            self._ivz = sum(vz)
        elif (not(self._topographic_correction)) & (self._num_sub_panels==0) & (self._slip_rate_function=='boxcar'):       
            vx=[]; vy=[]; vz=[];
            for i in range(self._num_panels):
                if self._panel_types[i]=='I':
                    vx0,vy0,vz0=_ok(self._xs,self._ys,self._zs,self._xc[i],self._yc[i],self._zc[i],
                                    self._length[i],self._width,self._dip,
                                    self._strike[i],self._ss[0],self._ds[0],0,self._mu,self._nu)
                    vx.append(vx0)
                    vy.append(vy0)
                    vz.append(vz0)
            self._ivx = sum(vx)
            self._ivy = sum(vy)
            self._ivz = sum(vz)
        
        elif (self._topographic_correction) & (self._num_sub_panels>0) & (self._slip_rate_function=='boxcar'):
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
            # # zl[zl <= -1*self._tip_location[2]] = -1*self._tip_location[2]+0.5

            ## This works consistently with high rates of subsidence. 
            if np.any(zl <= -1*self._tip_location[2]):
                tip = -1*self._tip_location[2]
                orig_rng = np.max(zl) - np.min(zl)
                new_rng = np.max(zl) - (tip + 0.1)
                zl = zl * (new_rng/orig_rng)
                zl += (tip - np.min(zl)) + 0.1

            vx=[]; vy=[]; vz=[];
            for i in range(self._num_panels):
                for j in range(self._num_sub_panels):
                    if self._panel_types[i][j]=='I':
                        vx0,vy0,vz0=_ok_topo(self._xs,self._ys,self._zs,self._xc[i,j],self._yc[i,j],self._zc[i,j],
                                             self._length[i],self._width[i,j],self._dip[i,j],
                                             self._strike[i],self._ss[0],self._ds[0],0,self._mu,self._nu,zl)
                        vx.append(vx0)
                        vy.append(vy0)
                        vz.append(vz0)
            self._ivx = sum(vx)
            self._ivy = sum(vy)
            self._ivz = sum(vz)
            
        elif (self._topographic_correction) & (self._num_sub_panels==0) & (self._slip_rate_function=='boxcar'): 
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
            # # zl[zl <= -1*self._tip_location[2]] = -1*self._tip_location[2]+0.5

            ## This works consistently with high rates of subsidence. 
            if np.any(zl <= -1*self._tip_location[2]):
                tip = -1*self._tip_location[2]
                orig_rng = np.max(zl) - np.min(zl)
                new_rng = np.max(zl) - (tip + 0.1)
                zl = zl * (new_rng/orig_rng)
                zl += (tip - np.min(zl)) + 0.1


            vx=[]; vy=[]; vz=[];
            for i in range(self._num_panels):
                if self._panel_types[i]=='I':
                    vx0,vy0,vz0=_ok_topo(self._xs,self._ys,self._zs,self._xc[i],self._yc[i],self._zc[i],
                                         self._length[i],self._width,self._dip,
                                         self._strike[i],self._ss[0],self._ds[0],0,self._mu,self._nu,zl)
                    vx.append(vx0)
                    vy.append(vy0)
                    vz.append(vz0)
            self._ivx = sum(vx)
            self._ivy = sum(vy)
            self._ivz = sum(vz)
            
        elif (not(self._slip_rate_function=='boxcar')) & (not(self._topographic_correction)):
            ixc = self._interseismic_patches[0]
            iyc = self._interseismic_patches[1]
            izc = self._interseismic_patches[2]
            iss = self._interseismic_patches[4]
            ids = self._interseismic_patches[5]
            ilengths = self._interseismic_patches[6]
            iwidths = self._interseismic_patches[7]
            istrikes = self._interseismic_patches[8]
            if not(self.parallel):
                vx=[]; vy=[]; vz=[];
                for i in range(len(ixc)):
                    vx0,vy0,vz0=_ok(self._xs,self._ys,self._zs,ixc[i],iyc[i],izc[i],
                                    ilengths[i],iwidths[i],self._dip.ravel()[0],
                                    istrikes[i],iss[i],ids[i],0,self._mu,self._nu)
                    vx.append(vx0)
                    vy.append(vy0)
                    vz.append(vz0)
                    
                self._ivx = sum(vx)
                self._ivy = sum(vy)
                self._ivz = sum(vz)
            else:
                items = [(self._xs,self._ys,self._zs,ixc[i],iyc[i],izc[i],ilengths[i],iwidths[i],self._dip.ravel()[0],istrikes[i],iss[i],ids[i],0,self._mu,self._nu) for i in range(len(ixc))]
                with mp.Pool(self._num_cores) as pool:
                    res = pool.starmap(_ok,items)
                    res = np.sum(list(zip(*res)),axis=1)
                    self._ivx = res[0,:].ravel()
                    self._ivy = res[1,:].ravel()
                    self._ivz = res[2,:].ravel()
        elif (not(self._slip_rate_function=='boxcar')) & (self._topographic_correction):
            
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
            # # zl[zl <= -1*self._tip_location[2]] = -1*self._tip_location[2]+0.5

            ## This works consistently with high rates of subsidence. 
            if np.any(zl <= -1*self._tip_location[2]):
                tip = -1*self._tip_location[2]
                orig_rng = np.max(zl) - np.min(zl)
                new_rng = np.max(zl) - (tip + 0.1)
                zl = zl * (new_rng/orig_rng)
                zl += (tip - np.min(zl)) + 0.1

            ixc = self._interseismic_patches[0]
            iyc = self._interseismic_patches[1]
            izc = self._interseismic_patches[2]
            iss = self._interseismic_patches[4]
            ids = self._interseismic_patches[5]
            ilengths = self._interseismic_patches[6]
            iwidths = self._interseismic_patches[7]
            istrikes = self._interseismic_patches[8]
            if not(self.parallel):
                vx=[]; vy=[]; vz=[];
                for i in range(len(ixc)):
                    vx0,vy0,vz0=_ok_topo(self._xs,self._ys,self._zs,ixc[i],iyc[i],izc[i],
                                              ilengths[i],iwidths[i],self._dip.ravel()[0],
                                              istrikes[i],iss[i],ids[i],0,self._mu,self._nu,zl)
                    vx.append(vx0)
                    vy.append(vy0)
                    vz.append(vz0)
                
                self._ivx = sum(vx)
                self._ivy = sum(vy)
                self._ivz = sum(vz)
            else:
                items = [(self._xs,self._ys,self._zs,ixc[i],iyc[i],izc[i],ilengths[i],iwidths[i],self._dip.ravel()[0],istrikes[i],iss[i],ids[i],0,self._mu,self._nu,zl) for i in range(len(ixc))]
                with mp.Pool(self._num_cores) as pool:
                    res = pool.starmap(_ok_topo,items)
                    res = np.sum(list(zip(*res)),axis=1)
                    self._ivx = res[0,:].ravel()
                    self._ivy = res[1,:].ravel()
                    self._ivz = res[2,:].ravel()
            
            

        
    def plot_fault_geometry(self,plot_seismogenic=False,cmap='viridis',return_handles=False,fig1size=(10,10),fig2size=(10,10)):
        """
        Plots map view of fault depth with respect to the bounds of the Landlab
        grid and cross-section of the fault

        Parameters
        ----------
        plot_seismogenic : boolean, optional
            Flag to plot the seismogenic zone (True) or not (False). The default is False.
        cmap : name of valid colormap or valid colormap, optional
            Colormap for the fault depth. The default is 'viridis'.
        return_handles : boolean, optional
            Flag to return the figure handles of the generated figures. The default
            is False.

        Returns
        -------
        f1 : figure handle, optional
            Handle to the produced figure.

        """
        
        f1=plt.figure(figsize=fig1size)
        f2=plt.figure(figsize=fig2size)
        
        # Define polygon that outlines LEM domain
        if type(self.grid)==RasterModelGrid:
            ext_y=self.grid.extent[0]
            ext_x=self.grid.extent[1]
        elif type(self.grid)==HexModelGrid:
            ext_y = np.max(self.grid.y_of_node)
            ext_x = np.max(self.grid.x_of_node)
            
            
        ax1 = f1.add_subplot(1,1,1)   
        
        if len(self._xc.shape)==1:
            for i in range(self._num_panels):
                x1=self._xc[i] + (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                y1=self._yc[i] + (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                x2=self._xc[i] - (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                y2=self._yc[i] - (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                if i==0:
                    ax1.plot([x1,x2],[y1,y2],c='k',label='Fault Segments')
                else:
                    ax1.plot([x1,x2],[y1,y2],c='k')
            
            ax1.scatter(self._xc,self._yc,c='k',s=50,label='Segment Centers')
        else:
            for i in range(self._num_panels):
                x1=self._xc[i,0] + (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                y1=self._yc[i,0] + (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                x2=self._xc[i,0] - (np.sin(np.radians(self._strike[i]))*self._length[i]/2)
                y2=self._yc[i,0] - (np.cos(np.radians(self._strike[i]))*self._length[i]/2)
                if i==0:
                    ax1.plot([x1,x2],[y1,y2],c='k',label='Fault Segments')
                else:
                    ax1.plot([x1,x2],[y1,y2],c='k')
            
            ax1.scatter(self._xc[:,0],self._yc[:,0],c='k',s=50,label='Segment Centers')
    
        ax1.plot([0,ext_x,ext_x,0,0],[0,0,ext_y,ext_y,0],c='k',linestyle=':',linewidth=2,label='LEM Boundary')
        
        ax1.set_aspect('equal')
        ax1.legend(loc='best')
        ax1.set_xlabel('X (m)')
        ax1.set_ylabel('Y (m)')
        
        # for i in range(self._num_panels):
        #     if self._panel_types!=None:
        #         if self._panel_types[i]=='A':
        #             ax1.plot(self._panel_boundaries[i][0],self._panel_boundaries[i][1],c='b')
        #             ax1.scatter(self._xc[i],self._yc[i],s=50,c='b')
        #         elif self._panel_types[i]=='C':
        #             ax1.plot(self._panel_boundaries[i][0],self._panel_boundaries[i][1],c='r')
        #             ax1.scatter(self._xc[i],self._yc[i],s=50,c='r')
        #         elif self._panel_types[i]=='I':
        #             ax1.plot(self._panel_boundaries[i][0],self._panel_boundaries[i][1],c='k')
        #             ax1.scatter(self._xc[i],self._yc[i],s=50,c='k')
        #     else:
        #         ax1.plot(self._panel_boundaries[i][0],self._panel_boundaries[i][1],c='k')
        #         ax1.scatter(self._xc[i],self._yc[i],s=50,c='k')    
                

        # cbar=plt.colorbar(im1,ax=ax1)
        # cbar.ax.set_ylabel('Depth (m)')
        # cbar.ax.invert_yaxis()
        
        ax2=f2.add_subplot(1,1,1)
        A_count = 0
        C_count = 0 
        I_count = 0
        
        if len(self._width.shape)>1:
            for i in range(self._num_panels):
                for j in range(self._num_sub_panels):
                    if self._panel_types[i][j]=='A':
                        if A_count == 0:
                            xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                            yp = [self._fz[i,j],self._fz[i,j],self._fz[i,j+1],self._fz[i,j+1],self._fz[i,j]]
                            ax2.plot(xp,yp,c='b',label='Above Seismogenic')
                            A_count += 1
                        else:
                            xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                            yp = [self._fz[i,j],self._fz[i,j],self._fz[i,j+1],self._fz[i,j+1],self._fz[i,j]]
                            ax2.plot(xp,yp,c='b')
                    elif self._panel_types[i][j]=='C':
                        if C_count == 0:
                            xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                            yp = [self._fz[i,j],self._fz[i,j],self._fz[i,j+1],self._fz[i,j+1],self._fz[i,j]]
                            ax2.plot(xp,yp,c='r',label='Within Seismogenic')
                            C_count += 1
                        else:
                            xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                            yp = [self._fz[i,j],self._fz[i,j],self._fz[i,j+1],self._fz[i,j+1],self._fz[i,j]]
                            ax2.plot(xp,yp,c='r')
                    elif self._panel_types[i][j]=='I':
                        if I_count == 0:
                            xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                            yp = [self._fz[i,j],self._fz[i,j],self._fz[i,j+1],self._fz[i,j+1],self._fz[i,j]]
                            ax2.plot(xp,yp,c='k',label='Below Seismogenic')
                            I_count += 1
                        else:
                            xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                            yp = [self._fz[i,j],self._fz[i,j],self._fz[i,j+1],self._fz[i,j+1],self._fz[i,j]]
                            ax2.plot(xp,yp,c='k')
        else:
            for i in range(self._num_panels):
                if self._panel_types[i]=='A':
                    if A_count == 0:
                        xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                        yp = [self._fz[i,0],self._fz[i,0],self._fz[i,1],self._fz[i,1],self._fz[i,0]]
                        ax2.plot(xp,yp,c='b',label='Above Seismogenic')
                        A_count += 1
                    else:
                        xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                        yp = [self._fz[i,0],self._fz[i,0],self._fz[i,1],self._fz[i,1],self._fz[i,0]]
                        ax2.plot(xp,yp,c='b')
                elif self._panel_types[i]=='C':
                    if C_count == 0:
                        xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                        yp = [self._fz[i,0],self._fz[i,0],self._fz[i,1],self._fz[i,1],self._fz[i,0]]
                        ax2.plot(xp,yp,c='r',label='Within Seismogenic')
                        C_count += 1
                    else:
                        xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                        yp = [self._fz[i,0],self._fz[i,0],self._fz[i,1],self._fz[i,1],self._fz[i,0]]
                        ax2.plot(xp,yp,c='r')
                elif self._panel_types[i]=='I':
                    if I_count == 0:
                        xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                        yp = [self._fz[i,0],self._fz[i,0],self._fz[i,1],self._fz[i,1],self._fz[i,0]]
                        ax2.plot(xp,yp,c='k',label='Below Seismogenic')
                        I_count += 1
                    else:
                        xp = [self._fy[i],self._fy[i+1],self._fy[i+1],self._fy[i],self._fy[i]]
                        yp = [self._fz[i,0],self._fz[i,0],self._fz[i,1],self._fz[i,1],self._fz[i,0]]
                        ax2.plot(xp,yp,c='k')
                
                        
        
        if plot_seismogenic:
            ax2.axhline(self._seismogenic_zone[0],c='r',linestyle=':')
            ax2.axhline(self._seismogenic_zone[1],c='r',linestyle=':')
        
        ax2.yaxis.set_inverted(True)
        ax2.set_aspect('equal')
        ax2.set_ylabel('Depth (m)')
        ax2.set_xlabel('Along Length Distance (m)')
        ax2.legend(loc='best')  

        if return_handles:
            return f1,f2
        
    def plot_slip_rate_along_fault(self,plot_components=False,return_handles=False,figsize=(10,10)):

        # Generate initial bin edges based on number of divisions
        fy = np.arange(0,self._fy.max(),self._fault_dx)
        sr_bins = np.linspace(0,self._fy.max(),self._along_fault_segments+1)
        # Interleave any bends in the fault, remove any duplicates,
        # and sort so bins are still ascending
        if self._num_panels>1:
            sr_bins = np.append(sr_bins,self._fy[1:-1])
            sr_bins = np.unique(sr_bins) # numpy unique returns sorted result
        ix = np.digitize(fy,sr_bins)-1 # Subtract 1 so that this is an index
        # Find means within bins and bin locations in fault length coordinates
        binned_mean_sr = np.bincount(ix,self._slip_rate_along_fault) / np.bincount(ix)
        binned_mean_ss = np.bincount(ix,self._ss_rate_along_fault) / np.bincount(ix)
        binned_mean_ds = np.bincount(ix,self._ds_rate_along_fault) / np.bincount(ix)


        approx_sr = np.zeros(fy.shape)
        approx_ss = np.zeros(fy.shape)
        approx_ds = np.zeros(fy.shape)
        for i in range(len(sr_bins)-1):
            approx_sr[ix==i] = binned_mean_sr[i]
            approx_ss[ix==i] = binned_mean_ss[i]
            approx_ds[ix==i] = binned_mean_ds[i]
        
        if plot_components:
            f1 = plt.figure(figsize=figsize,layout='tight')
            
            plt.subplot(3,1,1)
            plt.plot((fy)/1000,self._slip_rate_along_fault*100*10,c='gray',linestyle=':',label='True Along-Strike Slip Rate')
            plt.plot((fy)/1000,approx_sr*100*10,c='k',label='Approximated Along-Strike Slip Rate')
            if self._num_panels>1:
                bnds = self._fy[1:-1]
                for i in range(len(bnds)):
                    plt.axvline(bnds[i]/1000,c='r',linestyle=':')
            plt.xlabel('Distance Along Fault Length (km)')
            plt.ylabel('Total Slip Rate (mm/yr)')
            plt.legend(loc='best')
            
            plt.subplot(3,1,2)
            plt.plot((fy)/1000,self._ds_rate_along_fault*100*10,c='gray',linestyle=':')
            plt.plot((fy)/1000,approx_ds*100*10,c='k')
            if self._num_panels>1:
                bnds = self._fy[1:-1]
                for i in range(len(bnds)):
                    plt.axvline(bnds[i]/1000,c='r',linestyle=':')
            plt.xlabel('Distance Along Fault Length (km)')
            plt.ylabel('Dip Slip Component (mm/yr)')       
    
            plt.subplot(3,1,3)
            plt.plot((fy)/1000,self._ss_rate_along_fault*100*10,c='gray',linestyle=':')
            plt.plot((fy)/1000,approx_ss*100*10,c='k')
            if self._num_panels>1:
                bnds = self._fy[1:-1]
                for i in range(len(bnds)):
                    plt.axvline(bnds[i]/1000,c='r',linestyle=':')
            plt.xlabel('Distance Along Fault Length (km)')
            plt.ylabel('Strike Slip Component (mm/yr)')
        else:
            f1 = plt.figure(figsize=figsize,layout='tight')
            
            plt.plot((fy)/1000,self._slip_rate_along_fault*100*10,c='gray',linestyle=':',label='True Along-Strike Slip Rate')
            plt.plot((fy)/1000,approx_sr*100*10,c='k',label='Approximated Along-Strike Slip Rate')
            if self._num_panels>1:
                bnds = self._fy[1:-1]
                for i in range(len(bnds)):
                    plt.axvline(bnds[i]/1000,c='r',linestyle=':')
            plt.xlabel('Distance Along Fault Length (km)')
            plt.ylabel('Total Slip Rate (mm/yr)')
            plt.legend(loc='best')  
            
        if return_handles:
            return f1

    def plot_interseismic_velocity_field(self,cmap='Spectral_r',return_handles=False,figsize=(15,3),
                                        fig_type='individual',quiver_interval=1000,shrink=0.75):
        """
        Plots the x, y, and z components of the interseismic velocity field

        Parameters
        ----------
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
        # This should works whether the grid is raster or hex since it uses
        # the built in landlab grid methods
        
        # Generate a deep copy of the grid to not modify the stored one
        _grid = copy.deepcopy(self.grid)

        if fig_type=='individual':
        
            ivx = np.zeros(self.grid.nodes.shape).ravel()
            ivy = np.zeros(self.grid.nodes.shape).ravel()
            ivz = np.zeros(self.grid.nodes.shape).ravel()
            
            # Assign core nodes values in mm/yr
            ivx[self.grid.core_nodes]=self._ivx[self._node_idx]*100*10
            ivy[self.grid.core_nodes]=self._ivy[self._node_idx]*100*10
            ivz[self.grid.core_nodes]=self._ivz[self._node_idx]*100*10
            
            # Assign values to nodes in copied grid
            _grid.add_field('ivx',ivx,at='node')
            _grid.add_field('ivy',ivy,at='node')
            _grid.add_field('ivz',ivz,at='node')
            
            # Use imshow to display values
            f1 = plt.figure(figsize=figsize,layout='tight')
            
            plt.subplot(1,3,1)
            plt.title('Displacement in X')
            _grid.imshow('ivx',shrink=shrink,
                         cmap=cmap,grid_units=('m','m'))
            
            plt.subplot(1,3,2)
            plt.title('Displacement in Y')
            _grid.imshow('ivy',shrink=shrink,
                         cmap=cmap,grid_units=('m','m'))
            
            plt.subplot(1,3,3)
            plt.title('Displacement in Z')
            _grid.imshow('ivz',colorbar_label='(mm/yr)',shrink=shrink,
                         cmap=cmap,grid_units=('m','m'))
        elif fig_type=='combined': 

            # Prepare Z velocity
            ivz = np.zeros(self.grid.nodes.shape).ravel()
            ivz[self.grid.core_nodes]=self._ivz[self._node_idx]*100*10
            _grid.add_field('ivz',ivz,at='node')

            # Prepare X and Y velocity
            xn = self.grid.x_of_node[self.grid.core_nodes]
            yn = self.grid.y_of_node[self.grid.core_nodes]
            xu = self._ivx[self._node_idx]*100*10
            yu = self._ivy[self._node_idx]*100*10

            idx = (np.mod(xn,quiver_interval)==0) & (np.mod(yn,quiver_interval)==0)

            horz_v = np.sqrt(xu[idx]**2 + yu[idx]**2)
            key_v = np.percentile(horz_v,90)

            f1 = plt.figure(figsize=figsize,layout='tight')
            ax1 = f1.add_subplot(111)

            _grid.imshow('ivz',colorbar_label='(mm/yr)',shrink=shrink,
                         cmap=cmap,grid_units=('m','m'))
            q = ax1.quiver(xn[idx],yn[idx],xu[idx],yu[idx],color='k')
            qk = ax1.quiverkey(q,0.05,1.05,key_v,f'{key_v:.2e} '+r'$\frac{mm}{yr}$',
                                labelpos='E',coordinates='axes')

        else: 
            raise ValueError("Argument for 'fig_type' must be either 'individual' or 'combined'.")

        if return_handles:
            return f1

    def run_one_step(self,dt):
        """
        Perform interseismic advection and uplift
        
        If topographic correction is turned on, recalculate interseismic velocity

        Parameters
        ----------
        dt : int
            Timestep.

        """

        # based on updated topography
        if self._topographic_correction:
            self._calc_interseismic_vel()
            self._update_advection_and_uplift()
        
        # Advect
        self._adv.run_one_step(dt)
        
        # Uplift 
        if 'bedrock__elevation' in self.grid.at_node.keys():
            # Add background elevation if it exists
            self._br_elev[self.grid.core_nodes] += self._bu*dt
            # Then deal with insterseismic uplift
            self._br_elev[self.grid.core_nodes] += self._u[self.grid.core_nodes]*dt
            self._elev[self.grid.core_nodes] = self._br_elev[self.grid.core_nodes] + self._sd[self.grid.core_nodes]
        else:
            # Add background elevation if it exists
            self._elev[self.grid.core_nodes] += self._bu*dt
            # Then deal with insterseismic uplift
            self._elev[self.grid.core_nodes] += self._u[self.grid.core_nodes]*dt
        
        # Update total displacements
        [x_comp,y_comp] = self.grid.map_link_vector_components_to_node('advection__velocity')
        self._tx_disp[self.grid.core_nodes] += x_comp[self.grid.core_nodes]*dt
        self._ty_disp[self.grid.core_nodes] += y_comp[self.grid.core_nodes]*dt
        self._tz_disp[self.grid.core_nodes] += self._bu*dt
        self._tz_disp[self.grid.core_nodes] += self._u[self.grid.core_nodes]*dt
     
