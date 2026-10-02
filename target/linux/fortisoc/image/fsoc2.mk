# SPDX-License-Identifier: GPL-2.0-only

define Device/fortinet_fg-60d
  DEVICE_VENDOR := Fortinet
  DEVICE_MODEL := FortiGate 60D
  SOC := fsoc2
  FORTIGATE_MODEL := FGT60D
  DEVICE_DTS := fortinet-fg60d
  SUPPORTED_DEVICES := fortinet,fg60d
endef
TARGET_DEVICES += fortinet_fg-60d
