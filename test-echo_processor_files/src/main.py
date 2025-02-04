import json
import urllib.error
import urllib.request

from extronlib import event
from extronlib.interface import (
    EthernetClientInterface,
    EthernetServerInterfaceEx,
    RelayInterface,
    SerialInterface,
)
from extronlib.system import File as open
from extronlib.system import Timer, Wait

import variables as v
from gui_elements.buttons import all_buttons
from gui_elements.knobs import all_knobs
from gui_elements.labels import all_labels
from gui_elements.levels import all_levels
from gui_elements.sliders import all_sliders
from hardware.hardware import all_processors, all_ui_devices
from utils import backend_server_ok, log, set_ntp

BUTTON_EVENTS = ["Pressed", "Held", "Repeated", "Tapped"]


def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return None


config = load_json("config.json")


class PageStateMachine:
    """
    Extron libs do not have the ability to query
    all possible pages and popups, nor do they have properties
    that contain current visible pages and popups.
    We track state here and store all unique pages and popups called
    """

    def __init__(self, ui_device, name):
        self.ui_device = str(ui_device)
        self.Name = name

        self.current_page = "unknown"
        self.current_popup = "unknown"  # includes modals

        # Collect all pages and popups that have been called,
        # to try and track all possibilities
        self.all_pages_called = []
        self.all_popups_called = []  # includes modals

    def _add_to_all(self, element, element_type_list):
        if element not in element_type_list:
            element_type_list.append(element)

    def _reset_popup(self):
        self.current_popup = "none"

    def hide_all_popups(self):
        self.current_popup = "none"

    def set_page(self, page):
        self.current_page = page
        self._add_to_all(page, self.all_pages_called)

    def show_popup(self, popup, duration=None):
        if duration is None:
            self.current_popup = popup
        else:
            self.current_popup = popup
            Wait(float(duration), self._reset_popup)

        self._add_to_all(popup, self.all_popups_called)


page_state_1 = PageStateMachine(all_ui_devices[0], "PageState1")
page_state_2 = None
page_state_3 = None
page_state_4 = None
if len(all_ui_devices) > 1:
    page_state_2 = PageStateMachine(all_ui_devices[1], "PageState2")
if len(all_ui_devices) > 2:
    page_state_3 = PageStateMachine(all_ui_devices[2], "PageState3")
if len(all_ui_devices) > 3:
    page_state_4 = PageStateMachine(all_ui_devices[3], "PageState4")

all_state_machines = [
    state_machine
    for state_machine in [page_state_1, page_state_2, page_state_3, page_state_4]
    if state_machine is not None
]


class PortInstantiation:
    """
    Instantiates all ports defined in ports.json

    Use port_instantiation_helper.py make the JSON file
    """

    def __init__(self):
        self.port_definitions = load_json("ports.json")
        self.all_relays = []
        self.all_serial_interfaces = []
        self.all_ethernet_interfaces = []
        self.instantiate_ports()

    def instantiate_ports(self):
        if not self.port_definitions:
            return
        for port_definition in self.port_definitions:
            port_class = port_definition["Class"]
            if port_class == "RelayInterface":
                self.instantiate_relays(port_definition)
            elif port_class == "SerialInterface":
                self.instantiate_serial_interface(port_definition)
            elif port_class == "EthernetClientInterface":
                self.instantiate_ethernet_client_interface(port_definition)
            else:
                log("Unknown Port Definition Class: {}".format(port_class), "error")

    def instantiate_relays(self, port_definition):
        host = PROCESSORS_MAP.get(port_definition["Host"], None)
        if not host:
            log(
                "Host Processor for relay port not found: {}".format(
                    port_definition["Host"]
                ),
                "error",
            )
            return
        port = port_definition["Port"]
        self.all_relays.append(RelayInterface(host, port))

    def instantiate_serial_interface(self, port_definition):
        host = PROCESSORS_MAP.get(port_definition["Host"], None)
        if not host:
            log(
                "Host Processor for relay port not found: {}".format(
                    port_definition["Host"]
                ),
                "error",
            )
            return
        port = port_definition["Port"]
        baud = int(port_definition["Baud"])
        data = int(port_definition["Data"])
        stop = int(port_definition["Stop"])
        char_delay = int(port_definition["CharDelay"])
        parity = port_definition["Parity"]
        flow_control = port_definition["FlowControl"]
        mode = port_definition["Mode"]
        self.all_serial_interfaces.append(
            SerialInterface(
                host,
                port,
                Baud=baud,
                Data=data,
                Parity=parity,
                Stop=stop,
                FlowControl=flow_control,
                CharDelay=char_delay,
                Mode=mode,
            )
        )

    def instantiate_ethernet_client_interface(self, port_definition):
        host = port_definition["Hostname"]
        ip_port = int(port_definition["IPPort"])
        protocol = port_definition["Protocol"]

        if protocol == "TCP":
            self.all_ethernet_interfaces.append(
                EthernetClientInterface(host, ip_port, Protocol=protocol)
            )
        elif protocol == "UDP":
            service_port = port_definition["ServicePort"]
            buffer_size = port_definition["bufferSize"]
            self.all_ethernet_interfaces.append(
                EthernetClientInterface(
                    host,
                    ip_port,
                    Protocol=protocol,
                    ServicePort=int(service_port),
                    bufferSize=int(buffer_size),
                )
            )
        elif protocol == "SSH":
            username = port_definition["Username"]
            password = port_definition["Password"]
            credentials = (username, password)
            self.all_ethernet_interfaces.append(
                EthernetClientInterface(
                    host, ip_port, Protocol=protocol, Credentials=credentials
                )
            )


