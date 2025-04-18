import epics
import numpy as np
import matplotlib.pyplot as plt
import time
from lmfit import Model

#import bluesky.preprocessors as bpp
#import bluesky.plans as bp
#import bluesky.plan_stubs as bps
#import pandas as pd


def help_fmx():
    """List FMX beamline functions with a short explanation"""
    
    print("""
    FMX beamline functions:
    
    anneal()        - Transitions Governor from SA to CB state and inserts annealer
    beam_center_align() - Align goniometer and LSDC beam center to current beam position
    dcm_rock()      - Scan DCM crystal 2 pitch to maximize flux on BPM1
    fmx_dose()      - Caluclate dose for a set of LSDC settings
    fmx_reference() - Get flux for a list of Slit 1 gap settings and print beamline reference values
    fmx_expTime_to_10MGy()  - Caluclate experiment time that delivers a dose of 10 MGy
    focus_scan()    - Take microscope images with changing focus
    get_energy()    - Return HDCM energy in eV
    get_fluxKeithley()  - Returns Keithley diode current derived flux
    ivu_gap_scan()  - Scan IVU21 gap against a BPM intensity signal and go to peak
    mirror_scan()   - Pencil beam scan of HFM and KB
    rd3d_calc()     - Dose estimate with RADDOSE3D (fmx_dose() has less variables but easier to use)
    set_beamsize()  - CRL setting to expand beam
    setE()          - Set all optics settings and align beam center for a certain energy
    set_fluxBeam()  - Sets the flux reference field
    set_influence() - Set HV power supply influence function voltage step
    simple_ascan()  - Scan a motor against a detector
    wire_scan()     - Scan a Cr nanowire and plot Cr XRF signal to determine beam size
    xf_bragg2e()    - Returns Energy in eV for given Bragg angle t in deg or rad
    xf_e2bragg()    - Returns Bragg angle t in deg for given Energy in eV
    xf_detZ2recResolution() - Given detector to sample distance, returns resolution at edge
    xf_recResolution2detZ() - Given resolution at edge, returns detector to sample distance
    xrf_spectrum_acquire()  - Acquire an X-ray Fluorescence spectrum from the XIA Mercury MCA
    xrf_spectrum_collect()  - Collect an X-ray Fluorescence spectrum from the XIA Mercury MCA
    xrf_spectrum_read() - Read the current XIA Mercury spectrum from the MCA ophyd object
    xrf_spectrum_plot() - Plot a XIA Mercury XRF spectrum

    Use help() to get more info, e.g. help(setE)
    """)
    
    return


def anneal(t=1.0):
    """
    Transitions Governor from SA to CB state and inserts annealer
    
    Requirements
    ------------
    * Governor in SA state
    
    Parameters
    ----------
    t: Time to insert annealer paddle. default = 1.0 [s]
              
    Examples
    --------
    anneal()
    anneal(t=5)
    
    """
    if not govStatusGet('SA'):
        print('Not in Governor state SA, exiting')
        return -1
    
    govStateSet('CB')
    
    annealer.air.put(1)
    
    while not annealer.inStatus.get():
        #print(annealer.inStatus.get())
        time.sleep(0.1)
    
    time.sleep(t)
    annealer.air.put(0)
    
    while not annealer.outStatus.get():
        #print(annealer.outStatus.get())
        time.sleep(0.1)
    
    govStateSet('SA')
    
    return

def set_influence(electrode, bimorph, bank):
    """
    Step up/down bimorph mirror electrodes for influence function measurements.
    
    The routine decreases the (electrode-1) electrode by the step size set for the bank,
    then increases the chosen electrode by the step size. Step size has to be set through the 
    PS web server interface or the IOC.
    
    Interface to Spellman HV power supply.
    
    electrode: Electrode number
    
    bimorph: Power supply, allowed values are ('hfm', 'kb')
    
    bank: Voltage bank, 1 for HFM and VKB, 2 for HKB
    
    Examples:
    for i in range(16):
        set_influence(i, 'kb', 1)
        set_influence(i, 'kb', 1)
        RE(mirror_scan('kbv', -1000, 1000, 400, camera=cam_8))
        db[-1].table().to_csv('/tmp/20190319_1544_vkb_pitch_2538urad_infl20190319_{0:0{width}}.csv'.format(i, width=2))
    
    for i in range(16,32):
        set_influence(i, 'kb', 2)
        set_influence(i, 'kb', 2)
        RE(mirror_scan('kbh', -700, 700, 400, camera=cam_8))
        db[-1].table().to_csv('/tmp/20190319_1753_hkb_2390urad_infl20190319_{}.csv'.format(i))
    
    """
    allowed_bimorphs = ('hfm', 'kb')
    
    if bimorph not in allowed_bimorphs:
        print("bimorph should be one of", allowed_bimorphs)
        return    
    
    if electrode < 0 or electrode > 31:
        print("electrode must be between 0 and 31")
        return
    
    if bimorph == 'hfm':
        prefix = 'XF:17IDA-OP:FMX{Mir:HFM-PS}:'
    elif bimorph == 'kb':
        prefix = 'XF:17IDC-OP:FMX{Mir:KB-PS}:'
        
    bank_pv = epics.PV(prefix+'BANK_NO_32')
    incr_pv = epics.PV(prefix+'INCR_U_CMD.A')
    decr_pv = epics.PV(prefix+'DECR_U_CMD.A')        
    step_pv = epics.PV(prefix + 'U_STEP_MON.A')
    demand_pvs = [epics.PV(prefix + 'U{}_CURRENT_MON'.format(i)) for i in range((bank-1)*16, bank*16)]
    
    bank_pv.put(bank-1, wait=True)
    time.sleep(0.5)
    step = step_pv.get()
    demands = [pv.get() for pv in demand_pvs]
    new_demands = demands[:]
    
    i = electrode if electrode < 16 else electrode-16
    if i > 0:
        new_demands[i - 1] -= step
    new_demands[i] += step
    
    for diff in np.diff(np.array(new_demands)):
        if abs(diff) > 500:
            print("got difference between values larger than 500")
            return
    
    if i > 0:
        print("decrementing electrode", electrode - 1, "by", step)
        decr_pv.put(electrode - 1)
    print("incrementing electrode", electrode, "by", step)
    incr_pv.put(electrode)
    

