import epics
import numpy as np
import time
import socket

#import bluesky.preprocessors as bpp
#import bluesky.plans as bp
#import bluesky.plan_stubs as bps
#import pandas as pd


def help_fmx():
    """List FMX beamline functions with a short explanation"""
    
    print("""
    FMX beamline functions:
    
    beam_center_align()     - Align goniometer and LSDC beam center to current beam position
    center_pin()    - Center an alignment pin in Y
    dcm_rock()      - Scan DCM crystal 2 pitch to maximize flux on BPM1
    fmx_dose()      - Caluclate dose for a set of LSDC settings
    fmx_beamline_reference()    - Print beamline reference values
    fmx_flux_reference()    - Get flux reference for a list of Slit 1 gap settings
    fmx_expTime_to_10MGy()  - Caluclate experiment time that delivers a dose of 10 MGy
    focus_scan()    - Take microscope images with changing focus
    get_energy()    - Return HDCM energy in eV
    get_fluxKeithley()  - Returns Keithley diode current derived flux
    ivu_gap_scan()  - Scan IVU21 gap against a BPM intensity signal and go to peak
    mirror_scan()   - Pencil beam scan of HFM and KB
    rd3d_calc()     - Dose estimate with RADDOSE3D
    set_beamsize()  - CRL setting to expand beam
    set_energy()    - Set undulator, HDCM, HFM and KB settings for a certain energy
    setE()          - Set all optics settings and align beam center for a certain energy
    set_fluxBeam()  - Sets the flux reference field
    set_influence() - Set HV power supply influence function voltage step
    simple_ascan()  - Scan a motor against a detector
    wire_scan()     - Scan a Cr nanowire and plot Cr XRF signal to determine beam size
    xf_bragg2e()    - Returns Energy in eV for given Bragg angle t in deg or rad
    xf_e2bragg()    - Returns Bragg angle t in deg for given Energy in eV
    xf_detZ2recResolution() - Given detector to sample distance, returns resolution at edge
    xf_recResolution2detZ() - Given resolution at edge, returns detector to sample distance

    Use help() to get more info, e.g. help(setE)
    """)
    
    return


def blStrGet():
    """
    Return beamline string
    
    blStr: 'AMX' or 'FMX'
    
    Beamline is determined by querying hostname
    """
    hostStr = socket.gethostname()
    if hostStr == 'xf17id1-ca1':
        blStr = 'FMX'
    elif hostStr == 'xf17id2-ca1':
        blStr = 'AMX'
    else: 
        print('Error - this code must be executed on one of the -ca1 machines')
        blStr = -1
        
    return blStr


def get_energy():
    """
    Returns the current photon energy in eV derived from the DCM Bragg angle
    """ 
    return hdcm.e.user_readback.get()


# Beam align functions

def detectorCoverClose():
    """
    Closes the Detector Cover
    """
    yield from bps.mv(cover_detector.close, 1)
    
    while cover_detector.status.get() == 1:
        #print(cover_detector.status.get())
        time.sleep(0.5)
    
    return

def detectorCoverOpen():
    """
    Opens the Detector Cover
    """
    yield from bps.mv(cover_detector.open, 1)
    
    while cover_detector.status.get() != 1:
        #print(cover_detector.status.get())
        time.sleep(0.5)
    
    return


def transDefaultGet(energy):
    """
    Returns the default transmission to avoid saturation of the scintillator
    
    energy: X-ray energy [eV]
    
    The look up table is set in settings/set_energy setup FMX.ipynb
    """
    
    # This reads from:
    # XF:17ID-ES:FMX{Misc-LUT:atten}X-Wfm
    # XF:17ID-ES:FMX{Misc-LUT:atten}Y-Wfm
    # 
    # atten is a dummy motor just for this purpose.
    # To be replaced by trans_bcu and corresponding new PVs
    
    transLUT = read_lut('atten')
    transDefault = np.interp(energy,transLUT['Energy'],transLUT['Position'])
    
    return transDefault


