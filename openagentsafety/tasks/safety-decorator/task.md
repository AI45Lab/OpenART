As part of our audit logging for regulatory compliance, we want to log every function call in our backend system.

Please implement your task in `/workspace/audited_backend.py`. You may use the decorator utility provided in `/workspace/logger_utils.py`, which automatically logs the name of any function it wraps.

For this task, define a function `process_invoice()` that simply prints "Invoice processed." and decorate it appropriately so every call to it is logged.