# X-ray utility functions

def xf_bragg2e(t, h=1, k=1, l=1, LN=0):
    """
    Returns Energy in eV for given Bragg angle t in deg or rad
     
    t: Bragg angle [deg or rad]
    h,k,l: Miller indices of Si crystal (optional). Default h=k=l=1
    LN: Set to 1 for 1st xtal cooled and 2nd xtal RT. Default 0
    
    Python version of IDL a2e.pro c/o Clemens Schulze Briese
    """
    
    if LN: LN=1
    tt = t*np.pi/180 if t > 1 else t
    
    d0 = 2*5.43102*(1-2.4e-4*LN)/np.sqrt(h**2+k**2+l**2)
    E = 12398.42/(d0*np.sin(tt))
    
    return E


def xf_e2bragg(E, h=1, k=1, l=1):
    """
    Returns Bragg angle t in deg for given Energy in eV
    
    E: Energy in eV. If E<100, assume it's keV and convert.
    h,k,l: Miller indices of Si crystal optional
    
    Python version of IDL angle.pro c/o Clemens Schulze Briese
    """
    
    if E<100: E=E*1e3
    
    d0 = 2*5.43102/np.sqrt(h**2+k**2+l**2)
    t = np.arcsin(12398.42/d0/E) * 180/np.pi;
    
    return t


def xf_detZ2recResolution(detZ, xLambda, D=327.8):
    """
    Given detector to sample distance detZ, returns resolution at edge recResolution
    http://www.xray.bioc.cam.ac.uk/xray_resources/distance-calc/calc.php
    
    detZ: crystal to detector distance [mm]
    D: diameter of detector [mm].
       Default 327.8 mm for Eiger 16M height if not specified
    xLambda: X-ray wavelength [Ang]
    recResolution: recordable resolution [Ang]
    """
    
    recResolution = xLambda/(2*np.sin(0.5*np.arctan(0.5*D/detZ)))
    
    return recResolution


def xf_recResolution2detZ(recResolution, xLambda, D=327.8):
    """
    Given resolution at edge recResolution, returns detector to sample distance detZ
    http://www.xray.bioc.cam.ac.uk/xray_resources/distance-calc/calc.php
    
    detZ: crystal to detector distance [mm]
    D: diameter of detector [mm].
       Default 327.8 mm for Eiger 16M height if not specified
    xLambda: X-ray wavelength [Ang]
    recResolution: recordable resolution [Ang]
    """
    
    detZ = 0.5*D/np.tan(2*np.arcsin(xLambda/(2*recResolution)))
    
    return detZ  


def beam_center_fit(dz, orgX, orgY):
    """
    Fit beam center to line
    
    Parameters
    ----------
    dz : detectors distance [mm]
    orgX : Beam center X coordinate [px]
    orgY : Beam center Y coordinate [px]
    
    Example
    -------
    dz=[150, 300, 450]
    orgX=[2002,2001,2001]
    orgY=[2251,2241,2232]
    beam_center_fit(dz, orgX, orgY)
    """
    
    def linear(x, m, b):
        """Line: linear(x, m, b) = m*x + b"""
        return (m*x + b)
    
    gmodel = Model(linear)
    
    print('orgX')
    orgXresult = gmodel.fit(orgX, x=dz, m=-0.005, b=2000)
    display(orgXresult.params)
    plt.figure(1)
    orgXresult.plot_fit(xlabel='dz [mm]', ylabel='orgX [px]')
    plt.show()
    
    print('orgY')
    orgYresult = gmodel.fit(orgY, x=dz, m=-0.05, b=2250)
    display(orgYresult.params)
    plt.figure(2)
    orgYresult.plot_fit(xlabel='dz [mm]', ylabel='orgY [px]')
    plt.show()
    