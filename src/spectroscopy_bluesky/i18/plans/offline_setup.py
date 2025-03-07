print("Running 'prepfunctions.py'")

import os

def set_server_port(port=6064) :
    print("Setting Epics CA server port to : %s" % (str(port)))
    os.environ['EPICS_CA_SERVER_PORT'] = str(port)

def create_runengine() :
    "Create new Bluesky RunEngine and subscribe to 'best effort' callbacks"
    return create_runengine_plot()[0]

def create_runengine_plot() :
    "Create new Bluesky RunEngine and subscribe to 'best effort' callbacks"
    print("Setting up Bluesky RunEngine and 'best effort' callbacks")
    # Create the RunEngioe
    from bluesky import RunEngine

    RE = RunEngine({})

    from bluesky.callbacks.best_effort import BestEffortCallback
    bec = BestEffortCallback()

    # Send all metadata/data captured to the BestEffortCallback.
    RE.subscribe(bec)

    return RE, bec
def add_databroker(run_engine) :
    "Subscribe a Bluesky RunEngine to temporary databroker"
    print("Subscribing Runengine to temporary databroker")
    from databroker import Broker
    db = Broker.named('temp')

    # Insert all metadata/data captured into db.
    run_engine.subscribe(db.insert)

    return db

#print("Importing dummy devices (det, motor 1 and 2)")
#from ophyd.sim import det1, det2, motor1, motor2