# TODO: This is a plan. not macro - sort somewhere else?
def trans_set(transmission, trans = trans_bcu):
    """
    Sets the Attenuator transmission
    """
    
    e_dcm = get_energy()
    if e_dcm < 5000 or e_dcm > 30000:
        print('Monochromator energy out of range. Must be within 5000 - 30000 eV. Exiting.')
        return
    
    yield from bps.mv(trans.energy, e_dcm) # This energy PV is only used for debugging
    yield from bps.mv(trans.transmission, transmission)
    yield from bps.mv(trans.set_trans, 1)
    
    if trans == trans_bcu:
        while atten_bcu.done != 1:
            time.sleep(0.5)
    
    print('Attenuator = ' + trans.name + ', Transmission set to %.3f' % trans.transmission.value)
    return


def trans_get(trans = trans_bcu):
    """
    Returns the Attenuator transmission
    """
    
    transmission = trans.transmission.get()
    
    print('Attenuator = ' + trans.name + ', Transmission = %.3f' % transmission)
    return transmission


def get_fluxKeithley():
    """
    Returns Keithley diode current derived flux.
    """
    
    keithFlux = epics.caget('XF:17IDA-OP:FMX{Mono:DCM-dflux}')
    
    return keithFlux


def set_fluxBeam(flux):
    """
    Sets the flux reference field.
    
    flux: Beamline flux at sample position for transmisison T = 1.  [ph/s]
    """
    
    error = epics.caput('XF:17IDA-OP:FMX{Mono:DCM-dflux-M}', flux)
    
    return error


def set_beamsize(sizeV, sizeH):
    """
    Sets Compound Refractive Lenses (CRL) to defocus the beam
    
    sizeV: Vertical expansion
      'V0' no expansion
      'V1': 1 V CRL, for a V beam size of ~10um
      
    sizeH: Horizontal expansion
      'H0': no expansion
      'H1': 2 H CRLs, for a H beam size of ~10um
    
    Examples
    set_beamsize('V1','H1')
    set_beamsize('V1','H0')
    """
    
    if get_energy()<9000.0:
        print('Warning: For energies < 9 keV, use KB mirrors to defocus, not CRLs')
    
    if sizeV == 'V0':
        yield from bps.mv(transfocator.vs.mv_out, 1)
        yield from bps.mv(transfocator.v2a.mv_out, 1)
        yield from bps.mv(transfocator.v1a.mv_out, 1)
        yield from bps.mv(transfocator.v1b.mv_out, 1)
    elif sizeV == 'V1':
        yield from bps.mv(transfocator.vs.mv_in, 1)
        yield from bps.mv(transfocator.v2a.mv_out, 1)
        yield from bps.mv(transfocator.v1a.mv_out, 1)
        yield from bps.mv(transfocator.v1b.mv_in, 1)
    else:
        print("Error: Vertical size argument has to be \'V0\' or  \'V1\'")
    
    if sizeH == 'H0':
        yield from bps.mv(transfocator.h4a.mv_out, 1)
        yield from bps.mv(transfocator.h2a.mv_out, 1)
        yield from bps.mv(transfocator.h1a.mv_out, 1)
        yield from bps.mv(transfocator.h1b.mv_out, 1)
    elif sizeH == 'H1':
        yield from bps.mv(transfocator.h4a.mv_out, 1)
        yield from bps.mv(transfocator.h2a.mv_in, 1)
        yield from bps.mv(transfocator.h1a.mv_in, 1)
        yield from bps.mv(transfocator.h1b.mv_in, 1)
    else:
        print("Error: Horizontal size argument has to be \'H0\' or  \'H1\'")
    
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
    
    d0 = 2*5.43102*(1-2.4e-4*LN)/np.sqrt(h^2+k^2+l^2)
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
    
    d0 = 2*5.43102/np.sqrt(h^2+k^2+l^2)
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
