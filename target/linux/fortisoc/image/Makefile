# SPDX-License-Identifier: GPL-2.0-only

include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/image.mk

DEVICE_VARS += FORTIGATE_CMDLINE FORTIGATE_MODEL

# flatkc: 512-byte header + gzip of the zImage with its DTB. A copy is
# kept next to the images: it is the part of the TFTP image built here.
define Build/fortigate-flatkc
	./fortigate-flatkc.py --cmdline "$(FORTIGATE_CMDLINE)" $@ $@.new
	mv $@.new $@
	mkdir -p $(BIN_DIR)
	cp $@ $(BIN_DIR)/$(DEVICE_IMG_PREFIX)-initramfs-flatkc.bin
endef

# TFTP image for the [R] option of the boot menu: a synthetic container by
# default; with CONFIG_FORTISOC_BASE_CONTAINER, the base container of the
# user instead (an image then not to be distributed).
define Build/fortigate-container
	./fortigate-container.py \
		$(if $(call qstrip,$(CONFIG_FORTISOC_BASE_CONTAINER)), \
			--base $(call qstrip,$(CONFIG_FORTISOC_BASE_CONTAINER)), \
			--model $(FORTIGATE_MODEL)) \
		--flatkc $@ --output $@.new
	mv $@.new $@
endef

define Device/Default
  PROFILES := Default
  DEVICE_DTS_DIR := ../dts
  KERNEL_NAME := zImage
  KERNEL := kernel-bin | append-dtb
  KERNEL_INITRAMFS := kernel-bin | append-dtb | fortigate-flatkc | \
	fortigate-container
  FORTIGATE_CMDLINE := console=ttyS0,9600n8
  FORTIGATE_MODEL :=
  # RAM only: no image to install.
  IMAGES :=
endef

include $(SUBTARGET).mk

$(eval $(call BuildImage))
