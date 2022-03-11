import nslsii

BEAMLINE_ID = 'fmx'

# nslsii.configure_base(get_ipython().user_ns, BEAMLINE_ID)
nslsii.configure_base(get_ipython().user_ns, BEAMLINE_ID, pbar=False) # Progress bar for scans

# Disable plots via BestEffortCallback:
bec.disable_plots()

from pathlib import Path

import appdirs

from bluesky.utils import PersistentDict

# runengine_metadata_dir = appdirs.user_data_dir(appname="bluesky") / Path("runengine-metadata")
runengine_metadata_dir = Path(f"/GPFS/CENTRAL/xf17id1/skinnerProjectsBackup/bnlpx_config/{BEAMLINE_ID}_bluesky_config/")

# PersistentDict will create the directory if it does not exist
RE.md = PersistentDict(runengine_metadata_dir)
