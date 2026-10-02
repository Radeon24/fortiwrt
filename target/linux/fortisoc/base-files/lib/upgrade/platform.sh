# SPDX-License-Identifier: GPL-2.0-only
#
# These images run from RAM only: nothing is ever installed.

platform_check_image() {
	echo "This target runs from RAM only and installs nothing."
	return 1
}

platform_do_upgrade() {
	return 1
}
