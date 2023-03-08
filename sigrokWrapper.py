"""Wrap sigrok python API 

   * sigrok-py hangs Python session if sr.Context created more than
     once --> use class leven persistent state 'context'

   * sigrok-py complains if device open/close state not managet
     correctly && make it easier to make several actions on device -->
     add support for python with statement (__enter__, __exit__ -methods)

   * key-names must be converted to sigrok internal representation -->
     hide this mapping

   * wrap error in exceptions to document error context (and to help
     user to solve the problem)


   * add support for some Python constructs:
     * manage device open/close state to support Python with -statement
     * drivers/device documentation string 

   * provide utilites for parsing datacquisition callback (WORK IN PROGRESS)

   * expose Sigrok Python API (i.e. no need to use import sigrok.core as sr)

"""

import sigrok.core as sr
import sys
import time
from datetime import datetime
import logging

class Device:
      """Responsibilities: 

      1) Manage device 'open' state
      2) Map keyName to internal key-id in getter&setter
      3) Get and set functions
      4) __str__ support for the device

      """

      # ------------------------------------------------------------------
      # Constructor
      def __init__( self, device):
        self.device = device     # sigrok device 
        self.isOpen = False      # we are managing device state, initially 'Closed'

      # Warning 'key.name' returned cannot be used for a keyName
      # use sigrok-cli to find key names. For exampe, for the demo device
      #
      # sigrok-cli --driver=demo --show

      def config_keys( self, channel_group=None ):
           if not channel_group is None:
               try:
                   configObject = self.device.channel_groups[channel_group]
               except KeyError as err:
                   raise KeyError(f"Invalid channel_group '{channel_group}'. Expect one of {[ k for k,v in self.device.channel_groups.items()]}") from err
           else:
                configObject = self.device
           config_key_names = [ key.name for key in configObject.config_keys() ]
           return config_key_names

      def channel_groups( self ):
           channel_group_names = [ gr for gr in self.device.channel_groups ]
           return channel_group_names

      def channels( self ):
           channel_names = [ ch.name for ch in self.device.channels ]
           return channel_names

      # Device getters and setters
      def get(self, keyName, channel_group=None):
        """
	:channel_group: access 'keyName' on channel_group if given
	"""
        logging.info( f"get: keyName={keyName}, channel_group={channel_group}")
        if self.isOpen:
           if not channel_group is None:
               try:
                   channel_group_obj = self.device.channel_groups[channel_group]
               except KeyError as err:
                   raise KeyError(f"Invalid channel_group '{channel_group}'. Expect one of {[ k for k,v in self.device.channel_groups.items()]}") from err
               return self.getConfigObject( keyName=keyName, configObject=channel_group_obj)
           else:
               return self.getConfigObject( keyName=keyName, configObject=self.device)
        else:
            print( f"Device {self} not open", file=sys.stderr)
            return None


      def set(self, keyName, value, channel_group=None):
        """Set 'keyName' to 'value' on device or  on 'channel_group'
       
	:channel_group: access 'keyName' on channel_group if given

	"""
        logging.info( f"set: keyName={keyName}, value={value}, channel_group={channel_group}")
        if self.isOpen:
           if not channel_group is None:
               try:
                   channel_group_obj = self.device.channel_groups[channel_group]
               except KeyError as err:
                   raise KeyError(f"Invalid channel_group '{channel_group}'. Expect one of {[ k for k,v in self.device.channel_groups.items()]}") from err
               return self.setConfigObject( keyName=keyName, value=value, configObject=channel_group_obj)
           else:
               return self.setConfigObject( keyName=keyName, value=value, configObject=self.device)
        else:
            print( f"Device {self} not open - nothin done", file=sys.stderr)
            return None

      def getConfigObject(self, keyName, configObject):
           """
           :configObject: sigrok.Configurable (i.e. Device, Channel_Group etc)
           """
           try:
              key = self.keyName2key(keyName)
           except ValueError as err:
              valid_key_names = [ key.name for key in configObject.config_keys() ]
              raise ValueError( f"Invalid key '{keyName}'. Expect one of: {valid_key_names}") from err 

           try:
              value = configObject.config_get(key)
           except ValueError as err:
              valid_key_names = [ key.name for key in configObject.config_keys() ]
              raise ValueError( f"Error reading '{keyName}'. Expect one of: {valid_key_names}") from err 

            
           return value

      def setConfigObject(self, keyName, value, configObject):
            try:
              key = self.keyName2key(keyName)
            except ValueError as err:
              valid_key_names = [ key.name for key in configObject.config_keys() ]
              raise ValueError( f"Invalid key '{keyName}'. Expect one of: {valid_key_names}") from err 

            try:
               # print( f"settign {value}[{type(value)}]")
               ret = configObject.config_set(key,value)
            except Exception as err:
              capabilities = configObject.config_capabilities(key)
              print( f"{keyName}[{key}], capabilities={capabilities}, listable: {sr.Capability.LIST in capabilities:}")
              try:
                   # Not possible to peek for value
                   if sr.Capability.LIST in capabilities:
                        valid_values = f" Valid values={ configObject.config_list(key) }"
                        # valid_values = f" Valid values={ [str(v)+type(v) for v in configObject.config_list(key)]}"
                   else: 
                        valid_values = ""
              except:
                   valid_values = "exception in valid values"

              raise Exception( f"Error in setting '{keyName}' to value {value}[{type(value)}].{valid_values}") from err 

            return  ret

      @staticmethod
      def keyName2key(keyName):
        """Map 'keyName' to key sigrok identifier"""
        key = sr.ConfigKey.get_by_identifier(keyName)
        return key

      # ------------------------------------------------------------------
      # Open close
      def open(self):
         if not self.isOpen: 
            self.isOpen = True
            self.device.open()
         return self

      def close(self):
         if self.isOpen: 
            self.isOpen = False
            self.device.close()

      # Device information string
      def __str__(self):
          return f"{self.device.vendor}, model :{self.device.model}, version: {self.device.version} - {len(self.device.channels)} channels: {', '.join([c.name for c in self.device.channels])}"

