class DefinedCallback:
    def listen_to_events(self):
        pass
        # todo add what kind of event are those listening, and which are filtered out
        # extract data from each event
        # define what computation happens afeter all events arrive - or per each.
        # If event driven might send back on some websocket maybe?
        # define a pure function taking the growing array of results, and stream the outputs
        # take curve_fit from the scikit and also use the Bounds class
        # reads those values from stomp