def make_str_obj_map(element_list):
    """Creates a dictionary using objects as values and their string names as keys"""
    # GUI Object: Name = "Name"
    # UI Devices (touch panels) and Processors: Name = DeviceAlias
    # Hardware interface = Name = "Port", ex: "COM1"
    # Ethernet interface = Name = "Hostname"
    attributes_to_try = ["Name", "DeviceAlias", "Port", "Hostname"]

    for attr in attributes_to_try:
        try:
            return {str(getattr(element, attr)): element for element in element_list}
        except AttributeError:
            continue
        except Exception as e:
            log(str(e), "error")
            return None

    log(
        "None of the attributes {} found in elements".format(attributes_to_try), "error"
    )
    return None


# Key: string name, Value: object
## Standard Extron Classes ##
PROCESSORS_MAP = make_str_obj_map(all_processors)
UI_DEVICE_MAP = make_str_obj_map(all_ui_devices)
BUTTONS_MAP = make_str_obj_map(all_buttons)
KNOBS_MAP = make_str_obj_map(all_knobs)
LEVELS_MAP = make_str_obj_map(all_levels)
SLIDERS_MAP = make_str_obj_map(all_sliders)
LABELS_MAP = make_str_obj_map(all_labels)

## Ports ##
ports = PortInstantiation()
RELAYS_MAP = make_str_obj_map(ports.all_relays)
SERIAL_INTERFACE_MAP = make_str_obj_map(ports.all_serial_interfaces)
ETHERNET_INTERFACE_MAP = make_str_obj_map(ports.all_ethernet_interfaces)

## Custom Classes ##
PAGE_STATES_MAP = make_str_obj_map(all_state_machines)


DOMAIN_CLASS_MAP = {
    ## Standard Extron Classes ##
    "ProcessorDevice": PROCESSORS_MAP,
    "UIDevice": UI_DEVICE_MAP,
    "Button": BUTTONS_MAP,
    "Knob": KNOBS_MAP,
    "Label": LABELS_MAP,
    "Level": LEVELS_MAP,
    "Slider": SLIDERS_MAP,
    "RelayInterface": RELAYS_MAP,
    "SerialInterface": SERIAL_INTERFACE_MAP,
    "EthernetClientInterface": ETHERNET_INTERFACE_MAP,
    ## Custom Classes ##
    "page_state": PAGE_STATES_MAP,
}


def string_to_bool(string):
    """Interperts RPC string values received as boolean"""
    if string.lower() in ["true", "1", "t", "y", "yes"]:
        return True
    elif string.lower() in ["false", "0", "f", "n", "no"]:
        return False
    else:
        log("Invalid boolean value: {}".format(string), "error")
        return None


def string_to_int(string):
    """
    Interperts RPC string values received as integers.
    Supports hardware interface string syntax.
    """
    if string in ["0", "1", "2"]:
        return int(string)
    else:
        string = string.lower()
        if string in ["close", "on"]:
            return 1
        elif string in ["open", "off"]:
            return 0


#### Externally callable functions ####


## Standard Extron Methods ##
def set_state(obj, state):
    obj.SetState(string_to_int(state))


def set_fill(obj, fill):
    obj.SetFill(int(fill))


def set_text(obj, text):
    obj.SetText(text)