class SigrokDriver:
  """Wrap sigrok python API 

  - find device for driver string

  - manage device open/close state = support Python with statement

  - manage context (class attribute)
   
  - manage session (class attribute)

  - session interface (open, start, run, close, clenaup)

  - utilities to parse session run callback

  Attributes:

  * 'driver': sigrok.Driver object

  """

  # Persisent, shared context - one instance to avoid python REPL
  # (Read-Eval-Print Loop) from freezing
  context = None

  # One context managed
  session = None

  # Contstructore
  def __init__( self, driver="rdtech-dps"):
    """Create 'sigrok.context', locate 'driver' (default rdtechDps')
    from this context, find device from from

    :driver: sigrok driver string used in sigrok-cli
    e.g. 'rdtech-dps:conn=/dev/ttyUSB0'

    """


    # Create only one 'context' instance in one python session 
    if SigrokDriver.context is None:
        SigrokDriver.context = sr.Context.create()


    # 
    driver_spec = driver.split(':')
    driver_name = driver_spec[0]

    # locate driver bundle into libsigrok
    if driver_name not in self.context.drivers: 
        raise KeyError( f"Unknown driver name '{driver_name}' in '{driver}'. Supported hardware drivers: {','.join(self.context.drivers.keys())}")
    self.driver = self.context.drivers[driver_name]



    driver_options = {}
    for pair in driver_spec[1:]:
        name, value = pair.split('=')
        # key = self.driver.ConfigKey.get_by_identifier(name)
        # driver_options[name] = key.parse_string(value)
        driver_options[name] = value



    # attach to sigrok.Device wrapped within Device class
    self.device = self.findDevice(self.driver, driver_options)

  def findDevice(self, driver, driver_options):
    """Locate first (=the one and only?) device found using
      driver_options. Stderr message if not found.

      :driver: Driver for the device we are looking for

      :driver_options: Hash map for drivers options used to locate the
      device

      :return: Device wrapper for the first sigrok device scanned,
      None if not found
"""
    scanned = driver.scan(**driver_options)
    if len(scanned) > 0: 
      # return first device found
      return Device(scanned[0])
    else:
      raise ValueError( f"Could not find any device for driver '{self.driver.name}' with options '{ ','.join([k+'='+v for k,v in driver_options.items()])}'")

  # ------------------------------------------------------------------
  # support with statement
  def open(self):
    if self.device is not None:
       self.device.open()
    return self.device

  def close(self):
    if self.device is not None:
      self.device.close()
  
  def __enter__(self):
    """Called when entering with -statement.

      :return: device (which is opened)
    """
    return( self.open())

  def __exit__( self, *args):
    """Called when exiting with -statement. Close 'device' (if it open)

      :return: device (which is opened)
    """
    self.close()

  # ------------------------------------------------------------------
  # support with statement
  @staticmethod
  def session_create():
    if SigrokDriver.session is None:
        logging.info( "session created")
        SigrokDriver.session = SigrokDriver.context.create_session()
    return SigrokDriver.session

  @staticmethod
  def session_get():
    if SigrokDriver.session is None:
        raise ValueError( "session_get: Session missing - should have called 'session_create'")
    return SigrokDriver.session



  @staticmethod
  def session_add_device( device ):
      session = SigrokDriver.session_get()
      session.add_device(device.device)
      logging.info( f"added device {device.device}[{type(device.device)}] to session ")


  @staticmethod
  def session_start( fRun, fStop=lambda device,frame: print( "Stopped" )  ):
      session = SigrokDriver.session_get()
      logging.debug( f"session_start: called: is_running={session.is_running()}")
      if session.is_running():
          raise ValueError( f"Session was already running - not started")
      # def datafeed_in(device, packet):
      #     logging.info( f"datafeed_in: packet type {packet.type} ")
      #     logging.debug( f"datafeed_in: payload methods  {dir(packet.payload)} ")
      #     # print( f"device:{device.name}")
      # session.append( device, packet)

      # session.begin_save(outputFile)
      session.add_datafeed_callback(fRun)
      logging.debug( f"session_start: before start is_running={session.is_running()}" )
      session.start()
      logging.debug( f"session_start: after start is_running={session.is_running()}" )

  @staticmethod
  def session_run():
      """:return: False is already running, else True
      """
      session = SigrokDriver.session_get()
      logging.debug( f"session_run: called session is_running {session.is_running()}" )
      # if session.is_running(): 
      #     logging.info( f"session_run: session already running {session.is_running()} - nothing done" )
      #     return False
      logging.info( f"session_run: before session.run, is_running {session.is_running()}" )
      session.run()
      logging.info( f"session_run: after session.run, is_running {session.is_running()}" )
      return True


  @staticmethod
  def session_stop():
      session = SigrokDriver.session_get()
      session.stop()
      # SigrokDriver.session = None

  @staticmethod
  def session_close():
      SigrokDriver.session = None

  # ------------------------------------------------------------------
  # utilities to process callback data

  @classmethod
  def isAnalogPacket(cls, packet):
      return packet.type == sr.PacketType.ANALOG

  @classmethod
  def isLogicPacket(cls, packet):
      return packet.type == sr.PacketType.LOGIC

  @classmethod
  def packetChannels(cls, packet):
      return [ch.name for ch in packet.payload._channels() ]

  @classmethod
  def packetChannels(cls, packet):
      return [ch.name for ch in packet.payload._channels() ]

  @classmethod
  def parsePacketData(cls, packet, data):
      logging.info( f"parsePacketData: packet.type={packet.type}")
      if cls.isAnalogPacket(packet): 
          for i, channel in enumerate(cls.packetChannels(packet)):
              # previosly unseen channel?
              if channel not in data: data[channel] = []
              logging.info( f"parsePacketData: channel {channel} {len(packet.payload.data[i])}")
              data[channel].extend(packet.payload.data[i])
              # data[channel].append(packet.payload.data[i][-1])
      elif cls.isLogicPacket(packet): 
          channel = "logic"
          # if channel not in data: data[channel] = []
          # logging.info( f"parsePacketData: channel {channel} {len(packet.payload.data)}")
          # data[channel].extend(packet.payload.data)
          # TODO: collect also logic data (sepately?)
      return data

  # ------------------------------------------------------------------
  # print out
  def __str__(self):
    return str(self.device)
