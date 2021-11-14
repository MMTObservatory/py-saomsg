#!/usr/bin/env python3
from saomsg.msgtoindi import msg_device
from saomsg.msgtoindi import wrapper as MSG

from saomsg.client import Subscriber
from pyindi.client import INDIClient
import asyncio
import logging
logging.getLogger().setLevel(logging.DEBUG)
import os


class WAVESERV(msg_device):

    def power_switches(self):
        """
        Define the INDI swithes related to power.
        """
        vec_att = dict(
                    device=self.device,
                    name="power",
                    label='Power',
                    group="Main",
                    rule="AnyOfMany",
                    perm="rw",
                    state="Idle"

                )

        switches = []
        names = ("epower", "spower", "ppower", "fpower", "apower", "bpower")
        labels = ("Encoder", "Servo", "Puntino", "Stellacam", "Apogee", "SBIG")
        for name, label in zip(names, labels):
            switches.append(dict(
                    name=name,
                    label=label,
                    state="Off"
                    ))

        vec = self.vectorFactory("Switch", vec_att, switches)
        self.IDDef(vec)


    def temps_numbers(self):
        """
        Define the INDI numbers related to temperature.
        """
        vec_att = dict(
                device=self.device,
                name="temps",
                label="Temps",
                group="Main",
                state="Idle",
                perm="ro",
                )
        names = dict(
                mMTemp="Mirror Motor Temp",
                tMTemp="Trans Motor Temp",
                cMTemp="Camera Motor Temp",
                fMTemp="Focus Motor Temp",
                mSTemp="Mirror Struct Temp",
                tSTemp="Trans Struct Temp",
                cSTemp="Camera Struct Temp",
                fSTemp="Focus Struct Temp",
                cpuTemp="CPU Temp",
                vTemp="vTemp"
                )
        numbers=[]
        for name, label in names.items():
            numbers.append(dict(
                name=name,
                label=label,
                min=-10000,
                max=10000,
                step=0.01,
                value=0,
                format="%8.2f"
                ))
        vec = self.vectorFactory("Number", vec_att, numbers)
        self.IDDef(vec)

    def registered_texts(self):
        for k in self.msg_client.server_info['registered']:
            vec = self.vectorFactory(
                "Text",
                dict(
                    device=self.device,
                    label=k,
                    name=k,
                    state="Idle",
                    perm="ro",
                    group="Registered Fxns"
                ),
                [
                dict(
                    name=k,
                    label=k,
                    text=k
                )
                ]

            )
            self.IDDef(vec)

    def axis_switches(self):
        """
        Define the axis switch for abort, clear, busy and estop
        """

        act_attr = dict(
                device=self.device,
                name="axis_actions",
                label="Axis Actions",
                state="Idle",
                perm="rw",
                group="Main",
                rule="AnyOfMany"
                )
        act_switches = [
                dict(
                    name="abort",
                    label="Abort",
                    state="Off"
                    ), 

                dict(
                    name="clear",
                    label="Clear",
                    state="Off"
                    ),
                ]

        vec = self.vectorFactory( "Switch",  act_attr, act_switches)

        self.IDDef(vec)
        state_attr = dict( 
                device=self.device,
                name="axis_states",
                label="Axis States",
                state="Idle",
                perm="ro",
                group="Main",
                rule="AnyOfMany"
                )
        
        state_switches = [
                 dict(
                    name="busy",
                    label="Busy",
                    state="Off"
                    ), 

                dict(
                    name="estop",
                    label="E-Stop",
                    state="Off"
                    ),
                    ]

        logging.debug(f"Defining states")
        self.IDDef(
                self.vectorFactory(
                    "Switch", 
                    state_attr, 
                    state_switches)
                )
       

    def axis_numbers(self):
        """
        Defines INDI numbers relating to axis
        position. 
        """
        axes = ("mirror", "trans", "select", "focus", "puntino")
        pos_types = ("actual", "commanded", "target")

        for axis in axes:
            att = dict(
                    device=self.device,
                    name=axis,
                    label=axis,
                    state="Idle",
                    perm="ro",
                    group="Main"
                    
                    )
            props = []
            for pos in pos_types:
                if axis=="puntino" and pos == "commanded":
                    continue
                props.append(dict( 
                    name=pos,
                    label=pos,
                    min=-10000,
                    max=10000,
                    step=0.01,
                    value=0,
                    format="%8.2f",

                    ))
            vec = self.vectorFactory(
                    "Number", 
                    att,
                    props
                    )
            self.IDDef(vec)


    def axis_details(self):

        axis_map = dict(
            mirror=('m', 1),
            trans= ('t', 2),
            camera=('c', 3),
            focus= ('f', 4),
            )

        prop_defaults = dict(min=-100000, max=100000, step=0.01, format="%8.3f", value=0)
        special_positions = dict( 
                p70="WFS Position",
                p71="Sci Position",
                p72="WFS T Offset",
                p73="Sci T Offset",
                p74="WFS F Offset",
                p75="Sci F Offset"
                )
        props = []
        for name,label in special_positions.items():
            prop = dict(
                    name=name,
                    label=label
                    )
            prop.update(prop_defaults)
            props.append(prop)

        vec = self.vectorFactory("Number",
                dict(
                    device=self.device,
                    name="special_positions",
                    label="Special Positions",
                    state="Idle",
                    perm="ro",
                    group="Special Positions"
                    ),
                props
                )
        self.IDDef(vec)

        for name, (letter, number) in axis_map.items():

            pnames = {
                    f"{letter}E"      : "Encoder Scale",
                    f"{letter}MlimPos": "Limit of Pos. Travel",
                    f"{letter}PlimPos": "Limit of Neg. Travel",
                    f"{letter}HomePos": "Encoder Home",
                    f"{letter}DAC"    : "DAC Value",
                    f"{letter}DACBias": "DAC Bias",
                    }
                    
            vec_att = dict(
                    device=self.device,
                    name=f"{name}_details",
                    state="Idle",
                    perm="ro",
                    label=f"{name} Details",
                    group=f"{name} Details"
                    )

            props =[]
            for pname, label in pnames.items():
                prop = dict(
                        name=pname,
                        label=label
                        )
                prop.update(prop_defaults)
                props.append(prop)

            vec = self.vectorFactory("Number", vec_att, props)
            self.IDDef(vec)

            pnames2 = {
                    f"i{number}30"  :   "Proportional Gain",
                    f"i{number}31"  :   "Derivative Gain",
                    f"i{number}32"  :   "Veclocity Feed Forward",
                    f"i{number}33"  :   "Integral Gain",
                    f"i{number}63"  :   "Integration Limit",
                    f"i{number}67"  :   "Big Step Limit",

                    f"p{number}05"    :   "Feed Rate",
                    f"p{number}06"    :   "Time of Acceleration",
                    f"p{number}07"    :   "Time of S-Curve",
                    f"p{number}02"    :   "Home Speed",
                    f"p{number}03"    :   "Home Offset",

                    f"i{number}16"    :   "Maximum Velocity",
                    f"i{number}17"    :   "Maximum Acceleration",

                    f"p{number}08"    :   "Position Tolerance",

                    f"i{number}11"    :   "Following Error",
                    f"i{number}95"    :   "Hold Decel Rate",
                    f"i{number}15"    :   "Error Deceleration Rate",
                    f"i{number}64"    :   "Dead Band Factor",
                    f"i{number}65"    :   "Dead Band Size"
                    }

            vec_att2 = dict(
                    device=self.device,
                    name=f"{name}_servo",
                    state="Idle",
                    perm="ro",
                    label=f"{name} Servo",
                    group=f"{name} Details"
                    )
            props2 = []
            for pname, label in pnames2.items():
                prop = dict(
                        name=pname,
                        label=label
                        )
                prop.update(prop_defaults)
                props2.append(prop)
            vec = self.vectorFactory("Number", vec_att2, props2)
            self.IDDef(vec)

            
    @MSG.subscribe("p70","p71","p72","p73","p74","p75")
    def on_special_pos_change(self, item, value):
        vec = self.IUFind("special_positions")
        vec[item].value = float(value[0])
        self.IDSet(vec)


    @MSG.subscribe("WAVESERV", 
            "mE", "mMlimPos", "mplimPos", "mHomePos","mDAC", "mDACBias")
    def on_mirror_details_change(self, item, value):
        self.IDMessage(f"mirror details called {item}={value}")
        vec = self.IUFind("mirror_details")

        value = float(value[0])
        vec[item].value = value
        self.IDSet(vec)


    @MSG.subscribe("WAVESERV", 
             "i130","i131","i132","i133","i163","i167",
             "p105","p106","p107","p102","p103",
             "i116","i117",
             "p108",
             "i111","i195","i115","i164","i165")
    def on_mirror_servo_change(self, item, value):
        vec = self.IUFind("mirror_servo")

        value = float(value[0])
        vec[item].value = value
        self.IDSet(vec)
       

    @MSG.subscribe("WAVESERV","mA","mC","mT")
    def on_mirror_change(self, item, value ):
        """
        Called when MSG server updates the 
        mirror position. Updates the corresponding 
        INDI numbers. 
        """
        vec = self.IUFind("mirror")
        if item == "mA":
            vec["actual"].value = float(value[0])
        elif item == "mC":
            vec["commanded"].value = float(value[0])
        elif item == "mT":
            vec["target"].value = float(value[0])

        self.IDSet(vec)


    @MSG.subscribe("WAVESERV","tA","tC","tT",)
    def on_trans_change(self, item, value ):
        vec = self.IUFind("trans")
        if item == "tA":
            vec["actual"].value = float(value[0])
        elif item == "tC":
            vec["commanded"].value = float(value[0])
        elif item == "tT":
            vec["target"].value = float(value[0])
   
        self.IDSet(vec)

    @MSG.subscribe("WAVESERV", 
            "tE", "tMlimPos", "tplimPos", "tHomePos","tDAC", "tDACBias")
    def on_trans_details_change(self, item, value):
        vec = self.IUFind("trans_details")

        value = float(value[0])
        vec[item].value = value
        self.IDSet(vec)


    @MSG.subscribe("WAVESERV", 
             "i230","i231","i232","i233","i263","i267",
             "p205","p206","p207","p202","p203",
             "i216","i217",
             "p208",
             "i211","i295","i215","i264","i265")
    def on_trans_servo_change(self, item, value):
        vec = self.IUFind("trans_servo")

        value = float(value[0])
        vec[item].value = value
        self.IDSet(vec)


    @MSG.subscribe("WAVESERV","fA","fC","fT",)
    def on_focus_change(self, item, value ):
        vec = self.IUFind("focus")
        if item == "fA":
            vec["actual"].value = float(value[0])
        elif item == "fC":
            vec["commanded"].value = float(value[0])
        elif item == "fT":
            vec["target"].value = float(value[0])
   
        self.IDSet(vec)


    @MSG.subscribe("WAVESERV", 
            "fE", "fMlimPos", "fplimPos", "fHomePos","fDAC", "fDACBias")
    def on_focus_details_change(self, item, value):
        vec = self.IUFind("focus_details")

        value = float(value[0])
        vec[item].value = value
        self.IDSet(vec)


    @MSG.subscribe("WAVESERV", 
             "i430","i431","i432","i433","i463","i467",
             "p405","p406","p407","p402","p403",
             "i416","i417",
             "p408",
             "i411","i495","i415","i464","i465")
    def on_focus_servo_change(self, item, value):
        vec = self.IUFind("focus_servo")

        value = float(value[0])
        vec[item].value = value
        self.IDSet(vec)



    @MSG.subscribe("WAVESERV","cA","cC","ct",)
    def on_camera_change(self, item, value ):
        vec = self.IUFind("select")
        if item == "cA":
            vec["actual"].value = float(value[0])
        elif item == "cC":
            vec["commanded"].value = float(value[0])
        elif item == "ct":
            vec["target"].value = float(value[0])
   
        self.IDSet(vec)


    @MSG.subscribe("WAVESERV", 
            "cE", "cMlimPos", "cplimPos", "cHomePos","cDAC", "cDACBias")
    def on_camera_details_change(self, item, value):
        vec = self.IUFind("camera_details")

        value = float(value[0])
        vec[item].value = value
        self.IDSet(vec)


    @MSG.subscribe("WAVESERV", 
             "i330","i331","i332","i333","i363","i367",
             "p305","p306","p307","p302","p303",
             "i316","i317",
             "p308",
             "i311","i395","i315","i364","i365")
    def on_camera_servo_change(self, item, value):
        vec = self.IUFind("camera_servo")

        value = float(value[0])
        vec[item].value = value
        self.IDSet(vec)



    @MSG.subscribe("WAVESERV","pA", "pt")
    def on_puntino_change(self, item, value ):
        vec = self.IUFind("puntino")
        if item == "pA":
            vec["actual"].value = float(value[0])
        elif item == "pt":
            vec["target"].value = float(value[0])
   
        self.IDSet(vec)




    async def buildProperties(self):
        await super().buildProperties()

        self.power_switches()
        self.temps_numbers()
        self.axis_switches()
        self.axis_numbers()
        self.axis_details()
        try:
            self.registered_texts()
        except Exception as error:
            logging.debug(f"registered details has this error: {error}")

    @msg_device.NewVectorProperty("epower_switch")
    def epower(self, device, name, states, names):
        vec, change = self.whats_changed(
                name, 
                states, 
                values
                )
        
        for name, newval in change.items():
            self.IDMessage(f"{name} changed to {newval}")
            vec[name].value = newval

        self.IDSet(vec)

    
    @MSG.subscribe("WAVESERV", "abort", "clear", "busy", "estop")
    def on_axis_change(self, item, value):
        acts = self.IUFind("axis_actions")
        states = self.IUFind("axis_states")
        value = int(value[0])

        if value == 1:
            value = "On"
        elif value == 0:
            value = "Off"
        else:
            raise ValueError(f"Value of {item} must be 0 or 1 not {value}")

        if item in ("busy", "estop"):
            states[item].value = value

        elif item in ("abort", "clear"):
            states[item].value = value


    @MSG.subscribe("WAVESERV", 
            "epower", # Encoder
            "spower", # Servo
            "ppower", # Puntino
            "bpower", # sbig power
            "apower", # apogee power
            "fpower"  # StellaCam
            )
    def on_power_change(self, item, value):
        """
        This method is called whenever one of the
        power states are published from the MSG
        server. 

        args:
        item => Name of power msg value
        value => new value of the power item. 

        """
        power = self.IUFind("power")
        #changed = self.whats_changed(power)
        self.IDMessage(f"power state change: {item} {value}")

        if type(value) == list:
            value = value[0]
        value = int(value)
        if value == 0:
            power[item].value = "Off"

        elif value == 1:
            power[item].value = "On"
        else:
            raise ValueError(
                    f"Power value of {item} should be '0' or '1' not {value}"
                    )

        self.IDSet(power)


    @MSG.subscribe("WAVESERV", 
            "mMtemp",
            "tMTemp",
            "cMTemp",
            "fMTemp",
            "mSTemp",
            "tSTemp",
            "cSTemp",
            "fSTemp",
            "cpuTemp",
            "vTemp"
            )
    def on_temps(self, item, value):
        temps = self.IUFind("temps")
        self.IDMessage(f"{item} changed to {value}")
        temps[item].value = float(value[0])
        self.IDSet(temps)

    
       

async def main():    
    hostport = os.environ.get("INDICONFIG", )
    device_name = os.environ.get("INDIDEV", )
    if hostport is None:
        host,port = "wavefront.mmto.arizona.edu", 3000
    else:
        host,port = hostport.split(':')
    m=WAVESERV(host, int(port), device_name)
    await m.astart()



asyncio.run(main())