def set_visible(obj, visible):
    obj.SetVisible(string_to_bool(visible))


def set_blinking(obj, rate, state_list):
    state_list = state_list.replace("[", "").replace("]", "").split(",")
    state_list = [int(state) for state in state_list]
    obj.SetBlinking(rate, state_list)


def set_enable(obj, enabled):
    obj.SetEnable(string_to_bool(enabled))


def show_popup(ui_device, popup, duration=None):
    if duration is None:
        ui_device.ShowPopup(popup)  # Default indefinite popup
    else:
        ui_device.ShowPopup(popup, int(duration))
    if ui_device == all_ui_devices[0]:
        page_state_1.show_popup(popup, duration)
    elif ui_device == all_ui_devices[1]:
        page_state_2.show_popup(popup, duration)
    elif ui_device == all_ui_devices[2]:
        page_state_3.show_popup(popup, duration)
    elif ui_device == all_ui_devices[3]:
        page_state_4.show_popup(popup, duration)


def hide_all_popups(ui_device):
    ui_device.HideAllPopups()
    if ui_device == all_ui_devices[0]:
        page_state_1.hide_all_popups()
    elif ui_device == all_ui_devices[1]:
        page_state_2.hide_all_popups()
    elif ui_device == all_ui_devices[2]:
        page_state_3.hide_all_popups()
    elif ui_device == all_ui_devices[3]:
        page_state_4.hide_all_popups()


def show_page(ui_device, page):
    ui_device.ShowPage(page)
    if ui_device == all_ui_devices[0]:
        page_state_1.set_page(page)
    elif ui_device == all_ui_devices[1]:
        page_state_2.set_page(page)
    elif ui_device == all_ui_devices[2]:
        page_state_3.set_page(page)
    elif ui_device == all_ui_devices[3]:
        page_state_4.set_page(page)


def get_volume(obj, name):
    return obj.GetVolume(name)


def play_sound(obj, filename):
    obj.PlaySound(filename)


def set_led_blinking(obj, ledid, rate, state_list):
    state_list = state_list.replace("[", "").replace("]", "").split(",")
    state_list = [state.strip() for state in state_list]
    obj.SetLEDBlinking(int(ledid), rate, state_list)


def set_led_state(obj, ledid, state):
    obj.SetLEDState(int(ledid), state)


def set_level(obj, level):
    obj.SetLevel(int(level))


def set_range(obj, min, max, step=1):
    obj.SetRange(int(min), int(max), int(step))


def inc(obj):
    obj.Inc()


def dec(obj):
    obj.Dec()


def pulse(obj, duration):
    obj.Pulse(float(duration))


def toggle(obj):
    obj.Toggle()


def send(obj, data):
    obj.Send(data)


def send_and_wait(obj, data, timeout):
    return obj.SendAndWait(data, float(timeout))


def reboot(obj):
    log("Rebooting {}".format(str(obj)), "warning")
    obj.Reboot()


def set_executive_mode(obj, mode):
    obj.SetExecutiveMode(string_to_int(mode))


def connect(obj, timeout=None):
    if timeout is None:
        return obj.Connect()
    else:
        return obj.Connect(float(timeout))


def disconnect(obj):
    obj.Disconnect()


def start_keepalive(obj, interval, data):
    obj.StartKeepAlive(float(interval), data)


def stop_keepalive(obj):
    obj.StopKeepAlive()


## Custom Methods ##


def get_property_(obj, property):
    try:
        attribute = getattr(obj, property)
        return attribute
    except AttributeError as e:
        log(str(e), "error")
        return e
    except Exception as e:
        log(str(e), "error")
        return e


# TODO: Add more methods as needed

#### Macros ####


def get_all_elements_():
    """Called through RPC by sending {"type": "get_all_elements"}"""
    data = {
        "all_processors": list(PROCESSORS_MAP.keys()),
        "all_ui_devices": list(UI_DEVICE_MAP.keys()),
        "all_buttons": list(BUTTONS_MAP.keys()),
        "all_knobs": list(KNOBS_MAP.keys()),
        "all_labels": list(LABELS_MAP.keys()),
        "all_levels": list(LEVELS_MAP.keys()),
        "all_sliders": list(SLIDERS_MAP.keys()),
        "all_relays": list(RELAYS_MAP.keys()),
        "all_serial_interfaces": list(SERIAL_INTERFACE_MAP.keys()),
        "all_ethernet_interfaces": str(ETHERNET_INTERFACE_MAP),
        "all_page_state_machines": [state.Name for state in all_state_machines],
        "backend_server_available": v.backend_server_available,
        "backend_server_role": v.backend_server_role,
        "backend_server_ip": v.backend_server_ip,
    }
    return data


