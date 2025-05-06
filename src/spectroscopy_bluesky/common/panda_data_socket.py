import socket
import re
from threading import Thread
"""
Class to connect to TCP data socket of Panda and cache the frames of data.
Data connection is established using ASCII format, received data is parsed to
separate the lines of data from the header information.
See : https://pandablocks.github.io/PandABlocks-server/master/capture.html
"""
class DataSocket :
    def __init__(self, host, port) :
        self.host = host
        self.port = port
        self.all_data = []
        self.data_start_index = 0
        self.data_end_index = 0
        self.socket = None

    def connect(self) :
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        print("Connecting")
        self.socket.connect((self.host, self.port))
        print("Connected")
        self.socket.sendall(b"ASCII\n") # don't forget the newline!
        data = self.socket.recv(1024)
        print("Server response {}".format(data))

    def collect_data_in_thread(self) :
        def collect_safe() :
            try :
                self.collect_data()
            except :
                print("Caught exception")

        t = Thread(target=collect_safe)
        t.start()

    def collect_data(self) :
        self.all_data = []
        data = b"\n"
        while len(data)>0 and not data.startswith(b"END") :
            data = self.socket.recv(1024)
            data_string = data.decode()
            print(len(data_string), data)
            if len(data_string) > 0 :
                ## remove the final \n (received data ends with 1 newline, fields ends with 2)
                data_string = data_string[:-1] 

                # split on whitespace
                split_string = re.split("[\n]+", data_string)

                self.all_data.extend(split_string)
        print("Finished. Final data : {}".format(data))

    def parse_data(self) :
        self.data_start_index = 0
        self.data_end_index = 0
        self.data_field_names = []

        # read and store the field names, set the data start index. 
        if "fields:" in self.all_data :
            ind = self.all_data.index("fields:") + 1
            field_names = []
            while len(self.all_data[ind]) > 0 :
                self.data_field_names.append(self.all_data[ind].strip().split()[0])
                ind += 1

            # the start index of the data lines is after the empty line following the field names
            self.data_start_index = ind+1
        
        # set the end index of the data
        if self.data_start_index > 0 :
            # find index of line that starts with 'END' (i.e. end of data block)
            end_index = [panda_socket.all_data.index(val) for val in panda_socket.all_data if val.startswith("END")]
            if len(end_index) == 1 :
                self.data_end_index = end_index[0]
            else : 
                self.data_end_index = len(self.all_data)

    def get_num_frames(self) :
        self.parse_data()
        return self.data_end_index - self.data_start_index

    # frame number is zero indexed
    def get_frame(self, frame_index) :
        num_frames = self.get_num_frames()
        if frame_index < 0 or frame_index >= num_frames :
            raise IndexError("Invalid frame index {} - only index values 0...{} are allowed".format(frame_index, num_frames-1))
        
        frame_index = self.data_start_index + frame_index
        if frame_index >= 0 and frame_index < len(self.all_data) :
            return self.all_data[frame_index]
        
panda_socket = DataSocket("bl20j-ts-panda-02", 8889)
panda_socket.connect()

