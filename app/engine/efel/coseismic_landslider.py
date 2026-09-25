#!/usr/bin/env python3
"""
Identify locations of coseismic landslides and fail
and route materieal

@author: amforte
"""

import numpy as np
import pandas as pd
from scipy.stats import linregress
from scipy.spatial.distance import cdist
import matplotlib.pyplot as plt
from matplotlib import path
from scipy import ndimage

from landlab import RasterModelGrid, HexModelGrid
from landlab.components import BedrockLandslider
from .fault_generator import DippingFault, VerticalFault
from .eq_generator import EarthquakeSequence

def _rot_coord(x,y,xo,yo,angle):
    '''
    Rotate coordinates about a point by an angle

    Parameters
    ----------
    x : array
        x-coordinates.
    y : array
        y-coordinates.
    xo : float
        x-coordinate of origin about which to rotate coordinates.
    yo : float
        y-coordinate of origin about which to rotate coordinates.
    angle : float
        angle (in degrees) to rotate coordinates by.

    Returns
    -------
    xp : array
        rotated x-coordinates.
    yp : array
        rotated y-coordinates.

    '''
    x = x-xo
    y = y-yo
    
    xp = x*np.cos(np.radians(angle)) + y*np.sin(np.radians(angle))
    yp = -x*np.sin(np.radians(angle)) + y*np.cos(np.radians(angle))
    
    return xp,yp

def _ip07_classifier(grid,median_window=3, focal_radius=10):
    """
    Implentation of the Iwahashi & Pike, 2007 terrain classifier,
    adapted from https://github.com/seniarwan/topographic-classification

    Parameters
    ----------
    grid : RasterModelGrid
        Raster model grid.
    median_window : int, optional
        Size of window for the median filter. The default is 3.
    focal_radius : int, optional
        Radius of window for focal statistics. The default is 10.

    Returns
    -------
    trcl : array of ints
        m x n array of classified values from 1 to 16.

    """
    
    
    def _raster_inflate(rstr,bc,width=10):
        # Variable inflation based on status of boundary nodes
        # Edge for open boundaries, symmetric for closed
        #
        # Move in one row-column on all sides 
        rstr0 = rstr[1:-1,1:-1]
        
        # Process each edge separately
        # Left fist
        if np.median(bc[:,0])==4:
            rstr0l = np.pad(rstr0,width+1,'symmetric')
        else:
            rstr0l = np.pad(rstr0,width+1,'constant',constant_values=0)
        # Top
        if np.median(bc[0,:])==4:
            rstr0t = np.pad(rstr0,width+1,'symmetric')
        else:
            rstr0t = np.pad(rstr0,width+1,'constant',constant_values=0)    
        # Right
        if np.median(bc[:,-1])==4:
            rstr0r = np.pad(rstr0,width+1,'symmetric')
        else:
            rstr0r = np.pad(rstr0,width+1,'constant',constant_values=0)
        # Bottom
        if np.median(bc[-1,:])==4:
            rstr0b = np.pad(rstr0,width+1,'symmetric')
        else:
            rstr0b = np.pad(rstr0,width+1,'constant',constant_values=0)
        
        # Assemble
        rstr_out = np.zeros(rstr0l.shape)
        # Fill in center
        rstr_out[width+1:-(width+1),width+1:-(width+1)] = rstr0
        # Fill in closed edges first
        if np.median(bc[:,0])==4:
            rstr_out[:,0:width+1]=rstr0l[:,0:width+1]
        if np.median(bc[0,:])==4:
            rstr_out[0:width+1,:]=rstr0t[0:width+1,:]
        if np.median(bc[:,-1])==4:
            rstr_out[:,-1*(width+1):]=rstr0r[:,-1*(width+1):]
        if np.median(bc[-1,:])==4:
            rstr_out[-1*(width+1):,:]=rstr0b[-1*(width+1):,:]
        
        # Fill in open edges last
        if np.median(bc[:,0])==1:
            rstr_out[:,0:width+1]=rstr0l[:,0:width+1]
        if np.median(bc[0,:])==1:
            rstr_out[0:width+1,:]=rstr0t[0:width+1,:]
        if np.median(bc[:,-1])==1:
            rstr_out[:,-1*(width+1):]=rstr0r[:,-1*(width+1):]
        if np.median(bc[-1,:])==1:
            rstr_out[-1*(width+1):,:]=rstr0b[-1*(width+1):,:]
        
        return rstr_out

    def _raster_deinflate(rstr_pad,width=10):
        rstr = rstr_pad[width:,width:]
        rstr = rstr[:-width,:-width]
        return rstr
    
    def _horn_slope(dem,cell_size):
        # Horn's method - same as ArcGIS Slope tool
        kernel_x = np.array([[-1, 0, 1],
                            [-2, 0, 2], 
                            [-1, 0, 1]]) / (8.0 * cell_size)
        
        kernel_y = np.array([[-1, -2, -1],
                            [0, 0, 0],
                            [1, 2, 1]]) / (8.0 * cell_size)
        
        dx = ndimage.convolve(dem, kernel_x, mode='constant', cval=np.nan)
        dy = ndimage.convolve(dem, kernel_y, mode='constant', cval=np.nan)
        
        slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
        slope_deg = np.degrees(slope_rad)
        
        return slope_deg
    
    def _focal_convexity(dem,focal_radius):
        laplacian_kernel = np.array([[-1, -1, -1],
                                       [-1,  8, -1],
                                       [-1, -1, -1]], dtype=np.float32)
    
        # Step 1: Apply Laplacian filter (FocalStatistics with Weight)
        laplacian = ndimage.convolve(dem, laplacian_kernel, mode='constant', cval=0.0)
        
        # Handle nodata properly
        dem_nan_mask = np.isnan(dem)
        laplacian[dem_nan_mask] = np.nan
        
        # Step 2: Con operation (VALUE > 0 -> 1, else 0)
        binary = np.zeros_like(laplacian)
        valid_mask = ~np.isnan(laplacian)
        binary[valid_mask & (laplacian > 0)] = 1.0
        binary[~valid_mask] = np.nan
        
        # Step 3: FocalStatistics Circle MEAN
        convexity = _focal_statistics_circular(binary, radius=focal_radius)
        
        return convexity    
     
    def _focal_texture(dem, median_window, focal_radius):
    
        # Step 1: Median filter (Rectangle 3 3 CELL)
        median_dem = ndimage.median_filter(dem, size=median_window)
        
        # Handle NaN
        dem_nan_mask = np.isnan(dem)
        median_dem[dem_nan_mask] = np.nan
        
        # Step 2: Minus operations (like ArcPy workflow)
        diff_pos = np.maximum(0, dem - median_dem)      # TC_dm_md_c
        diff_neg = np.maximum(0, median_dem - dem)      # TC_md_dm_c
        
        # Step 3: Plus operation
        texture_raw = diff_pos + diff_neg               # TC_plus
        
        # Step 4: Float operation
        texture_float = texture_raw.astype(np.float32)  # TC_plus_c_f
        
        # Step 5: FocalStatistics Circle MEAN
        texture = _focal_statistics_circular(texture_float, radius=focal_radius)
        
        return texture 
    
    def _focal_statistics_circular(data, radius, statistic='mean'):

       # Create exact circular kernel like ArcPy
       size = 2 * radius + 1
       y, x = np.ogrid[-radius:radius+1, -radius:radius+1]
       circle_mask = x**2 + y**2 <= radius**2
       
       # Initialize result
       result = np.full_like(data, np.nan)
       
       # Apply focal statistics
       for i in range(radius, data.shape[0] - radius):
           for j in range(radius, data.shape[1] - radius):
               if not np.isnan(data[i, j]):
                   # Extract circular neighborhood
                   neighborhood = data[i-radius:i+radius+1, j-radius:j+radius+1]
                   circular_values = neighborhood[circle_mask]
                   
                   # Remove NaN values
                   valid_values = circular_values[~np.isnan(circular_values)]
                   
                   if len(valid_values) > 0:
                       if statistic == 'mean':
                           result[i, j] = np.mean(valid_values)
                       elif statistic == 'sum':
                           result[i, j] = np.sum(valid_values)
                       elif statistic == 'median':
                           result[i, j] = np.median(valid_values)
                       elif statistic == 'std':
                           result[i, j] = np.std(valid_values)
       
       return result
    
    
    # Convert elevation from RasterModelGrid to simple mxn numpy array
    dem = grid.at_node['topographic__elevation']
    dem = dem.reshape(grid.shape)
    # Find the dx
    dx = grid.dx
    # Get boundary node status
    bc = grid.status_at_node.reshape(grid.shape)
    
    # Pad edges to avoid swath of nans because of the focal statistics
    dem_pad = _raster_inflate(dem,bc)
    
    # Calculate slope, convexity, and texture
    slp = _horn_slope(dem_pad,dx)
    con = _focal_convexity(dem_pad,focal_radius)
    tex = _focal_texture(dem_pad,median_window,focal_radius)
    
    slpv = slp.ravel()
    conv = con.ravel()
    texv = tex.ravel()
    
    # Calculate stats needed for indices
    ## First Threshold
    slp_mean = np.nanmean(slpv)
    con_mean = np.nanmean(conv)
    tex_mean = np.nanmean(texv)
    ## Second Threshold
    slp_mean_gentle_half = np.nanmean(slpv[slpv < np.nanpercentile(slpv,50)])
    con_mean_gentle_half = np.nanmean(conv[conv < np.nanpercentile(conv,50)])
    tex_mean_gentle_half = np.nanmean(texv[slpv < np.nanpercentile(texv,50)])
    ## Third Threshold
    slp_mean_gentle_quarter = np.nanmean(slpv[slpv < np.nanpercentile(slpv,25)])
    con_mean_gentle_quarter = np.nanmean(conv[conv < np.nanpercentile(conv,25)])
    tex_mean_gentle_quarter = np.nanmean(texv[slpv < np.nanpercentile(texv,25)])

    
    #Generate empty terrain classification raster
    trcl = np.zeros(dem_pad.shape,dtype=int)
    
    idx1 = (slp > slp_mean) & (con > con_mean) & (tex < tex_mean)
    trcl[idx1] = 1
    idx2 = (slp > slp_mean) & (con > con_mean) & (tex >= tex_mean)
    trcl[idx2] = 2
    idx3 = (slp > slp_mean) & (con <= con_mean) & (tex < tex_mean)
    trcl[idx3] = 3
    idx4 = (slp > slp_mean) & (con <= con_mean) & (tex >= tex_mean)
    trcl[idx4] = 4
    
    idx5 = (slp <= slp_mean) & (slp > slp_mean_gentle_half) & (con > con_mean_gentle_half) & (tex < tex_mean_gentle_half)
    trcl[idx5] = 5
    idx6 = (slp <= slp_mean) & (slp > slp_mean_gentle_half) & (con > con_mean_gentle_half) & (tex >= tex_mean_gentle_half)
    trcl[idx6] = 6
    idx7 = (slp <= slp_mean) & (slp > slp_mean_gentle_half) & (con <= con_mean_gentle_half) & (tex < tex_mean_gentle_half)
    trcl[idx7] = 7
    idx8 = (slp <= slp_mean) & (slp > slp_mean_gentle_half) & (con <= con_mean_gentle_half) & (tex >= tex_mean_gentle_half)
    trcl[idx8] = 8
    
    idx9 = (slp <= slp_mean) & (slp <= slp_mean_gentle_half) & (slp > slp_mean_gentle_quarter) & (con > con_mean_gentle_quarter) & (tex < tex_mean_gentle_quarter)
    trcl[idx9] = 9
    idx10 = (slp <= slp_mean) & (slp <= slp_mean_gentle_half) & (slp > slp_mean_gentle_quarter) & (con > con_mean_gentle_quarter) & (tex >= tex_mean_gentle_quarter)
    trcl[idx10] = 10
    idx11 = (slp <= slp_mean) & (slp <= slp_mean_gentle_half) & (slp > slp_mean_gentle_quarter) & (con <= con_mean_gentle_quarter) & (tex < tex_mean_gentle_quarter)
    trcl[idx11] = 11
    idx12 = (slp <= slp_mean) & (slp <= slp_mean_gentle_half) & (slp > slp_mean_gentle_quarter) & (con <= con_mean_gentle_quarter) & (tex >= tex_mean_gentle_quarter)
    trcl[idx12] = 12
    
    idx13 = (slp <= slp_mean) & (slp <= slp_mean_gentle_half) & (slp <= slp_mean_gentle_quarter) & (con > con_mean_gentle_quarter) & (tex < tex_mean_gentle_quarter)
    trcl[idx13] = 13
    idx14 = (slp <= slp_mean) & (slp <= slp_mean_gentle_half) & (slp <= slp_mean_gentle_quarter) & (con > con_mean_gentle_quarter) & (tex >= tex_mean_gentle_quarter)
    trcl[idx14] = 14    
    idx15 = (slp <= slp_mean) & (slp <= slp_mean_gentle_half) & (slp <= slp_mean_gentle_quarter) & (con <= con_mean_gentle_quarter) & (tex < tex_mean_gentle_quarter)
    trcl[idx15] = 15
    idx16 = (slp <= slp_mean) & (slp <= slp_mean_gentle_half) & (slp <= slp_mean_gentle_quarter) & (con <= con_mean_gentle_quarter) & (tex >= tex_mean_gentle_quarter)
    trcl[idx16] = 16    
    
    trcl = _raster_deinflate(trcl)
    
    return trcl    