def set_backend_server_(ip=None):
    """
    Call example: {"type": "set_backend_server", "ip": "http://10.0.0.1:8080"}

    If no IP is provided, the function will try servers in the config.json file.
    """

    def _set_server(role, ip, message, log_level):
        v.backend_server_available = True
        v.backend_server_role = role
        v.backend_server_ip = ip
        log(message, log_level)

    def _no_server(message):
        v.backend_server_available = False
        v.backend_server_role = "none"
        v.backend_server_ip = None
        log(message, "error")
        for ui_device in all_ui_devices:
            ui_device.ShowPage("NoBackendServer")

    if ip:  # Custom IP specified
        if backend_server_ok(ip):
            _set_server(
                "custom", ip, "Using custom backend server: {}".format(ip), "warning"
            )
            return "OK"
        else:
            err = "Custom backend server {} is not available".format(ip)
            _no_server(err)
            return err

    # Try primary from the config
    if backend_server_ok(config["primary_backend_server_ip"]):
        _set_server(
            "primary",
            config["primary_backend_server_ip"],
            "Using primary backend server",
            "info",
        )
        return "OK"
    # Try secondary from the config
    elif backend_server_ok(config["secondary_backend_server_ip"]):
        _set_server(
            "secondary",
            config["secondary_backend_server_ip"],
            "Using secondary backend server",
            "warning",
        )
        return "OK"
    else:
        _no_server("No backend servers available")
        return "No backend servers available"


METHODS_MAP = {
    # All 'methods' take "type", "object", "function" as required arguments
    # and "arg1", "arg2", "arg3" as optional arguments.
    # This is different from 'macros' which can have custom call formats
    "SetState": set_state,
    "SetFill": set_fill,
    "SetText": set_text,
    "SetVisible": set_visible,
    "SetBlinking": set_blinking,
    "SetEnable": set_enable,
    "ShowPopup": show_popup,
    "HideAllPopups": hide_all_popups,
    "ShowPage": show_page,
    "GetVolume": get_volume,
    "PlaySound": play_sound,
    "SetLEDBlinking": set_led_blinking,
    "SetLEDState": set_led_state,
    "SetLevel": set_level,
    "SetRange": set_range,
    "Inc": inc,
    "Dec": dec,
    "Pulse": pulse,
    "Toggle": toggle,
    "Send": send,
    "SendAndWait": send_and_wait,
    "SetExecutiveMode": set_executive_mode,
    "Reboot": reboot,
    "Connect": connect,
    "Disconnect": disconnect,
    "StartKeepAlive": start_keepalive,
    "StopKeepAlive": stop_keepalive,
    "get_property": get_property_,
}

MACROS_MAP = {
    "get_all_elements": get_all_elements_,
    "set_backend_server": set_backend_server_,
}

#### User interaction events ####


@event(all_buttons, BUTTON_EVENTS)
def any_button_event(button, action):
    button_data = ("button", str(button.Name), action, str(button.State))
    send_user_interaction(button_data)


@event(all_sliders, "Changed")
def any_slider_changed(slider, action, value):
    slider_data = ("slider", str(slider.Name), action, str(value))
    send_user_interaction(slider_data)


# TODO: Knob events


#### Internal Functions ####


def get_object(string_key, object_map):
    """
    Pass in string representing an object and the dictionary map of the object domain,
    returns the object
    """
    try:
        return object_map[string_key]
    except KeyError:
        log("{} not in {}".format(string_key, object_map), "error")
        log("Valid options for map are: {}".format(object_map.keys()), "info")
        return None
    except Exception as e:
        log(str(e), "error")
        log("Valid options for map are: {}".format(object_map.keys()), "info")
        return None


def method_call_handler(data):
    try:
        # Required
        type_str = data["type"]
        object_str = data["object"]
        function_str = data["function"]

        # Optional
        arg1 = data.get("arg1", None)
        arg2 = data.get("arg2", None)
        arg3 = data.get("arg3", None)

        object_type_map = DOMAIN_CLASS_MAP[type_str]
        obj = get_object(object_str, object_type_map)
        func = METHODS_MAP[function_str]
        args = [arg for arg in [arg1, arg2, arg3] if arg not in ["", None]]
        result = func(obj, *args)
        if result == None:
            return "OK"
        return str(result)
    except Exception as e:
        error = "Function Error: {} | with data {}".format(str(e), str(data))
        log(str(error), "error")
        return str(error)


