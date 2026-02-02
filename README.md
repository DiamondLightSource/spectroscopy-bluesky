[![CI](https://github.com/DiamondLightSource/spectroscopy-bluesky/actions/workflows/ci.yml/badge.svg)](https://github.com/DiamondLightSource/spectroscopy-bluesky/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/DiamondLightSource/spectroscopy-bluesky/branch/main/graph/badge.svg)](https://codecov.io/gh/DiamondLightSource/spectroscopy-bluesky)
[![PyPI](https://img.shields.io/pypi/v/spectroscopy-bluesky.svg)](https://pypi.org/project/spectroscopy-bluesky)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

# spectroscopy_bluesky

Plans to use at spectroscopy beamlines at DLS

Currently the `scan_runner` tool is available to run some tests scans in p51's turbo slits.

In order to run the scans you'll first need to install the repository into a virtual environment:

```bash
python -m venv venv
sourve venv/bin/activate
pip install --upgrade pip
pip install -e .
```

It's important to remember that due to network isolation, in order to run the scans you'll need to access a machine that's currently connected to p51's network. This can be done by:

```bash
ssh p51-ws002
```

if you already have the environment installed you can just source otherwise you'll need to install it (steps above).

Once the module has been installed and you have access to the network you can run the `scan_runner` tool by typing:

```bash
./scan_runner --help
```

This will give you an overview of all the available scans, like this:

```bash
│ case-2         Run an "energy" scan with constant speed on the motor and SeqTable. Steps are not linearly spaced. But time between them is always equal to 1us. │
│ case-1         Run a trajectory scan using the sequencer table as a trigger source and a trajectory on the PMAC. Constant speed and step size.                                            │
│ case-1-pcomp   Run a trajectory scan using the PCOMP block as trigger source and a trajectory on the PMAC. Constant speed and step size.                                                  │
│ fly-scan       Run a scan using the PCOMP block as trigger source.                                                                                                                        │
```

each case can be expanded to give more information by doing:
```bash
./scan_runner case-1 --help
```

Which will print this:

```bash
 Usage: scan_runner.py case-1 [OPTIONS]                                                                                                                                                      
                                                                                                                                                                                             
 Run a trajectory scan using the sequencer table as a trigger source and a trajectory on the PMAC. Constant speed and step size.                                                             
                                                                                                                                                                                             
 Currently only supports one sequencer table with 4096 points.                                                                                                                               
 This scan requires the `seq_table` design to be loaded in the Panda.                                                                                                                        
                                                                                                                                                                                             
╭─ Options ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --start           FLOAT    Starting position/energy of the scan [default: 0.0]                                                                                                            │
│ --stop            FLOAT    Ending position/energy of the scan [default: 10.0]                                                                                                             │
│ --num             INTEGER  Number of points of the scan [default: 100]                                                                                                                    │
│ --duration        FLOAT    Duration of the acquisition starting on the rising edge of a trigger [default: 0.01]                                                                           │
│ --sweeps          INTEGER  Number of sweeps [default: 1]                                                                                                                                  │
│ --help                     Show this message and exit.                                                                                                                                    │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```