class CoseismicLandslider:
    """ Calculate coseismic landslides
    
    Landlab component that uses provided earthquake catalog to calculate peak ground
    accelerations and determine areas expected to fail as a result of individual
    earthquakes. The component then uses BedrockLandslider to calculate runout
    of failed nodes.
    
    Examples
    --------


    References
    ----------

    **Required Software Citation(s) Specific to this Component**
    
    Campforts B., Shobe C.M., Steer P., Vanmaercke M., Lague D., Braun J.
    (2020) HyLands 1.0: a hybrid landscape evolution model to simulate the
    impact of landslides and landslide-derived sediment on landscape evolution.
    Geosci Model Dev: 13(9):3863–86. https://dx.doi.org/10.5194/esurf-6-1-2018
    
    **Additional References**
    
    Jibson, R.W. (2007) Regression models for estimating coseismic landslide 
    displacement. Engineering Geology: 91(2-4): 209-218. 
    https://doi.org/10.1016/j.enggeo.2007.01.013
    
    Iwahashi, J., Pike, R.J. (2007) Automated classifications of topography 
    from DEMs by an unsupervised nested-means algorithm and a three-part 
    geometric signature. Geomorphology: 86(3-4): 409-444. 
    https://doi.org/10.1016/j.geomorph.2006.09.012
    
    Yong, A., Hough, S.E., Iwahashi, J., Braverman, A. (2012) A Terrain-Based 
    Site-Conditions Map of California with Implications for the Contiguous 
    United States. Bulletin of the Seismological Society of America: 102(1):
    114-128. https://doi.org/10.1785/0120100262
    
    Yong, A. (2016) Comparison of Measured and Proxy-Based V_S30 Values in
    California. Earthquake Spectra: 32(1): 171-192. 
    https://doi.org/10.1193/013114EQS025M
    
    Allen, T.I., Wald, D.J. (2009) On the Use of High-Resolution Topographic
    Data as a Proxy for Seismic Site Conditions (VS30). Bulletin of the 
    Seismological Society of America: 99(2A): 935-943. 
    https://doi.org/10.1785/0120080255
    
    Chiou, B.S.-J., Youngs, R.R. (2008) An NGA Model for the Average 
    Horizontal Component of Peak Ground Motion and Response Spectra. 
    Earthquake Spectra: 24(1): 173-215. https://doi.org/10.1193/1.2894832
    
    Abrahamson, N., Gregor, N., Addo, K. (2016) BC Hydro Ground Motion 
    Prediction Equations for Subduction Earthquakes. Earthquake Spectra:
    32(1): 23-44. https://doi.org/10.1193/051712EQS188MR
    
    Pezeshk, S., Zandieh, A., Tavakoli, B. (2011) Hybrid Empirical Ground-
    Motion Prediction Equations for Eastern North America Using NGA Models
    and Updated Seismological Parameters. Bulletin of the Seismological Society
    of America: 101(4): 1859-1870. https://doi.org/10.1785/0120100144
    
    Montgomery, D.R., Dietrich, W.E. (1994) A physically based model for the 
    topographic control on shallow landsliding. Water Resources Research:
    30(4): 1153-1171. https://doi.org/10.1029/93WR02979
    
    
    """
    _name = 'CoseismicLandslider'
    
    _time_units = 'y'
    
    _unit_agnostic = False
    
    _info = {
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
        # From BedrockLandslider
        "flow__receiver_node": {
            "dtype": int,
            "intent": "in",
            "optional": False,
            "units": "-",
            "mapping": "node",
            "doc": "Node array of receivers (node that receives flow from current node)",
            },
        # From BedrockLandslider
        "flow__upstream_node_order": {
            "dtype": int,
            "intent": "in",
            "optional": False,
            "units": "-",
            "mapping": "node",
            "doc": "Node array containing downstream-to-upstream ordered list of node IDs",
            },
        # From BedrockLandslider
        "hill_flow__receiver_node": {
            "dtype": int,
            "intent": "in",
            "optional": False,
            "units": "-",
            "mapping": "node",
            "doc": "Node array of receivers (node that receives flow from current node)",
            },
        # From BedrockLandslider
        "hill_flow__receiver_proportions": {
            "dtype": float,
            "intent": "in",
            "optional": False,
            "units": "-",
            "mapping": "node",
            "doc": "Node array of proportion of flow sent to each receiver.",
            },
        # From BedrockLandslider
        "hill_topographic__steepest_slope": {
            "dtype": float,
            "intent": "in",
            "optional": False,
            "units": "-",
            "mapping": "node",
            "doc": "The steepest *downhill* slope",
            },
        # From BedrockLandslider
        "LS_sediment__flux": {
            "dtype": float,
            "intent": "out",
            "optional": False,
            "units": "m3/s",
            "mapping": "node",
            "doc": "Sediment flux originating from landslides \
                (volume per unit time of sediment entering each node)",
            },
        # From BedrockLandslider
        "landslide__erosion": {
            "dtype": float,
            "intent": "out",
            "optional": False,
            "units": "m",
            "mapping": "node",
            "doc": "Total erosion caused by landsliding ",
            },
        # From BedrockLandslider
        "landslide__deposition": {
            "dtype": float,
            "intent": "out",
            "optional": False,
            "units": "m",
            "mapping": "node",
            "doc": "Total deposition of derived sediment",
            },
        # From BedrockLandslider
        "landslide_sediment_point_source": {
            "dtype": float,
            "intent": "out",
            "optional": False,
            "units": "m3",
            "mapping": "node",
            "doc": "Landslide derived sediment, as point sources on all the \
                critical nodes where landslides initiate, \
                before landslide runout is calculated ",
            },
        "soil__thickness": {
            "dtype": float,
            "inent": "inout",
            "optional": False,
            'units': "m",
            "mapping": "node",
            "doc": "Thickness of soil or weathered bedrock \
                perpendicular to slope"
            },
        "vs__30": {
            "dtype": float,
            "intent": "out",
            "optional": False,
            "units": "m/s",
            "mapping": "node",
            "doc": "Average shear wave velocity in the top 30 meters",
            
            },
        "peak_ground__acceleration": {
            "dtype": float,
            "intent": "out",
            "optional": False,
            "units": "g",
            "mapping": "node",
            "doc": "Peak ground acceleration"
            },
        "factor_of__safety": {
            "dtype": float,
            "intent": "out",
            "optional": False,
            "units": "-",
            "mapping": "node",
            "doc": "Factor of safety"
            },
        "critical__acceleration": {
            "dtype": float,
            "intent": "out",
            "optional": False,
            "units": "g",
            "mapping": "node",
            "doc": "Critical acceleration to initiate sliding"
            },
        "newmark__displacement": {
            "dtype": float,
            "intent": "out",
            "optional": False,
            "units": "cm",
            "mapping": "node",
            "doc": "Newmark displacements to estimate nodes \
                capable of sliding in coseismic events"
            },
        "acceleration_ratio": {
            "dtype":float,
            "intent": "out",
            "optional": False,
            "units": "-",
            "mapping": "node",
            "doc": "Ratio of critical acceleration to peak ground\
                acceleration"
            },
        }
    
    
    
    def __init__(self,grid,eq,gmpe_model='cy08',vs30_method='aw09',
                 vs30_setting='active_tectonic',F_event=0,F_FABA=0,g=9.81,
                 store_spectral_accelerations=False,
                 cohesion=1e4,angle_int_frict=45.,
                 rho_r=2700.,rho_w=1000.,w=0,hydraulic_conductivity=500,transmissivity=None,
                 route_excess_discharge=False,
                 min_newmark_disp=5,
                 use_magnitude=False,porosity=0,allow_non_seismogenic_LS=False,
                 fraction_fines_LS=0,landslides_return_time=1e5,Mw_min=None,
                 store_LS_dict=False,include_landslide_locations=False,
                 perform_landslides=True,store_event_details=False,
                 random=False,seed=None):
        """
        

        Parameters
        ----------
        grid : RasterModelGrid
            A landlab grid, can be either a hex or raster model grid.
        eq : EarthquakeSequence
            Earthquake sequence object created by the EarthquakeSequence component.
        gmpe_model : str, optional
            Choice of ground motion prediction equations to use to generate peak ground
            and spectral accelerations. There are three possible choices:
                'cy08' - Model of Chiou & Youngs, 2008. This is a generic model considered
                    appropriate for general active tectonic environments that are not subduction
                    zones. This model makes use of estimates of V_S30 so choices for these
                    parameters will impact estimates of peak ground and spectral accelerations.
                'aea16' - Model of Abrahamson et al., 2016. This is a model specficially for
                    subduction zones. This model makes uses of estimates of V_S30 so choices for
                    these parameters will impact estimates of peak ground and spectral accelerations.
                'pea11' - Model of Pezeshk et al., 2011. This is a appropriate for stable continental
                    interiors. It does not use estimates of V_S30.
            The default is 'cy08'.
        vs30_method : str, optional
            Choice of method for estimating V_S30 in m/s, i.e., the average shear wave velocity in
            the top 30 meters. This parameter is used for both the 'cy08' and 'aea16' ground motion prediction
            equations. There are four possible choices:
                'aw09' - Topographic slope based method from Allen & Wald, 2009. Can be used for either raster
                    or hex grids.
                'y12' - Topographic classification method of Yong et al., 2012 that relies on topographic
                    classifications of Iwahashi & Pike, 2007. This can only be used with raster grids.
                'y14' - Topographic classification method of Yong, 2014, which is an update of the 
                    Yong et al., 2012 method. This can only be used with raster grids.
                None - If None is provided, then V_S30 will not be calculated, but upon instantiation a 
                    field within the grid named 'vs__30' will be created and filled with zeros. This option 
                    should be used if you wish to provide V_S30 values in some other manner, e.g., you want to 
                    just assert a constant value or calculate V_S30 by some other method. If you choose None, 
                    it is strongly suggested that you populate the 'vs__30' grid field before you invoke
                    "run_one_step" of the CoseismicLandlider instance in question, as otherwise this would have the 
                    effect of calculating peak ground acceleration with a V_S30 of 0 everywhere, which will produce
                    unrelasitic results.
                Note that either the 'y12' and 'y14' are more computationally intensive and so will slow 
                run time if chosen. The default is 'aw09'.
        vs30_setting : str, optional
            Choice of relationship to use for slope based 'aw09' method for esimating V_S30. Valid choices are
            'active_tectonic' or 'stable_continent'. The default is 'active_tectonic'.
        F_event : boolean or str, optional
            If the GMPE model is 'aea16', flag for indicating whether earthquake events should be treated as 
            "interface events", i.e., earthquakes occuring on the subduction thrust (F_event = 0 or F_event=False),
            or whether earthquakes should be treated as "intraslab events", i.e., earthquakes occuring within the slab
            (F_event = 1 or F_event = True). Alternatively, "random" can be provided and the code will randomly assign
            events to being either interface of intraslab, i.e., different events in the provided catalog will be 
            treated differently. The default is 0.
        F_FABA : boolean or float, optional
            If the GMPE model is 'aea16', flag for indicating whether locations within the provided grid should be
            treated as being in the forearc (F_FABA = 0 or F_FABA = False) or being in the backarc
            (F_FABA = 1 or F_FABA =True). Alternatively, you can provide a float that will be interpreted as
            the distance (in meters) in the direction of dip from the tip of the fault as the transition from the
            forearc to the backarc. For example, if 5000 was provided to F_FABA, then this would treat any sites
            within 5 km of the fault tip (and any portions of the grid that are not "above" the fault) as being
            within the forearc and any sites greater than 5 km in the dip direction from the tip of the fault as
            being in the backarc. The default is 0.
        g : float, optional
            Gravitational acceleration in m/s^2. The default is 9.81.
        store_spectral_accelerations : boolean, optional
            Flag to either store spectral accelerations (True) or not (False) as fields within the grid. If set to
            True, then there will be fields within the grid with names of the form "##.#_spectral__acceleration" where
            ##.# will be a period, in seconds, for which the chosen GMPE model calculates spetral accelerations, e.g.
            "0.01_spectral__acceleration" or "10.0_spectral__acceleration". The default is False.
        cohesion : float, optional
            Total effective cohesion in Pa. The default is 1e4.
        angle_int_frict : float, optional
            Angle of internal friction in degrees. The default is 45..
        rho_r : float, optional
            Density of soil in kg/m^3. The default is 2700..
        rho_w : float, optional
            Density of water in kg/m^3. The default is 1000..
        w : float or str, optional
            Relative wetness ratio, must be a value between 0 and 1 if you wish to assert a constant value for the 
            whole landscape. If you provide None to this parameter, this will calculate relative wetness using the 
            simplified assumptions from Montgomery & Dietrich, 1994. If w is set to None, it is expected that 
            grid fields for "topographic__steepest_slope", "water__unit_flux_in", "surface_water__discharge",
            and "drainage_area" will exist, which should generally be created when a flow accumulation instance is
            instantiated. Alternatively, if you wish to calculate relative wetness in some other fashion, you can provide
            "external" as the value and where the component will expect there to be a field "relative__wetness" within the 
            Landlab grid that it will interpret in the context of relative wetness but will not modify this field with the
            expectation that the user is updating this field as desired. If "external" is provided but a "relative__wetness" field
            does not already exist within the grid, the component will create it and populate it with zeros. The default is 0.
        hydraulic_conductivity : float, optional
            Value for saturated hydraulic conductivity in m/y (assuming timestep is in years). Will only be used if
            w=None indicating that relative wetness should be calculated within the model as as function of time.
            A value other than None can only be provided to either this or transmissivity, i.e., one must be None
            and the other must have a float value. If providing a value to hydraulic_conductivity, then transmissivity
            will vary as a function of soil thickness within the grid.
            The default is 500.
        transmissivity : float, optional
            Value for transmissivity in m^2/y (assuming timestep is in years). Will only be used if w=None indicating
            that relative wetness should be calculated within the model as a function of time. A value other than
            None can only be provided to either this or hydraulic_conductivity, i.e., one must be None and the other
            have a float value. If providing a value to transmissivity, this effectively assumes constant soil thickness
            and the model soil depth will not be considered in the transmissivity value. The default is None.
        route_excess_discharge : boolean, optional
            Flag to either track and route excess discharge or not. This parameter is only considered
            if w=None and relative wetness is calculated. If set to True, the surface_water__discharge will 
            be updated at each node to reflect only the water that does not infiltrate. The default is False.
        min_newmark_disp : float, optional
            The minimum value of a Newmark displacement (in cm) to consider as a node that could potentially fail
            as a coseismic landslide. The default is 5.
        use_magnitude : boolean, optional
            Flag to either use the version of the Newmark displacement calculation from Jibson, 2007 that considers
            event magnitude (True) or that does not consider event magnitude (False). The default is False.
        porosity : float, optional
            Soil porosity, used by the BedrockLandslider component. The default is 0.
        allow_non_seismogenic_LS : boolean, optional
            Flag to run a standard timestep of the BedrockLandlsider component after all coseismic landslides
            have been considered within a timestep (True) or to only consider coseimsmic landslides.
            The default is False.
        fraction_fines_LS : float, optional
            Fraction of permanently suspendable fines in bedrock, used by BedrockLandslider. The default is 0.
        landslides_return_time : float, optional
            Return time for stochastic landslides, only considered if allow_non_seismogenic_LS is set to True.
            The default is 1e5.
        Mw_min : float, optional
            Minimum magnitude of earthquake to consider capable of creating a coseismic landslide. If left at
            the default value, all earthquakes within the catalog provided are considered capable of producing
            coseismic landslides. The default is None.
        store_LS_dict : boolean, optional
            Flag to initiate the storage of landslide information in a dictionary (True) or not (False). If 
            set to True, then a dictionary tracking the event id, magnitude, critical sliding nodes, area of landslides,
            volumes of landslides, and volumes of sediment within each landslide will be stored within the instance.
            The default is False.
        include_landslide_locations : boolean, optional
            Flag to include lists of nodes of both the landslide source areas and the landslide runout areas along with
            separate lists of the magnitudes of erosion and deposition (m) at each of node within the stored landslide 
            dictionary. This is optional because these node lists can become long, so this is mainly
            a memory management option if the landslide dictionary is becoming too large and/or if you're not interested
            in having a record of the landslide spatial characteristics. This parameter is ignored if 'store_LS_dict' is False.
            The default is False.
        perform_landslides: boolean, optional
            Flag to indicate whether you want to identify and route landslides using the BedrockLandslider. Setting this
            to False will still calculate the peak ground accelerations (and spectral accelerations), factor of safety,
            critical acceleration, and Newmark displacements (and store these as fields within the grid), but will not 
            use these to identify critical nodes and then generate and route landslides. This option is included primarily 
            if the user wishes to generate landslides based on Newmark displacements through an alternative routine or is
            only interested in one of the input datasets (e.g., spectral accelerations) and not actually modifying the 
            topography with landslides. The default is True.
        store_event_details: boolean, optional
            Flag to indicate whether you want to store a dictionary within the CoseismicLandslider instance named 'EventDetails'
            that will store the values of all nodes in the Landlab grid for the various intermediate steps up to identifying
            the location of critical slip nodes (e.g., peak ground acceleration, etc.) for each earthquake within that timestep.
            This dictionary is reset at the beginning of each call of 'run_one_step', so if you wish to use or store the outputs
            as stored in this dictionary, this must be done within the model loop. The default is False.
        random : boolean, optional
            All of the GMPEs calculate a median peak ground acceleration and a variance on that peak ground acceleration
            where the variance reflects a variety of uncertainties. If set to true, instead of the peak ground acceleration
            at every node being the median calculated value, it will be a stochastically drawn value from a 
            normal distribution based on the median and variance. The default is False.
        seed : int, optional
            Seed value for the random number generator if random is set to True. The default is None.


        Returns
        -------
        None.

        """

        
        self.grid = grid
        self.eq = eq
        self.fault = eq.fault
        self.gmpe_model = gmpe_model
        self.vs30_method = vs30_method
        self.vs30_setting = vs30_setting
        self.F_event = F_event
        self.F_FABA = F_FABA
        self.store_spectral_accelerations = store_spectral_accelerations
        self.C = cohesion
        self.phi = angle_int_frict
        self.rho_r = rho_r
        self.rho_w = rho_w
        self.w = w # Saturated thickness ratio
        self.Ks = hydraulic_conductivity
        self.T = transmissivity
        self.route_Q = route_excess_discharge
        self.g = g
        self.min_newmark_disp = min_newmark_disp
        self.use_magnitude = use_magnitude
        self.porosity = porosity
        self.allow_non_seismogenic_LS = allow_non_seismogenic_LS
        self.fraction_fines_LS = fraction_fines_LS
        self.landslides_return_time = landslides_return_time
        self.Mw_min = Mw_min
        self.store_LS_dict = store_LS_dict
        self.include_landslide_locations = include_landslide_locations
        self.perform_landslides = perform_landslides
        self.store_event_details = store_event_details
        self.random = random
        self.seed = seed
        
        
        if self._gmpe_model == 'cy08':
            self._cy08_constants()
            
            # Determine reverse and normal flags via signs and magnitude of
            # dip-slip and strike_slip rate components
            if np.abs(self.fault._ss) > np.abs(self.fault._ds):
                self.F_RV = 0
                self.F_NM = 0
            elif np.sign(self.fault._ds)==1:
                self.F_RV = 1
                self.F_NM = 0
            elif np.sign(self.fault._ds)==-1:
                self.F_RV = 0
                self.F_NM = 1
                
        elif self._gmpe_model == 'aea16':
            self._aea16_constants()
            # Deal with choices for F_event and F_FABA
            if self.F_event=='random':
                num_events = len(self.eq.Events['Event_ID'])
                rng = np.random.default_rng(seed=self.seed)
                self.F_event = np.round(rng.uniform(size=num_events)).astype(bool)
            
            if self.F_FABA > 1:
                self._calc_forearc_to_backarc()
                self.F_FABA = self.fb_distance > self.F_FABA

        elif self._gmpe_model == 'pea11':
            self._pea11_constants()
            
        # Instantiate an internal instance of the BedrockLandslider
        self.hy = BedrockLandslider(self.grid,angle_int_frict=np.tan(np.radians(self.phi)),
                                    cohesion_eff=self.C,
                                    landslides_return_time=self.landslides_return_time,
                                    rho_r=self.rho_r,fraction_fines_LS=self.fraction_fines_LS,
                                    phi=self.porosity,landslides_on_boundary_nodes=False)
            
        # Check whether a soil thickness field already exists
        if "soil__thickness" not in self.grid.at_node:
            self.convert_depth_to_thickness = True
            # Calculate initial soil thickness
            grad = self.grid.calc_slope_at_node()
            alpha = np.atan(grad) 
            self.grid.at_node['soil__thickness'] = np.cos(alpha)*self.grid.at_node['soil__depth']
            self._hs = self.grid.at_node['soil__thickness']
        else:
            self.convert_depth_to_thickness = False
            self._hs = self.grid.at_node['soil__thickness']
        
        
        # Preform various checks and assignments if relative wetness is going to be calculated
        if self.w == None:
            self.calc_relative_wetness=True
            # Check for single numeric value to either hydraulic conductivity or transmissivity
            if (self.Ks!=None) & (self.T!=None):
                raise ValueError('Values other than None cannot be provided to both "hydraulic_conductivity" and "transmissivity", please only provide a value to one.')
            elif (self.Ks==None) & (self.T==None):
                raise ValueError('If relative wetness "w" is set to None, then you must provide a numeric value to either "hydraulic_conductivity" or "transmissivity".')
            elif (self.Ks==None) & (self.T!=None):
                # Assert constant transmissivity
                self.constant_trans = True
                self._trans = self.grid.add_full('transmissivity',self.T,at='node',clobber=True)
            elif (self.Ks!=None) & (self.T==None):
                # Calculate transmissivity at each timestep
                self.constant_trans = False
                self.grid.at_node['transmissivity'] = self.Ks*self._hs
                self._trans = self.grid.at_node['transmissivity']
            
            # Check for existing fields that are needed
            if "topographic__steepest_slope" not in self.grid.at_node:
                raise ValueError('If relative wetness "w" is set to None, please run a flow accumulator before instantiating an instance of the CoseismicLandslider to generate a field for "topographic__steepest_slope".')
            else:
                self._st_slope = self.grid.at_node['topographic__steepest_slope']
            
            if "water__unit_flux_in" not in self.grid.at_node:
                raise ValueError('If relative wetness "w" is set to None, please run a flow accumulator before instantiating an instance of the CoseismicLandslider to generate a field for "water__unit_flux_in" or generate this field.')
            else:
                self._r = self.grid.at_node['water__unit_flux_in']
            
            if "surface_water__discharge" not in self.grid.at_node:
                raise ValueError('If relative wetness "w" is set to None, please run a flow accumulator before instantiating an instance of the CoseismicLandslider to generate a field for "surface_water__discharge".')
            else:
                self._q = self.grid.at_node['surface_water__discharge']
            
            if "drainage_area" not in self.grid.at_node:
                raise ValueError('If relative wetness "w" is set to None, please run a flow accumulator before instantiating an instance of the CoseismicLandslider to generate a field for "drainage_area".')
            else:
                self._area = self.grid.at_node['drainage_area']
            
            self._rw = grid.add_zeros('relative__wetness',at='node')
                
        elif (self.w<0) | (self.w>1):
            raise ValueError('Value provided to relative wetness "w" must be between 0 and 1.')
        elif self.w == 'external':
            if "relative__wetness" not in self.grid.at_node:
                self._rw = grid.add_zeros('relative__wetness',at='node')
        else:
            self.calc_relative_wetness=False
            self.constant_trans=True
            self._rw = grid.add_full('relative__wetness',self.w,at='node',clobber=True)
            
        
        # Generate an empty dictionary for storage if initiated
        if self.store_LS_dict:
            if self.include_landslide_locations:
                self.Landslides = {'Event_ID':[],
                   'Magnitude':[],
                   'Critical_Nodes':[],
                   'Landslide_Source_Nodes':[],
                   'Landslide_Runout_Nodes':[],
                   'Landslide_Erosion':[],
                   'Landslide_Deposition':[],
                   'Areas':[],
                   'Volumes':[],
                   'Sed_Volumes':[]}
                
            else:
                self.Landslides = {'Event_ID':[],
                                   'Magnitude':[],
                                   'Critical_Nodes':[],
                                   'Areas':[],
                                   'Volumes':[],
                                   'Sed_Volumes':[]}
        
        # If Mw_min is None, set to negative infinity so that all earthquakes will be considered   
        if self.Mw_min==None:
            self.Mw_min = -np.inf
    
    @property
    def gmpe_model(self):
        return self._gmpe_model
    
    @gmpe_model.setter
    def gmpe_model(self,new_gmpe_model):
        if (new_gmpe_model=='cy08') | (new_gmpe_model=='aea16') | (new_gmpe_model=='pea11'):
            self._gmpe_model = new_gmpe_model
        else:
            raise ValueError('Argument provided to gmpe_model must be "cy08", "aea16", or "pea11"')
            
    @property
    def vs30_method(self):
        return self._vs30_method
    
    @vs30_method.setter
    def vs30_method(self,new_vs30_method):
        if (new_vs30_method=='y12') & (type(self.grid)==HexModelGrid):
            new_vs30_method='aw09'
            print('Warning: "y12" method for calculating V_S30 is not possible with a hex grid, setting to "aw09".')
        elif (new_vs30_method=='y14') & (type(self.grid)==HexModelGrid):
            new_vs30_method='aw09'
            print('Warning: "y14" method for calculating V_S30 is not possible with a hex grid, setting to "aw09".')
            
        if (new_vs30_method=='aw09') | (new_vs30_method=='y12') | (new_vs30_method=='y14') | (new_vs30_method==None):
            self._vs30_method = new_vs30_method
        else:
            raise ValueError('Argument provided to vs30_method msut be "aw09", "y12", "y14" or None')

        if (new_vs30_method==None) & ("vs__30" not in self.grid.at_node):
            self.grid.add_zeros('vs__30',at='node')
        elif (new_vs30_method==None):
            # If there is already a 'vs__30' field for some reason and you've set None, enforce that it starts at zero
            self.grid.add_zeros('vs__30',at='node',clobber=True)
        

    def _calc_R_Joyner_Boore_distance(self,event_id):
        '''
        Calculate the Joyner Boore distance for every node in 
        a Landlab grid relative to a rupture. The Joyner Boore 
        distance is the shortest distance between a site and the 
        edge of the rupture patch projected to a horizontal zero
        surface. Sites that lie within the projected rupture patch
        have a Joyner Boore distance of 0.

        Parameters
        ----------
        event_id : int
            ID number of the event within an earthquake catalog to calculate
            distances.

        Returns
        -------
        R_JB : array
            Array of Joyner Boore distances for every node in a Landlab grid,
            distance are in kilometers.

        '''

        if type(self.fault)==DippingFault:       
            # Grab interpolation dx
            dx = self.fault._fault_dx
            
            # Find event of interest and the projected surface boundaries
            eidx = self.eq.SubEvents['Event_ID']==event_id
            bx = self.eq.SubEvents['Bound_X'][eidx]
            by = self.eq.SubEvents['Bound_Y'][eidx]
            
            D = []
            
            for i in range(len(bx)):
                bx_dense = []
                by_dense = []

                if (np.isclose(self.fault._strike,0)) | (np.isclose(self.fault._strike,180)) | (np.isclose(self.fault._strike,360)):
                    for j in range(4):
                        x0 = bx[i][j]
                        x1 = bx[i][j+1]
                        y0 = by[i][j]
                        y1 = by[i][j+1]
                        
                        if (j==0) | (j==2):
                            # Horizontal Edges
                            if x1>x0:
                                x_vec = np.arange(x0,x1+dx,dx)
                            else:
                                x_vec = np.arange(x1,x0+dx,dx)
                            y_vec = np.full(x_vec.shape,y0)
                            
                            bx_dense.append(x_vec)
                            by_dense.append(y_vec)
                        else:
                            # Vertical edges
                            if y1>y0:
                                y_vec = np.arange(y0,y1+dx,dx)
                            else:
                                y_vec = np.arange(y1,y0+dx,dx)
                            x_vec = np.full(y_vec.shape,x0)
                            
                            bx_dense.append(x_vec)
                            by_dense.append(y_vec)
                            
                elif (np.isclose(self.fault._strike,90)) | (np.isclose(self.fault._strike,270)):
                    for j in range(4):
                        x0 = bx[i][j]
                        x1 = bx[i][j+1]
                        y0 = by[i][j]
                        y1 = by[i][j+1]
                        
                        if (j==1) | (j==3):
                            # Horizontal Edges
                            if x1>x0:
                                x_vec = np.arange(x0,x1+dx,dx)
                            else:
                                x_vec = np.arange(x1,x0+dx,dx)
                            y_vec = np.full(x_vec.shape,y0)
                            
                            bx_dense.append(x_vec)
                            by_dense.append(y_vec)
                        else:
                            # Vertical edges
                            if y1>y0:
                                y_vec = np.arange(y0,y1+dx,dx)
                            else:
                                y_vec = np.arange(y1,y0+dx,dx)
                            x_vec = np.full(y_vec.shape,x0)
                            
                            bx_dense.append(x_vec)
                            by_dense.append(y_vec)
                else:
                    dxi = dx * np.sin(np.radians(self.fault._strike))
                    for j in range(4):
                    
                        x0 = bx[i][j]
                        x1 = bx[i][j+1]
                        y0 = by[i][j]
                        y1 = by[i][j+1]
                        
                        m = (y1-y0)/(x1-x0)
                        b = y0 - m*x0
                        
                        if x1>x0:
                            x_vec = np.arange(x0,x1+dxi[0],dxi[0])
                        else:
                            x_vec = np.arange(x1,x0+dxi[0],dxi[0])
                        y_vec = m * x_vec + b
                        
                        bx_dense.append(x_vec)
                        by_dense.append(y_vec)
                    
                bx_dense=np.concat(bx_dense)
                by_dense=np.concat(by_dense)
                b_dense = np.hstack((bx_dense.reshape(len(bx_dense),1),by_dense.reshape(len(by_dense),1)))
                
                D.append(cdist(self.grid.xy_of_node,b_dense,'euclidean'))
                    
                R_JB = np.min(np.hstack(D),1)
                
                # Set distances within the rupture patch projections to 0
                for i in range(len(bx)):
                    p = path.Path([[bx[i][0],by[i][0]],[bx[i][1],by[i][1]],[bx[i][2],by[i][2]],[bx[i][3],by[i][3]],[bx[i][4],by[i][4]]])
                    idx = p.contains_points(self.grid.xy_of_node)
                    R_JB[idx] = 0
                    
                # Convert R_JB to kilometers as all the GMPE models expect distances in km
                R_JB = R_JB/1000
                
        elif type(self.fault)==VerticalFault:
            
            # Extract dx
            dx = self.fault._fault_dx
            
            # Find event of interest and bounds
            eidx = self.eq.SubEvents['Event_ID']==event_id
            bx = self.eq.SubEvents['Bound_X'][eidx]
            by = self.eq.SubEvents['Bound_Y'][eidx]
            
            D = []
            for i in range(len(bx)):
                # Extract points defining top of rupture
                x0 = bx[i][0]; x1 = bx[i][1]
                y0 = by[i][0]; y1 = by[i][1]
                
                if (np.isclose(self.eq.SubEvents['Strike'][i],0)) | (np.isclose(self.eq.SubEvents['Strike'][i],180)) | (np.isclose(self.eq.SubEvents['Strike'][i],360)):
                    if y1>y0:
                        y_vec = np.arange(y0,y1+dx,dx)
                    else:
                        y_vec = np.arange(y1,y0+dx,dx)
                    x_vec = np.full(y_vec.shape,x0)
                    b_dense = np.hstack((x_vec.reshape(len(x_vec),1),y_vec.reshape(len(y_vec),1)))
                    D.append(cdist(self.grid.xy_of_node,b_dense,'euclidean'))
                elif (np.isclose(self.eq.SubEvents['Strike'][i],90)) | (np.isclose(self.eq.SubEvents['Strike'][i],270)):
                    if x1>x0:
                        x_vec = np.arange(x0,x1+dx,dx)
                    else:
                        x_vec = np.arange(x1,x0+dx,dx)
                    y_vec = np.full(x_vec.shape,y0)
                    b_dense = np.hstack((x_vec.reshape(len(x_vec),1),y_vec.reshape(len(y_vec),1)))
                    D.append(cdist(self.grid.xy_of_node,b_dense,'euclidean'))
                else:
                    dxi = dx * np.sin(np.radians(self.eq.SubEvents['Strike'][i]))
                    m = (y1-y0)/(x1-x0)
                    b = y0 - m*x0
                    if x1>x0:
                        x_vec = np.arange(x0,x1+dxi,dxi)
                    else:
                        x_vec = np.arange(x1,x0+dxi,dxi)
                    y_vec = m * x_vec + b
                    b_dense = np.hstack((x_vec.reshape(len(x_vec),1),y_vec.reshape(len(y_vec),1)))
                    D.append(cdist(self.grid.xy_of_node,b_dense,'euclidean'))
                    
                R_JB = np.min(np.hstack(D),1)
                
                # Convert R_RUP to kilometers as allt he GMPE models expect distances in km
                R_JB = R_JB/1000
                
                plt.figure()
                self.grid.at_node['rjb']=R_JB
                self.grid.imshow('rjb')
                for i in range(len(bx)):
                    plt.plot(bx[i],by[i])

        return R_JB
    
    def _calc_Z_Hypocenter_distance(self,event_id):
        '''
        Calculate the hypocenter depth for an event relative to a
        zero surface. For DippingFault ruptures, this is the weighted 
        average of the depths of all ruptured panels. For VerticalFault
        ruptures, this is identical to the depth of the center of the rupture
        patch.
        

        Parameters
        ----------
        event_id : int
            ID number of the event within an earthquake catalog to calculate
            distances.

        Returns
        -------
        Z_HYPO : float
            Hypocenter depth in km.

        '''

        if type(self.fault)==DippingFault:                   
            # Find event of interest
            eidx = self.eq.SubEvents['Event_ID']==event_id
            
            # Calculate subrupture areas
            A = self.eq.SubEvents['Length'][eidx] * self.eq.SubEvents['Width'][eidx]
            # Convert to fractions of the total area for weighting purposes
            area_fractions = A/np.sum(A)
            
            # Grid of xy in model coordinates
            MX = self.fault._MX
            MY = self.fault._MY
            FZ = self.fault._FZ
            mx = MX.ravel()
            my = MY.ravel()
            fz = FZ.ravel()
            m = np.hstack((mx.reshape((len(mx),1)),my.reshape((len(my),1))))
            
            # Find event of interest and the projected surface boundaries
            eidx = self.eq.SubEvents['Event_ID']==event_id
            bx = self.eq.SubEvents['Bound_X'][eidx]
            by = self.eq.SubEvents['Bound_Y'][eidx]

            # Generate array to store depths on rupture patch
            mz = np.zeros(mx.shape)
            aw = np.zeros(mx.shape) # Area weighting
            for i in range(len(bx)):
                p = path.Path([[bx[i][0],by[i][0]],[bx[i][1],by[i][1]],[bx[i][2],by[i][2]],[bx[i][3],by[i][3]],[bx[i][4],by[i][4]]])
                idx = p.contains_points(m)
                mz[idx] = fz[idx]
                aw[idx] = area_fractions[i]
                
            # Strip any parts of rz that are still zero
            ridx = mz>0
            rz = mz[ridx]
            aw = aw[ridx]
            
            # Area weighted means to approximate hypocenter depth
            hrz = np.average(rz,weights=aw)

            # Convert to km
            Z_HYPO = hrz/1000
            
        elif type(self.fault)==VerticalFault:
            # Find event of interest
            eidx = self.eq.SubEvents['Event_ID']==event_id
            hrz = self.eq.SubEvents['Center_Z'][eidx][0]
            
            # Convert to km
            Z_HYPO = hrz/1000
        
        return Z_HYPO
        
    def _calc_R_Hypocenter_distance(self,event_id):
        '''
        Calculate the hypocenter distance between a node and the hypocenter
        of a rupture. Hypocenter location reflects weighted average of rupture
        surface to find an approximate center in X, Y, and Z space. Distance for
        each node is then distance from this point and the X, Y, and Z coordinate of
        the node (including topography)

        Parameters
        ----------
        event_id : int
            ID number of the event within an earthquake catalog to calculate
            distances.

        Returns
        -------
        R_HYPO : array
            Array of Hypocenter distances for every node in a Landlab grid,
            distance are in kilometers.

        '''
        
        if type(self.fault)==DippingFault:                   
            # Find event of interest
            eidx = self.eq.SubEvents['Event_ID']==event_id
            
            # Calculate subrupture areas
            A = self.eq.SubEvents['Length'][eidx] * self.eq.SubEvents['Width'][eidx]
            # Convert to fractions of the total area for weighting purposes
            area_fractions = A/np.sum(A)
            
            # Grid of xy in model coordinates
            MX = self.fault._MX
            MY = self.fault._MY
            FZ = self.fault._FZ
            mx = MX.ravel()
            my = MY.ravel()
            fz = FZ.ravel()
            m = np.hstack((mx.reshape((len(mx),1)),my.reshape((len(my),1))))
            
            # Find event of interest and the projected surface boundaries
            eidx = self.eq.SubEvents['Event_ID']==event_id
            bx = self.eq.SubEvents['Bound_X'][eidx]
            by = self.eq.SubEvents['Bound_Y'][eidx]

            # Generate array to store depths on rupture patch
            mz = np.zeros(mx.shape)
            aw = np.zeros(mx.shape) # Area weighting
            for i in range(len(bx)):
                p = path.Path([[bx[i][0],by[i][0]],[bx[i][1],by[i][1]],[bx[i][2],by[i][2]],[bx[i][3],by[i][3]],[bx[i][4],by[i][4]]])
                idx = p.contains_points(m)
                mz[idx] = fz[idx]
                aw[idx] = area_fractions[i]
                
            # Strip any parts of rz that are still zero
            ridx = mz>0
            rx = mx[ridx]
            ry = my[ridx]
            rz = -1*mz[ridx] # Convert to depths
            aw = aw[ridx]
            
            # Area weighted means to approximate hypocenter
            hrx = np.average(rx,weights=aw)
            hry = np.average(ry,weights=aw)
            hrz = np.average(rz,weights=aw)

            # Generate xyz coords of nodes
            z = self.grid.at_node['topographic__elevation']
            xyz = np.hstack((self.grid.xy_of_node,z.reshape(len(z),1)))
            hrxyz = np.array([hrx,hry,hrz]).reshape(1,3)
            R_HYPO = cdist(xyz,hrxyz,'euclidean')
            
            # Convert R_HYPO to kilometers as allt he GMPE models expect distances in km
            R_HYPO = (R_HYPO/1000).ravel()
        
            # plt.figure()
            # self.grid.at_node['rhypo']=R_HYPO
            # self.grid.imshow('rhypo')
            # for i in range(len(bx)):
            #     plt.plot(bx[i],by[i])
            # plt.scatter(hrx,hry)
            
        elif type(self.fault)==VerticalFault:
            # Find event of interest
            eidx = self.eq.SubEvents['Event_ID']==event_id
            
            # Calculate subrupture areas
            A = self.eq.SubEvents['Length'][eidx] * self.eq.SubEvents['Width'][eidx]
            # Convert to fractions of the total area for weighting purposes
            area_fractions = A/np.sum(A)
            
            # Grid of fault in model coordinates
            FL = self.fault._FY
            FZ = self.fault._FZ
            fl = FL.ravel()
            fz = FZ.ravel()
            m = np.hstack((fl.reshape((len(fl),1)),fz.reshape((len(fz),1))))
            
            # Find event of interest and the projected surface boundaries
            eidx = self.eq.SubEvents['Event_ID']==event_id
            bl = self.eq.SubEvents['Bound_L'][eidx]
            bz = self.eq.SubEvents['Bound_Z'][eidx]

            # Generate array to store depths on rupture patch
            mz = np.zeros(fl.shape)
            ml = np.zeros(fl.shape)
            aw = np.zeros(fl.shape) # Area weighting
            for i in range(len(bl)):
                p = path.Path([[bl[i][0],bz[i][0]],[bl[i][1],bz[i][1]],[bl[i][2],bz[i][2]],[bl[i][3],bz[i][3]],[bl[i][4],bz[i][4]]])
                idx = p.contains_points(m)
                ml[idx] = fl[idx]
                mz[idx] = fz[idx]
                aw[idx] = area_fractions[i]
                
            # Strip any parts of rz that are still zero
            ridx = mz>0
            rl = ml[ridx]
            rz = -1*mz[ridx] # Convert to depths
            aw = aw[ridx]
            
            hrl = np.average(rl,weights=aw)
            hrz = np.average(rz,weights=aw)
            # Convert from length to xy
            [hrx,hry] = self.fault._length_to_xy(hrl)
            
            # Generate xyz coords of nodes
            z = self.grid.at_node['topographic__elevation']
            xyz = np.hstack((self.grid.xy_of_node,z.reshape(len(z),1)))
            hrxyz = np.array([hrx,hry,hrz]).reshape(1,3)
            R_HYPO = cdist(xyz,hrxyz,'euclidean')
            
            # Convert R_HYPO to kilometers as allt he GMPE models expect distances in km
            R_HYPO = (R_HYPO/1000).ravel()
            
            # plt.figure()
            # self.grid.at_node['rhypo']=R_HYPO
            # self.grid.imshow('rhypo')
            # bx = self.eq.SubEvents['Bound_X'][eidx]
            # by = self.eq.SubEvents['Bound_Y'][eidx]
            # for i in range(len(bx)):
            #     plt.plot(bx[i],by[i])
            # plt.scatter(hrx,hry,c='r')
            
        return R_HYPO
    
    def _calc_R_Rupture_distance(self,event_id):
        '''
        Calculate rupture distances between every node in a Landlab grid
        and the rupture for a particular event. The rupture distance is defined
        as the minimum distance between any point on the rupture plane and the
        site (in this case the node). The nodes topographic elevation is included
        in its location.

        Parameters
        ----------
        event_id : int
            ID number of the event within an earthquake catalog to calculate
            distances.

        Returns
        -------
        R_RUP : array
            Array of R_RUP distances for every node in a Landlab grid,
            distance are in kilometers.

        '''
        
        if type(self.fault)==DippingFault:
            # Grid of xy in model coordinates
            MX = self.fault._MX
            MY = self.fault._MY
            FZ = self.fault._FZ
            mx = MX.ravel()
            my = MY.ravel()
            fz = FZ.ravel()
            m = np.hstack((mx.reshape((len(mx),1)),my.reshape((len(my),1))))
            
            # Find event of interest and the projected surface boundaries
            eidx = self.eq.SubEvents['Event_ID']==event_id
            bx = self.eq.SubEvents['Bound_X'][eidx]
            by = self.eq.SubEvents['Bound_Y'][eidx]

            # Generate array to store depths on rupture patch
            mz = np.zeros(mx.shape)
            for i in range(len(bx)):
                p = path.Path([[bx[i][0],by[i][0]],[bx[i][1],by[i][1]],[bx[i][2],by[i][2]],[bx[i][3],by[i][3]],[bx[i][4],by[i][4]]])
                idx = p.contains_points(m)
                mz[idx] = fz[idx]
            # Strip any parts of rz that are still zero
            ridx = mz>0
            rx = mx[ridx]
            ry = my[ridx]
            rz = -1*mz[ridx] # Convert to depths
            # Build array of rupture depths
            rxyz = np.hstack((rx.reshape(len(rx),1),ry.reshape(len(rx),1),rz.reshape(len(rx),1)))
            # Generate xyz coords of nodes
            z = self.grid.at_node['topographic__elevation']
            xyz = np.hstack((self.grid.xy_of_node,z.reshape(len(z),1)))
            # Calculate distances and find minimum            
            D = cdist(xyz,rxyz,'euclidean')
            R_RUP = np.min(D,1)
            
            # Convert R_RUP to kilometers as allt he GMPE models expect distances in km
            R_RUP = R_RUP/1000
            
            # plt.figure()
            # self.grid.at_node['rrup']=R_RUP
            # self.grid.imshow('rrup')
            # for i in range(len(bx)):
            #     plt.plot(bx[i],by[i])
            
        elif type(self.fault)==VerticalFault:
            
            # Extract dx
            dx = self.fault._fault_dx
            
            # Find event of interest and bounds
            eidx = self.eq.SubEvents['Event_ID']==event_id
            bx = self.eq.SubEvents['Bound_X'][eidx]
            by = self.eq.SubEvents['Bound_Y'][eidx]
            bz = self.eq.SubEvents['Bound_Z'][eidx]
            
            z = self.grid.at_node['topographic__elevation']
            xyz = np.hstack((self.grid.xy_of_node,z.reshape(len(z),1)))
            
            D = []
            for i in range(len(bx)):
                # Extract points defining top of rupture
                x0 = bx[i][0]; x1 = bx[i][1]
                y0 = by[i][0]; y1 = by[i][1]
                z0 = bz[i][0]; z1 = bz[i][1]
                
                if (np.isclose(self.eq.SubEvents['Strike'][i],0)) | (np.isclose(self.eq.SubEvents['Strike'][i],180)) | (np.isclose(self.eq.SubEvents['Strike'][i],360)):
                    if y1>y0:
                        y_vec = np.arange(y0,y1+dx,dx)
                    else:
                        y_vec = np.arange(y1,y0+dx,dx)
                    x_vec = np.full(y_vec.shape,x0)
                    z_vec = np.full(y_vec.shape,z0)
                    b_dense = np.hstack((x_vec.reshape(len(x_vec),1),y_vec.reshape(len(y_vec),1),z_vec.reshape(len(z_vec),1)))
                    D.append(cdist(xyz,b_dense,'euclidean'))
                elif (np.isclose(self.eq.SubEvents['Strike'][i],90)) | (np.isclose(self.eq.SubEvents['Strike'][i],270)):
                    if x1>x0:
                        x_vec = np.arange(x0,x1+dx,dx)
                    else:
                        x_vec = np.arange(x1,x0+dx,dx)
                    y_vec = np.full(x_vec.shape,y0)
                    z_vec = np.full(x_vec.shape,z0)
                    b_dense = np.hstack((x_vec.reshape(len(x_vec),1),y_vec.reshape(len(y_vec),1),z_vec.reshape(len(z_vec),1)))
                    D.append(cdist(xyz,b_dense,'euclidean'))
                else:
                    dxi = dx * np.sin(np.radians(self.eq.SubEvents['Strike'][i]))
                    m = (y1-y0)/(x1-x0)
                    b = y0 - m*x0
                    if x1>x0:
                        x_vec = np.arange(x0,x1+dxi,dxi)
                    else:
                        x_vec = np.arange(x1,x0+dxi,dxi)
                    y_vec = m * x_vec + b
                    z_vec = np.full(x_vec.shape,z0)
                    b_dense = np.hstack((x_vec.reshape(len(x_vec),1),y_vec.reshape(len(y_vec),1),z_vec.reshape(len(z_vec),1)))
                    D.append(cdist(xyz,b_dense,'euclidean'))
                    
                R_RUP = np.min(np.hstack(D),1)
                
                # Convert R_RUP to kilometers as allt he GMPE models expect distances in km
                R_RUP = R_RUP/1000

        return R_RUP
    
    def _calc_R_X_distance(self,event_id):
        '''
        Calculate distance between the site (Landlab node) and the up-dip tip of
        the rupture, measured perpendicular to fault strike along a horizontal 
        surface. By definition, distances in the direction of dip are positive,
        the up-dip location of the rupture is zero, and distances in the direction
        opposite dip are negative. R_X is undefined for a vertical fault, returns
        -1 everywhere to ensure that no area is identified as being in the hanging
        wall.

        Parameters
        ----------
        event_id : int
            ID number of the event within an earthquake catalog to calculate
            distances.

        Returns
        -------
        R_X : array
            Array of R_X distances for every node in a Landlab grid,
            distance are in kilometers.

        '''
        
        if type(self.fault)==DippingFault:
            # Find event of interest and the projected surface boundaries
            eidx = self.eq.SubEvents['Event_ID']==event_id
            bx = self.eq.SubEvents['Bound_X'][eidx]
            by = self.eq.SubEvents['Bound_Y'][eidx]
            # Extract panel indices
            panel_ix = self.eq.SubEvents['Panel_IX'][eidx]
            # Identify top panel (should be first, but this is robust in case something strange has happened)
            top_ix = np.argmin(panel_ix)
            # Grab the x-y coordinates of the updip edge of the rupture and the upper right corner
            # to use as an origin
            bx_top = bx[top_ix]
            by_top = by[top_ix]
            x0 = bx_top[0]
            y0 = by_top[0]
            # Rotate the x,y nodes of the grid 
            [xp,yp]=_rot_coord(self.grid.x_of_node,self.grid.y_of_node,x0,y0,-self.fault._strike)
            # The rotated x coordinates will represent the "R_X" distance
            R_X = xp
            # Convert R_X to kilometers as allt he GMPE models expect distances in km
            R_X = R_X/1000

            # plt.figure()
            # self.grid.at_node['rx']=R_X
            # self.grid.imshow('rx',cmap='terrain',symmetric_cbar=True)
            # for i in range(len(bx)):
            #     plt.plot(bx[i],by[i])
            
        elif type(self.fault)==VerticalFault:
            # R_X is effectively undefined for a vertical fault, so return a grid of -1
            # to ensure that all nodes will have a value of 0 for the hanging wall flag
            # and thus the value of R_X will not matter
            R_X = np.full(self.grid.x_of_node.shape,-1)
            
        return R_X
    
    def _calc_forearc_to_backarc(self):
        '''
        Calculate distances from the up-dip fault tip, in the direction of dip,
        identical to R_X but for the fault as a whole as opposed to a particular 
        rupture. Stores result as fb_distance in object.

        Returns
        -------
        None.

        '''
        if type(self.fault)==DippingFault:
            # Grab the x-y coordinates of the updip edge of the fault and the upper right corner
            # to use as an origin
            panel_x = self.fault._panel_boundaries[0][0]
            panel_y = self.fault._panel_boundaries[0][1]
            x0 = panel_x[0]
            y0 = panel_y[0]
            # Rotate the x,y nodes of the grid 
            [xp,yp]=_rot_coord(self.grid.x_of_node,self.grid.y_of_node,x0,y0,-self.fault._strike)
            # The rotated x coordinates will represent the distance from the tip of the fault in the direction of strike
            self.fb_distance = xp
        elif type(self.fault)==VerticalFault:
            self.fb_distance = np.full(self.grid.x_of_node.shape,-1)
    
    def _calc_Z_TOR_distance(self,event_id):
        '''
        Calculate depth to the top of the rupture for a given event.

        Parameters
        ----------
        event_id : int
            ID number of the event within an earthquake catalog to calculate
            distances.

        Returns
        -------
        Z_TOR : float
            Depth to the top of the rupture plane in kilometers.

        '''
        
        if type(self.fault)==DippingFault:
            # Find event of interest and the projected surface boundaries
            eidx = self.eq.SubEvents['Event_ID']==event_id
            bx = self.eq.SubEvents['Bound_X'][eidx]
            by = self.eq.SubEvents['Bound_Y'][eidx]
            # Extract panel indices
            panel_ix = self.eq.SubEvents['Panel_IX'][eidx]
            # Identify top panel (should be first, but this is robust in case something strange has happened)
            top_ix = np.argmin(panel_ix)
            panel = np.min(panel_ix)
            # Grab upper corner
            x0 = bx[top_ix][0]
            y0 = by[top_ix][0]
            Z_TOR = (self.fault._query_depth(x0,y0,panel))/1000
            
        elif type(self.fault)==VerticalFault:
            # Find event of interest and the projected surface boundaries
            eidx = self.eq.SubEvents['Event_ID']==event_id
            bz = self.eq.SubEvents['Bound_Z'][eidx]
            Z_TOR = (bz[0][0])/1000
            
        return Z_TOR
    
    
    def _calc_average_dip(self,event_id):
        '''
        Calculates an average dip for events that span more than one panel.
        This is needed because the GMPEs that take dip as an argument only 
        consider one dip value. This calculates a weighted average of the dip 
        based on the area of the different panels.

        Parameters
        ----------
        event_id : int
            ID number of the event within an earthquake catalog to calculate
            distances.

        Returns
        -------
        dip : float
            Area weighted average dip of a particular rupture.

        '''
        
        if type(self.fault)==DippingFault:
            eidx = self.eq.SubEvents['Event_ID']==event_id
            l = self.eq.SubEvents['Length']
            w = self.eq.SubEvents['Width']
            a = l*w
            d = self.eq.SubEvents['Dip']
            dip = np.average(d,weights=a)
        elif type(self.fault)==VerticalFault:
            dip = 90.
            
        return dip
            
    
    def _calc_vs30(self):
        '''
        Calculates V_s30 by based on selections upon instantiation.

        Returns
        -------
        None.

        '''
        
        ## Calculate the V_S30 using the slope method regardless of method choice
        # because this will be used to fill in for any missing values if the
        # Yong terrain classification based methods are invoked
        
        # Define the slope bins based on 9 arcsec slope bins in 
        # Allen & Wald, 2009. These are chosen over the original bins 
        # from Wald & Allen, 2007 as there, slopes from 30 arcsec data 
        # is used to define the bins and nominally, the expected grid size
        # of a landlab model will probably be closer to the 9 arcsec case
        # than the 30 arcsec case.
        if self.vs30_setting=='active_tectonic':
            g_bns = np.array([3e-4,3.5e-3,0.01,0.024,0.08,0.14,0.2])
        elif self.vs30_setting=='stable_continent':
            g_bns = np.array([1e-4,4.5e-3,8.5e-3,0.013,0.022,0.03,0.04])
        
        # The right and left bin edges are defined as <180 or >760 respectively, 
        # so the values for data that falls in those bins are set such that the 
        # relative median position with respect to the bin edges of the adjacent
        # bins are applied to these end bins as an "offset" from the prescribed
        # bin edge
        vs30_bns = np.array([180-(240-180)/2,(240+180)/2,(300+240)/2,(360+300)/2,(490+360)/2,(620+490)/2,(760+620)/2,760+(760-620)/2])
        
        # Calculate gradient at nodes
        g = self.grid.calc_slope_at_node()
        # Assign V_S30
        V_S30_SLOPE = vs30_bns[np.digitize(g,g_bns)]
        
        if self.vs30_method == 'aw09':
            # Store as field
            self.grid.at_node['vs__30'] = vs30_bns[np.digitize(g,g_bns)]
        elif self.vs30_method == 'y12':
            # Calculate Iwahashi & Pike, 2007 terrain classification values
            trcl = _ip07_classifier(self.grid).ravel()
            
            # Convert classification into V_S30
            V_S30 = np.zeros(trcl.shape)
            V_S30[trcl==1]  = 519
            V_S30[trcl==2]  = 393
            V_S30[trcl==3]  = 547
            V_S30[trcl==4]  = 459
            V_S30[trcl==5]  = 402
            V_S30[trcl==6]  = 345
            V_S30[trcl==7]  = 388
            V_S30[trcl==8]  = 374
            V_S30[trcl==9]  = 497
            V_S30[trcl==10]  = 349
            V_S30[trcl==11]  = 328
            V_S30[trcl==12]  = 297
            V_S30[trcl==14]  = 209
            V_S30[trcl==15]  = 363
            V_S30[trcl==16]  = 246
            # Deal with missing value for classifcation for 13
            V_S30[trcl==13] = V_S30_SLOPE[trcl==13]
            
            # Store as a field
            self.grid.at_node['vs__30'] = V_S30
        elif self.vs30_method == 'y14':
            # Calculate Iwahashi & Pike, 2007 terrain classification values
            trcl = _ip07_classifier(self.grid).ravel()
            
            # Convert classification into V_S30
            V_S30 = np.zeros(trcl.shape)
            
            V_S30[trcl==1]  = 519
            V_S30[trcl==2]  = 586
            V_S30[trcl==3]  = 517
            V_S30[trcl==4]  = 568
            V_S30[trcl==5]  = 425
            V_S30[trcl==6]  = 448
            V_S30[trcl==7]  = 429
            V_S30[trcl==8]  = 382
            V_S30[trcl==9]  = 353
            V_S30[trcl==10]  = 348
            V_S30[trcl==11]  = 392
            V_S30[trcl==12]  = 281
            V_S30[trcl==14]  = 236
            V_S30[trcl==15]  = 460
            V_S30[trcl==16]  = 225
            # Deal with missing value for classifcation for 13
            V_S30[trcl==13] = V_S30_SLOPE[trcl==13]
            
            # Store as a field
            self.grid.at_node['vs__30'] = V_S30
    
    def _calc_pga(self,event_id):
        '''
        Calculates peak ground acceleration based on selections upon
        instantiation for a particular event.

        Parameters
        ----------
        event_id : int
            ID number of the event within an earthquake catalog to calculate
            distances.

        Returns
        -------
        None.

        '''
        
        if self._gmpe_model == 'cy08':
            # Calculate distances
            R_RUP = self._calc_R_Rupture_distance(event_id)
            R_X = self._calc_R_X_distance(event_id)
            F_HW = np.zeros(R_X.shape)
            F_HW[R_X>=0] = 1
            R_JB = self._calc_R_Joyner_Boore_distance(event_id)
            Z_TOR = self._calc_Z_TOR_distance(event_id)
            # Calculate V_S30
            if not(self.vs30_method==None):
                self._calc_vs30()
            V_S30 = self.grid.at_node['vs__30']
            # Extract magnitude
            eidx = self.eq.Events['Event_ID']==event_id
            M = self.eq.Events['Magnitude'][eidx] 
            # Determine if aftershock and set flags
            if 'Aftershock' in self.eq.Events:
                if self.eq.Events['Aftershock'][eidx]:
                    AS = 1
                else:
                    AS = 0
            else:
                AS = 0

            # Calculate area weighted dip
            delta = self._calc_average_dip(event_id)
            
            y = self._cy08_one_event_calc(self.F_RV,self.F_NM,F_HW,AS,M,delta,
                                            Z_TOR,R_RUP,R_X,R_JB,V_S30,
                                            self.random,self.seed)
            self.grid.at_node['peak_ground__acceleration'] = y[0,:]
            if self.store_spectral_accelerations:
                self.grid.at_node['peak_ground__velocity'] = y[1,:]
                for i in range(len(self._period)-2):
                    nm = str(self._period[i+2])+'_spectral__acceleration'
                    self.grid.at_node[nm] = y[i+2]
                        
                
        
        elif self._gmpe_model == 'aea16':
            # Calculate distances
            R_RUP = self._calc_R_Rupture_distance(event_id)
            R_HYPO = self._calc_R_Hypocenter_distance(event_id)
            Z_HYPO = self._calc_Z_Hypocenter_distance(event_id)
            # Calculate V_S30
            if not(self.vs30_method==None):
                self._calc_vs30()
            V_S30 = self.grid.at_node['vs__30']
            # Extract magnitude
            eidx = self.eq.Events['Event_ID']==event_id
            M = self.eq.Events['Magnitude'][eidx] 
            
            # Determine the form of theF_event and F_FABA input
            if isinstance(self.F_event,np.ndarray):
                F_event = self.F_event[eidx]
            else:
                F_event=self.F_event
            
            y = self._aea16_one_event_calc(F_event,self.F_FABA,M,
                                             Z_HYPO,R_RUP,R_HYPO,V_S30,
                                             self.random,self.seed)
            self.grid.at_node['peak_ground__acceleration'] = y[0,:]
            if self.store_spectral_accelerations:
                for i in range(len(self._period)-1):
                    nm = str(self._period[i+1])+'_spectral__acceleration'
                    self.grid.at_node[nm] = y[i+1]
            
            
        elif self._gmpe_model == 'pea11':
            # Calculate distance
            R_RUP = self._calc_R_Rupture_distance(event_id)
            # Extract magnitude
            eidx = self.eq.Events['Event_ID']==event_id
            M = self.eq.Events['Magnitude'][eidx] 
            # Calculate PGA
            y = self._pea11_one_event_calc(M,R_RUP,self.random,self.seed)
            
            self.grid.at_node['peak_ground__acceleration'] = y[0,:]
            if self.store_spectral_accelerations:
                for i in range(len(self._period)-1):
                    nm = str(self._period[i+1])+'_spectral__acceleration'
                    self.grid.at_node[nm] = y[i+1]
            


    def _cy08_constants(self):
        # First period is PGA, second is PGV
        self._period = np.array([0.0,-1.0,0.01, 0.02, 0.03, 0.04, 0.05, 0.075,
                                 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1,
                                 1.5, 2, 3, 4, 5, 7.5, 10])
        self._c1 = np.array([-1.2687,  2.2884, -1.2687, -1.2515, -1.1744, -1.0671, -0.9464,
                             -0.7051, -0.5747, -0.5309, -0.6352, -0.7766, -0.9278, -1.2176,
                             -1.4695, -1.9278, -2.2453, -2.7307, -3.1413, -3.7413, -4.1814,
                             -4.5187, -5.1224, -5.5872])
        self._c1a = np.array([ 0.1   ,  0.1094,  0.1   ,  0.1   ,  0.1   ,  0.1   ,  0.1   ,
                              0.1   ,  0.1   ,  0.1   ,  0.1   ,  0.1   ,  0.0999,  0.0997,
                              0.0991,  0.0936,  0.0766,  0.0022, -0.0591, -0.0931, -0.0982,
                              -0.0994, -0.0999, -0.1])
        self._c1b = np.array([-0.255 , -0.0626, -0.255 , -0.255 , -0.255 , -0.255 , -0.255 ,
                              -0.254 , -0.253 , -0.25  , -0.2449, -0.2382, -0.2313, -0.2146,
                              -0.1972, -0.162 , -0.14  , -0.1184, -0.11  , -0.104 , -0.102 ,
                              -0.101 , -0.101 , -0.1   ])
        self._cn = np.array([2.996, 1.648, 2.996, 3.292, 3.514, 3.563, 3.547, 3.448, 3.312,
                             3.044, 2.831, 2.658, 2.505, 2.261, 2.087, 1.812, 1.648, 1.511,
                             1.47 , 1.456, 1.465, 1.478, 1.498, 1.502])
        self._cM = np.array([4.184 , 4.2979, 4.184 , 4.1879, 4.1556, 4.1226, 4.1011, 4.086 ,
                             4.103 , 4.1717, 4.2476, 4.3184, 4.3844, 4.4979, 4.5881, 4.7571,
                             4.882 , 5.0697, 5.2173, 5.4385, 5.5977, 5.7276, 5.9891, 6.193 ])
        self._c5 = np.array([6.16  , 5.17  , 6.16  , 6.158 , 6.155 , 6.1508, 6.1441, 6.12  ,
                             6.085 , 5.9871, 5.8699, 5.7547, 5.6527, 5.4997, 5.4029, 5.29  ,
                             5.248 , 5.2194, 5.2099, 5.204 , 5.202 , 5.201 , 5.2 , 5.2 ])
        self._c6 = np.array([0.4893, 0.4407, 0.4893, 0.4892, 0.489 , 0.4888, 0.4884, 0.4872,
                             0.4854, 0.4808, 0.4755, 0.4706, 0.4665, 0.4607, 0.4571, 0.4531,
                             0.4517, 0.4507, 0.4504, 0.4501, 0.4501, 0.45  , 0.45  , 0.45  ])
        self._c7 = np.array([0.0512, 0.0207, 0.0512, 0.0512, 0.0511, 0.0508, 0.0504, 0.0495,
                             0.0489, 0.0479, 0.0471, 0.0464, 0.0458, 0.0445, 0.0429, 0.0387,
                             0.035 , 0.028 , 0.0213, 0.0106, 0.0041, 0.001 , 0. , 0.])
        self._c7a = np.array([0.086 , 0.0437, 0.086 , 0.086 , 0.086 , 0.086 , 0.086 , 0.086 ,
                              0.086 , 0.086 , 0.086 , 0.086 , 0.086 , 0.085 , 0.083 , 0.069 ,
                              0.045 , 0.0134, 0.004 , 0.001 , 0., 0. , 0. , 0. ])
        self._c9 = np.array([0.79  , 0.3079, 0.79  , 0.8129, 0.8439, 0.874 , 0.8996, 0.9442,
                             0.9677, 0.966 , 0.9334, 0.8946, 0.859 , 0.8019, 0.7578, 0.6788,
                             0.6196, 0.5101, 0.3917, 0.1244, 0.0086, 0. , 0. , 0.])
        self._c9a = np.array([1.5005, 2.669 , 1.5005, 1.5028, 1.5071, 1.5138, 1.523 , 1.5597,
                              1.6104, 1.7549, 1.9157, 2.0709, 2.2005, 2.3886, 2.5   , 2.6224,
                              2.669 , 2.6985, 2.7085, 2.7145, 2.7164, 2.7172, 2.7177, 2.718 ])
        self._c10 = np.array([-0.3218, -0.1166, -0.3218, -0.3323, -0.3394, -0.3453, -0.3502,
                              -0.3579, -0.3604, -0.3565, -0.347 , -0.3379, -0.3314, -0.3256,
                              -0.3189, -0.2702, -0.2059, -0.0852,  0.016 ,  0.1876,  0.3378,
                              0.4579,  0.7514,  1.1856])
        self._cgamma1 = np.array([-0.00804, -0.00275, -0.00804, -0.00811, -0.00839, -0.00875,
                                  -0.00912, -0.00973, -0.00975, -0.00883, -0.00778, -0.00688,
                                  -0.00612, -0.00498, -0.0042 , -0.00308, -0.00246, -0.0018 ,
                                  -0.00147, -0.00117, -0.00107, -0.00102, -0.00096, -0.00094])
        self._cgamma2 = np.array([-0.00785, -0.00625, -0.00785, -0.00792, -0.00819, -0.00855,
                                  -0.00891, -0.0095 , -0.00952, -0.00862, -0.00759, -0.00671,
                                  -0.00598, -0.00486, -0.0041 , -0.00301, -0.00241, -0.00176,
                                  -0.00143, -0.00115, -0.00104, -0.00099, -0.00094, -0.00091])
        self._phi1 = np.array([-0.4417, -0.7861, -0.4417, -0.434 , -0.4177, -0.4   , -0.3903,
                               -0.404 , -0.4423, -0.5162, -0.5697, -0.6109, -0.6444, -0.6931,
                               -0.7246, -0.7708, -0.799 , -0.8382, -0.8663, -0.9032, -0.9231,
                               -0.9222, -0.8346, -0.7332])
        self._phi2 = np.array([-0.1417, -0.0699, -0.1417, -0.1364, -0.1403, -0.1591, -0.1862,
                               -0.2538, -0.2943, -0.3113, -0.2927, -0.2662, -0.2405, -0.1975,
                               -0.1633, -0.1028, -0.0699, -0.0425, -0.0302, -0.0129, -0.0016,
                               0., 0., 0.])
        self._phi3 = np.array([-0.00701 , -0.008444, -0.00701 , -0.007279, -0.007354, -0.006977,
                               -0.006467, -0.005734, -0.005604, -0.005845, -0.006141, -0.006439,
                               -0.006704, -0.007125, -0.007435, -0.00812 , -0.008444, -0.007707,
                               -0.004792, -0.001828, -0.001523, -0.00144 , -0.001369, -0.001361])
        self._phi4 = np.array([1.02151e-01, 5.41000e+00, 1.02151e-01, 1.08360e-01, 1.19888e-01,
                               1.33641e-01, 1.48927e-01, 1.90596e-01, 2.30662e-01, 2.66468e-01,
                               2.55253e-01, 2.31541e-01, 2.07277e-01, 1.65464e-01, 1.33828e-01,
                               8.51530e-02, 5.85950e-02, 3.17870e-02, 1.97160e-02, 9.64300e-03,
                               5.37900e-03, 3.22300e-03, 1.13400e-03, 5.15000e-04])
        self._phi5 = np.array([0.2289, 0.2899, 0.2289, 0.2289, 0.2289, 0.2289, 0.229 , 0.2292,
                               0.2297, 0.2326, 0.2386, 0.2497, 0.2674, 0.312 , 0.361 , 0.4353,
                               0.4629, 0.4756, 0.4785, 0.4796, 0.4799, 0.4799, 0.48  , 0.48  ])
        self._phi6 = np.array([0.014996, 0.006718, 0.014996, 0.014996, 0.014996, 0.014996,
                               0.014996, 0.014996, 0.014996, 0.014988, 0.014964, 0.014881,
                               0.014639, 0.013493, 0.011133, 0.006739, 0.005749, 0.005544,
                               0.005521, 0.005517, 0.005517, 0.005517, 0.005517, 0.005517])
        self._phi7 = np.array([580. , 459. , 580. , 580. , 580. , 579.9, 579.9, 579.6, 579.2,
                               577.2, 573.9, 568.5, 560.5, 540. , 512.9, 441.9, 391.8, 348.1,
                               332.5, 324.1, 321.7, 320.9, 320.3, 320.1])
        self._phi8 = np.array([ 0.07  ,  0.1138,  0.07  ,  0.0699,  0.0701,  0.0702,  0.0701,
                               0.0686,  0.0646,  0.0494, -0.0019, -0.0479, -0.0756, -0.096 ,
                               -0.0998, -0.0765, -0.0412,  0.014 ,  0.0544,  0.1232,  0.1859,
                               0.2295,  0.266 ,  0.2682])
        self._c2 = np.full(self._phi8.shape,1.06)
        self._c3 = np.full(self._phi8.shape,3.45)
        self._c4 = np.full(self._phi8.shape,-2.1)
        self._c4a = np.full(self._phi8.shape,-0.5)
        self._cRB = np.full(self._phi8.shape,50)
        self._cHM = np.full(self._phi8.shape,3)
        self._cgamma3 = np.full(self._phi8.shape,4)
        self._tau1 = np.array([0.3437, 0.2539, 0.3437, 0.3471, 0.3603, 0.3718, 0.3848, 0.3878,
                               0.3835, 0.3719, 0.3601, 0.3522, 0.3438, 0.3351, 0.3353, 0.3429,
                               0.3577, 0.3769, 0.4023, 0.4406, 0.4784, 0.5074, 0.5328, 0.5542])
        self._tau2 = np.array([0.2637, 0.2381, 0.2637, 0.2671, 0.2803, 0.2918, 0.3048, 0.3129,
                               0.3152, 0.3128, 0.3076, 0.3047, 0.3005, 0.2984, 0.3036, 0.3205,
                               0.3419, 0.3703, 0.4023, 0.4406, 0.4784, 0.5074, 0.5328, 0.5542])
        self._sigma1 = np.array([0.4458, 0.4496, 0.4458, 0.4458, 0.4535, 0.4589, 0.463 , 0.4702,
                                 0.4747, 0.4798, 0.4816, 0.4815, 0.4801, 0.4758, 0.471 , 0.4621,
                                 0.4581, 0.4493, 0.4459, 0.4433, 0.4424, 0.442 , 0.4416, 0.4414])
        self._sigma2 = np.array([0.3459, 0.3554, 0.3459, 0.3459, 0.3537, 0.3592, 0.3635, 0.3713,
                                 0.3769, 0.3847, 0.3902, 0.3946, 0.3981, 0.4036, 0.4079, 0.4157,
                                 0.4213, 0.4213, 0.4213, 0.4213, 0.4213, 0.4213, 0.4213, 0.4213])
        self._sigma3 = np.array([0.8   , 0.7504, 0.8   , 0.8   , 0.8   , 0.8   , 0.8   , 0.8   ,
                                 0.8   , 0.8   , 0.8   , 0.7999, 0.7997, 0.7988, 0.7966, 0.7792,
                                 0.7504, 0.7136, 0.7035, 0.7006, 0.7001, 0.7   , 0.7   , 0.7   ])
        self._sigma4 = np.array([0.0663, 0.0133, 0.0663, 0.0663, 0.0663, 0.0663, 0.0663, 0.0663,
                                 0.0663, 0.0612, 0.053 , 0.0457, 0.0398, 0.0312, 0.0255, 0.0175,
                                 0.0133, 0.009 , 0.0068, 0.0045, 0.0034, 0.0027, 0.0018, 0.0014])
        
    
    def _cy08_one_event_calc(self,F_RV,F_NM,F_HW,AS,M,delta,Z_TOR,R_RUP,R_X,R_JB,V_S30,random,seed):
        '''
        Calculationg of spectral acceleration for the 'cy08' model

        Parameters
        ----------
        F_RV : boolean
            Reverse fault flag, 1 if reverse.
        F_NM : boolean
            Normal fault flag, 1 if normal.
        F_HW : array
            Hanging wall flag, 1 for any node where R_X is positive.
        AS : boolean
            Aftershock flag, 1 if aftershock.
        M : float
            Magnitude of event.
        delta : float
            Dip angle. (degrees)
        Z_TOR : float
            Depth to top of rupture. (km)
        R_RUP : array
            R_RUP distance for every node in grid. (km)
        R_X : array
            R_X distance for every node in grid. (km)
        R_JB : array
            Joyner Boore distance for every node in grid. (km)
        V_S30 : array
            V_s30 for every node in grid. (m/s)
        random : boolean
            Flag to turn on random selection of normal distribution of PGA.
        seed : int
            Seed for random number generator if random is True

        Returns
        -------
        sa : array
            Spectral accelerations for every node in units of g.

        '''
        
        # Calculate natural log of yref
        ln_yref = self._cy08_ln_yref(F_RV,F_NM,F_HW,AS,M,delta,Z_TOR,R_RUP,R_X,R_JB)
        # Calculate natural log of y and the standard deviation of natural log of y
        ln_y,sigma_t = self._cy08_ln_y(ln_yref,V_S30,M,AS)
        
        if random:
            rng = np.random.default_rng(seed)
            # Random normal sampling
            ln_y_r=np.zeros(ln_y.shape)
            for j in range(len(self._period)):
                ln_y_r[j,:] = np.array([rng.normal(ln_y[j,i],sigma_t[j,i]) for i in range(len(ln_y[j,:]))])
            return np.exp(ln_y_r)
        else:
            return np.exp(ln_y)
            
            
    def _cy08_ln_yref(self,F_RV,F_NM,F_HW,AS,M,delta,Z_TOR,R_RUP,R_X,R_JB):
        '''
        Equation 13a for calculating the natural log of yref

        Parameters
        ----------
        F_RV : boolean
            Reverse fault flag, 1 if reverse.
        F_NM : boolean
            Normal fault flag, 1 if normal.
        F_HW : array
            Hanging wall flag, 1 for any node where R_X is positive.
        AS : boolean
            Aftershock flag, 1 if aftershock.
        M : float
            Magnitude of event.
        delta : float
            Dip angle. (degrees)
        Z_TOR : float
            Depth to top of rupture. (km)
        R_RUP : array
            R_RUP distance for every node in grid. (km)
        R_X : array
            R_X distance for every node in grid. (km)
        R_JB : array
            Joyner Boore distance for every node in grid. (km)

        Returns
        -------
        sa : array
            Array of natural logs of reference spectral accelerations.

        '''
        # Preallocate
        num_periods = len(self._c1)
        num_sites = len(R_RUP)
        out = np.zeros((num_periods,num_sites))
        
        for i in range(num_periods):
            term1 = self._c1[i]
            term2 = (self._c1a[i]*F_RV + self._c1b[i]*F_NM + self._c7[i]*(Z_TOR-4))*(1-AS)
            term3 = (self._c10[i] + self._c7a[i]*(Z_TOR-4))*AS
            term4 = self._c2[i]*(M-6)
            term5 = ((self._c2[i] -self._c3[i])/self._cn[i])*np.log(1+np.exp(self._cn[i] *(self._cM[i]-M)))
            term6 = self._c4[i] *np.log(R_RUP + self._c5[i]*np.cosh(self._c6[i]*np.maximum(M-self._cHM[i],0)))
            term7 = (self._c4a[i]-self._c4[i]) * np.log(np.sqrt(R_RUP**2 + self._cRB[i]**2))
            term8 = R_RUP * (self._cgamma1[i] + self._cgamma2[i]/(np.cosh(np.maximum(M-self._cgamma3[i],0))))
            term9 = self._c9[i] *F_HW*np.tanh((R_X*np.cos(np.radians(delta))**2)/self._c9a[i])*(1 - (np.sqrt(R_JB**2 + Z_TOR**2))/(R_RUP+0.001))
            out[i,:] = term1 + term2 + term3 + term4 + term5 + term6 + term7 + term8 + term9
            
        return out
    
    def _cy08_ln_y(self,ln_yref,V_S30,M,AS):
        '''
        Equation 13b for calculating the natural log of y

        Parameters
        ----------
        ln_yref : array
            Result of equation 13a.
        V_S30 : array
            V_s30 for every node in grid. (m/s)
        M : float
            Magnitude of event.
        AS : boolean
            Aftershock flag, 1 if aftershock.

        Returns
        -------
        median: array
            Array of natural log of spectral accelerations.
        sigma_t: array
            Array of standard deviation of spectral accelerations

        '''
        # Preallocate
        num_periods = len(self._c1)
        num_sites = len(V_S30)
        median = np.zeros((num_periods,num_sites))
        sigma_t =  np.zeros((num_periods,num_sites))
        
        # Estimate Z_1
        Z_1 = self._cy08_Z1(V_S30)
        # Calculate the reference value for each site
        yref = np.exp(ln_yref)
        b = self._cy08_b(V_S30)
        c = self._cy08_c()
        
        # Calculate median assuming eta and epsilon are 0 using equation 13b
        for i in range(num_periods):
            term1 = ln_yref[i,:]
            term2 = self._phi1[i] *  np.minimum(np.log(V_S30/1130),0)
            term3 = b[i,:] * np.log((yref[i,:] + self._phi4[i]) / self._phi4[i])
            term4a = np.maximum(Z_1-self._phi7[i],0)
            term4 = self._phi5[i] * (1 - (1/(np.cosh(self._phi6[i]*term4a))))
            term5a = np.maximum(Z_1-15,0)
            term5  = self._phi8[i]  / (np.cosh(0.15*term5a))
            median[i,:] = term1 + term2 + term3 + term4 + term5
        
        # Calculate components of intra and inter-event error
        # Tau - inter-event standard deviation (equation 19)
        for i in range(num_periods):
            tau = self._tau1[i] + ((self._tau2[i] - self._tau1[i])/2) * (np.minimum(np.maximum(M,5),7)-5)
            # NL0 (part of equation 20)
            NL0 = b[i,:] * yref[i,:] / (yref[i,:] +c[i])
            # Sigma - intra-event standard deviation (equation 20)
            term1 = self._sigma1[i] + ((self._sigma2[i] - self._sigma1[i] )/2)*np.minimum(np.maximum(M,5),7) + self._sigma4[i]*AS
            # Embed assumpition that the VS30 is inferred as opposed to measured
            F_inf = 1
            F_mea = 0
            term2 = np.sqrt(self._sigma3[i]*F_inf + 0.7*F_mea + (1+NL0)**2)
            sigma = term1 * term2
            # Calculate total sigma (equation 21)
            sigma_t[i,:] = np.sqrt( (((1+NL0)**2) * (tau**2)) + sigma**2 )
        return  median,sigma_t
        
    def _cy08_Z1(self,V_S30):
        '''
        Approximation of Z_1.0 from equation 1, based on V_S30

        Parameters
        ----------
        V_S30 : array
            V_s30 for every node in grid. (m/s)

        Returns
        -------
        Z1: array
            Z1 at every node.

        '''
        lnZ1 = 28.5 - (3.82/8) * np.log(V_S30**8 + 378.7**8)
        return np.exp(lnZ1)
    
    
    def _cy08_a(self,V_S30):
        '''
        Equation 10 - for coefficient a

        Parameters
        ----------
        V_S30 : array
            V_s30 for every node in grid. (m/s)

        Returns
        -------
        a: array
            a at every node for all periods.

        '''
        num_periods = len(self._c1)
        num_sites = len(V_S30)
        a = np.zeros((num_periods,num_sites))
        for i in range(num_periods):
            a[i,:] = self._phi1[i]*np.log(V_S30/1130)
        
        return a
    
    def _cy08_b(self,V_S30):
        '''
        Equation 10 - for coefficient b

        Parameters
        ----------
        V_S30 : array
            V_s30 for every node in grid. (m/s)

        Returns
        -------
        b: array
            b at every node for all periods

        '''
        num_periods = len(self._c1)
        num_sites = len(V_S30)
        b = np.zeros((num_periods,num_sites))
        
        for i in range(num_periods):
            term1 = self._phi2[i]
            term2 = np.exp(self._phi3[i] * (np.minimum(V_S30,1130) - 360))
            term3 = np.exp(self._phi3[i] * (1130 - 360))
            b[i,:]=term1*(term2-term3)
        return b
    
    def _cy08_c(self):
        '''
        Equation 10 - for coefficient c

        Parameters
        ----------

        Returns
        -------
        phi4
            c constant.

        '''
        
        return self._phi4 
    
    def _aea16_constants(self):
        # First period is PGA
        self._period = np.array([ 0.   ,  0.02 ,  0.05 ,  0.075,  0.1  ,  0.15 ,  0.2  ,  0.25 ,
                                 0.3  ,  0.4  ,  0.5  ,  0.6  ,  0.75 ,  1.   ,  1.5  ,  2.   ,
                                 2.5  ,  3.   ,  4.   ,  5.   ,  6.   ,  7.5  , 10.   ])
        self._Vlin = np.array([ 865.1,  865.1, 1053.5, 1085.7, 1032.5,  877.6,  748.2,  654.3,
                               587.1,  503. ,  456.6,  430.3,  410.5,  400. ,  400. ,  400. ,
                               400. ,  400. ,  400. ,  400. ,  400. ,  400. ,  400. ])
        self._b = np.array([-1.186, -1.186, -1.346, -1.471, -1.624, -1.931, -2.188, -2.381,
                            -2.518, -2.657, -2.669, -2.599, -2.401, -1.955, -1.025, -0.299,
                            0.   ,  0.   ,  0.   ,  0.   ,  0.   ,  0.   ,  0.   ])
        self._theta1 = np.array([ 4.2203,  4.2203,  4.5371,  5.0733,  5.2892,  5.4563,  5.2684,
                                 5.0594,  4.7945,  4.4644,  4.0181,  3.6055,  3.2174,  2.7981,
                                 2.0123,  1.4128,  0.9976,  0.6443,  0.0657, -0.4624, -0.9809,
                                 -1.6017, -2.2937])
        self._theta2 = np.array([-1.35, -1.35, -1.4 , -1.45, -1.45, -1.45, -1.4 , -1.35, -1.28,
                                 -1.18, -1.08, -0.99, -0.91, -0.85, -0.77, -0.71, -0.67, -0.64,
                                 -0.58, -0.54, -0.5 , -0.46, -0.4 ])
        self._theta6 = np.array([-0.0012, -0.0012, -0.0012, -0.0012, -0.0012, -0.0014, -0.0018,
                                 -0.0023, -0.0027, -0.0035, -0.0044, -0.005 , -0.0058, -0.0062,
                                 -0.0064, -0.0064, -0.0064, -0.0064, -0.0064, -0.0064, -0.0064,
                                 -0.0064, -0.0064])
        self._theta7 = np.array([ 1.0988,  1.0988,  1.2536,  1.4175,  1.3997,  1.3582,  1.1648,
                                 0.994 ,  0.8821,  0.7046,  0.5799,  0.5021,  0.3687,  0.1746,
                                 -0.082 , -0.2821, -0.4108, -0.4466, -0.4344, -0.4368, -0.4586,
                                 -0.4433, -0.4828])
        self._theta8 = np.array([-1.42, -1.42, -1.65, -1.8 , -1.8 , -1.69, -1.49, -1.3 , -1.18,
                                 -0.98, -0.82, -0.7 , -0.54, -0.34, -0.05,  0.12,  0.25,  0.3 ,
                                 0.3 ,  0.3 ,  0.3 ,  0.3 ,  0.3 ])
        self._theta10 = np.array([3.12, 3.12, 3.37, 3.37, 3.33, 3.25, 3.03, 2.8 , 2.59, 2.2 , 1.92,
                                  1.7 , 1.42, 1.1 , 0.7 , 0.7 , 0.7 , 0.7 , 0.7 , 0.7 , 0.7 , 0.7 ,
                                  0.7 ])
        self._theta11 = np.array([ 0.013 ,  0.013 ,  0.013 ,  0.013 ,  0.013 ,  0.013 ,  0.0129,
                                  0.0129,  0.0128,  0.0127,  0.0125,  0.0124,  0.012 ,  0.0114,
                                  0.01  ,  0.0085,  0.0069,  0.0054,  0.0027,  0.0005, -0.0013,
                                  -0.0033, -0.006 ])
        self._theta12 = np.array([ 0.98 ,  0.98 ,  1.288,  1.483,  1.613,  1.882,  2.076,  2.248,
                                  2.348,  2.427,  2.399,  2.273,  1.993,  1.47 ,  0.408, -0.401,
                                  -0.723, -0.673, -0.627, -0.596, -0.566, -0.528, -0.504])
        self._theta13 = np.array([-0.0135, -0.0135, -0.0138, -0.0142, -0.0145, -0.0153, -0.0162,
                                  -0.0172, -0.0183, -0.0206, -0.0231, -0.0256, -0.0296, -0.0363,
                                  -0.0493, -0.061 , -0.0711, -0.0798, -0.0935, -0.098 , -0.098 ,
                                  -0.098 , -0.098 ])
        self._theta14 = np.array([-0.4 , -0.4 , -0.4 , -0.4 , -0.4 , -0.4 , -0.35, -0.31, -0.28,
                                  -0.23, -0.19, -0.16, -0.12, -0.07,  0.  ,  0.  ,  0.  ,  0.  ,
                                  0.  ,  0.  ,  0.  ,  0.  ,  0.  ])
        self._theta15 = np.array([0.9996, 0.9996, 1.103 , 1.2732, 1.3042, 1.26  , 1.223 , 1.16  ,
                                  1.05  , 0.8   , 0.662 , 0.58  , 0.48  , 0.33  , 0.31  , 0.3   ,
                                  0.3   , 0.3   , 0.3   , 0.3   , 0.3   , 0.3   , 0.3   ])
        self._theta16 = np.array([-1.  , -1.  , -1.18, -1.36, -1.36, -1.3 , -1.25, -1.17, -1.06,
                                  -0.78, -0.62, -0.5 , -0.34, -0.14,  0.  ,  0.  ,  0.  ,  0.  ,
                                  0.  ,  0.  ,  0.  ,  0.  ,  0.  ])
        self._phi = np.full(self._theta16.shape,0.6)
        self._tau = np.full(self._theta16.shape,0.43)
        self._sigma = np.full(self._theta16.shape,0.74)
        self._n = np.full(self._theta16.shape,1.18)
        self._c = np.full(self._theta16.shape,1.88)
        self._theta3 = np.full(self._theta16.shape,0.1)
        self._theta4 = np.full(self._theta16.shape,0.9)
        self._theta5 = np.full(self._theta16.shape,0.)
        self._theta9 = np.full(self._theta16.shape,0.4)
        self._C4 = np.full(self._theta16.shape,10.)
        self._C1 = np.full(self._theta16.shape,7.8)
        
        # Linear interpolation of DeltaC1
        period_int = np.array([0.3,0.5,1.0,2.0,3.0])
        logperiod = np.log10(period_int)
        delta_c = np.array([0.2,0.1,0.0,-0.1,-0.2])
        res = linregress(logperiod,delta_c)
        delta_c_pred = res.slope * np.log10(self._period[1:]) + res.intercept
        delta_c_pred[self._period[1:]>=3]=-0.2 
        self._deltaC1 = np.concat(([0.2],delta_c_pred))

        
    def _aea16_one_event_calc(self,F_event,F_FABA,M,Z_H,R_RUP,R_HYPO,V_S30,random,seed):
        '''
        Calculation of spectral acceleration for the 'aea16' model

        Parameters
        ----------
        F_event : boolean
            Flag to set event type to interface (0) or intraslab (1).
        F_FABA : boolean array
            Flag to set site to be treated as forearc (0) or backarc (1).
        M : float
            Magnitude of event.
        Z_H : float
            Hypocenter depth of event. (km)
        R_RUP : array
            R_RUP distances for all nodes. (km)
        R_HYPO : array
            Hypocenter distnaces for all nodes. (km)
        V_S30 : array
            V_s30 for all nodes. (m/s)
        random : boolean
            Flag to turn on random selection of normal distribution of PGA.
        seed : int
            Seed for random number generator if random is True

        Returns
        -------
        sa: array
            spectral accelerations for every node in g.

        '''
        
        # Calculate the natural log of the acceleration and the standard deviation
        ln_y,sigma_t = self._aea16_ln_y(F_event,F_FABA,M,Z_H,R_RUP,R_HYPO,V_S30)
        
        if random:
            rng = np.random.default_rng(seed)
            # Random normal sampling
            ln_y_r=np.zeros(ln_y.shape)
            for j in range(len(self._period)):
                ln_y_r[j,:] = np.array([rng.normal(ln_y[j,i],sigma_t[j,i]) for i in range(len(ln_y[j,:]))])
            return np.exp(ln_y_r)
        else:
            return np.exp(ln_y)
    
    
    def _aea16_ln_y(self,F_event,F_FABA,M,Z_H,R_RUP,R_HYPO,V_S30):
        '''
        Equation 1a and 1b

        Parameters
        ----------
        F_event : boolean
            Flag to set event type to interface (0) or intraslab (1).
        F_FABA : boolean array
            Flag to set site to be treated as forearc (0) or backarc (1).
        M : float
            Magnitude of event.
        Z_H : float
            Hypocenter depth of event. (km)
        R_RUP : array
            R_RUP distances for all nodes. (km)
        R_HYPO : array
            Hypocenter distnaces for all nodes. (km)
        V_S30 : array
            V_s30 for all nodes. (m/s)

        Returns
        -------
        ln_y : array
            Natural log of spectral accelerations.
        sigma_t : array
            Standard deviation of spectral accelerations.

        '''
        
        # Set Vs*
        V_S_star = V_S30.copy()
        V_S_star[V_S30>1000] = 1000
        
        # Calculae natural log of y based on whether it is an intraslab or interface event
        num_periods = len(self._period)
        num_sites = len(R_RUP)
        ln_y = np.zeros((num_periods,num_sites))
        sigma_t = np.zeros((num_periods,num_sites))
        
        for i in range(num_periods):
            if F_event:
                # Intraslab event
                term1 = self._theta1[i] 
                term2 = self._theta4[i] *-0.3 # Delta C1 is set to a constant value for an intraslab event
                term3a = (self._theta2[i] + self._theta14[i]*F_event + self._theta3[i]*(M-7.8))
                term3b = np.log(R_HYPO + self._C4[i]*np.exp(self._theta9[i]*(M-6)))
                term3 = term3a*term3b
                term4 = self._theta6[i]*R_HYPO
                term5 = self._theta10[i]*F_event
                term6 = self._aea16_fmag(M,-0.3,i)
                term7 = self._aea16_fdepth(F_event,Z_H,i)
                term8 = self._aea16_ffaba(F_event,F_FABA,R_RUP,R_HYPO,i)
                term9 = self._theta12[i]*np.log(1000/self._Vlin[i]) + self._b[i]*self._n[i]*np.log(1000/self._Vlin[i])
                PGA1000 = np.exp(term1 + term2 + term3 + term4 + term5 + term6 + term7 + term8 + term9).ravel()
                term9s = self._aea16_fsite(V_S30,V_S_star,PGA1000,i)
                ln_y[i,:] = term1 + term2 + term3 + term4 + term5 + term6 + term7 + term8 + term9s
            else:
                # Interface event
                term1 = self._theta1[i]
                term2 = self._theta4[i]*self._deltaC1[i]
                term3a = (self._theta2[i] + self._theta3[i]*(M-7.8))
                term3b = np.log(R_RUP + self._C4[i]*np.exp(self._theta9[i]*(M-6)))
                term3  = term3a * term3b
                term4 = self._theta6[i]*R_RUP
                # No term 5 as it is zero if F_event = 0
                term6 = self._aea16_fmag(M,self._deltaC1[i],i)
                # No term 7 as the fdepth is zero if F_event = 0
                term8 = self._aea16_ffaba(F_event,F_FABA,R_RUP,R_HYPO,i)
                term9 = self._theta12[i]*np.log(1000/self._Vlin[i]) + self._b[i]*self._n[i]*np.log(1000/self._Vlin[i])
                PGA1000 = np.exp(term1 + term2 + term3 + term4  + term6 + term8 + term9).ravel()
                term9s = self._aea16_fsite(V_S30,V_S_star,PGA1000,i)
                ln_y[i,:] = term1 + term2 + term3 + term4  + term6 + term8 + term9s
            
            # Standard deviation is fixed across all periods
            sigma_t[i,:] = np.sqrt(self._phi[i]**2 + self._tau[i]**2)
            
        return ln_y,sigma_t
    
    
    def _aea16_fmag(self,M,deltaC1,i):
        """
        Equation 2

        Parameters
        ----------
        M : float
            Magnitude of event.
        deltaC1 : array
            Constant DeltaC1
            

        Returns
        -------
        f_MAG: array
            f_Mag for different periods

        """
        
        
        c_val = self._C1[i] + deltaC1
        
        if M <= c_val:
            return self._theta4[i] * (M - c_val) + self._theta13[i]*((10-M)**2)
        else:
            return self._theta5[i] * (M - c_val) + self._theta13[i] *((10-M)**2)
        
    def _aea16_fdepth(self,F_event,Z_H,i):
        """
        Equation 3

        Parameters
        ----------
        F_event : boolean
            Flag to set event type to interface (0) or intraslab (1).
        Z_H : float
            Hypocenter depth of event. (km)

        Returns
        -------
        f_depth: float
            f_depth value from Equation 3.

        """
        
        m = np.minimum(Z_H,120)
        return self._theta11[i] * (m-60) * F_event
    
    def _aea16_ffaba(self,F_event,F_FABA,R_RUP,R_HYPO,i):
        """
        Equation 4

        Parameters
        ----------
        F_event : boolean
            Flag to set event type to interface (0) or intraslab (1).
        F_FABA : boolean array
            Flag to set site to be treated as forearc (0) or backarc (1).
        R_RUP : array
            R_RUP distances for all nodes. (km)
        R_HYPO : array
            Hypocenter distnaces for all nodes. (km)

        Returns
        -------
        f_FABA: array
            f_FABA value from Equation 4.

        """
        
        if F_event:
            max_term = np.maximum(R_HYPO,85)
            inner = self._theta7[i] + self._theta8[i]*np.log(max_term/40)
        else:
            max_term = np.maximum(R_RUP,100)
            inner = self._theta15[i] + self._theta16[i]*np.log(max_term/40)
            
        return inner*F_FABA
    
    def _aea16_fsite(self,V_S30,V_S_star,PGA1000,i):
        """
        Equation 5

        Parameters
        ----------
        V_S30 : array
            V_s30 for all nodes. (m/s)
        V_S_star : float
            Constant V_S^*. (m/s)
        PGA1000 : array
            PGA for a reference V_s30 of 1000.

        Returns
        -------
        f_site : array
            f_site for all nodes.

        """
        
        # Establish output vector
        out = np.zeros(V_S30.shape)
        
        # Establish index
        idx = V_S30 < self._Vlin[i]
        
        # Do first set of calculations for sites where V_S30 is less than V_lin
        out[idx]  = self._theta12[i]*np.log(V_S_star[idx]/self._Vlin[i]) - self._b[i]*np.log(PGA1000[idx] + self._c[i]) + self._b[i]*np.log(PGA1000[idx] + self._c[i]*((V_S_star[idx]/self._Vlin[i])**self._n[i]))
        # Do second set of calculatiosn for sites where V_S30 is greater than V_lin
        out[~idx] = self._theta12[i]*np.log(V_S_star[~idx]/self._Vlin[i]) + self._b[i]*self._n[i]*np.log(V_S_star[~idx]/self._Vlin[i])
        
        return out
        
    def _pea11_constants(self):
        # First period is PGA
        self._period = np.array([0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.075, 0.1,
                                 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1, 1.5,
                                 2, 3, 4, 5, 7.5, 10])
        self._c1 = np.array([ 1.5828,  2.0434,  2.305 ,  1.9848,  1.6854,  1.4517,  1.0698,
                             0.9314,  0.3964, -0.4883, -1.0098, -1.68  , -2.3106, -3.1365,
                             -4.5494, -5.4113, -6.4806, -6.934 , -7.4264, -7.8064, -8.2704,
                             -8.3376, -9.1046])
        self._c2 = np.array([0.2298, 0.1987, 0.1877, 0.2203, 0.2404, 0.2414, 0.2989, 0.3088,
                             0.4317, 0.6278, 0.7401, 0.886 , 1.022 , 1.201 , 1.508 , 1.69  ,
                             1.867 , 1.907 , 1.881 , 1.895 , 1.938 , 1.806 , 1.899 ])
        self._c3 = np.array([-0.03847, -0.03837, -0.03697, -0.03616, -0.03578, -0.03468,
                             -0.03897, -0.03844, -0.04578, -0.05654, -0.06309, -0.07162,
                             -0.07965, -0.09037, -0.1087 , -0.1196 , -0.1282 , -0.1287 ,
                             -0.1205 , -0.1183 , -0.118  , -0.1042 , -0.1076 ])
        self._c4 = np.array([-3.8325, -4.0521, -4.0443, -3.8032, -3.6129, -3.4683, -3.377 ,
                             -3.2926, -3.2112, -3.0304, -2.9959, -2.8894, -2.9265, -2.8823,
                             2.8614, -2.8998, -2.9338, -3.0128, -2.9742, -3.005 , -2.9501,
                             -2.9839, -2.8611])
        self._c5 = np.array([0.3535, 0.3688, 0.3616, 0.3384, 0.3247, 0.3177, 0.318 , 0.3063,
                             0.2937, 0.2673, 0.2623, 0.2481, 0.2515, 0.2456, 0.2424, 0.2465,
                             0.2525, 0.2639, 0.2576, 0.2588, 0.2503, 0.2542, 0.2395])
        self._c6 = np.array([ 0.3321 ,  0.1995 , -0.1222 ,  0.07814,  0.2956 ,  0.5224 ,
                             0.7422 ,  0.7064 ,  0.6084 ,  0.5422 ,  0.4421 ,  0.4869 ,
                             0.4716 ,  0.3333 ,  0.4023 ,  0.3766 ,  0.2633 ,  0.3172 ,
                             0.2585 ,  0.3069 ,  0.3296 ,  0.2879 ,  0.2868 ])
        self._c7 = np.array([-0.09165, -0.08918, -0.09157, -0.1126 , -0.118  , -0.1296 ,
                             -0.1215 , -0.09521, -0.06727, -0.05347, -0.03625, -0.04324,
                             -0.04039, -0.02105, -0.03092, -0.02928, -0.01442, -0.0215 ,
                             -0.0152 , -0.02545, -0.03023, -0.02252, -0.0229 ])
        self._c8 = np.array([-2.5517, -2.5948, -2.9998, -3.3125, -3.332 , -3.2109, -2.6889,
                             -2.209 , -1.6121, -1.3516, -1.2309, -1.149 , -1.0923, -1.0022,
                             -0.975 , -0.947 , -0.9007, -0.8749, -0.8821, -0.8808, -1.0125,
                             -1.1817, -1.3786])
        self._c9 = np.array([0.1831 , 0.1847 , 0.1941 , 0.2017 , 0.1977 , 0.1956 , 0.1723 ,
                             0.1472 , 0.1072 , 0.08784, 0.07733, 0.07056, 0.06554, 0.05519,
                             0.05536, 0.05249, 0.04974, 0.04774, 0.05376, 0.05703, 0.07332,
                             0.09598, 0.1222 ])
        self._c10 = np.array([-4.224e-04, -3.965e-04, -1.707e-04, -5.322e-05, -1.113e-04,
                              -2.669e-04, -6.659e-04, -9.254e-04, -1.077e-03, -1.045e-03,
                              -9.648e-04, -9.049e-04, -7.853e-04, -7.069e-04, -5.685e-04,
                              -4.563e-04, -3.540e-04, -3.025e-04, -2.641e-04, -2.423e-04,
                              -2.002e-04, -1.624e-04, -1.268e-04])
        self._c11 = np.array([6.6521, 7.0645, 7.3314, 7.1183, 6.8113, 6.3705, 6.0817, 6.1621,
                              6.2667, 6.1905, 6.0635, 5.9891, 6.0263, 5.9117, 5.9835, 6.1234,
                              5.9875, 6.1355, 6.0598, 6.2536, 6.3423, 6.5181, 6.5384])
        self._c12 = np.array([-0.02105 , -0.01974 , -0.01974 , -0.02094 , -0.0218  , -0.02244 ,
                              -0.02312 , -0.02259 , -0.02185 , -0.02046 , -0.01933 , -0.01837 ,
                              -0.01683 , -0.01556 , -0.01339 , -0.0118  , -0.0104  , -0.009443,
                              -0.008509, -0.007859, -0.0069  , -0.00724 , -0.007485])
        self._c13 = np.array([0.3778, 0.3688, 0.3691, 0.3817, 0.3914, 0.399 , 0.4108, 0.4102,
                              0.4066, 0.3979, 0.3908, 0.3867, 0.3774, 0.3722, 0.3654, 0.3588,
                              0.3569, 0.3561, 0.354 , 0.3527, 0.3577, 0.373 , 0.3848])
        self._c14 = np.array([0.2791, 0.2792, 0.2796, 0.2838, 0.2874, 0.2905, 0.2976, 0.3007,
                              0.3023, 0.3033, 0.3041, 0.3068, 0.3082, 0.3119, 0.3203, 0.3249,
                              0.3327, 0.3387, 0.3431, 0.3463, 0.358 , 0.371 , 0.381 ])
        self._sigmaReg = np.array([0.021, 0.022, 0.023, 0.022, 0.024, 0.025, 0.025, 0.022, 0.016,
                                   0.014, 0.015, 0.015, 0.017, 0.017, 0.021, 0.022, 0.019, 0.021,
                                   0.024, 0.03 , 0.032, 0.03 , 0.024])
   
    
    def _pea11_one_event_calc(self,M,R_RUP,random,seed):
        '''
        Calculation of spectral acceleration for the 'pea11' model

        Parameters
        ----------
        M : float
            Magnitude of event.
        R_RUP : array
            R_RUP distances for all nodes. (km)
        random : boolean
            Flag to turn on random selection of normal distribution of PGA.
        seed : int
            Seed for random number generator if random is True

        Returns
        -------
        sa: array
            spectral accelerations for every node in g.

        '''
        
        # Calculate the natural log of the acceleration and the standard deviation
        ln_y,sigma_t = self._pea11_ln_y(M,R_RUP)
        
        if random:
            rng = np.random.default_rng(seed)
            # Random normal sampling
            ln_y_r=np.zeros(ln_y.shape)
            for j in range(len(self._period)):
                ln_y_r[j,:] = np.array([rng.normal(ln_y[j,i],sigma_t[j,i]) for i in range(len(ln_y[j,:]))])
            return np.exp(ln_y_r)
        else:
            return np.exp(ln_y)
    
    def _pea11_ln_y(self,M,R_RUP):
        '''
        Equation 4 - natural log of spectral acceleration

        Parameters
        ----------
        M : float
            Magnitude of event.
        R_RUP : array
            R_RUP distances for all nodes. (km)

        Returns
        -------
        ln_y : array
            Natural log of spectral accelerations.
        sigma_t : array
            Standard deviation of spectral accelerations.

        '''
        
        num_periods = len(self._period)
        num_sites = len(R_RUP)
        ln_y = np.zeros((num_periods,num_sites))
        sigma_t = np.zeros((num_periods,num_sites))
        
        for i in range(num_periods):
            # Convert R_RUP to R
            R = np.sqrt(R_RUP**2 + self._c11[i])
            
            term1 = self._c1[i]
            term2 = self._c2[i]*M
            term3 = self._c3[i]*M**2
            term4 = (self._c4[i] + self._c5[i]*M) *  np.minimum(np.log(R),np.log(70))    
    
            min_term = np.minimum(np.log(R/70),np.log(140/70))
            term5 = (self._c6[i] + self._c7[i]*M) * np.maximum(min_term,0)
            term6 = (self._c8[i] + self._c9[i]*M) * np.maximum(np.log(R/140),0)
            term7 = self._c10[i]*R
            
            ln_y[i,:] = term1 + term2 + term3 + term4 + term5 + term6 +term7
            
            if M<=7:
                std_ln_y = self._c12[i]*M + self._c13[i]
            else:
                std_ln_y = (-6.95e-3)*M + self._c14[i]
                
            sigma_t[i,:] = np.sqrt(std_ln_y**2 + self._sigmaReg[i]**2)
        
        return ln_y,sigma_t

    def _calc_factor_of_safety(self):
        '''
        Calculate factor of safety

        Returns
        -------
        None.

        '''
        # Calculate hillslope angle (alpha) in radians
        grad = self.grid.calc_slope_at_node()
        alpha = np.atan(grad)
        # Convert input friction angle to radians
        phi_r = np.radians(self.phi)

        if self.convert_depth_to_thickness:
            # Update thickness
            self._hs[:] = np.cos(alpha)*self.grid.at_node['soil__depth']
        
        if not(self.constant_trans):
            # Update transmissivity
            self._trans[:] = self.Ks*self._hs

        # Calculate dimensionless cohesion
        C_nodim = np.divide(self.C,self._hs*self.rho_r*self.g,where=(self._hs*self.rho_r*self.g)>0,out=np.zeros_like(grad))

        # Density ratio
        r = self.rho_w/self.rho_r

        # Peform relative wetness calculation if turned on
        if self.calc_relative_wetness:
            # Steepest slope is used instead of average patch slope as for alpha
            discharge = self._r * self._area
            if type(self.grid)==RasterModelGrid:
                subsurf_capacity = self._trans * np.sin(np.atan(self._st_slope)) * self.grid.dx
            elif type(self.grid)==HexModelGrid:
                subsurf_capacity = self._trans * np.sin(np.atan(self._st_slope)) * self.grid.spacing
            rw = np.divide(discharge,subsurf_capacity,where=subsurf_capacity>0,out=np.zeros_like(alpha))
            self._rw[:] = np.minimum(rw,1)
            
            if self.route_Q:
                q_subsurface = np.minimum(discharge,subsurf_capacity)
                self._q[:] = discharge - q_subsurface

        # FS_num = C_nodim + np.cos(alpha)*(1-self.w*r)*np.tan(phi_r)
        FS_num = C_nodim + np.cos(alpha)*(1-self._rw*r)*np.tan(phi_r)
        FS = np.divide(FS_num,np.sin(alpha),where=np.sin(alpha)>0,out=np.zeros_like(grad))
        self.grid.at_node['factor_of__safety'] = FS

    
    def _calc_critical_acceleration(self):
        '''
        Calculate critical acceleration using Equation 1 from Jibson, 2007


        Returns
        -------
        None.

        '''
        
        if "factor_of__safety" not in self.grid.at_node:
            raise ValueError('The grid must have a field for "factor_of__safety" to calculate the critical acceleration.')
        
        grad = self.grid.calc_slope_at_node()
        alpha = np.atan(grad)
        
        # This is calculated in units of g, so removing the multiplication by gravitational acceleration from the equation in Jibson, 2007
        self.grid.at_node['critical__acceleration'] = (self.grid.at_node['factor_of__safety']-1) * np.sin(alpha)
    
    def _calc_Newmark_displacements(self):
        """
        Calculate Newmark displacements using Equation 6 from Jibson, 2007


        Returns
        -------
        None.

        """
        
        
        if "peak_ground__acceleration" not in self.grid.at_node:
            raise ValueError('The grid must have a field for "peak_ground__acceleration" to calculate Newmark displacements')
        elif "critical__acceleration" not in self.grid.at_node:
            raise ValueError('the grid must have a field for "critical__acceleration" to calculate Newmark displacements')
            
        pga = self.grid.at_node['peak_ground__acceleration']
        
        # Catch incase PGA is zero anywyere
        ac_amax = np.divide(self.grid.at_node['critical__acceleration'],pga,
                            where=pga>0,out=np.zeros_like(pga))
        # If PGA is 0, this implies a very larger ac / amax, so set these to inf
        ac_amax[pga==0] = np.inf
        
        # The newmark displacement equation is going to be undefined anywhere the ac/amax is greater than 1, 
        # as this effectively implies zero displacement, after the calculation, set any areas with a ac/amax
        # greater than 1 to zero
        term1 = np.power(1-ac_amax,2.341,where=np.logical_and(ac_amax>0,ac_amax<1),out=np.zeros_like(pga))
        term2 = np.power(ac_amax,-1.438,where=np.logical_and(ac_amax>0,ac_amax<1),out=np.zeros_like(pga))
        inner = term1 * term2
        logDN = 0.215 + np.log10(inner, where=inner>0,out=np.zeros_like(pga))
        DN = 10**logDN
        DN[ac_amax>1] = 0
        
        self.grid.at_node['newmark__displacement'] = DN
        self.grid.at_node['acceleration__ratio'] = ac_amax
        
    def _calc_Newmark_displacements_M(self,event_id):
        """
        Calculate Newmark displacement using Equation 7 from Jibson, 2007

        Parameters
        ----------
        M : float
            Magnitude of event.


        Returns
        -------
        None.

        """
        
        if "peak_ground__acceleration" not in self.grid.at_node:
            raise ValueError('The grid must have a field for "peak_ground__acceleration" to calculate Newmark displacements')
        elif "critical__acceleration" not in self.grid.at_node:
            raise ValueError('the grid must have a field for "critical__acceleration" to calculate Newmark displacements')
        
        # Extract magnitude of event
        eidx = self.eq.Events['Event_ID']==event_id
        M = self.eq.Events['Magnitude'][eidx]     
        
        pga = self.grid.at_node['peak_ground__acceleration']
        
        # Catch incase PGA is zero anywyere
        ac_amax = np.divide(self.grid.at_node['critical__acceleration'],pga,where=pga>0,out=np.zeros_like(pga))
        # If PGA is 0, this implies a very larger ac / amax, so set these to inf
        ac_amax[pga==0] = np.inf
        
        # The newmark displacement equation is going to be undefined anywhere the ac/amax is greater than 1, 
        # as this effectively implies zero displacement, after the calculation, set any areas with a ac/amax
        # greater than 1 to zero
        term1 = np.power(1-ac_amax,2.335,where=np.logical_and(ac_amax>0,ac_amax<1),out=np.zeros_like(pga))
        term2 = np.power(ac_amax,-1.478,where=np.logical_and(ac_amax>0,ac_amax<1),out=np.zeros_like(pga))
        inner = term1 * term2
        logDN = -0.2710 + 0.424*M + np.log10(inner, where=inner>0,out=np.zeros_like(pga))
        DN = 10**logDN
        DN[ac_amax>1] = 0
        
        self.grid.at_node['newmark__displacement'] = DN
        self.grid.at_node['acceleration__ratio'] = ac_amax
        # self.grid.at_node['critical__nodes'] = DN>self.min_newmark_disp
        
    def run_one_step(self,dt):
        '''
        Primary method to calculate expected shaking, identify location of landslides
        and route failed material, depending on choices during instantiation.

        Parameters
        ----------
        dt : int
            Time step in years.

        Returns
        -------
        None.

        '''
        
        # Grab the events that occur in this timestep
        eto = self.eq.events_to_occur

        # Check whether landslides will be performed and if not, prepare a basic dictionary for storing the information
        if self.store_event_details:
            self.EventDetails = {'Event_ID':[],
                                 'Factor_of_Safety':[],
                                 'Peak_Ground_Acceleration':[],
                                 'Critical_Acceleration':[],
                                 'Acceleration_Ratio':[],
                                 'Newmark_Displacement':[]
                                }
            if self.store_spectral_accelerations:
                if self._gmpe_model=='cy08':
                    self.EventDetails['Peak_Ground_Velocity']=[]
                    for i in range(len(self._period)-2):
                        nm = str(self._period[i+2])+'_Spectral_Acceleration'
                        self.EventDetails[nm] = []
                if self._gmpe_model=='aea16':
                    for i in range(len(self._period)-1):
                        nm = str(self._period[i+1])+'_Spectral_Acceleration'
                        self.EventDetails[nm] = []
                if self._gmpe_model=='pea11':
                    for i in range(len(self._period)-1):
                        nm = str(self._period[i+1])+'_Spectral_Acceleration'
                        self.EventDetails[nm] = []
                    

        for i in range(len(eto)):
            # Check to see if event magnitude exceeds minimum, if defined
            Mw = self.eq.Events['Magnitude'][self.eq.Events['Event_ID']==eto[i]]
            if (Mw>=self.Mw_min) | (self.Mw_min==None):
                # Calculate peak ground acceleration
                self._calc_pga(eto[i])
                # Calculate factor of saftey
                self._calc_factor_of_safety()
                # Calculate critical acceleration
                self._calc_critical_acceleration()
                if self.use_magnitude:
                    self._calc_Newmark_displacements_M(eto[i])
                else:
                    self._calc_Newmark_displacements()
                
                if self.perform_landslides:
                    # Adapt from BedrockLandslider to only consider downstream most node that exceeds
                    # the minimum newmark displacement
                    sliding_nodes = self.grid.at_node['newmark__displacement'] > self.min_newmark_disp
                    ix = np.unique(self.grid.at_node["flow__receiver_node"][np.where(sliding_nodes)])
                    # Remove any nodes that are on the boundary
                    ix = ix[~self.grid.node_is_boundary(ix)]
                        
                    if ix.shape[0]>0:
                        # Set as critical nodes within the internal bedrock landslider 
                        # instance
                        self.ix = ix
                        self.hy._critical_sliding_nodes=ix
                        # Run
                        self.hy.run_one_step(dt)

                        if self.include_landslide_locations:
                            # Determine the nodes from which landslides are sourced and where they runout to
                            ls_src_nodes = self.grid.nodes.ravel()[self.grid.at_node['landslide__erosion']>0]
                            ls_rnt_nodes = self.grid.nodes.ravel()[self.grid.at_node['landslide__deposition']>0]
                            ls_ero = self.grid.at_node['landslide__erosion'][ls_src_nodes]
                            ls_dep = self.grid.at_node['landslide__deposition'][ls_rnt_nodes]

                        # Generate an empty dictionary for storage if initiated
                        if self.store_LS_dict:
                            self.Landslides['Event_ID'].append(eto[i])
                            self.Landslides['Magnitude'].append(Mw)
                            self.Landslides['Critical_Nodes'].append(ix)
                            self.Landslides['Areas'].append(np.array(self.hy.landslides_size) * self.grid.dx**2)
                            self.Landslides['Volumes'].append(self.hy.landslides_volume)
                            self.Landslides['Sed_Volumes'].append(self.hy.landslides_volume_sed)

                            if self.include_landslide_locations:
                                self.Landslides['Landslide_Source_Nodes'].append(ls_src_nodes)
                                self.Landslides['Landslide_Runout_Nodes'].append(ls_rnt_nodes)
                                self.Landslides['Landslide_Erosion'].append(ls_ero)
                                self.Landslides['Landslide_Deposition'].append(ls_dep)

                if self.store_event_details:
                    # Store outputs in dictionary
                    self.EventDetails['Event_ID'].append(eto[i])
                    self.EventDetails['Factor_of_Safety'].append(self.grid.at_node['factor_of__safety'])
                    self.EventDetails['Peak_Ground_Acceleration'].append(self.grid.at_node['peak_ground__acceleration'])
                    self.EventDetails['Critical_Acceleration'].append(self.grid.at_node['critical__acceleration'])
                    self.EventDetails['Acceleration_Ratio'].append(self.grid.at_node['acceleration__ratio'])
                    self.EventDetails['Newmark_Displacement'].append(self.grid.at_node['newmark__displacement'])
                    if self.store_spectral_accelerations:
                        if self._gmpe_model=='cy08':
                            self.EventDetails['Peak_Ground_Velocity'].append(self.grid.at_node['peak_ground__velocity'])
                            for i in range(len(self._period)-2):
                                nm = str(self._period[i+2])+'_Spectral_Acceleration'
                                nmg = str(self._period[i+2])+'_spectral__acceleration'
                                self.EventDetails[nm].append(self.grid.at_node[nmg])
                        if self._gmpe_model=='aea16':
                            for i in range(len(self._period)-1):
                                nm = str(self._period[i+1])+'_Spectral_Acceleration'
                                nmg = str(self._period[i+1])+'_spectral__acceleration'
                                self.EventDetails[nm].append(self.grid.at_node[nmg])
                        if self._gmpe_model=='pea11':
                            for i in range(len(self._period)-1):
                                nm = str(self._period[i+1])+'_Spectral_Acceleration'
                                nmg = str(self._period[i+1])+'_spectral__acceleration'
                                self.EventDetails[nm].append(self.grid.at_node[nmg])

                
        # Run non-seismogenic landslides if turned on
        if self.allow_non_seismogenic_LS:
            self.hy._critical_sliding_nodes=None
            self.hy.run_one_step(dt)
 
            
            
                
                
            

        
        
        
        
        
        
        
        
        







   
        