def macro_call_handler(command_type, client=None, data_dict=None):
    if command_type == "get_all_elements":
        if not client:
            return
        else:
            data = get_all_elements_()
            data = json.dumps(data).encode()
            client.Send(data)
            return

    elif command_type == "set_backend_server":
        ip = data_dict.get("ip", None)
        result = set_backend_server_(ip)
        if client:
            client.Send(result)
        return


def process_rx_data_and_send_reply(json_data, client):
    # Client is only present when function is called from RPC server
    # Function does not send replies when invoked as a REST API reply processor
    try:
        data_dict = json.loads(json_data)
        command_type = data_dict["type"]

        if command_type in DOMAIN_CLASS_MAP.keys():
            result = method_call_handler(data_dict)
            if client:
                client.Send(result)
            return

        elif command_type in MACROS_MAP.keys():
            macro_call_handler(command_type, client, data_dict)

        else:
            log("Unknown action: {}".format(str(command_type)), "error")
            if client:
                client.Send(b"Unknown action{}\n".format(str(command_type)))

    except (json.JSONDecodeError, KeyError) as e:
        log("Error decoding JSON: {}".format(str(e)), "error")
        log("Bad JSON raw: {}".format(str(json_data)), "error")
        if client:
            client.Send(b"Error decoding JSON : {}\n".format(str(e)))
    except Exception as e:
        log(str(e), "error")
        if client:
            client.Send(b"Error processing data : {}".format(str(e)))


def handle_backend_server_timeout():
    log("Backend Server Timed Out", "error")


def format_user_interaction_data(gui_element_data):
    domain = gui_element_data[0]
    data = {
        "name": gui_element_data[1],
        "action": gui_element_data[2],
        "value": gui_element_data[3],
    }

    data = json.dumps(data).encode()
    headers = {"Content-Type": "application/json"}
    url = "{}/api/v1/{}".format(v.backend_server_ip, domain)
    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    return req


def send_to_backend_server(req):
    try:
        with urllib.request.urlopen(
            req, timeout=int(config["backend_server_timeout"])
        ) as response:
            response_data = response.read().decode()
            process_rx_data_and_send_reply(response_data, None)

    # Timeout
    except urllib.error.URLError as e:
        if (
            isinstance(e.reason, urllib.error.URLError)
            and "timed out" in str(e.reason).lower()
        ):
            handle_backend_server_timeout()
        else:
            log("URLError: {}".format(str(e)), "error")

    except Exception as e:
        log(str(e), "error")


def send_user_interaction(gui_element_data):
    req = format_user_interaction_data(gui_element_data)
    send_to_backend_server(req)


#### RPC Server ####

rpc_serv = EthernetServerInterfaceEx(
    IPPort=int(config["rpc_server_port"]),
    Protocol="TCP",
    Interface=config["rpc_server_interface"],
)

if rpc_serv.StartListen() != "Listening":
    raise ResourceWarning("Port unavailable")  # this is not likely to recover


@event(rpc_serv, "ReceiveData")
def handle_unsolicited_rpc_rx(client, data):
    # log("Rx: {}".format(data), "info")
    try:
        data_str = data.decode()

        # Extract the body from the HTTP request
        body = data_str.split("\r\n\r\n", 1)[1]

        if body:
            # log(str(body), "info")
            process_rx_data_and_send_reply(body, client)
            if "User-Agent: curl" in data_str:
                client.Disconnect()  # curl expects a disconnect after a response
        else:
            log("No data received", "error")
    except json.JSONDecodeError as e:
        log(str(e), "error")
    except Exception as e:
        log(str(e), "error")


@event(rpc_serv, "Connected")
def handle_rpc_client_connect(client, state):
    # log("Client connected ({}).".format(client.IPAddress), "info")
    # client.Send(b"Connected\n")
    # Log the state to see if any data is sent on connection
    # log("Connection state: {}".format(state), "info")
    # TODO: Debug mode
    pass


@event(rpc_serv, "Disconnected")
def handle_rpc_client_disconnect(client, state):
    log("Server/Client {} disconnected.".format(client.IPAddress), "info")


def Initialize():
    set_ntp(config["ntp_primary"], config["ntp_secondary"])
    set_backend_server_()  # Using addresses from config.json

    log("Initialized", "info")


Initialize()
