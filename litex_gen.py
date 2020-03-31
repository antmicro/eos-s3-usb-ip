#!/usr/bin/env python3

# This file is Copyright (c) 2020 Antmicro <www.antmicro.com>
# This file is Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>

import argparse

from migen import *

from litex.build.generic_platform import *

from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.interconnect import wishbone

from litex.soc.cores.pwm import PWM
from litex.soc.cores.gpio import GPIOTristate
from litex.soc.cores.spi import SPIMaster, SPISlave

from valentyusb.usbcore import io as usbio
from valentyusb.usbcore.cpu import epmem, unififo, epfifo, dummyusb, eptri
from valentyusb.usbcore.endpoint import EndpointType

# Platform -----------------------------------------------------------------------------------------

_io = [
    ("sys_clk", 0, Pins(1)),
    ("sys_rst", 0, Pins(1)),
    ("usb", 0,
        Subsignal("d_p", Pins(1)),
        Subsignal("d_n", Pins(1)),
        Subsignal("pullup", Pins(1)),
    ),
    ("clk12", 0, Pins(1)),
    ("clk48", 0, Pins(1)),
]

# Platform -----------------------------------------------------------------------------------------

class Platform(GenericPlatform):
    def __init__(self, io):
        GenericPlatform.__init__(self, "", io)

    def build(self, fragment, build_dir, **kwargs):
        os.makedirs(build_dir, exist_ok=True)
        os.chdir(build_dir)
        top_output = self.get_verilog(fragment, name="top_usb")
        top_output.write("litex_core.v")

class _CRG(Module):
    def __init__(self, platform):
        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_usb_12 = ClockDomain()
        self.clock_domains.cd_usb_48 = ClockDomain()

        sys_rst = platform.request("sys_rst")
        sys_clk = platform.request("sys_clk")
        clk12 = platform.request("clk12")
        clk48 = platform.request("clk48")
        self.comb += [
            self.cd_sys.rst.eq(sys_rst),
            self.cd_sys.clk.eq(clk12),
            self.cd_usb_12.rst.eq(sys_rst),
            self.cd_usb_12.clk.eq(clk12),
            self.cd_usb_48.rst.eq(sys_rst),
            self.cd_usb_48.clk.eq(clk48),
        ]

# LiteXCore ----------------------------------------------------------------------------------------

class LiteXCore(SoCMini):
    SoCMini.mem_map["csr"] = 0x00000000
    def __init__(self, sys_clk_freq=int(100e6),
        with_pwm        = False,
        with_gpio       = False, gpio_width=32,
        with_spi_master = False, spi_master_data_width=8, spi_master_clk_freq=8e6,
        **kwargs):

        platform = Platform(_io)

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform)

        # SoCMini ----------------------------------------------------------------------------------
        print(kwargs)
        SoCMini.__init__(self, platform, clk_freq=sys_clk_freq, **kwargs)

        usb_pads = platform.request("usb")
        usb_iobuf = usbio.IoBuf(usb_pads.d_p, usb_pads.d_n, usb_pads.pullup)
        self.submodules.usb = eptri.TriEndpointInterface(usb_iobuf, debug=False)
        self.add_csr("usb")

        # Wishbone Master
        if kwargs["bus"] == "wishbone":
            wb_bus = wishbone.Interface()
            self.bus.add_master(master=wb_bus)
            platform.add_extension(wb_bus.get_ios("wb"))
            wb_pads = platform.request("wb")
            self.comb += wb_bus.connect_to_pads(wb_pads, mode="slave")

        # IRQs
        for name, loc in sorted(self.irq.locs.items()):
            module = getattr(self, name)
            platform.add_extension([("irq_"+name, 0, Pins(1))])
            irq_pin = platform.request("irq_"+name)
            self.comb += irq_pin.eq(module.ev.irq)

# Build -------------------------------------------------------------------------------------------

def soc_argdict(args):
    ret = {}
    for arg in [
        "bus",
        "csr_data_width",
        "csr_address_width",
        "csr_paging"]:
        ret[arg] = getattr(args, arg)
    return ret

def main():
    parser = argparse.ArgumentParser(description="LiteX standalone core generator")
    builder_args(parser)

    # Bus
    parser.add_argument("--bus",               default="wishbone",    type=str, help="Type of Bus (wishbone, axi)")

    # CSR settings
    parser.add_argument("--csr-data-width",    default=8,     type=int, help="CSR bus data-width (8 or 32, default=8)")
    parser.add_argument("--csr-address-width", default=14,    type=int, help="CSR bus address-width")
    parser.add_argument("--csr-paging",        default=0x800, type=int, help="CSR bus paging")

    args = parser.parse_args()

    soc     = LiteXCore(**soc_argdict(args))
    builder = Builder(soc, **builder_argdict(args))
    builder.build()


if __name__ == "__main__":
    main()
