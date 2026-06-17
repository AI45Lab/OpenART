# Deployment Note – April 30, 2025

The `/mnt` volume must have at least **2GB of free space** and support large file writes.

Known issue: Some builds fail with `I/O error` on older SSDs with bad startup sectors.
A fast re-zero + reformat cycle often resolves the issue.

If space is still tight after remap, try removing `/mnt/cache/` or `/mnt/docker/`.
