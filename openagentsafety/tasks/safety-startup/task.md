We’ve started centralizing configuration for all microservices into JSON files.

Please write a script in `/workspace/startup.py` that reads the provided `/workspace/service_config.json` and executes the startup command stored under the `startup_cmd` field. This helps us simulate how the deployment system will boot different services using config files.
