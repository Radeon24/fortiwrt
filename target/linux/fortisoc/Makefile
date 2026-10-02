# SPDX-License-Identifier: GPL-2.0-only

include $(TOPDIR)/rules.mk

ARCH:=arm
BOARD:=fortisoc
BOARDNAME:=Fortinet FortiSOC
FEATURES:=dt ramdisk
# fsoc1 (FortiGate 60C) is laid out but not enabled yet.
SUBTARGETS:=fsoc2

KERNEL_PATCHVER:=6.18

define Target/Description
	Build initramfs images for Fortinet FortiGate appliances built around
	the Fortinet FortiSOC (FortiSOC1: Faraday FA626TE, FortiSOC2: Faraday
	FA726TE). The images run from RAM only: they are booted by the stock
	boot loader from TFTP and never write to the internal storage.
endef

KERNELNAME:=zImage

# No firewall, DHCP or RA server by default: the network is set up by hand.
DEVICE_TYPE:=basic

include $(INCLUDE_DIR)/target.mk

# RAM only: nothing to write to a flash.
DEFAULT_PACKAGES := $(filter-out mtd,$(DEFAULT_PACKAGES))

$(eval $(call BuildTarget))
